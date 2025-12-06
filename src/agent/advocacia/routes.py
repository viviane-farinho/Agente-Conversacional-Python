"""
Rotas da API para Advocacia

Este módulo contém as rotas FastAPI específicas para o sistema de advocacia.
É 100% independente das rotas do sistema principal.

Endpoints:
- POST /webhook/advocacia - Webhook do Chatwoot para advocacia
- GET /api/advocacia/areas - Lista áreas do direito
- GET /api/advocacia/servicos - Lista serviços
- POST /api/advocacia/buscar - Busca na base de conhecimento
"""

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List
import hmac
import hashlib

from src.config import Config
from src.agent.advocacia.handler import process_advocacia_message
from src.services.rag_advocacia import (
    rag_advocacia_list_areas,
    rag_advocacia_list_servicos,
    rag_advocacia_search_async,
    rag_advocacia_get_area
)


# Router independente para advocacia
router = APIRouter(prefix="/advocacia", tags=["Advocacia"])


# --- Modelos Pydantic ---

class BuscaAdvocacia(BaseModel):
    """Modelo para busca na base de conhecimento de advocacia"""
    query: str
    area_ids: Optional[List[str]] = None
    servico_id: Optional[str] = None
    limit: int = 5


# --- Funções auxiliares ---

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


# --- Endpoints ---

@router.post("/webhook")
async def advocacia_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Webhook para receber mensagens do Chatwoot - Sistema ADVOCACIA

    Configure este endpoint no Chatwoot para direcionar mensagens
    para o sistema multi-agente de escritórios de advocacia.

    URL completa: /advocacia/webhook
    """
    try:
        # Validar assinatura do webhook
        body = await request.body()
        signature = request.headers.get("X-Chatwoot-Signature", "")
        if not verify_webhook_signature(body, signature):
            print("[ADVOCACIA] Webhook com assinatura inválida rejeitado")
            raise HTTPException(status_code=401, detail="Assinatura inválida")

        data = await request.json()
        print(f"[ADVOCACIA] Webhook recebido")

        # Valida o evento
        event = data.get("event")
        if event != "message_created":
            print(f"[ADVOCACIA] Evento ignorado: {event}")
            return {"status": "ignored", "reason": "event not message_created"}

        message_type = data.get("message_type")
        print(f"[ADVOCACIA] message_type={message_type}, content={data.get('content')}")

        # Ignora mensagens enviadas pelo agente (outgoing)
        if message_type != "incoming":
            print(f"[ADVOCACIA] Mensagem ignorada: message_type={message_type}")
            return {"status": "ignored", "reason": "not incoming message"}

        # Extrai dados da mensagem
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
            print(f"[ADVOCACIA] Mensagem sem conteúdo ignorada")
            return {"status": "ignored", "reason": "no content or audio"}

        print(f"[ADVOCACIA] Processando: id={message_id}, phone={phone}, content={content[:50] if content else 'AUDIO'}...")

        # Processa em background usando o handler de advocacia
        background_tasks.add_task(
            process_advocacia_message,
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

        return {"status": "processing", "system": "advocacia"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ADVOCACIA] Erro no webhook: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/areas")
async def listar_areas():
    """Lista todas as áreas do direito disponíveis"""
    try:
        areas = await rag_advocacia_list_areas()
        return {"areas": areas, "total": len(areas)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/areas/{area_id}")
async def buscar_area(area_id: str):
    """Busca uma área específica pelo ID"""
    try:
        area = await rag_advocacia_get_area(area_id)
        if not area:
            raise HTTPException(status_code=404, detail="Área não encontrada")
        return {"area": area}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/servicos")
async def listar_servicos(area_id: Optional[str] = None):
    """Lista serviços disponíveis, opcionalmente filtrados por área"""
    try:
        servicos = await rag_advocacia_list_servicos(area_id=area_id)
        return {"servicos": servicos, "total": len(servicos)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/buscar")
async def buscar_documentos(busca: BuscaAdvocacia):
    """Busca documentos na base de conhecimento de advocacia"""
    try:
        resultados = await rag_advocacia_search_async(
            query=busca.query,
            area_ids=busca.area_ids,
            servico_id=busca.servico_id,
            limit=busca.limit
        )
        return {"resultados": resultados, "total": len(resultados)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Verificação de saúde do sistema de advocacia"""
    return {
        "status": "healthy",
        "system": "advocacia",
        "version": "1.0.0"
    }
