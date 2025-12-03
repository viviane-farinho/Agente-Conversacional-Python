"""
Servico de integracao com Telegram
Para envio de alertas e notificacoes

Paradigma: Funcional
"""
import httpx

from src.config import Config


# --- Funcoes de Envio ---

async def send_telegram_message(
    text: str,
    chat_id: str = None,
    parse_mode: str = "HTML"
) -> dict:
    """
    Envia uma mensagem de texto via Telegram

    Args:
        text: Texto da mensagem
        chat_id: ID do chat (usa padrao se nao fornecido)
        parse_mode: Modo de formatacao (HTML, Markdown, MarkdownV2)

    Returns:
        Resposta da API do Telegram
    """
    if chat_id is None:
        chat_id = Config.TELEGRAM_CHAT_ID

    base_url = f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}"
    url = f"{base_url}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": text
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        return response.json()


async def send_telegram_alert(
    title: str,
    message: str,
    chat_id: str = None
) -> dict:
    """
    Envia um alerta formatado

    Args:
        title: Titulo do alerta
        message: Mensagem do alerta
        chat_id: ID do chat

    Returns:
        Resposta da API do Telegram
    """
    formatted_text = f"<b>{title}</b>\n\n{message}"
    return await send_telegram_message(formatted_text, chat_id)


async def send_escalation_alert(
    patient_name: str,
    patient_phone: str,
    last_message: str,
    chat_id: str = None
) -> dict:
    """
    Envia alerta de escalacao para humano

    Args:
        patient_name: Nome do paciente
        patient_phone: Telefone do paciente
        last_message: Ultima mensagem do paciente
        chat_id: ID do chat

    Returns:
        Resposta da API do Telegram
    """
    text = (
        f"Assistente desabilitado para o usuario "
        f"{patient_name or '(usuario nao cadastrado)'} ({patient_phone}).\n\n"
        f"Ultima mensagem:\n\n---\n\n{last_message}"
    )
    return await send_telegram_message(text, chat_id, parse_mode=None)


async def send_cancellation_alert(
    patient_name: str,
    appointment_date: str,
    appointment_time: str,
    chat_id: str = None
) -> dict:
    """
    Envia alerta de cancelamento de consulta

    Args:
        patient_name: Nome do paciente
        appointment_date: Data da consulta
        appointment_time: Hora da consulta
        chat_id: ID do chat

    Returns:
        Resposta da API do Telegram
    """
    text = (
        f"<b>Cancelamento de Consulta</b>\n\n"
        f"<b>Paciente:</b> {patient_name}\n"
        f"<b>Data:</b> {appointment_date}\n"
        f"<b>Horario:</b> {appointment_time}"
    )
    return await send_telegram_message(text, chat_id)


# --- Compatibilidade (para transicao gradual) ---

class TelegramService:
    """Classe de compatibilidade - usar funcoes diretamente"""

    def __init__(self):
        self.bot_token = Config.TELEGRAM_BOT_TOKEN
        self.default_chat_id = Config.TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    async def send_message(self, text: str, chat_id: str = None, parse_mode: str = "HTML") -> dict:
        return await send_telegram_message(text, chat_id, parse_mode)

    async def send_alert(self, title: str, message: str, chat_id: str = None) -> dict:
        return await send_telegram_alert(title, message, chat_id)

    async def send_escalation_alert(self, patient_name: str, patient_phone: str, last_message: str, chat_id: str = None) -> dict:
        return await send_escalation_alert(patient_name, patient_phone, last_message, chat_id)

    async def send_cancellation_alert(self, patient_name: str, appointment_date: str, appointment_time: str, chat_id: str = None) -> dict:
        return await send_cancellation_alert(patient_name, appointment_date, appointment_time, chat_id)


# Instancia global para compatibilidade
telegram_service = TelegramService()
