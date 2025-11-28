"""
Servidor Principal - Secretaria IA
Sistema de atendimento via WhatsApp para clinicas medicas
"""
import asyncio
from datetime import datetime, timezone, date, timedelta
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

from src.config import Config
from src.services.database import get_db_service
from src.services.chatwoot import chatwoot_service
from src.services.audio import audio_service
from src.services.rag import get_rag_service
from src.services.agenda import get_agenda_service
from src.agent.graph import get_agent


# --- Modelos Pydantic ---

class ChatwootWebhookBody(BaseModel):
    """Corpo do webhook do Chatwoot"""
    id: int
    content: Optional[str] = None
    message_type: str
    account: dict
    conversation: dict
    sender: dict
    attachments: Optional[list] = None
    created_at: int


class ChatwootWebhook(BaseModel):
    """Webhook do Chatwoot"""
    event: str
    body: ChatwootWebhookBody


class DocumentoBase(BaseModel):
    """Modelo para criar/atualizar documento na base de conhecimento"""
    titulo: str
    conteudo: str
    categoria: str = "geral"
    metadata: Optional[dict] = None


class DocumentoUpdate(BaseModel):
    """Modelo para atualizar documento (campos opcionais)"""
    titulo: Optional[str] = None
    conteudo: Optional[str] = None
    categoria: Optional[str] = None
    metadata: Optional[dict] = None


class BuscaDocumento(BaseModel):
    """Modelo para busca na base de conhecimento"""
    query: str
    categoria: Optional[str] = None
    limit: int = 5


class ProfissionalBase(BaseModel):
    nome: str
    cargo: Optional[str] = None
    especialidade: Optional[str] = None


class ProfissionalUpdate(BaseModel):
    nome: Optional[str] = None
    cargo: Optional[str] = None
    especialidade: Optional[str] = None
    ativo: Optional[bool] = None


class AgendamentoBase(BaseModel):
    profissional_id: int
    paciente_nome: str
    paciente_telefone: Optional[str] = None
    paciente_nascimento: Optional[str] = None
    data_hora: str
    duracao_minutos: int = 30
    observacoes: Optional[str] = None
    conversation_id: Optional[str] = None


class AgendamentoUpdate(BaseModel):
    data_hora: Optional[str] = None
    duracao_minutos: Optional[int] = None
    status: Optional[str] = None
    confirmado: Optional[bool] = None
    observacoes: Optional[str] = None


class PromptBase(BaseModel):
    nome: str
    conteudo: str
    descricao: Optional[str] = None


class PromptPrincipalUpdate(BaseModel):
    conteudo: str


# --- Contexto do App ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia o ciclo de vida da aplicacao"""
    # Startup
    print("Iniciando Secretaria IA...")
    db = await get_db_service()
    print("Banco de dados conectado")

    # Inicializa RAG
    try:
        rag = await get_rag_service(db.pool)
        if rag.initialized:
            print("Base de conhecimento (RAG) inicializada")
        else:
            print("RAG nao inicializado - extensao 'vector' pode nao estar habilitada")
    except Exception as e:
        print(f"RAG nao disponivel: {e}")

    # Inicializa Agenda
    try:
        agenda = await get_agenda_service(db.pool)
        print("Servico de agenda inicializado")
    except Exception as e:
        print(f"Agenda nao disponivel: {e}")

    print(f"Servidor rodando em http://{Config.SERVER_HOST}:{Config.SERVER_PORT}")
    print(f"Admin disponivel em http://{Config.SERVER_HOST}:{Config.SERVER_PORT}/admin")

    yield

    # Shutdown
    print("Encerrando Secretaria IA...")
    if db.pool:
        await db.disconnect()


# --- Aplicacao FastAPI ---

app = FastAPI(
    title="Secretaria IA",
    description="Sistema de atendimento via WhatsApp para clinicas medicas",
    version="1.0.0",
    lifespan=lifespan
)

# Templates
templates = Jinja2Templates(directory="templates")


# --- Processamento de Mensagens ---

