"""
Servidor Principal - Secretaria IA
Sistema de atendimento via WhatsApp para clinicas medicas
"""
import asyncio
from datetime import datetime, timezone, date, timedelta
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Depends, Form
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
import uvicorn
import secrets

from src.config import Config
from src.services.database import get_db_service
from src.services.chatwoot import chatwoot_service
from src.services.audio import audio_service
from src.services.rag import get_rag_service
from src.services.agenda import get_agenda_service
from src.services.tenant import get_tenant_service, TenantService
from src.agent.graph import get_agent
from src.agent.multi_agent import get_multi_agent_runner


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


# --- Modelos Pydantic para Multi-tenant ---

class TenantBase(BaseModel):
    nome: str
    slug: str
    email: Optional[str] = None
    telefone: Optional[str] = None
    endereco: Optional[str] = None
    plano: str = "basico"
    chatwoot_url: Optional[str] = None
    chatwoot_api_token: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None


class TenantUpdate(BaseModel):
    nome: Optional[str] = None
    email: Optional[str] = None
    telefone: Optional[str] = None
    endereco: Optional[str] = None
    plano: Optional[str] = None
    ativo: Optional[bool] = None
    chatwoot_url: Optional[str] = None
    chatwoot_api_token: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None


class AgenteBase(BaseModel):
    tenant_id: Optional[int] = None  # NULL para agentes do admin
    nome: str
    descricao: Optional[str] = None
    # Configurações do Chatwoot
    chatwoot_url: Optional[str] = None  # URL base do Chatwoot
    chatwoot_api_token: Optional[str] = None  # Token para enviar mensagens
    chatwoot_account_id: Optional[str] = None  # ID da conta
    chatwoot_inbox_id: Optional[str] = None  # ID da inbox (WhatsApp)
    webhook_secret: Optional[str] = None  # Secret para validar webhooks
    # Configurações do agente
    system_prompt: Optional[str] = None
    modelo_llm: str = "google/gemini-2.0-flash-001"
    temperatura: float = 0.7
    max_tokens: int = 4096
    info_empresa: Optional[dict] = None


class AgenteUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    # Configurações do Chatwoot
    chatwoot_url: Optional[str] = None
    chatwoot_api_token: Optional[str] = None
    chatwoot_account_id: Optional[str] = None
    chatwoot_inbox_id: Optional[str] = None
    webhook_secret: Optional[str] = None
    # Configurações do agente
    system_prompt: Optional[str] = None
    modelo_llm: Optional[str] = None
    temperatura: Optional[float] = None
    max_tokens: Optional[int] = None
    info_empresa: Optional[dict] = None
    ativo: Optional[bool] = None


class SubAgenteBase(BaseModel):
    agente_id: int
    nome: str
    tipo: str
    descricao: Optional[str] = None
    system_prompt: Optional[str] = None
    ferramentas: Optional[list] = None
    condicao_ativacao: Optional[str] = None
    prioridade: int = 0


class SubAgenteUpdate(BaseModel):
    nome: Optional[str] = None
    tipo: Optional[str] = None
    descricao: Optional[str] = None
    system_prompt: Optional[str] = None
    ferramentas: Optional[list] = None
    condicao_ativacao: Optional[str] = None
    prioridade: Optional[int] = None
    ativo: Optional[bool] = None


class VinculacaoAgenteBase(BaseModel):
    """Modelo para vincular um agente a outro"""
    agente_principal_id: int
    agente_vinculado_id: int
    condicao_ativacao: Optional[str] = None
    prioridade: int = 0
    modo_transferencia: str = "interno"  # 'interno' ou 'externo'
    manter_contexto: bool = True


class VinculacaoAgenteUpdate(BaseModel):
    """Modelo para atualizar uma vinculação"""
    condicao_ativacao: Optional[str] = None
    prioridade: Optional[int] = None
    modo_transferencia: Optional[str] = None
    manter_contexto: Optional[bool] = None
    ativo: Optional[bool] = None


class AgenteVinculavelUpdate(BaseModel):
    """Modelo para configurar um agente como vinculável"""
    pode_ser_vinculado: bool
    tipo: Optional[str] = None
    condicao_ativacao: Optional[str] = None
    ferramentas: Optional[list] = None
    prioridade: int = 0


# --- Contexto do App ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia o ciclo de vida da aplicacao"""
    # Startup
    print("Iniciando Secretaria IA...")
    db = await get_db_service()
    print("Banco de dados conectado")

    # Executa migracoes multi-tenant
    try:
        tenant_svc = await get_tenant_service()
        await tenant_svc.run_migrations()
        print("Migracoes multi-tenant executadas")
    except Exception as e:
        print(f"Aviso: Migracoes multi-tenant nao executadas: {e}")

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

# Middleware de sessao para autenticacao
app.add_middleware(SessionMiddleware, secret_key=secrets.token_hex(32))

# Templates
templates = Jinja2Templates(directory="templates")

# --- Configuracoes de Autenticacao ---
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "mudaradmin123"


def get_current_user(request: Request):
    """Verifica se o usuario esta autenticado"""
    user = request.session.get("user")
    if not user:
        return None
    return user


def require_auth(request: Request):
    """Dependency para exigir autenticacao"""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Nao autenticado")
    return user


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

        # Tenta usar o sistema multi-agente se houver agente configurado
        response = None
        try:
            tenant_svc = await get_tenant_service()
            agente = await tenant_svc.buscar_agente_por_chatwoot(account_id)

            if agente:
                # Usa sistema multi-agente
                print(f"Usando agente configurado: {agente.nome} (ID: {agente.id})")
                multi_agent = await get_multi_agent_runner()
                response = await multi_agent.process_message(
                    agente=agente,
                    message=final_message,
                    phone=phone,
                    account_id=account_id,
                    conversation_id=conversation_id,
                    message_id=message_id,
                    telegram_chat_id=telegram_chat_id,
                    is_audio_message=is_audio
                )
        except Exception as e:
            print(f"Aviso: Multi-agente nao disponivel, usando agente padrao: {e}")

        # Fallback para agente padrao se multi-agente nao processou
        if not response:
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

        # Formata a resposta (usa agente padrao para formatacao)
        agent = get_agent()
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


