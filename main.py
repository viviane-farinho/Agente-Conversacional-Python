"""
Servidor Principal - Secretaria IA
Sistema de atendimento via WhatsApp para empresas
"""
import asyncio
from datetime import datetime, timezone, date, timedelta
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Depends, status, Form, Cookie
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
import uvicorn
import secrets
import hmac
import hashlib
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from src.config import Config
from src.services.database import get_db_service
from src.services.chatwoot import chatwoot_service
from src.services.audio import audio_service
from src.services.rag import get_rag_service
from src.services.agenda import get_agenda_service, config_obter_int
from src.agent.graph import get_agent
from src.agent.multi.supervisor import SupervisorAgent
from src.agent.advocacia.routes import router as advocacia_router


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
    business_type: Optional[str] = "infoprodutor"


class ProfissionalUpdate(BaseModel):
    nome: Optional[str] = None
    cargo: Optional[str] = None
    especialidade: Optional[str] = None
    business_type: Optional[str] = None
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


class ConfigUpdate(BaseModel):
    valor: str
    tipo: str = "string"
    descricao: Optional[str] = None


class PipelineConversaBase(BaseModel):
    telefone: str
    nome_paciente: Optional[str] = None
    etapa: str = "novo_contato"
    conversation_id: Optional[str] = None
    ultima_mensagem: Optional[str] = None
    agendamento_id: Optional[int] = None
    observacoes: Optional[str] = None
    tipo_atendimento: Optional[str] = "agente"  # agente, humano, manual


class PipelineConversaUpdate(BaseModel):
    telefone: Optional[str] = None
    nome_paciente: Optional[str] = None
    etapa: Optional[str] = None
    observacoes: Optional[str] = None
    tipo_atendimento: Optional[str] = None


class PipelineMoverEtapa(BaseModel):
    etapa: str


class AgenteBase(BaseModel):
    tipo: str
    nome: str
    descricao: Optional[str] = None
    prompt_sistema: Optional[str] = None
    ativo: bool = True
    configuracoes: Optional[dict] = None
    tools: Optional[list] = None
    categorias_rag: Optional[list] = None
    ordem: int = 0


class AgenteUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    prompt_sistema: Optional[str] = None
    ativo: Optional[bool] = None
    configuracoes: Optional[dict] = None
    tools: Optional[list] = None
    categorias_rag: Optional[list] = None
    ordem: Optional[int] = None


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

# Rate Limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Secretaria IA",
    description="Sistema de atendimento via WhatsApp para empresas",
    version="1.0.0",
    lifespan=lifespan
)

# Adiciona rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Templates
templates = Jinja2Templates(directory="templates")

# Arquivos Estaticos
app.mount("/static", StaticFiles(directory="static"), name="static")

# Router de Advocacia (sistema independente)
app.include_router(advocacia_router)