async def process_incoming_message(
    message_id: str,
    account_id: str,
    conversation_id: str,
    phone: str,
    message: str,
    is_audio: bool,
    audio_url: Optional[str],
    labels: list,
    telegram_chat_id: str
):
    """
    Processa uma mensagem recebida

    Esta funcao implementa a logica de:
    1. Verificar se o agente esta habilitado (etiqueta agente-off)
    2. Enfileirar mensagens para evitar processamento duplicado
    3. Aguardar mensagens encavaladas
    4. Transcrever audio se necessario
    5. Processar com o agente IA
    6. Enviar resposta (texto ou audio)
    """
    try:
        # Verifica se o agente esta desabilitado para esta conversa
        if "agente-off" in labels:
            print(f"Agente desabilitado para conversa {conversation_id}")
            return

        db = await get_db_service()

        # Enfileira a mensagem
        await db.enqueue_message(
            message_id=message_id,
            phone=phone,
            message=message,
            timestamp=datetime.now(timezone.utc)
        )

        # Aguarda mensagens encavaladas
        await asyncio.sleep(Config.MESSAGE_QUEUE_WAIT_TIME)

        # Verifica se esta e a ultima mensagem da fila
        last_id = await db.get_last_message_id(phone)
        if last_id != message_id:
            print(f"Mensagem encavalada ignorada: {message_id}")
            return

        # Busca todas as mensagens da fila
        queued_messages = await db.get_queued_messages(phone)

        # Limpa a fila
        await db.clear_message_queue(phone)

        # Concatena as mensagens
        if is_audio and audio_url:
            # Baixa e transcreve o audio
            audio_data = await chatwoot_service.download_attachment(audio_url)
            final_message = await audio_service.transcribe_audio(audio_data)
        else:
            final_message = "\n".join([m["mensagem"] for m in queued_messages])

        print(f"Processando mensagem de {phone}: {final_message[:50]}...")

        # Marca como lida e mostra "digitando"
        await chatwoot_service.mark_as_read(account_id, conversation_id)

        typing_status = "recording" if is_audio else "on"
        await chatwoot_service.set_typing_status(account_id, conversation_id, typing_status)

        # Processa com o agente
        agent = get_agent()
        response = await agent.process_message(
            message=final_message,
            phone=phone,
            account_id=account_id,
            conversation_id=conversation_id,
            message_id=message_id,
            telegram_chat_id=telegram_chat_id,
            is_audio_message=is_audio
        )

        # Formata a resposta
        formatted_response = await agent.format_response_for_whatsapp(response)

        # Desliga o status de digitacao
        await chatwoot_service.set_typing_status(account_id, conversation_id, "off")

        # Envia a resposta
        if is_audio:
            # Gera audio da resposta
            tts_text = audio_service.format_text_for_tts(formatted_response)
            audio_response = await audio_service.text_to_speech(tts_text)

            await chatwoot_service.send_audio(
                account_id=account_id,
                conversation_id=conversation_id,
                audio_data=audio_response,
                filename="resposta.mp3"
            )
        else:
            await chatwoot_service.send_message(
                account_id=account_id,
                conversation_id=conversation_id,
                content=formatted_response
            )

        print(f"Resposta enviada para {phone}")

    except Exception as e:
        print(f"Erro ao processar mensagem: {e}")
        import traceback
        traceback.print_exc()

        # Tenta enviar mensagem de erro
        try:
            await chatwoot_service.set_typing_status(account_id, conversation_id, "off")
            await chatwoot_service.send_message(
                account_id=account_id,
                conversation_id=conversation_id,
                content="Desculpe, ocorreu um erro ao processar sua mensagem. Por favor, tente novamente."
            )
        except:
            pass


# --- Endpoints ---