# --- Rotas de Autenticacao ---

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Pagina de login"""
    # Se ja estiver logado, redireciona para o admin
    if get_current_user(request):
        return RedirectResponse(url="/admin", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login", response_class=HTMLResponse)
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    """Processa o login"""
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        request.session["user"] = {"username": username}
        return RedirectResponse(url="/admin", status_code=302)

    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": "Usuario ou senha incorretos"
    })


@app.get("/logout")
async def logout(request: Request):
    """Faz logout do usuario"""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


# --- API de Modelos OpenRouter ---

# Lista de modelos populares do OpenRouter (fallback se a API não responder)
OPENROUTER_POPULAR_MODELS = [
    # Google Gemini
    {"id": "google/gemini-2.5-flash", "name": "Gemini 2.5 Flash", "provider": "Google"},
    {"id": "google/gemini-2.5-flash-lite", "name": "Gemini 2.5 Flash Lite", "provider": "Google"},
    {"id": "google/gemini-2.5-flash-preview", "name": "Gemini 2.5 Flash Preview", "provider": "Google"},
    {"id": "google/gemini-2.5-pro-exp-03-25:free", "name": "Gemini 2.5 Pro Exp (Free)", "provider": "Google"},
    {"id": "google/gemini-2.0-flash-001", "name": "Gemini 2.0 Flash", "provider": "Google"},
    {"id": "google/gemini-2.0-flash-thinking-exp:free", "name": "Gemini 2.0 Flash Thinking (Free)", "provider": "Google"},
    {"id": "google/gemini-pro-1.5", "name": "Gemini Pro 1.5", "provider": "Google"},
    {"id": "google/gemini-flash-1.5", "name": "Gemini Flash 1.5", "provider": "Google"},
    {"id": "google/gemini-flash-1.5-8b", "name": "Gemini Flash 1.5 8B", "provider": "Google"},
    {"id": "google/gemma-2-27b-it", "name": "Gemma 2 27B", "provider": "Google"},
    {"id": "google/gemma-2-9b-it:free", "name": "Gemma 2 9B (Free)", "provider": "Google"},

    # DeepSeek
    {"id": "deepseek/deepseek-r1", "name": "DeepSeek R1", "provider": "DeepSeek"},
    {"id": "deepseek/deepseek-r1:free", "name": "DeepSeek R1 (Free)", "provider": "DeepSeek"},
    {"id": "deepseek/deepseek-r1-distill-llama-70b", "name": "DeepSeek R1 Distill Llama 70B", "provider": "DeepSeek"},
    {"id": "deepseek/deepseek-chat", "name": "DeepSeek Chat V3", "provider": "DeepSeek"},
    {"id": "deepseek/deepseek-chat:free", "name": "DeepSeek Chat V3 (Free)", "provider": "DeepSeek"},
    {"id": "deepseek/deepseek-coder", "name": "DeepSeek Coder", "provider": "DeepSeek"},

    # OpenAI
    {"id": "openai/gpt-4o", "name": "GPT-4o", "provider": "OpenAI"},
    {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini", "provider": "OpenAI"},
    {"id": "openai/gpt-4o-mini-2024-07-18", "name": "GPT-4o Mini (2024-07-18)", "provider": "OpenAI"},
    {"id": "openai/gpt-4-turbo", "name": "GPT-4 Turbo", "provider": "OpenAI"},
    {"id": "openai/gpt-4-turbo-preview", "name": "GPT-4 Turbo Preview", "provider": "OpenAI"},
    {"id": "openai/gpt-4", "name": "GPT-4", "provider": "OpenAI"},
    {"id": "openai/gpt-3.5-turbo", "name": "GPT-3.5 Turbo", "provider": "OpenAI"},
    {"id": "openai/o1-preview", "name": "O1 Preview", "provider": "OpenAI"},
    {"id": "openai/o1-mini", "name": "O1 Mini", "provider": "OpenAI"},

    # Anthropic Claude
    {"id": "anthropic/claude-3.5-sonnet", "name": "Claude 3.5 Sonnet", "provider": "Anthropic"},
    {"id": "anthropic/claude-3.5-sonnet-20241022", "name": "Claude 3.5 Sonnet (2024-10-22)", "provider": "Anthropic"},
    {"id": "anthropic/claude-3.5-haiku", "name": "Claude 3.5 Haiku", "provider": "Anthropic"},
    {"id": "anthropic/claude-3.5-haiku-20241022", "name": "Claude 3.5 Haiku (2024-10-22)", "provider": "Anthropic"},
    {"id": "anthropic/claude-3-opus", "name": "Claude 3 Opus", "provider": "Anthropic"},
    {"id": "anthropic/claude-3-sonnet", "name": "Claude 3 Sonnet", "provider": "Anthropic"},
    {"id": "anthropic/claude-3-haiku", "name": "Claude 3 Haiku", "provider": "Anthropic"},

    # Meta Llama
    {"id": "meta-llama/llama-3.3-70b-instruct", "name": "Llama 3.3 70B", "provider": "Meta"},
    {"id": "meta-llama/llama-3.2-90b-vision-instruct", "name": "Llama 3.2 90B Vision", "provider": "Meta"},
    {"id": "meta-llama/llama-3.1-405b-instruct", "name": "Llama 3.1 405B", "provider": "Meta"},
    {"id": "meta-llama/llama-3.1-70b-instruct", "name": "Llama 3.1 70B", "provider": "Meta"},
    {"id": "meta-llama/llama-3.1-8b-instruct:free", "name": "Llama 3.1 8B (Free)", "provider": "Meta"},

    # Mistral
    {"id": "mistralai/mistral-large-2411", "name": "Mistral Large (2411)", "provider": "Mistral"},
    {"id": "mistralai/mistral-medium", "name": "Mistral Medium", "provider": "Mistral"},
    {"id": "mistralai/mistral-small-24b-instruct-2501", "name": "Mistral Small 24B", "provider": "Mistral"},
    {"id": "mistralai/mistral-7b-instruct:free", "name": "Mistral 7B (Free)", "provider": "Mistral"},
    {"id": "mistralai/codestral-latest", "name": "Codestral", "provider": "Mistral"},

    # Qwen
    {"id": "qwen/qwen-2.5-72b-instruct", "name": "Qwen 2.5 72B", "provider": "Qwen"},
    {"id": "qwen/qwen-2.5-coder-32b-instruct", "name": "Qwen 2.5 Coder 32B", "provider": "Qwen"},
    {"id": "qwen/qwq-32b:free", "name": "QwQ 32B (Free)", "provider": "Qwen"},

    # Outros
    {"id": "cohere/command-r-plus", "name": "Command R+", "provider": "Cohere"},
    {"id": "perplexity/llama-3.1-sonar-huge-128k-online", "name": "Sonar Huge 128K Online", "provider": "Perplexity"},
]


@app.get("/api/modelos-llm")
async def listar_modelos_llm(buscar_api: bool = False):
    """
    Lista os modelos LLM disponíveis do OpenRouter

    Args:
        buscar_api: Se True, busca a lista atualizada da API do OpenRouter
    """
    import httpx

    if buscar_api:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {Config.OPENROUTER_API_KEY}"},
                    timeout=10.0
                )
                if response.status_code == 200:
                    data = response.json()
                    models = []
                    for model in data.get("data", []):
                        models.append({
                            "id": model.get("id"),
                            "name": model.get("name", model.get("id")),
                            "provider": model.get("id", "").split("/")[0].title() if "/" in model.get("id", "") else "Unknown",
                            "context_length": model.get("context_length"),
                            "pricing": model.get("pricing", {})
                        })
                    # Ordena por provider e nome
                    models.sort(key=lambda x: (x.get("provider", ""), x.get("name", "")))
                    return {"modelos": models, "fonte": "api", "total": len(models)}
        except Exception as e:
            print(f"Erro ao buscar modelos da API OpenRouter: {e}")

    # Retorna lista de modelos populares como fallback
    return {"modelos": OPENROUTER_POPULAR_MODELS, "fonte": "cache", "total": len(OPENROUTER_POPULAR_MODELS)}


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


@app.post("/webhook/chatwoot/{agente_id}")
async def chatwoot_webhook_agente(agente_id: int, request: Request, background_tasks: BackgroundTasks):
    """
    Webhook dinâmico para receber mensagens do Chatwoot por agente

    Cada agente tem sua própria URL de webhook: /webhook/chatwoot/{agente_id}
    Configure esta URL no Chatwoot para o evento message_created
    """
    try:
        data = await request.json()
        print(f"Webhook recebido para agente {agente_id}")

        # Busca o agente no banco de dados
        tenant_service = await get_tenant_service()
        agente = await tenant_service.obter_agente(agente_id)

        if not agente:
            print(f"Agente {agente_id} nao encontrado")
            raise HTTPException(status_code=404, detail="Agente nao encontrado")

        if not agente.ativo:
            print(f"Agente {agente_id} inativo")
            return {"status": "ignored", "reason": "agent inactive"}

        # Valida o evento
        event = data.get("event")
        if event != "message_created":
            print(f"Evento ignorado: {event}")
            return {"status": "ignored", "reason": "event not message_created"}

        message_type = data.get("message_type")
        print(f"[Agente {agente_id}] message_type={message_type}, content={data.get('content')}")

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

        print(f"[Agente {agente_id}] Processando: id={message_id}, phone={phone}, content={content[:50] if content else 'AUDIO'}...")

        # Processa em background com informações do agente
        background_tasks.add_task(
            process_incoming_message_for_agent,
            agente_id=agente_id,
            message_id=message_id,
            account_id=account_id,
            conversation_id=conversation_id,
            phone=phone,
            message=content,
            is_audio=is_audio,
            audio_url=audio_url,
            labels=labels,
            sender_name=sender_name
        )

        return {"status": "processing", "agent_id": agente_id}

    except HTTPException:
        raise
    except Exception as e:
        print(f"Erro no webhook do agente {agente_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def process_incoming_message_for_agent(
    agente_id: int,
    message_id: str,
    account_id: str,
    conversation_id: str,
    phone: str,
    message: str,
    is_audio: bool = False,
    audio_url: str = None,
    labels: list = None,
    sender_name: str = ""
):
    """
    Processa uma mensagem recebida para um agente específico

    Usa as configurações do agente (chatwoot_url, chatwoot_api_token) para responder
    """
    from src.services.chatwoot import ChatwootService

    try:
        # Busca o agente com todas as configurações
        tenant_service = await get_tenant_service()
        agente = await tenant_service.obter_agente(agente_id)

        if not agente:
            print(f"[Agente {agente_id}] Nao encontrado, ignorando mensagem")
            return

        # Cria instância do ChatwootService com as configurações do agente
        agente_chatwoot = ChatwootService(
            base_url=agente.chatwoot_url or Config.CHATWOOT_URL,
            api_token=agente.chatwoot_api_token or Config.CHATWOOT_API_TOKEN,
            account_id=agente.chatwoot_account_id or Config.CHATWOOT_ACCOUNT_ID
        )

        # Sistema de debounce por conversa
        queue_key = f"agente_{agente_id}_{conversation_id}"

        if queue_key not in message_queues:
            message_queues[queue_key] = []

        message_queues[queue_key].append({
            "message_id": message_id,
            "mensagem": message,
            "is_audio": is_audio,
            "audio_url": audio_url,
            "timestamp": asyncio.get_event_loop().time()
        })

        # Espera para agrupar mensagens
        await asyncio.sleep(2.0)

        if not message_queues.get(queue_key):
            return

        queued_messages = message_queues.pop(queue_key, [])
        if not queued_messages:
            return

        # Verifica se a ultima mensagem e audio
        last_msg = queued_messages[-1]
        is_audio = last_msg.get("is_audio", False)
        audio_url = last_msg.get("audio_url")

        # Prepara mensagem final
        if is_audio and audio_url:
            audio_data = await agente_chatwoot.download_attachment(audio_url)
            final_message = await audio_service.transcribe_audio(audio_data)
        else:
            final_message = "\n".join([m["mensagem"] for m in queued_messages])

        print(f"[Agente {agente_id}] Processando: {final_message[:50]}...")

        # Processa com o multi-agent runner
        runner = await get_multi_agent_runner()
        result = await runner.process(
            agente=agente,
            message=final_message,
            phone=phone,
            account_id=account_id,
            conversation_id=conversation_id
        )

        response_text = result.get("response", "Desculpe, nao consegui processar sua mensagem.")
        print(f"[Agente {agente_id}] Resposta: {response_text[:100]}...")

        # Envia resposta via Chatwoot do agente
        await agente_chatwoot.send_message(
            conversation_id=conversation_id,
            message=response_text
        )

    except Exception as e:
        print(f"[Agente {agente_id}] Erro ao processar mensagem: {e}")
        import traceback
        traceback.print_exc()


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
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "data_atual": datetime.now().strftime("%d/%m/%Y")
    })


@app.get("/admin/agenda", response_class=HTMLResponse)
async def admin_agenda(request: Request):
    """Pagina de agenda"""
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("agenda.html", {"request": request})


@app.get("/admin/profissionais", response_class=HTMLResponse)
async def admin_profissionais(request: Request):
    """Pagina de profissionais"""
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("profissionais.html", {"request": request})


@app.get("/admin/agentes", response_class=HTMLResponse)
async def admin_agentes(request: Request):
    """Pagina de agentes do admin"""
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("agentes.html", {"request": request})


@app.get("/admin/rag", response_class=HTMLResponse)
async def admin_rag(request: Request):
    """Pagina de base de conhecimento"""
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("rag.html", {"request": request})


@app.get("/admin/prompts", response_class=HTMLResponse)
async def admin_prompts(request: Request):
    """Pagina de prompts"""
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("prompts.html", {"request": request})


@app.get("/admin/pipeline", response_class=HTMLResponse)
async def admin_pipeline(request: Request):
    """Pagina de pipeline de atendimento"""
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("pipeline.html", {"request": request})


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
    """Lista profissionais do admin (tenant_id = NULL)"""
    try:
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)
        profissionais = await agenda.listar_profissionais(apenas_ativos=apenas_ativos, apenas_admin=True)
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
    """Atualiza um profissional do admin (tenant_id = NULL)"""
    try:
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)
        success = await agenda.atualizar_profissional(
            prof_id=prof_id,
            nome=prof.nome,
            cargo=prof.cargo,
            especialidade=prof.especialidade,
            ativo=prof.ativo,
            apenas_admin=True
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
    """Desativa um profissional do admin (tenant_id = NULL)"""
    try:
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)
        success = await agenda.deletar_profissional(prof_id, apenas_admin=True)
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


# --- API Pipeline de Atendimento ---

@app.get("/api/admin/pipeline")
async def api_listar_pipeline():
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
async def api_criar_conversa_pipeline(conversa: PipelineConversaBase):
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
async def api_atualizar_conversa_pipeline(conversa_id: int, conversa: PipelineConversaUpdate):
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
async def api_mover_conversa_pipeline(conversa_id: int, dados: PipelineMoverEtapa):
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
async def api_deletar_conversa_pipeline(conversa_id: int):
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
async def api_historico_conversa_pipeline(conversa_id: int):
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


# --- API Multi-Tenant ---

@app.get("/api/admin/tenants")
async def api_listar_tenants(apenas_ativos: bool = True):
    """Lista todos os tenants"""
    try:
        tenant_svc = await get_tenant_service()
        tenants = await tenant_svc.listar_tenants(apenas_ativos=apenas_ativos)
        return {"tenants": [
            {
                "id": t.id,
                "nome": t.nome,
                "slug": t.slug,
                "email": t.email,
                "telefone": t.telefone,
                "plano": t.plano,
                "ativo": t.ativo
            } for t in tenants
        ]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/tenants/{tenant_id}")
async def api_buscar_tenant(tenant_id: int):
    """Busca um tenant por ID"""
    try:
        tenant_svc = await get_tenant_service()
        tenant = await tenant_svc.buscar_tenant(tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant nao encontrado")
        return {
            "tenant": {
                "id": tenant.id,
                "nome": tenant.nome,
                "slug": tenant.slug,
                "email": tenant.email,
                "telefone": tenant.telefone,
                "endereco": tenant.endereco,
                "plano": tenant.plano,
                "ativo": tenant.ativo,
                "chatwoot_url": tenant.chatwoot_url,
                "telegram_chat_id": tenant.telegram_chat_id,
                "agentes": [
                    {
                        "id": a.id,
                        "nome": a.nome,
                        "descricao": a.descricao,
                        "chatwoot_account_id": a.chatwoot_account_id,
                        "modelo_llm": a.modelo_llm,
                        "ativo": a.ativo
                    } for a in tenant.agentes
                ]
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/tenants")
async def api_criar_tenant(tenant: TenantBase):
    """Cria um novo tenant"""
    try:
        tenant_svc = await get_tenant_service()
        novo_tenant = await tenant_svc.criar_tenant(
            nome=tenant.nome,
            slug=tenant.slug,
            email=tenant.email,
            telefone=tenant.telefone,
            endereco=tenant.endereco,
            plano=tenant.plano,
            chatwoot_url=tenant.chatwoot_url,
            chatwoot_api_token=tenant.chatwoot_api_token,
            telegram_bot_token=tenant.telegram_bot_token,
            telegram_chat_id=tenant.telegram_chat_id
        )
        return {"id": novo_tenant.id, "message": "Tenant criado com sucesso"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/admin/tenants/{tenant_id}")
async def api_atualizar_tenant(tenant_id: int, tenant: TenantUpdate):
    """Atualiza um tenant"""
    try:
        tenant_svc = await get_tenant_service()
        atualizado = await tenant_svc.atualizar_tenant(
            tenant_id=tenant_id,
            nome=tenant.nome,
            email=tenant.email,
            telefone=tenant.telefone,
            endereco=tenant.endereco,
            plano=tenant.plano,
            ativo=tenant.ativo,
            chatwoot_url=tenant.chatwoot_url,
            chatwoot_api_token=tenant.chatwoot_api_token,
            telegram_bot_token=tenant.telegram_bot_token,
            telegram_chat_id=tenant.telegram_chat_id
        )
        if not atualizado:
            raise HTTPException(status_code=404, detail="Tenant nao encontrado")
        return {"message": "Tenant atualizado"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/admin/tenants/{tenant_id}")
async def api_deletar_tenant(tenant_id: int):
    """Deleta um tenant"""
    try:
        tenant_svc = await get_tenant_service()
        success = await tenant_svc.deletar_tenant(tenant_id)
        if not success:
            raise HTTPException(status_code=404, detail="Tenant nao encontrado")
        return {"message": "Tenant deletado"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- API Agentes ---

@app.get("/api/admin/tenants/{tenant_id}/agentes")
async def api_listar_agentes(tenant_id: int, apenas_ativos: bool = True):
    """Lista agentes de um tenant"""
    try:
        tenant_svc = await get_tenant_service()
        agentes = await tenant_svc.listar_agentes(tenant_id, apenas_ativos=apenas_ativos)
        return {"agentes": [
            {
                "id": a.id,
                "tenant_id": a.tenant_id,
                "nome": a.nome,
                "descricao": a.descricao,
                "chatwoot_account_id": a.chatwoot_account_id,
                "chatwoot_inbox_id": a.chatwoot_inbox_id,
                "modelo_llm": a.modelo_llm,
                "temperatura": a.temperatura,
                "ativo": a.ativo
            } for a in agentes
        ]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- API Admin Agentes (agentes do admin sem tenant) ---

@app.get("/api/admin/agentes-admin")
async def api_listar_agentes_admin(apenas_ativos: bool = True):
    """Lista agentes do admin (tenant_id = null)"""
    try:
        tenant_svc = await get_tenant_service()
        agentes = await tenant_svc.listar_agentes_admin(apenas_ativos=apenas_ativos)
        return {"agentes": [
            {
                "id": a.id,
                "nome": a.nome,
                "descricao": a.descricao,
                "modelo_llm": a.modelo_llm,
                "ativo": a.ativo,
                "tipo": a.tipo,
                "pode_ser_vinculado": a.pode_ser_vinculado
            } for a in agentes
        ]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/agentes-admin")
async def api_criar_agente_admin(agente: AgenteBase):
    """Cria um novo agente do admin (sem tenant)"""
    try:
        tenant_svc = await get_tenant_service()
        novo_agente = await tenant_svc.criar_agente(
            tenant_id=None,  # Admin agentes nao tem tenant
            nome=agente.nome,
            descricao=agente.descricao,
            chatwoot_account_id=agente.chatwoot_account_id,
            chatwoot_inbox_id=agente.chatwoot_inbox_id,
            system_prompt=agente.system_prompt,
            modelo_llm=agente.modelo_llm,
            temperatura=agente.temperatura,
            max_tokens=agente.max_tokens,
            info_empresa=agente.info_empresa
        )
        return {"id": novo_agente.id, "message": "Agente criado com sucesso"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/agentes-admin/vinculaveis")
async def api_listar_agentes_admin_vinculaveis(excluir_agente_id: int = None):
    """Lista agentes do admin que podem ser vinculados"""
    try:
        tenant_svc = await get_tenant_service()
        agentes = await tenant_svc.listar_agentes_admin_vinculaveis(
            excluir_agente_id=excluir_agente_id
        )
        return {"agentes_vinculaveis": [
            {
                "id": a.id,
                "nome": a.nome,
                "tipo": a.tipo,
                "descricao": a.descricao
            } for a in agentes
        ]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/agentes/{agente_id}")
async def api_buscar_agente(agente_id: int):
    """Busca um agente por ID"""
    try:
        tenant_svc = await get_tenant_service()
        agente = await tenant_svc.buscar_agente(agente_id)
        if not agente:
            raise HTTPException(status_code=404, detail="Agente nao encontrado")
        return {
            "agente": {
                "id": agente.id,
                "tenant_id": agente.tenant_id,
                "nome": agente.nome,
                "descricao": agente.descricao,
                "chatwoot_account_id": agente.chatwoot_account_id,
                "chatwoot_inbox_id": agente.chatwoot_inbox_id,
                "system_prompt": agente.system_prompt,
                "modelo_llm": agente.modelo_llm,
                "temperatura": agente.temperatura,
                "max_tokens": agente.max_tokens,
                "info_empresa": agente.info_empresa,
                "ativo": agente.ativo,
                # Novos campos para agentes vinculados
                "tipo": agente.tipo,
                "pode_ser_vinculado": agente.pode_ser_vinculado,
                "condicao_ativacao": agente.condicao_ativacao,
                "ferramentas": agente.ferramentas,
                "prioridade": agente.prioridade,
                "sub_agentes": [
                    {
                        "id": sa.id,
                        "nome": sa.nome,
                        "tipo": sa.tipo,
                        "descricao": sa.descricao,
                        "prioridade": sa.prioridade,
                        "ativo": sa.ativo
                    } for sa in agente.sub_agentes
                ],
                "agentes_vinculados": [
                    {
                        "id": av.id,
                        "agente_id": av.agente_id,
                        "agente_nome": av.agente_nome,
                        "agente_tipo": av.agente_tipo,
                        "condicao_ativacao": av.condicao_ativacao,
                        "prioridade": av.prioridade,
                        "modo_transferencia": av.modo_transferencia,
                        "manter_contexto": av.manter_contexto
                    } for av in agente.agentes_vinculados
                ]
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/agentes")
async def api_criar_agente(agente: AgenteBase):
    """Cria um novo agente"""
    try:
        tenant_svc = await get_tenant_service()
        novo_agente = await tenant_svc.criar_agente(
            tenant_id=agente.tenant_id,
            nome=agente.nome,
            descricao=agente.descricao,
            chatwoot_account_id=agente.chatwoot_account_id,
            chatwoot_inbox_id=agente.chatwoot_inbox_id,
            system_prompt=agente.system_prompt,
            modelo_llm=agente.modelo_llm,
            temperatura=agente.temperatura,
            max_tokens=agente.max_tokens,
            info_empresa=agente.info_empresa
        )
        return {"id": novo_agente.id, "message": "Agente criado com sucesso"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/admin/agentes/{agente_id}")
async def api_atualizar_agente(agente_id: int, agente: AgenteUpdate):
    """Atualiza um agente"""
    try:
        tenant_svc = await get_tenant_service()
        atualizado = await tenant_svc.atualizar_agente(
            agente_id=agente_id,
            nome=agente.nome,
            descricao=agente.descricao,
            chatwoot_account_id=agente.chatwoot_account_id,
            chatwoot_inbox_id=agente.chatwoot_inbox_id,
            system_prompt=agente.system_prompt,
            modelo_llm=agente.modelo_llm,
            temperatura=agente.temperatura,
            max_tokens=agente.max_tokens,
            info_empresa=agente.info_empresa,
            ativo=agente.ativo
        )
        if not atualizado:
            raise HTTPException(status_code=404, detail="Agente nao encontrado")
        return {"message": "Agente atualizado"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/admin/agentes/{agente_id}")
async def api_deletar_agente(agente_id: int):
    """Deleta um agente"""
    try:
        tenant_svc = await get_tenant_service()
        success = await tenant_svc.deletar_agente(agente_id)
        if not success:
            raise HTTPException(status_code=404, detail="Agente nao encontrado")
        return {"message": "Agente deletado"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- API Sub-Agentes ---

@app.get("/api/admin/agentes/{agente_id}/sub-agentes")
async def api_listar_sub_agentes(agente_id: int, apenas_ativos: bool = True):
    """Lista sub-agentes de um agente"""
    try:
        tenant_svc = await get_tenant_service()
        sub_agentes = await tenant_svc.listar_sub_agentes(agente_id, apenas_ativos=apenas_ativos)
        return {"sub_agentes": [
            {
                "id": sa.id,
                "agente_id": sa.agente_id,
                "nome": sa.nome,
                "tipo": sa.tipo,
                "descricao": sa.descricao,
                "condicao_ativacao": sa.condicao_ativacao,
                "prioridade": sa.prioridade,
                "ativo": sa.ativo
            } for sa in sub_agentes
        ]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/sub-agentes")
async def api_criar_sub_agente(sub_agente: SubAgenteBase):
    """Cria um novo sub-agente"""
    try:
        tenant_svc = await get_tenant_service()
        novo_sub = await tenant_svc.criar_sub_agente(
            agente_id=sub_agente.agente_id,
            nome=sub_agente.nome,
            tipo=sub_agente.tipo,
            descricao=sub_agente.descricao,
            system_prompt=sub_agente.system_prompt,
            ferramentas=sub_agente.ferramentas,
            condicao_ativacao=sub_agente.condicao_ativacao,
            prioridade=sub_agente.prioridade
        )
        return {"id": novo_sub.id, "message": "Sub-agente criado com sucesso"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/admin/sub-agentes/{sub_agente_id}")
async def api_atualizar_sub_agente(sub_agente_id: int, sub_agente: SubAgenteUpdate):
    """Atualiza um sub-agente"""
    try:
        tenant_svc = await get_tenant_service()
        atualizado = await tenant_svc.atualizar_sub_agente(
            sub_agente_id=sub_agente_id,
            nome=sub_agente.nome,
            tipo=sub_agente.tipo,
            descricao=sub_agente.descricao,
            system_prompt=sub_agente.system_prompt,
            ferramentas=sub_agente.ferramentas,
            condicao_ativacao=sub_agente.condicao_ativacao,
            prioridade=sub_agente.prioridade,
            ativo=sub_agente.ativo
        )
        if not atualizado:
            raise HTTPException(status_code=404, detail="Sub-agente nao encontrado")
        return {"message": "Sub-agente atualizado"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/admin/sub-agentes/{sub_agente_id}")
async def api_deletar_sub_agente(sub_agente_id: int):
    """Deleta um sub-agente"""
    try:
        tenant_svc = await get_tenant_service()
        success = await tenant_svc.deletar_sub_agente(sub_agente_id)
        if not success:
            raise HTTPException(status_code=404, detail="Sub-agente nao encontrado")
        return {"message": "Sub-agente deletado"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Endpoints Agentes Vinculados ---

@app.get("/api/admin/agentes/{agente_id}/vinculados")
async def api_listar_agentes_vinculados(agente_id: int, apenas_ativos: bool = True):
    """Lista agentes vinculados a um agente principal"""
    try:
        tenant_svc = await get_tenant_service()
        vinculados = await tenant_svc.listar_agentes_vinculados(agente_id, apenas_ativos=apenas_ativos)
        return {"agentes_vinculados": [
            {
                "id": av.id,
                "agente_id": av.agente_id,
                "agente_nome": av.agente_nome,
                "agente_tipo": av.agente_tipo,
                "condicao_ativacao": av.condicao_ativacao,
                "prioridade": av.prioridade,
                "modo_transferencia": av.modo_transferencia,
                "manter_contexto": av.manter_contexto,
                "chatwoot_account_id": av.chatwoot_account_id
            } for av in vinculados
        ]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/admin/agentes/vinculaveis")
async def api_listar_agentes_vinculaveis(tenant_id: int, excluir_agente_id: int = None):
    """Lista agentes que podem ser vinculados (pode_ser_vinculado = true)"""
    try:
        tenant_svc = await get_tenant_service()
        vinculaveis = await tenant_svc.listar_agentes_vinculaveis(tenant_id, excluir_agente_id)
        return {"agentes_vinculaveis": [
            {
                "id": a.id,
                "nome": a.nome,
                "tipo": a.tipo,
                "condicao_ativacao": a.condicao_ativacao,
                "prioridade": a.prioridade,
                "chatwoot_account_id": a.chatwoot_account_id
            } for a in vinculaveis
        ]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/agentes/vincular")
async def api_vincular_agente(vinculacao: VinculacaoAgenteBase):
    """Cria uma vinculação entre dois agentes"""
    try:
        tenant_svc = await get_tenant_service()
        result = await tenant_svc.vincular_agente(
            agente_principal_id=vinculacao.agente_principal_id,
            agente_vinculado_id=vinculacao.agente_vinculado_id,
            condicao_ativacao=vinculacao.condicao_ativacao,
            prioridade=vinculacao.prioridade,
            modo_transferencia=vinculacao.modo_transferencia,
            manter_contexto=vinculacao.manter_contexto
        )
        return {"id": result["id"], "message": "Agentes vinculados com sucesso"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/admin/agentes/vinculacao/{vinculacao_id}")
async def api_atualizar_vinculacao(vinculacao_id: int, vinculacao: VinculacaoAgenteUpdate):
    """Atualiza uma vinculação"""
    try:
        tenant_svc = await get_tenant_service()
        result = await tenant_svc.atualizar_vinculacao(
            vinculacao_id=vinculacao_id,
            condicao_ativacao=vinculacao.condicao_ativacao,
            prioridade=vinculacao.prioridade,
            modo_transferencia=vinculacao.modo_transferencia,
            manter_contexto=vinculacao.manter_contexto,
            ativo=vinculacao.ativo
        )
        if not result:
            raise HTTPException(status_code=404, detail="Vinculacao nao encontrada")
        return {"message": "Vinculacao atualizada"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/admin/agentes/{agente_principal_id}/desvincular/{agente_vinculado_id}")
async def api_desvincular_agente(agente_principal_id: int, agente_vinculado_id: int):
    """Remove uma vinculação entre dois agentes"""
    try:
        tenant_svc = await get_tenant_service()
        success = await tenant_svc.desvincular_agente(agente_principal_id, agente_vinculado_id)
        if not success:
            raise HTTPException(status_code=404, detail="Vinculacao nao encontrada")
        return {"message": "Agentes desvinculados"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/admin/agentes/{agente_id}/vinculavel")
async def api_configurar_agente_vinculavel(agente_id: int, config: AgenteVinculavelUpdate):
    """Configura um agente como vinculável (pode ser chamado por outros)"""
    try:
        tenant_svc = await get_tenant_service()
        result = await tenant_svc.atualizar_agente(
            agente_id=agente_id,
            pode_ser_vinculado=config.pode_ser_vinculado,
            tipo=config.tipo,
            condicao_ativacao=config.condicao_ativacao,
            ferramentas=config.ferramentas,
            prioridade=config.prioridade
        )
        if not result:
            raise HTTPException(status_code=404, detail="Agente nao encontrado")
        return {"message": "Agente configurado como vinculavel"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Endpoints Admin Multi-tenant (HTML) ---

@app.get("/admin/tenants", response_class=HTMLResponse)
async def admin_tenants_page(request: Request):
    """Pagina de gerenciamento de tenants"""
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("tenants.html", {"request": request})


# --- Endpoints Area do Tenant (por slug) ---

async def get_tenant_or_404(slug: str):
    """Helper para buscar tenant por slug ou retornar 404"""
    tenant_svc = await get_tenant_service()
    tenant = await tenant_svc.buscar_tenant_por_slug(slug)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant nao encontrado")
    if not tenant.ativo:
        raise HTTPException(status_code=403, detail="Tenant inativo")
    return tenant


@app.get("/tenant/{slug}", response_class=HTMLResponse)
async def tenant_dashboard(request: Request, slug: str):
    """Dashboard do tenant"""
    tenant = await get_tenant_or_404(slug)
    return templates.TemplateResponse("tenant/dashboard.html", {
        "request": request,
        "tenant": tenant,
        "active_page": "dashboard"
    })


@app.get("/tenant/{slug}/agenda", response_class=HTMLResponse)
async def tenant_agenda(request: Request, slug: str):
    """Pagina de agenda do tenant"""
    tenant = await get_tenant_or_404(slug)
    return templates.TemplateResponse("tenant/agenda.html", {
        "request": request,
        "tenant": tenant,
        "active_page": "agenda"
    })


@app.get("/tenant/{slug}/pipeline", response_class=HTMLResponse)
async def tenant_pipeline(request: Request, slug: str):
    """Pagina de pipeline do tenant"""
    tenant = await get_tenant_or_404(slug)
    return templates.TemplateResponse("tenant/pipeline.html", {
        "request": request,
        "tenant": tenant,
        "active_page": "pipeline"
    })


@app.get("/tenant/{slug}/profissionais", response_class=HTMLResponse)
async def tenant_profissionais(request: Request, slug: str):
    """Pagina de profissionais do tenant"""
    tenant = await get_tenant_or_404(slug)
    return templates.TemplateResponse("tenant/profissionais.html", {
        "request": request,
        "tenant": tenant,
        "active_page": "profissionais"
    })


@app.get("/tenant/{slug}/agentes", response_class=HTMLResponse)
async def tenant_agentes(request: Request, slug: str):
    """Pagina de agentes do tenant"""
    tenant = await get_tenant_or_404(slug)
    return templates.TemplateResponse("tenant/agentes.html", {
        "request": request,
        "tenant": tenant,
        "active_page": "agentes"
    })


@app.get("/tenant/{slug}/prompts", response_class=HTMLResponse)
async def tenant_prompts(request: Request, slug: str):
    """Pagina de prompts do tenant"""
    tenant = await get_tenant_or_404(slug)
    return templates.TemplateResponse("tenant/prompts.html", {
        "request": request,
        "tenant": tenant,
        "active_page": "prompts"
    })


@app.get("/tenant/{slug}/rag", response_class=HTMLResponse)
async def tenant_rag(request: Request, slug: str):
    """Pagina de RAG do tenant"""
    tenant = await get_tenant_or_404(slug)
    return templates.TemplateResponse("tenant/rag.html", {
        "request": request,
        "tenant": tenant,
        "active_page": "rag"
    })


@app.get("/tenant/{slug}/configuracoes", response_class=HTMLResponse)
async def tenant_configuracoes(request: Request, slug: str):
    """Pagina de configuracoes do tenant"""
    tenant = await get_tenant_or_404(slug)
    return templates.TemplateResponse("tenant/configuracoes.html", {
        "request": request,
        "tenant": tenant,
        "active_page": "configuracoes"
    })


# --- API Tenant (dados filtrados por tenant) ---

@app.get("/api/tenant/{slug}/pipeline")
async def api_tenant_pipeline(slug: str):
    """Lista conversas do pipeline filtradas por tenant"""
    try:
        tenant = await get_tenant_or_404(slug)
        db = await get_db_service()
        conversas = await db.pipeline_listar_conversas(tenant_id=tenant.id)
        stats = await db.pipeline_stats(tenant_id=tenant.id)

        for c in conversas:
            if c.get('ultima_atualizacao'):
                c['ultima_atualizacao'] = c['ultima_atualizacao'].isoformat()
            if c.get('created_at'):
                c['created_at'] = c['created_at'].isoformat()
            if c.get('agendamento_data'):
                c['agendamento_data'] = c['agendamento_data'].isoformat()

        return {"conversas": conversas, "stats": stats}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tenant/{slug}/profissionais")
async def api_tenant_profissionais(slug: str, apenas_ativos: bool = True):
    """Lista profissionais filtrados por tenant"""
    try:
        tenant = await get_tenant_or_404(slug)
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)
        profissionais = await agenda.listar_profissionais(tenant_id=tenant.id, apenas_ativos=apenas_ativos)
        return {"profissionais": profissionais}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tenant/{slug}/profissionais")
async def api_tenant_criar_profissional(slug: str, prof: ProfissionalBase):
    """Cria um profissional para o tenant"""
    try:
        tenant = await get_tenant_or_404(slug)
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)
        prof_id = await agenda.criar_profissional(
            nome=prof.nome,
            cargo=prof.cargo,
            especialidade=prof.especialidade,
            tenant_id=tenant.id
        )
        return {"id": prof_id, "message": "Profissional criado com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/tenant/{slug}/profissionais/{prof_id}")
async def api_tenant_atualizar_profissional(slug: str, prof_id: int, prof: ProfissionalUpdate):
    """Atualiza um profissional do tenant"""
    try:
        tenant = await get_tenant_or_404(slug)
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)
        success = await agenda.atualizar_profissional(
            prof_id=prof_id,
            nome=prof.nome,
            cargo=prof.cargo,
            especialidade=prof.especialidade,
            ativo=prof.ativo,
            tenant_id=tenant.id
        )
        if not success:
            raise HTTPException(status_code=404, detail="Profissional nao encontrado")
        return {"message": "Profissional atualizado com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/tenant/{slug}/profissionais/{prof_id}")
async def api_tenant_deletar_profissional(slug: str, prof_id: int):
    """Desativa um profissional do tenant"""
    try:
        tenant = await get_tenant_or_404(slug)
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)
        success = await agenda.desativar_profissional(prof_id, tenant_id=tenant.id)
        if not success:
            raise HTTPException(status_code=404, detail="Profissional nao encontrado")
        return {"message": "Profissional desativado com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tenant/{slug}/agendamentos")
async def api_tenant_agendamentos(
    slug: str,
    data_inicio: str = None,
    data_fim: str = None,
    profissional_id: int = None,
    status: str = None
):
    """Lista agendamentos filtrados por tenant"""
    try:
        tenant = await get_tenant_or_404(slug)
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)
        agendamentos = await agenda.listar_agendamentos(
            data_inicio=data_inicio,
            data_fim=data_fim,
            profissional_id=profissional_id,
            status=status,
            tenant_id=tenant.id
        )
        return {"agendamentos": agendamentos}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tenant/{slug}/horarios-disponiveis")
async def api_tenant_horarios_disponiveis(slug: str, profissional_id: int, data: str):
    """Lista horarios disponiveis para o tenant"""
    try:
        tenant = await get_tenant_or_404(slug)
        db = await get_db_service()
        agenda = await get_agenda_service(db.pool)
        from datetime import date as date_type
        data_parsed = date_type.fromisoformat(data)
        horarios = await agenda.buscar_horarios_disponiveis(
            profissional_id=profissional_id,
            data=data_parsed,
            tenant_id=tenant.id
        )
        return {"horarios": horarios}
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