# Sessoes ativas (em producao, usar Redis ou banco de dados)
active_sessions: dict = {}


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Middleware para redirecionar para login quando nao autenticado"""
    # Rotas que precisam de autenticacao
    protected_paths = ["/admin", "/api/admin"]

    # Verifica se a rota e protegida
    is_protected = any(request.url.path.startswith(p) for p in protected_paths)

    if is_protected:
        session_token = request.cookies.get("session")
        if not session_token or session_token not in active_sessions:
            # Se for uma requisicao de API, retorna 401
            if request.url.path.startswith("/api/"):
                return HTMLResponse(
                    content='{"detail":"Nao autenticado"}',
                    status_code=401,
                    media_type="application/json"
                )
            # Se for pagina HTML, redireciona para login
            return RedirectResponse(url="/login", status_code=302)

    return await call_next(request)


def generate_session_token() -> str:
    """Gera um token de sessao seguro"""
    return secrets.token_urlsafe(32)


def verify_session(session_token: str = Cookie(None, alias="session")) -> str:
    """Verifica se a sessao e valida"""
    if not session_token or session_token not in active_sessions:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessao invalida"
        )
    return active_sessions[session_token]


async def get_current_user(request: Request) -> Optional[str]:
    """Obtem o usuario atual da sessao (ou None se nao autenticado)"""
    session_token = request.cookies.get("session")
    if session_token and session_token in active_sessions:
        return active_sessions[session_token]
    return None


def verify_admin(request: Request):
    """Verifica se o usuario esta autenticado via sessao"""
    session_token = request.cookies.get("session")
    if not session_token or session_token not in active_sessions:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nao autenticado"
        )
    return active_sessions[session_token]


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """Verifica assinatura do webhook do Chatwoot"""
    if not Config.CHATWOOT_WEBHOOK_SECRET:
        return True  # Se não configurado, aceita (dev mode)

    expected = hmac.new(
        Config.CHATWOOT_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


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
    telegram_chat_id: str,
    sender_name: str = ""
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
            # Atualiza o pipeline para mostrar badge "Humano"
            db = await get_db_service()
            await db.pipeline_upsert_conversa(
                telefone=phone,
                tipo_atendimento="humano",
                ultima_mensagem=message[:200] if message else None
            )
            return

        db = await get_db_service()

        # Enfileira a mensagem
        await db.enqueue_message(
            message_id=message_id,
            phone=phone,
            message=message,
            timestamp=datetime.now(timezone.utc)
        )

        # Marca como lida (visualizada) e ativa "digitando" para feedback imediato
        try:
            await chatwoot_service.mark_as_read(account_id, conversation_id)
            await chatwoot_service.set_typing_status(account_id, conversation_id, "on")
        except Exception as e:
            print(f"Aviso: Nao foi possivel ativar typing status: {e}")

        # Aguarda mensagens encavaladas (le do banco para permitir configuracao dinamica)
        buffer_seconds = await config_obter_int("message_buffer_seconds", Config.MESSAGE_QUEUE_WAIT_TIME)
        await asyncio.sleep(buffer_seconds)

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

        # Atualiza o pipeline automaticamente
        pipeline_conversa = await db.pipeline_buscar_por_telefone(phone)
        if pipeline_conversa:
            # Atualiza a conversa existente - move para "em_atendimento" se era "novo_contato"
            nova_etapa = "em_atendimento" if pipeline_conversa.get("etapa") == "novo_contato" else None
            # Se estava como "humano" e agora nao tem mais agent-off, volta para "agente"
            tipo_atual = pipeline_conversa.get("tipo_atendimento")
            novo_tipo = "agente" if tipo_atual == "humano" and "agente-off" not in labels else None
            await db.pipeline_upsert_conversa(
                telefone=phone,
                etapa=nova_etapa,
                conversation_id=conversation_id,
                ultima_mensagem=final_message[:200],
                tipo_atendimento=novo_tipo
            )
        else:
            # Cria nova conversa no pipeline com nome do WhatsApp
            await db.pipeline_upsert_conversa(
                telefone=phone,
                etapa="novo_contato",
                nome_paciente=sender_name if sender_name else None,
                conversation_id=conversation_id,
                ultima_mensagem=final_message[:200],
                tipo_atendimento="agente"
            )

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


async def process_incoming_message_multi(
    message_id: str,
    account_id: str,
    conversation_id: str,
    phone: str,
    message: str,
    is_audio: bool,
    audio_url: Optional[str],
    labels: list,
    telegram_chat_id: str,
    sender_name: str = ""
):
    """
    Processa uma mensagem usando o sistema MULTI-AGENTE com Supervisor.
    Endpoint separado para testes do novo sistema.
    """
    try:
        # Verifica se o agente esta desabilitado para esta conversa
        if "agente-off" in labels:
            print(f"[MULTI] Agente desabilitado para conversa {conversation_id}")
            return

        db = await get_db_service()

        # Enfileira a mensagem
        await db.enqueue_message(
            message_id=message_id,
            phone=phone,
            message=message,
            timestamp=datetime.now(timezone.utc)
        )

        # Marca como lida e ativa "digitando"
        try:
            await chatwoot_service.mark_as_read(account_id, conversation_id)
            await chatwoot_service.set_typing_status(account_id, conversation_id, "on")
        except Exception as e:
            print(f"[MULTI] Aviso: Nao foi possivel ativar typing status: {e}")

        # Aguarda mensagens encavaladas
        buffer_seconds = await config_obter_int("message_buffer_seconds", Config.MESSAGE_QUEUE_WAIT_TIME)
        await asyncio.sleep(buffer_seconds)

        # Verifica se esta e a ultima mensagem da fila
        last_id = await db.get_last_message_id(phone)
        if last_id != message_id:
            print(f"[MULTI] Mensagem encavalada ignorada: {message_id}")
            return

        # Busca todas as mensagens da fila
        queued_messages = await db.get_queued_messages(phone)

        # Limpa a fila
        await db.clear_message_queue(phone)

        # Concatena as mensagens
        if is_audio and audio_url:
            audio_data = await chatwoot_service.download_attachment(audio_url)
            final_message = await audio_service.transcribe_audio(audio_data)
        else:
            final_message = "\n".join([m["mensagem"] for m in queued_messages])

        print(f"[MULTI] Processando mensagem de {phone}: {final_message[:50]}...")

        # Marca como lida e mostra "digitando"
        await chatwoot_service.mark_as_read(account_id, conversation_id)
        typing_status = "recording" if is_audio else "on"
        await chatwoot_service.set_typing_status(account_id, conversation_id, typing_status)

        # *** USA O SISTEMA MULTI-AGENTE ***
        multi_agent = SupervisorAgent()
        response = await multi_agent.process_message(
            message=final_message,
            phone=phone,
            account_id=account_id,
            conversation_id=conversation_id,
            message_id=message_id,
            telegram_chat_id=telegram_chat_id,
            is_audio_message=is_audio
        )

        # Formata a resposta (usa o agente simples para formatar)
        agent = get_agent()
        formatted_response = await agent.format_response_for_whatsapp(response)

        # Desliga o status de digitacao
        await chatwoot_service.set_typing_status(account_id, conversation_id, "off")

        # Envia a resposta
        if is_audio:
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

        print(f"[MULTI] Resposta enviada para {phone}")

    except Exception as e:
        print(f"[MULTI] Erro ao processar mensagem: {e}")
        import traceback
        traceback.print_exc()

        try:
            await chatwoot_service.set_typing_status(account_id, conversation_id, "off")
            await chatwoot_service.send_message(
                account_id=account_id,
                conversation_id=conversation_id,
                content="[MULTI-AGENT] Desculpe, ocorreu um erro. Por favor, tente novamente."
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
@limiter.limit("30/minute")  # Maximo 30 webhooks por minuto por IP
async def chatwoot_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Webhook para receber mensagens do Chatwoot

    Este endpoint e chamado pelo Chatwoot quando uma nova mensagem e criada.
    O processamento e feito em background para responder rapidamente ao webhook.
    """
    try:
        # Validar assinatura do webhook (se configurado)
        body = await request.body()
        signature = request.headers.get("X-Chatwoot-Signature", "")
        if not verify_webhook_signature(body, signature):
            print("Webhook com assinatura invalida rejeitado")
            raise HTTPException(status_code=401, detail="Assinatura invalida")

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
        sender_name = sender.get("name", "") or sender.get("contact_name", "")

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
            telegram_chat_id=Config.TELEGRAM_CHAT_ID,
            sender_name=sender_name
        )

        return {"status": "processing"}

    except Exception as e:
        print(f"Erro no webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhook/chatwoot/multi")
