"""
Handler de Mensagens para Advocacia

Este módulo processa mensagens recebidas pelo webhook da advocacia,
usando o sistema multi-agente independente de advogados.

Fluxo:
1. Recebe mensagem do webhook
2. Enfileira e processa mensagens encavaladas
3. Transcreve áudio se necessário
4. Processa com o grafo de advocacia
5. Envia resposta via Chatwoot
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional

from src.config import Config
from src.services.database import get_db_service
from src.services.chatwoot import chatwoot_service
from src.services.audio import audio_service
from src.services.agenda import config_obter_int
from src.agent.advocacia import create_advocacia_graph
from langchain_core.messages import HumanMessage, AIMessage


async def process_advocacia_message(
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
    Processa uma mensagem usando o sistema multi-agente de ADVOCACIA.

    Este handler é 100% independente do sistema principal de infoprodutos.
    Usa o grafo LangGraph específico para escritórios de advocacia.

    Args:
        message_id: ID da mensagem no Chatwoot
        account_id: ID da conta no Chatwoot
        conversation_id: ID da conversa no Chatwoot
        phone: Telefone do cliente
        message: Conteúdo da mensagem
        is_audio: Se é mensagem de áudio
        audio_url: URL do áudio (se aplicável)
        labels: Labels da conversa no Chatwoot
        telegram_chat_id: Chat ID do Telegram para notificações
        sender_name: Nome do remetente
    """
    try:
        # Verifica se o agente está desabilitado para esta conversa
        if "agente-off" in labels:
            print(f"[ADVOCACIA] Agente desabilitado para conversa {conversation_id}")
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
            print(f"[ADVOCACIA] Aviso: Não foi possível ativar typing status: {e}")

        # Aguarda mensagens encavaladas
        buffer_seconds = await config_obter_int("message_buffer_seconds", Config.MESSAGE_QUEUE_WAIT_TIME)
        await asyncio.sleep(buffer_seconds)

        # Verifica se esta é a última mensagem da fila
        last_id = await db.get_last_message_id(phone)
        if last_id != message_id:
            print(f"[ADVOCACIA] Mensagem encavalada ignorada: {message_id}")
            return

        # Busca todas as mensagens da fila
        queued_messages = await db.get_queued_messages(phone)

        # Limpa a fila
        await db.clear_message_queue(phone)

        # Concatena as mensagens ou transcreve áudio
        if is_audio and audio_url:
            audio_data = await chatwoot_service.download_attachment(audio_url)
            final_message = await audio_service.transcribe_audio(audio_data)
        else:
            final_message = "\n".join([m["mensagem"] for m in queued_messages])

        print(f"[ADVOCACIA] Processando mensagem de {phone}: {final_message[:50]}...")

        # Marca como lida e mostra "digitando"
        await chatwoot_service.mark_as_read(account_id, conversation_id)
        typing_status = "recording" if is_audio else "on"
        await chatwoot_service.set_typing_status(account_id, conversation_id, typing_status)

        # =====================================================
        # USA O SISTEMA MULTI-AGENTE DE ADVOCACIA
        # =====================================================

        # Busca histórico de mensagens para contexto
        history = await db.get_message_history(phone, limit=10)

        # Converte histórico para formato LangGraph
        messages = []
        for msg in history:
            if msg.get("role") == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg.get("role") == "assistant":
                messages.append(AIMessage(content=msg["content"]))

        # Adiciona mensagem atual
        messages.append(HumanMessage(content=final_message))

        # Cria e executa o grafo de advocacia
        graph = create_advocacia_graph()

        result = await graph.ainvoke({
            "messages": messages,
            "next_agent": None,
            "last_agent": None,
            "detected_areas": None,
            "telefone": phone
        })

        # Extrai resposta do resultado
        response = None
        for msg in reversed(result.get("messages", [])):
            if isinstance(msg, AIMessage) and msg.content:
                response = msg.content
                break

        if not response:
            response = "Desculpe, não consegui processar sua mensagem. Por favor, tente novamente."

        # Log do agente usado
        last_agent = result.get("last_agent", "desconhecido")
        detected_areas = result.get("detected_areas", [])
        print(f"[ADVOCACIA] Agente: {last_agent}, Áreas: {detected_areas}")

        # Salva mensagem do usuário no histórico
        await db.add_message_to_history(
            session_id=phone,
            role="user",
            content=final_message
        )

        # Salva resposta no histórico
        await db.add_message_to_history(
            session_id=phone,
            role="assistant",
            content=response
        )

        # Desliga o status de digitação
        await chatwoot_service.set_typing_status(account_id, conversation_id, "off")

        # Envia a resposta
        if is_audio:
            # Gera áudio da resposta
            tts_text = audio_service.format_text_for_tts(response)
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
                content=response
            )

        print(f"[ADVOCACIA] Resposta enviada para {phone}")

    except Exception as e:
        print(f"[ADVOCACIA] Erro ao processar mensagem: {e}")
        import traceback
        traceback.print_exc()

        # Tenta enviar mensagem de erro
        try:
            await chatwoot_service.set_typing_status(account_id, conversation_id, "off")
            await chatwoot_service.send_message(
                account_id=account_id,
                conversation_id=conversation_id,
                content="Desculpe, ocorreu um erro ao processar sua mensagem. Por favor, tente novamente em alguns instantes."
            )
        except:
            pass
