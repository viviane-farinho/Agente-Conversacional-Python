"""
Serviço de integração com Telegram
Para envio de alertas e notificações
"""
import httpx
from src.config import Config


class TelegramService:
    """Serviço para envio de mensagens via Telegram"""

    def __init__(self):
        self.bot_token = Config.TELEGRAM_BOT_TOKEN
        self.default_chat_id = Config.TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    async def send_message(
        self,
        text: str,
        chat_id: str = None,
        parse_mode: str = "HTML"
    ) -> dict:
        """
        Envia uma mensagem de texto

        Args:
            text: Texto da mensagem
            chat_id: ID do chat (usa padrão se não fornecido)
            parse_mode: Modo de formatação (HTML, Markdown, MarkdownV2)

        Returns:
            Resposta da API do Telegram
        """
        if chat_id is None:
            chat_id = self.default_chat_id

        url = f"{self.base_url}/sendMessage"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": parse_mode
                }
            )
            response.raise_for_status()
            return response.json()

    async def send_alert(
        self,
        title: str,
        message: str,
        chat_id: str = None
    ) -> dict:
        """
        Envia um alerta formatado

        Args:
            title: Título do alerta
            message: Mensagem do alerta
            chat_id: ID do chat

        Returns:
            Resposta da API do Telegram
        """
        formatted_text = f"<b>🚨 {title}</b>\n\n{message}"
        return await self.send_message(formatted_text, chat_id)

    async def send_escalation_alert(
        self,
        patient_name: str,
        patient_phone: str,
        last_message: str,
        chat_id: str = None
    ) -> dict:
        """
        Envia alerta de escalação para humano

        Args:
            patient_name: Nome do paciente
            patient_phone: Telefone do paciente
            last_message: Última mensagem do paciente
            chat_id: ID do chat

        Returns:
            Resposta da API do Telegram
        """
        text = (
            f"Assistente desabilitado para o usuário "
            f"{patient_name or '(usuário não cadastrado)'} ({patient_phone}).\n\n"
            f"Última mensagem:\n\n---\n\n{last_message}"
        )
        return await self.send_message(text, chat_id, parse_mode=None)

    async def send_cancellation_alert(
        self,
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
            f"<b>❌ Cancelamento de Consulta</b>\n\n"
            f"<b>Paciente:</b> {patient_name}\n"
            f"<b>Data:</b> {appointment_date}\n"
            f"<b>Horário:</b> {appointment_time}"
        )
        return await self.send_message(text, chat_id)


# Instância global do serviço
telegram_service = TelegramService()