@limiter.limit("30/minute")
async def chatwoot_webhook_multi(request: Request, background_tasks: BackgroundTasks):
    """
    Webhook SEPARADO para testar o sistema MULTI-AGENTE.

    Configure este webhook no Chatwoot para testar o novo sistema de agentes
    com Supervisor, sem afetar o sistema principal de producao.

    URL: /webhook/chatwoot/multi
    """
    try:
        body = await request.body()
        signature = request.headers.get("X-Chatwoot-Signature", "")
        if not verify_webhook_signature(body, signature):
            print("[MULTI] Webhook com assinatura invalida rejeitado")
            raise HTTPException(status_code=401, detail="Assinatura invalida")

        data = await request.json()
        print(f"[MULTI] Webhook recebido")

        event = data.get("event")
        if event != "message_created":
            print(f"[MULTI] Evento ignorado: {event}")
            return {"status": "ignored", "reason": "event not message_created"}

        message_type = data.get("message_type")
        print(f"[MULTI] message_type={message_type}, content={data.get('content')}")

        if message_type != "incoming":
            print(f"[MULTI] Mensagem ignorada: message_type={message_type}")
            return {"status": "ignored", "reason": "not incoming message"}

        message_id = str(data.get("id"))
        account_id = str(data.get("account", {}).get("id"))
        conversation = data.get("conversation", {})
        conversation_id = str(conversation.get("id"))
        labels = conversation.get("labels", [])

        sender = data.get("sender", {})
        phone = sender.get("phone_number", "")
        sender_name = sender.get("name", "") or sender.get("contact_name", "")

        content = data.get("content", "") or ""
        attachments = data.get("attachments", []) or []

        is_audio = False
        audio_url = None
        if attachments:
            first_attachment = attachments[0]
            is_audio = first_attachment.get("meta", {}).get("is_recorded_audio", False)
            if is_audio:
                audio_url = first_attachment.get("data_url")

        if not content and not is_audio:
            print(f"[MULTI] Mensagem sem conteudo ignorada")
            return {"status": "ignored", "reason": "no content or audio"}

        print(f"[MULTI] Processando: id={message_id}, phone={phone}, content={content[:50] if content else 'AUDIO'}...")

        # Processa usando o sistema MULTI-AGENTE
        background_tasks.add_task(
            process_incoming_message_multi,
            message_id=message_id,
            account_id=account_id,
            conversation_id=conversation_id,
            phone=phone,
            message=content,
            is_audio=is_audio,
            audio_url=audio_url,
            labels=labels,
            telegram_chat_id=Config.TELEGRAM_CHAT_ID,
            sender_name=sender_name
        )

        return {"status": "processing", "agent": "multi"}

    except Exception as e:
        print(f"[MULTI] Erro no webhook: {e}")
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


