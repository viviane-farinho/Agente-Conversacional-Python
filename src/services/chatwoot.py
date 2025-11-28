"""
Serviço de integração com Chatwoot
"""
import httpx
from typing import Optional
from src.config import Config


class ChatwootService:
    """Serviço para interação com a API do Chatwoot"""

    def __init__(self):
        self.base_url = Config.CHATWOOT_URL.rstrip("/")
        self.api_token = Config.CHATWOOT_API_TOKEN
        self.headers = {
            "api_access_token": self.api_token,
            "Content-Type": "application/json"
        }

    async def send_message(
        self,
        account_id: str,
        conversation_id: str,
        content: str
    ) -> dict:
        """Envia uma mensagem de texto para a conversa"""
        url = f"{self.base_url}/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers=self.headers,
                json={"content": content}
            )
            response.raise_for_status()
            return response.json()

    async def send_audio(
        self,
        account_id: str,
        conversation_id: str,
        audio_data: bytes,
        filename: str = "audio.mp3"
    ) -> dict:
        """Envia um áudio para a conversa"""
        url = f"{self.base_url}/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages"

        headers = {"api_access_token": self.api_token}

        async with httpx.AsyncClient() as client:
            files = {
                "attachments[]": (filename, audio_data, "audio/mpeg")
            }
            data = {
                "is_recorded_audio": f'["{filename}"]'
            }
            response = await client.post(
                url,
                headers=headers,
                files=files,
                data=data
            )
            response.raise_for_status()
            return response.json()

    async def send_file(
        self,
        account_id: str,
        conversation_id: str,
        file_data: bytes,
        filename: str,
        content_type: str = "application/octet-stream"
    ) -> dict:
        """Envia um arquivo para a conversa"""
        url = f"{self.base_url}/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages"

        headers = {"api_access_token": self.api_token}

        async with httpx.AsyncClient() as client:
            files = {
                "attachments[]": (filename, file_data, content_type)
            }
            response = await client.post(
                url,
                headers=headers,
                files=files
            )
            response.raise_for_status()
            return response.json()

    async def react_to_message(
        self,
        account_id: str,
        conversation_id: str,
        message_id: str,
        emoji: str
    ) -> dict:
        """Reage a uma mensagem com um emoji"""
        url = f"{self.base_url}/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers=self.headers,
                json={
                    "content": emoji,
                    "content_attributes": {
                        "in_reply_to": int(message_id),
                        "is_reaction": True
                    }
                }
            )
            response.raise_for_status()
            return response.json()

    async def mark_as_read(self, account_id: str, conversation_id: str) -> None:
        """Marca as mensagens como lidas"""
        url = f"{self.base_url}/api/v1/accounts/{account_id}/conversations/{conversation_id}/update_last_seen"

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=self.headers)
            response.raise_for_status()

    async def set_typing_status(
        self,
        account_id: str,
        conversation_id: str,
        status: str = "on"
    ) -> None:
        """Define o status de digitação (on, off, recording)"""
        url = f"{self.base_url}/api/v1/accounts/{account_id}/conversations/{conversation_id}/toggle_typing_status"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers=self.headers,
                json={"typing_status": status}
            )
            response.raise_for_status()

    async def get_labels(self, account_id: str, conversation_id: str) -> list:
        """Obtém as etiquetas de uma conversa"""
        url = f"{self.base_url}/api/v1/accounts/{account_id}/conversations/{conversation_id}/labels"

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json().get("payload", [])

    async def add_label(
        self,
        account_id: str,
        conversation_id: str,
        labels: list
    ) -> dict:
        """Adiciona etiquetas a uma conversa"""
        url = f"{self.base_url}/api/v1/accounts/{account_id}/conversations/{conversation_id}/labels"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers=self.headers,
                json={"labels": labels}
            )
            response.raise_for_status()
            return response.json()

    async def download_attachment(self, attachment_url: str) -> bytes:
        """Baixa um anexo (áudio, imagem, etc.)"""
        headers = {"api_access_token": self.api_token}

        async with httpx.AsyncClient() as client:
            response = await client.get(attachment_url, headers=headers)
            response.raise_for_status()
            return response.content


# Instância global do serviço
chatwoot_service = ChatwootService()