@app.get("/")
async def root():
    """Endpoint de verificacao de saude"""
    return {
        "status": "ok",
        "service": "Secretaria IA",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    """Verificacao de saude do servico"""
    return {"status": "healthy"}


@app.post("/webhook/chatwoot")
async def chatwoot_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Webhook para receber mensagens do Chatwoot

    Este endpoint e chamado pelo Chatwoot quando uma nova mensagem e criada.
    O processamento e feito em background para responder rapidamente ao webhook.
    """
    try:
        data = await request.json()
        print(f"Webhook recebido")

        # Valida o evento
        event = data.get("event")
        if event != "message_created":
            print(f"Evento ignorado: {event}")
            return {"status": "ignored", "reason": "event not message_created"}

        # Os dados vem direto no JSON, nao em "body"
        message_type = data.get("message_type")
        print(f"message_type={message_type}, content={data.get('content')}")

        # Ignora mensagens enviadas pelo agente (outgoing)
        if message_type != "incoming":
            print(f"Mensagem ignorada: message_type={message_type}")
            return {"status": "ignored", "reason": "not incoming message"}

        message_id = str(data.get("id"))
        account_id = str(data.get("account", {}).get("id"))
        conversation = data.get("conversation", {})
        conversation_id = str(conversation.get("id"))
        labels = conversation.get("labels", [])

        sender = data.get("sender", {})
        phone = sender.get("phone_number", "")

        content = data.get("content", "") or ""
        attachments = data.get("attachments", []) or []

        # Verifica se e mensagem de audio
        is_audio = False
        audio_url = None
        if attachments:
            first_attachment = attachments[0]
            is_audio = first_attachment.get("meta", {}).get("is_recorded_audio", False)
            if is_audio:
                audio_url = first_attachment.get("data_url")

        # Ignora se nao tem conteudo nem audio
        if not content and not is_audio:
            print(f"Mensagem sem conteudo ignorada")
            return {"status": "ignored", "reason": "no content or audio"}

        print(f"Processando mensagem: id={message_id}, phone={phone}, content={content[:50] if content else 'AUDIO'}...")

        # Processa em background
        background_tasks.add_task(
            process_incoming_message,
            message_id=message_id,
            account_id=account_id,
            conversation_id=conversation_id,
            phone=phone,
            message=content,
            is_audio=is_audio,
            audio_url=audio_url,
            labels=labels,
            telegram_chat_id=Config.TELEGRAM_CHAT_ID
        )

        return {"status": "processing"}

    except Exception as e:
        print(f"Erro no webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Endpoints da Base de Conhecimento (RAG) ---

@app.get("/api/documentos")
async def listar_documentos(categoria: Optional[str] = None, limit: int = 50):
    """Lista todos os documentos da base de conhecimento"""
    try:
        db = await get_db_service()
        rag = await get_rag_service(db.pool)
        documentos = await rag.list_documents(categoria=categoria, limit=limit)
        return {"documentos": documentos, "total": len(documentos)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/documentos/categorias")
async def listar_categorias():
    """Lista todas as categorias de documentos"""
    try:
        db = await get_db_service()
        rag = await get_rag_service(db.pool)
        categorias = await rag.get_categories()
        return {"categorias": categorias}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/documentos")
async def criar_documento(documento: DocumentoBase):
    """Adiciona um novo documento a base de conhecimento"""
    try:
        db = await get_db_service()
        rag = await get_rag_service(db.pool)
        doc_id = await rag.add_document(
            titulo=documento.titulo,
            conteudo=documento.conteudo,
            categoria=documento.categoria,
            metadata=documento.metadata
        )
        return {"id": doc_id, "message": "Documento criado com sucesso"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/documentos/{doc_id}")
async def atualizar_documento(doc_id: int, documento: DocumentoUpdate):
    """Atualiza um documento existente"""
    try:
        db = await get_db_service()
        rag = await get_rag_service(db.pool)
        success = await rag.update_document(
            doc_id=doc_id,
            titulo=documento.titulo,
            conteudo=documento.conteudo,
            categoria=documento.categoria,
            metadata=documento.metadata
        )
        if not success:
            raise HTTPException(status_code=404, detail="Documento nao encontrado")
        return {"message": "Documento atualizado com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/documentos/{doc_id}")
async def deletar_documento(doc_id: int):
    """Remove um documento da base de conhecimento"""
    try:
        db = await get_db_service()
        rag = await get_rag_service(db.pool)
        success = await rag.delete_document(doc_id)
        if not success:
            raise HTTPException(status_code=404, detail="Documento nao encontrado")
        return {"message": "Documento removido com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/documentos/buscar")
async def buscar_documentos(busca: BuscaDocumento):
    """Busca documentos por similaridade semantica"""
    try:
        db = await get_db_service()
        rag = await get_rag_service(db.pool)
        resultados = await rag.search(
            query=busca.query,
            limit=busca.limit,
            categoria=busca.categoria
        )
        return {"resultados": resultados, "total": len(resultados)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Endpoints Admin (HTML) ---

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    """Dashboard administrativo"""
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "data_atual": datetime.now().strftime("%d/%m/%Y")
    })


@app.get("/admin/agenda", response_class=HTMLResponse)
async def admin_agenda(request: Request):
    """Pagina de agenda"""
    return templates.TemplateResponse("agenda.html", {"request": request})


@app.get("/admin/profissionais", response_class=HTMLResponse)
async def admin_profissionais(request: Request):
    """Pagina de profissionais"""
    return templates.TemplateResponse("profissionais.html", {"request": request})


@app.get("/admin/rag", response_class=HTMLResponse)
async def admin_rag(request: Request):
    """Pagina de base de conhecimento"""
    return templates.TemplateResponse("rag.html", {"request": request})


@app.get("/admin/prompts", response_class=HTMLResponse)
async def admin_prompts(request: Request):
    """Pagina de prompts"""
    return templates.TemplateResponse("prompts.html", {"request": request})


# --- API Admin ---

@app.get("/api/admin/stats")
async def admin_stats():
    """Estatisticas para o dashboard"""
    try:
        db = await get_db_service()
        rag = await get_rag_service(db.pool)
        agenda = await get_agenda_service(db.pool)

        # Conta agendamentos de hoje
        hoje = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        amanha = hoje + timedelta(days=1)

        agendamentos_hoje = await agenda.listar_agendamentos(
            data_inicio=hoje,
            data_fim=amanha
        )

        confirmados = len([a for a in agendamentos_hoje if a.get("confirmado")])
        profissionais = await agenda.listar_profissionais()
        documentos = await rag.list_documents(limit=1000)

        return {
            "agendamentos_hoje": len(agendamentos_hoje),
            "confirmados": confirmados,
            "total_documentos": len(documentos),
            "total_profissionais": len(profissionais),
            "rag_status": rag.initialized
        }
    except Exception as e:
        return {
            "agendamentos_hoje": 0,
            "confirmados": 0,
            "total_documentos": 0,
            "total_profissionais": 0,
            "rag_status": False,
            "error": str(e)
        }


@app.get("/api/admin/proximos-agendamentos")
async def admin_proximos_agendamentos(limit: int = 5):
    """Lista proximos agendamentos"""
    try:
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)

        agora = datetime.now()
        agendamentos = await agenda.listar_agendamentos(
            data_inicio=agora,
            data_fim=agora + timedelta(days=7)
        )

        # Filtra apenas nao cancelados e ordena
        agendamentos = [a for a in agendamentos if a.get("status") != "cancelado"]
        agendamentos = sorted(agendamentos, key=lambda x: x["data_hora"])[:limit]

        return {"agendamentos": agendamentos}
    except Exception as e:
        return {"agendamentos": [], "error": str(e)}


# --- API Profissionais ---

@app.get("/api/admin/profissionais")
async def api_listar_profissionais(apenas_ativos: bool = True):
    """Lista profissionais"""
    try:
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)
        profissionais = await agenda.listar_profissionais(apenas_ativos=apenas_ativos)
        return {"profissionais": profissionais}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/profissionais")
async def api_criar_profissional(prof: ProfissionalBase):
    """Cria um profissional"""
    try:
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)
        prof_id = await agenda.criar_profissional(
            nome=prof.nome,
            cargo=prof.cargo,
            especialidade=prof.especialidade
        )
        return {"id": prof_id, "message": "Profissional criado"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/admin/profissionais/{prof_id}")
async def api_atualizar_profissional(prof_id: int, prof: ProfissionalUpdate):
    """Atualiza um profissional"""
    try:
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)
        success = await agenda.atualizar_profissional(
            profissional_id=prof_id,
            nome=prof.nome,
            cargo=prof.cargo,
            especialidade=prof.especialidade,
            ativo=prof.ativo
        )
        if not success:
            raise HTTPException(status_code=404, detail="Profissional nao encontrado")
        return {"message": "Profissional atualizado"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/admin/profissionais/{prof_id}")
async def api_deletar_profissional(prof_id: int):
    """Desativa um profissional"""
    try:
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)
        success = await agenda.deletar_profissional(prof_id)
        if not success:
            raise HTTPException(status_code=404, detail="Profissional nao encontrado")
        return {"message": "Profissional desativado"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- API Agendamentos ---

@app.get("/api/admin/agendamentos")
async def api_listar_agendamentos(
    profissional_id: Optional[int] = None,
    data_inicio: Optional[str] = None,
    data_fim: Optional[str] = None,
    status: Optional[str] = None
):
    """Lista agendamentos"""
    try:
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)

        data_inicio_dt = datetime.fromisoformat(data_inicio.replace('Z', '+00:00')) if data_inicio else None
        data_fim_dt = datetime.fromisoformat(data_fim.replace('Z', '+00:00')) if data_fim else None

        agendamentos = await agenda.listar_agendamentos(
            profissional_id=profissional_id,
            data_inicio=data_inicio_dt,
            data_fim=data_fim_dt,
            status=status
        )
        return {"agendamentos": agendamentos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/agendamentos/{ag_id}")
async def api_buscar_agendamento(ag_id: int):
    """Busca um agendamento"""
    try:
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)
        agendamento = await agenda.buscar_agendamento(ag_id)
        if not agendamento:
            raise HTTPException(status_code=404, detail="Agendamento nao encontrado")
        return {"agendamento": agendamento}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/agendamentos")
async def api_criar_agendamento(ag: AgendamentoBase):
    """Cria um agendamento"""
    try:
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)

        data_hora = datetime.fromisoformat(ag.data_hora)
        nascimento = None
        if ag.paciente_nascimento:
            nascimento = date.fromisoformat(ag.paciente_nascimento)

        result = await agenda.criar_agendamento(
            profissional_id=ag.profissional_id,
            paciente_nome=ag.paciente_nome,
            data_hora=data_hora,
            paciente_telefone=ag.paciente_telefone,
            paciente_nascimento=nascimento,
            duracao_minutos=ag.duracao_minutos,
            observacoes=ag.observacoes,
            conversation_id=ag.conversation_id
        )

        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/admin/agendamentos/{ag_id}")
async def api_atualizar_agendamento(ag_id: int, ag: AgendamentoUpdate):
    """Atualiza um agendamento"""
    try:
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)

        data_hora = datetime.fromisoformat(ag.data_hora) if ag.data_hora else None

        result = await agenda.atualizar_agendamento(
            agendamento_id=ag_id,
            data_hora=data_hora,
            duracao_minutos=ag.duracao_minutos,
            status=ag.status,
            confirmado=ag.confirmado,
            observacoes=ag.observacoes
        )

        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/agendamentos/{ag_id}/cancelar")
async def api_cancelar_agendamento(ag_id: int):
    """Cancela um agendamento"""
    try:
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)
        success = await agenda.cancelar_agendamento(ag_id)
        if not success:
            raise HTTPException(status_code=404, detail="Agendamento nao encontrado")
        return {"message": "Agendamento cancelado"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/agendamentos/{ag_id}/confirmar")
async def api_confirmar_agendamento(ag_id: int):
    """Confirma um agendamento"""
    try:
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)
        success = await agenda.confirmar_agendamento(ag_id)
        if not success:
            raise HTTPException(status_code=404, detail="Agendamento nao encontrado")
        return {"message": "Agendamento confirmado"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/horarios-disponiveis")
async def api_horarios_disponiveis(
    profissional_id: int,
    data: str,
    duracao: int = 30
):
    """Lista horarios disponiveis para agendamento"""
    try:
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)

        data_obj = date.fromisoformat(data)
        horarios = await agenda.buscar_horarios_disponiveis(
            profissional_id=profissional_id,
            data=data_obj,
            duracao_minutos=duracao
        )
        return {"horarios": horarios}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- API Prompts ---

@app.get("/api/admin/prompts")
async def api_listar_prompts():
    """Lista todos os prompts"""
    try:
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)
        prompts = await agenda.listar_prompts()
        return {"prompts": prompts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/prompts")
async def api_salvar_prompt(prompt: PromptBase):
    """Salva ou atualiza um prompt"""
    try:
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)
        prompt_id = await agenda.salvar_prompt(
            nome=prompt.nome,
            conteudo=prompt.conteudo,
            descricao=prompt.descricao
        )
        return {"id": prompt_id, "message": "Prompt salvo"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/admin/prompts/{nome}")
async def api_deletar_prompt(nome: str):
    """Remove um prompt"""
    try:
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)
        success = await agenda.deletar_prompt(nome)
        if not success:
            raise HTTPException(status_code=404, detail="Prompt nao encontrado")
        return {"message": "Prompt removido"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/prompt-principal")
async def api_obter_prompt_principal():
    """Obtem o prompt principal do agente"""
    try:
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)

        # Tenta buscar do banco
        prompt = await agenda.obter_prompt("system_prompt")
        if prompt:
            return {"conteudo": prompt["conteudo"]}

        # Se nao existe, retorna o padrao do codigo
        from src.agent.prompts import get_system_prompt
        conteudo = get_system_prompt("TELEFONE_EXEMPLO", "CONVERSA_EXEMPLO")
        return {"conteudo": conteudo}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/prompt-principal")
async def api_salvar_prompt_principal(prompt: PromptPrincipalUpdate):
    """Salva o prompt principal"""
    try:
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)
        await agenda.salvar_prompt(
            nome="system_prompt",
            conteudo=prompt.conteudo,
            descricao="Prompt principal do sistema"
        )
        return {"message": "Prompt principal salvo"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/prompt-principal/restaurar")
async def api_restaurar_prompt_principal():
    """Restaura o prompt principal para o padrao"""
    try:
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)
        await agenda.deletar_prompt("system_prompt")
        return {"message": "Prompt restaurado para o padrao"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Execucao ---

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=Config.SERVER_HOST,
        port=Config.SERVER_PORT,
        reload=True
    )