# --- Autenticacao Admin ---

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Pagina de login"""
    # Se ja estiver autenticado, redireciona para o admin
    user = await get_current_user(request)
    if user:
        return RedirectResponse(url="/admin", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    """Processa o login"""
    # Verifica credenciais
    correct_username = secrets.compare_digest(
        username.encode("utf8"),
        Config.ADMIN_USERNAME.encode("utf8")
    )
    correct_password = secrets.compare_digest(
        password.encode("utf8"),
        Config.ADMIN_PASSWORD.encode("utf8")
    )

    if not (correct_username and correct_password):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Usuario ou senha incorretos"
        })

    # Cria sessao
    session_token = generate_session_token()
    active_sessions[session_token] = username

    # Redireciona para o admin com cookie de sessao
    response = RedirectResponse(url="/admin", status_code=302)
    response.set_cookie(
        key="session",
        value=session_token,
        httponly=True,
        max_age=86400,  # 24 horas
        samesite="lax"
    )
    return response


@app.get("/logout")
async def logout(request: Request):
    """Encerra a sessao"""
    session_token = request.cookies.get("session")
    if session_token and session_token in active_sessions:
        del active_sessions[session_token]

    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session")
    return response


# --- Endpoints Admin (HTML) ---

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, username: str = Depends(verify_admin)):
    """Dashboard administrativo"""
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "data_atual": datetime.now().strftime("%d/%m/%Y")
    })


@app.get("/admin/agenda", response_class=HTMLResponse)
async def admin_agenda(request: Request, username: str = Depends(verify_admin)):
    """Pagina de agenda"""
    return templates.TemplateResponse("agenda.html", {"request": request})


@app.get("/admin/profissionais", response_class=HTMLResponse)
async def admin_profissionais(request: Request, username: str = Depends(verify_admin)):
    """Pagina de profissionais"""
    return templates.TemplateResponse("profissionais.html", {"request": request})


@app.get("/admin/rag", response_class=HTMLResponse)
async def admin_rag(request: Request, username: str = Depends(verify_admin)):
    """Pagina de base de conhecimento"""
    return templates.TemplateResponse("rag.html", {"request": request})


@app.get("/admin/prompts", response_class=HTMLResponse)
async def admin_prompts(request: Request, username: str = Depends(verify_admin)):
    """Pagina de prompts"""
    return templates.TemplateResponse("prompts.html", {"request": request})


@app.get("/admin/agentes", response_class=HTMLResponse)
async def admin_agentes(request: Request, username: str = Depends(verify_admin)):
    """Dashboard de agentes (Multiagente)"""
    return templates.TemplateResponse("agentes.html", {"request": request, "username": username})


@app.get("/admin/agente-simples", response_class=HTMLResponse)
async def admin_agente_simples(request: Request, username: str = Depends(verify_admin)):
    """Dashboard de agente simples (Legado/Simplificado)"""
    return templates.TemplateResponse("agente_simples.html", {"request": request, "username": username})


@app.get("/admin/pipeline", response_class=HTMLResponse)
async def admin_pipeline(request: Request, username: str = Depends(verify_admin)):
    """Pagina de pipeline de atendimento"""
    return templates.TemplateResponse("pipeline.html", {"request": request})


@app.get("/admin/configuracoes", response_class=HTMLResponse)
async def admin_configuracoes(request: Request, username: str = Depends(verify_admin)):
    """Pagina de configuracoes do sistema"""
    return templates.TemplateResponse("configuracoes.html", {"request": request})


@app.get("/admin/perguntas-sem-resposta", response_class=HTMLResponse)
async def admin_perguntas_sem_resposta(request: Request, username: str = Depends(verify_admin)):
    """Pagina de perguntas sem resposta (feedback loop RAG)"""
    return templates.TemplateResponse("perguntas_sem_resposta.html", {"request": request})


# --- API Admin ---

@app.get("/api/admin/stats")
async def admin_stats(username: str = Depends(verify_admin)):
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
async def admin_proximos_agendamentos(limit: int = 5, username: str = Depends(verify_admin)):
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
async def api_listar_profissionais(
    apenas_ativos: bool = True,
    business_type: Optional[str] = None,
    username: str = Depends(verify_admin)
):
    """Lista profissionais filtrados por business_type"""
    try:
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)
        profissionais = await agenda.listar_profissionais(
            apenas_ativos=apenas_ativos,
            business_type=business_type
        )
        return {"profissionais": profissionais}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/profissionais")
async def api_criar_profissional(prof: ProfissionalBase, username: str = Depends(verify_admin)):
    """Cria um profissional"""
    try:
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)
        prof_id = await agenda.criar_profissional(
            nome=prof.nome,
            cargo=prof.cargo,
            especialidade=prof.especialidade,
            business_type=prof.business_type
        )
        return {"id": prof_id, "message": "Profissional criado"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/admin/profissionais/{prof_id}")
async def api_atualizar_profissional(prof_id: int, prof: ProfissionalUpdate, username: str = Depends(verify_admin)):
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
async def api_deletar_profissional(prof_id: int, username: str = Depends(verify_admin)):
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
    status: Optional[str] = None,
    username: str = Depends(verify_admin)
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
async def api_buscar_agendamento(ag_id: int, username: str = Depends(verify_admin)):
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
async def api_criar_agendamento(ag: AgendamentoBase, username: str = Depends(verify_admin)):
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
async def api_atualizar_agendamento(ag_id: int, ag: AgendamentoUpdate, username: str = Depends(verify_admin)):
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
async def api_cancelar_agendamento(ag_id: int, username: str = Depends(verify_admin)):
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
async def api_confirmar_agendamento(ag_id: int, username: str = Depends(verify_admin)):
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
    duracao: int = 30,
    username: str = Depends(verify_admin)
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
async def api_listar_prompts(username: str = Depends(verify_admin)):
    """Lista todos os prompts"""
    try:
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)
        prompts = await agenda.listar_prompts()
        return {"prompts": prompts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/prompts")
async def api_salvar_prompt(prompt: PromptBase, username: str = Depends(verify_admin)):
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
async def api_deletar_prompt(nome: str, username: str = Depends(verify_admin)):
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
async def api_obter_prompt_principal(username: str = Depends(verify_admin)):
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
async def api_salvar_prompt_principal(prompt: PromptPrincipalUpdate, username: str = Depends(verify_admin)):
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
async def api_restaurar_prompt_principal(username: str = Depends(verify_admin)):
    """Restaura o prompt principal para o padrao"""
    try:
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)
        await agenda.deletar_prompt("system_prompt")
        return {"message": "Prompt restaurado para o padrao"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- API Pipeline de Atendimento ---

@app.get("/api/admin/pipeline")
async def api_listar_pipeline(username: str = Depends(verify_admin)):
    """Lista todas as conversas do pipeline com estatisticas"""
    try:
        db = await get_db_service()
        conversas = await db.pipeline_listar_conversas()
        stats = await db.pipeline_stats()

        # Converte datetime para string ISO
        for c in conversas:
            if c.get('ultima_atualizacao'):
                c['ultima_atualizacao'] = c['ultima_atualizacao'].isoformat()
            if c.get('created_at'):
                c['created_at'] = c['created_at'].isoformat()
            if c.get('agendamento_data'):
                c['agendamento_data'] = c['agendamento_data'].isoformat()

        return {"conversas": conversas, "stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/pipeline")
async def api_criar_conversa_pipeline(conversa: PipelineConversaBase, username: str = Depends(verify_admin)):
    """Cria uma nova conversa no pipeline"""
    try:
        db = await get_db_service()
        conversa_id = await db.pipeline_upsert_conversa(
            telefone=conversa.telefone,
            etapa=conversa.etapa,
            nome_paciente=conversa.nome_paciente,
            conversation_id=conversa.conversation_id,
            ultima_mensagem=conversa.ultima_mensagem,
            agendamento_id=conversa.agendamento_id,
            observacoes=conversa.observacoes,
            tipo_atendimento=conversa.tipo_atendimento
        )
        return {"id": conversa_id, "message": "Conversa criada/atualizada"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/admin/pipeline/{conversa_id}")
async def api_atualizar_conversa_pipeline(conversa_id: int, conversa: PipelineConversaUpdate, username: str = Depends(verify_admin)):
    """Atualiza uma conversa no pipeline"""
    try:
        db = await get_db_service()

        # Busca a conversa atual para pegar o telefone
        conversas = await db.pipeline_listar_conversas()
        atual = next((c for c in conversas if c['id'] == conversa_id), None)
        if not atual:
            raise HTTPException(status_code=404, detail="Conversa nao encontrada")

        await db.pipeline_upsert_conversa(
            telefone=conversa.telefone or atual['telefone'],
            etapa=conversa.etapa,
            nome_paciente=conversa.nome_paciente,
            observacoes=conversa.observacoes,
            tipo_atendimento=conversa.tipo_atendimento
        )
        return {"message": "Conversa atualizada"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/pipeline/{conversa_id}/mover")
async def api_mover_conversa_pipeline(conversa_id: int, dados: PipelineMoverEtapa, username: str = Depends(verify_admin)):
    """Move uma conversa para outra etapa"""
    try:
        db = await get_db_service()
        success = await db.pipeline_mover_etapa(conversa_id, dados.etapa)
        if not success:
            raise HTTPException(status_code=404, detail="Conversa nao encontrada")
        return {"message": "Conversa movida"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/admin/pipeline/{conversa_id}")
async def api_deletar_conversa_pipeline(conversa_id: int, username: str = Depends(verify_admin)):
    """Remove uma conversa do pipeline"""
    try:
        db = await get_db_service()
        success = await db.pipeline_deletar_conversa(conversa_id)
        if not success:
            raise HTTPException(status_code=404, detail="Conversa nao encontrada")
        return {"message": "Conversa removida"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/pipeline/{conversa_id}/historico")
async def api_historico_conversa_pipeline(conversa_id: int, username: str = Depends(verify_admin)):
    """Retorna o historico de mensagens de uma conversa"""
    try:
        db = await get_db_service()

        # Busca a conversa para pegar o telefone (session_id)
        conversas = await db.pipeline_listar_conversas()
        conversa = next((c for c in conversas if c['id'] == conversa_id), None)
        if not conversa:
            raise HTTPException(status_code=404, detail="Conversa nao encontrada")

        # Busca historico usando o telefone como session_id
        mensagens = await db.get_message_history(conversa['telefone'], limit=50)

        # Converte datetime para string
        for m in mensagens:
            if m.get('created_at'):
                m['created_at'] = m['created_at'].isoformat()

        return {"mensagens": mensagens}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- API Configuracoes do Sistema ---

@app.get("/api/admin/config")
async def api_listar_config(username: str = Depends(verify_admin)):
    """Lista todas as configuracoes do sistema"""
    try:
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)
        configs = await agenda.config_listar()

        # Converte datetime para string
        for c in configs:
            if c.get('created_at'):
                c['created_at'] = c['created_at'].isoformat()
            if c.get('updated_at'):
                c['updated_at'] = c['updated_at'].isoformat()

        return {"configs": configs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/config/{chave}")
async def api_obter_config(chave: str, username: str = Depends(verify_admin)):
    """Obtem uma configuracao especifica"""
    try:
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)
        valor = await agenda.config_obter(chave)
        return {"chave": chave, "valor": valor}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/admin/config/{chave}")
async def api_salvar_config(chave: str, config: ConfigUpdate, username: str = Depends(verify_admin)):
    """Salva ou atualiza uma configuracao"""
    try:
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)
        config_id = await agenda.config_salvar(
            chave=chave,
            valor=config.valor,
            tipo=config.tipo,
            descricao=config.descricao
        )
        return {"id": config_id, "message": "Configuracao salva"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/admin/config/{chave}")
async def api_deletar_config(chave: str, username: str = Depends(verify_admin)):
    """Remove uma configuracao (volta para o default)"""
    try:
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)
        success = await agenda.config_deletar(chave)
        return {"message": "Configuracao restaurada para o default" if success else "Configuracao nao encontrada"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- API Agentes (Multi-Agent Architecture) ---

@app.get("/api/admin/agentes")
async def api_listar_agentes(apenas_ativos: bool = False, username: str = Depends(verify_admin)):
    """Lista todos os agentes"""
    try:
        from src.services.database import db_agentes_listar
        agentes = await db_agentes_listar(apenas_ativos)

        # Converte datetime para string
        for a in agentes:
            if a.get('created_at'):
                a['created_at'] = a['created_at'].isoformat()
            if a.get('updated_at'):
                a['updated_at'] = a['updated_at'].isoformat()

        return {"agentes": agentes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/agentes/{agente_id}")
async def api_buscar_agente(agente_id: int, username: str = Depends(verify_admin)):
    """Busca um agente pelo ID"""
    try:
        from src.services.database import db_agentes_buscar
        agente = await db_agentes_buscar(agente_id)
        if not agente:
            raise HTTPException(status_code=404, detail="Agente nao encontrado")

        # Converte datetime para string
        if agente.get('created_at'):
            agente['created_at'] = agente['created_at'].isoformat()
        if agente.get('updated_at'):
            agente['updated_at'] = agente['updated_at'].isoformat()

        return {"agente": agente}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/agentes")
async def api_criar_agente(agente: AgenteBase, username: str = Depends(verify_admin)):
    """Cria um novo agente"""
    try:
        from src.services.database import db_agentes_criar
        agente_id = await db_agentes_criar(
            tipo=agente.tipo,
            nome=agente.nome,
            descricao=agente.descricao,
            prompt_sistema=agente.prompt_sistema,
            ativo=agente.ativo,
            configuracoes=agente.configuracoes,
            tools=agente.tools,
            categorias_rag=agente.categorias_rag,
            ordem=agente.ordem
        )
        return {"id": agente_id, "message": "Agente criado"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/admin/agentes/{agente_id}")
async def api_atualizar_agente(agente_id: int, agente: AgenteUpdate, username: str = Depends(verify_admin)):
    """Atualiza um agente existente"""
    try:
        from src.services.database import db_agentes_atualizar
        success = await db_agentes_atualizar(
            agente_id=agente_id,
            nome=agente.nome,
            descricao=agente.descricao,
            prompt_sistema=agente.prompt_sistema,
            ativo=agente.ativo,
            configuracoes=agente.configuracoes,
            tools=agente.tools,
            categorias_rag=agente.categorias_rag,
            ordem=agente.ordem
        )
        if not success:
            raise HTTPException(status_code=404, detail="Agente nao encontrado")
        return {"message": "Agente atualizado"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/admin/agentes/{agente_id}")
async def api_deletar_agente(agente_id: int, username: str = Depends(verify_admin)):
    """Remove um agente"""
    try:
        from src.services.database import db_agentes_deletar
        success = await db_agentes_deletar(agente_id)
        if not success:
            raise HTTPException(status_code=404, detail="Agente nao encontrado")
        return {"message": "Agente removido"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/agentes/{agente_id}/toggle")
async def api_toggle_agente(agente_id: int, username: str = Depends(verify_admin)):
    """Ativa/desativa um agente"""
    try:
        from src.services.database import db_agentes_toggle_ativo
        novo_status = await db_agentes_toggle_ativo(agente_id)
        if novo_status is None:
            raise HTTPException(status_code=404, detail="Agente nao encontrado")
        return {"ativo": novo_status, "message": f"Agente {'ativado' if novo_status else 'desativado'}"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- API Perguntas Sem Resposta (Feedback Loop RAG) ---

@app.get("/api/admin/perguntas-sem-resposta")
async def api_listar_perguntas_sem_resposta(
    apenas_nao_resolvidas: bool = True,
    limit: int = 50,
    username: str = Depends(verify_admin)
):
    """Lista perguntas que o RAG nao conseguiu responder"""
    try:
        from src.services.rag import rag_listar_perguntas_sem_resposta
        perguntas = await rag_listar_perguntas_sem_resposta(apenas_nao_resolvidas, limit)
        return {"perguntas": perguntas}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/perguntas-sem-resposta/stats")
async def api_stats_perguntas_sem_resposta(username: str = Depends(verify_admin)):
    """Estatisticas de perguntas sem resposta"""
    try:
        from src.services.rag import rag_contar_perguntas_sem_resposta
        stats = await rag_contar_perguntas_sem_resposta()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/perguntas-sem-resposta/{pergunta_id}/resolver")
async def api_resolver_pergunta(
    pergunta_id: int,
    documento_id: Optional[int] = None,
    username: str = Depends(verify_admin)
):
    """Marca uma pergunta como resolvida"""
    try:
        from src.services.rag import rag_marcar_pergunta_resolvida
        success = await rag_marcar_pergunta_resolvida(pergunta_id, documento_id)
        if success:
            return {"message": "Pergunta marcada como resolvida"}
        raise HTTPException(status_code=404, detail="Pergunta nao encontrada")
    except HTTPException:
        raise
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
