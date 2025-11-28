"""
Servidor Principal - Secretária IA
Sistema de atendimento via WhatsApp para clínicas médicas
"""
import asyncio
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel
import uvicorn

from src.config import Config
from src.services.database import get_db_service
from src.services.chatwoot import chatwoot_service
from src.services.audio import audio_service
from src.services.rag import get_rag_service
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


# --- Contexto do App ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia o ciclo de vida da aplicação"""
    # Startup
    print("🚀 Iniciando Secretária IA...")
    db = await get_db_service()
    print("✅ Banco de dados conectado")

    # Inicializa RAG
    try:
        rag = await get_rag_service(db.pool)
        if rag.initialized:
            print("✅ Base de conhecimento (RAG) inicializada")
        else:
            print("⚠️ RAG não inicializado - extensão 'vector' pode não estar habilitada")
    except Exception as e:
        print(f"⚠️ RAG não disponível: {e}")

    print(f"✅ Servidor rodando em http://{Config.SERVER_HOST}:{Config.SERVER_PORT}")

    yield

    # Shutdown
    print("👋 Encerrando Secretária IA...")
    if db.pool:
        await db.disconnect()


# --- Aplicação FastAPI ---

app = FastAPI(
    title="Secretária IA",
    description="Sistema de atendimento via WhatsApp para clínicas médicas",
    version="1.0.0",
    lifespan=lifespan
)


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

    Esta função implementa a lógica de:
    1. Verificar se o agente está habilitado (etiqueta agente-off)
    2. Enfileirar mensagens para evitar processamento duplicado
    3. Aguardar mensagens encavaladas
    4. Transcrever áudio se necessário
    5. Processar com o agente IA
    6. Enviar resposta (texto ou áudio)
    """
    try:
        # Verifica se o agente está desabilitado para esta conversa
        if "agente-off" in labels:
            print(f"⏭️ Agente desabilitado para conversa {conversation_id}")
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

        # Verifica se esta é a última mensagem da fila
        last_id = await db.get_last_message_id(phone)
        if last_id != message_id:
            print(f"⏭️ Mensagem encavalada ignorada: {message_id}")
            return

        # Busca todas as mensagens da fila
        queued_messages = await db.get_queued_messages(phone)

        # Limpa a fila
        await db.clear_message_queue(phone)

        # Concatena as mensagens
        if is_audio and audio_url:
            # Baixa e transcreve o áudio
            audio_data = await chatwoot_service.download_attachment(audio_url)
            final_message = await audio_service.transcribe_audio(audio_data)
        else:
            final_message = "\n".join([m["mensagem"] for m in queued_messages])

        print(f"📨 Processando mensagem de {phone}: {final_message[:50]}...")

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

        # Desliga o status de digitação
        await chatwoot_service.set_typing_status(account_id, conversation_id, "off")

        # Envia a resposta
        if is_audio:
            # Gera áudio da resposta
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

        print(f"✅ Resposta enviada para {phone}")

    except Exception as e:
        print(f"❌ Erro ao processar mensagem: {e}")
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
    """Endpoint de verificação de saúde"""
    return {
        "status": "ok",
        "service": "Secretária IA",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    """Verificação de saúde do serviço"""
    return {"status": "healthy"}


@app.post("/webhook/chatwoot")
async def chatwoot_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Webhook para receber mensagens do Chatwoot

    Este endpoint é chamado pelo Chatwoot quando uma nova mensagem é criada.
    O processamento é feito em background para responder rapidamente ao webhook.
    """
    try:
        data = await request.json()
        print(f"📥 Webhook recebido")

        # Valida o evento
        event = data.get("event")
        if event != "message_created":
            print(f"⏭️ Evento ignorado: {event}")
            return {"status": "ignored", "reason": "event not message_created"}

        # Os dados vêm direto no JSON, não em "body"
        message_type = data.get("message_type")
        print(f"📋 message_type={message_type}, content={data.get('content')}")

        # Ignora mensagens enviadas pelo agente (outgoing)
        if message_type != "incoming":
            print(f"⏭️ Mensagem ignorada: message_type={message_type}")
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

        # Verifica se é mensagem de áudio
        is_audio = False
        audio_url = None
        if attachments:
            first_attachment = attachments[0]
            is_audio = first_attachment.get("meta", {}).get("is_recorded_audio", False)
            if is_audio:
                audio_url = first_attachment.get("data_url")

        # Ignora se não tem conteúdo nem áudio
        if not content and not is_audio:
            print(f"⏭️ Mensagem sem conteúdo ignorada")
            return {"status": "ignored", "reason": "no content or audio"}

        print(f"✅ Processando mensagem: id={message_id}, phone={phone}, content={content[:50] if content else 'AUDIO'}...")

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
        print(f"❌ Erro no webhook: {e}")
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
    """Adiciona um novo documento à base de conhecimento"""
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
            raise HTTPException(status_code=404, detail="Documento não encontrado")
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
            raise HTTPException(status_code=404, detail="Documento não encontrado")
        return {"message": "Documento removido com sucesso"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/documentos/buscar")
async def buscar_documentos(busca: BuscaDocumento):
    """Busca documentos por similaridade semântica"""
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


# --- Execução ---

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=Config.SERVER_HOST,
        port=Config.SERVER_PORT,
        reload=True
    )
