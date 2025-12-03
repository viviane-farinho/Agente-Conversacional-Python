"""
Servico de integracao com Chatwoot

Paradigma: Funcional
"""
import httpx
from urllib.parse import urlparse

from src.config import Config


# --- Helpers ---

def _get_base_url() -> str:
    """Retorna a URL base do Chatwoot"""
    return Config.CHATWOOT_URL.rstrip("/")


def _is_safe_attachment_url(url: str) -> bool:
    """
    Valida se a URL de anexo e segura (previne SSRF)

    Args:
        url: URL para validar

    Returns:
        True se a URL e segura
    """
    try:
        parsed = urlparse(url)

        # Deve ser HTTPS
        if parsed.scheme not in ["https", "http"]:
            return False

        # Deve ser do dominio do Chatwoot configurado
        chatwoot_domain = urlparse(Config.CHATWOOT_URL).netloc
        if not parsed.netloc.endswith(chatwoot_domain):
            return False

        # Nao pode ser IP privado/localhost
        hostname = parsed.hostname or ""
        blocked_hosts = ["localhost", "127.0.0.1", "0.0.0.0", "::1"]
        if hostname in blocked_hosts or hostname.startswith("192.168.") or hostname.startswith("10.") or hostname.startswith("172."):
            return False

        return True
    except Exception:
        return False


def _get_headers() -> dict:
    """Retorna headers padrao para requisicoes"""
    return {
        "api_access_token": Config.CHATWOOT_API_TOKEN,
        "Content-Type": "application/json"
    }


def _get_headers_multipart() -> dict:
    """Retorna headers para upload de arquivos (sem Content-Type)"""
    return {
        "api_access_token": Config.CHATWOOT_API_TOKEN
    }


# --- Envio de Mensagens ---

async def chatwoot_send_message(
    account_id: str,
    conversation_id: str,
    content: str
) -> dict:
    """
    Envia uma mensagem de texto para a conversa

    Args:
        account_id: ID da conta no Chatwoot
        conversation_id: ID da conversa
        content: Conteudo da mensagem

    Returns:
        Resposta da API do Chatwoot
    """
    url = f"{_get_base_url()}/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            headers=_get_headers(),
            json={"content": content}
        )
        response.raise_for_status()
        return response.json()


async def chatwoot_send_audio(
    account_id: str,
    conversation_id: str,
    audio_data: bytes,
    filename: str = "audio.mp3"
) -> dict:
    """
    Envia um audio para a conversa

    Args:
        account_id: ID da conta no Chatwoot
        conversation_id: ID da conversa
        audio_data: Dados do audio em bytes
        filename: Nome do arquivo

    Returns:
        Resposta da API do Chatwoot
    """
    url = f"{_get_base_url()}/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages"

    async with httpx.AsyncClient() as client:
        files = {
            "attachments[]": (filename, audio_data, "audio/mpeg")
        }
        data = {
            "is_recorded_audio": f'["{filename}"]'
        }
        response = await client.post(
            url,
            headers=_get_headers_multipart(),
            files=files,
            data=data
        )
        response.raise_for_status()
        return response.json()


async def chatwoot_send_file(
    account_id: str,
    conversation_id: str,
    file_data: bytes,
    filename: str,
    content_type: str = "application/octet-stream"
) -> dict:
    """
    Envia um arquivo para a conversa

    Args:
        account_id: ID da conta no Chatwoot
        conversation_id: ID da conversa
        file_data: Dados do arquivo em bytes
        filename: Nome do arquivo
        content_type: Tipo MIME do arquivo

    Returns:
        Resposta da API do Chatwoot
    """
    url = f"{_get_base_url()}/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages"

    async with httpx.AsyncClient() as client:
        files = {
            "attachments[]": (filename, file_data, content_type)
        }
        response = await client.post(
            url,
            headers=_get_headers_multipart(),
            files=files
        )
        response.raise_for_status()
        return response.json()


# --- Reacoes e Status ---

async def chatwoot_react_to_message(
    account_id: str,
    conversation_id: str,
    message_id: str,
    emoji: str
) -> dict:
    """
    Reage a uma mensagem com um emoji

    Args:
        account_id: ID da conta no Chatwoot
        conversation_id: ID da conversa
        message_id: ID da mensagem
        emoji: Emoji para reagir

    Returns:
        Resposta da API do Chatwoot
    """
    url = f"{_get_base_url()}/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            headers=_get_headers(),
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


async def chatwoot_mark_as_read(account_id: str, conversation_id: str) -> None:
    """
    Marca as mensagens como lidas

    Args:
        account_id: ID da conta no Chatwoot
        conversation_id: ID da conversa
    """
    url = f"{_get_base_url()}/api/v1/accounts/{account_id}/conversations/{conversation_id}/update_last_seen"

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=_get_headers())
        response.raise_for_status()


async def chatwoot_set_typing_status(
    account_id: str,
    conversation_id: str,
    status: str = "on"
) -> None:
    """
    Define o status de digitacao

    Args:
        account_id: ID da conta no Chatwoot
        conversation_id: ID da conversa
        status: Status (on, off, recording)
    """
    url = f"{_get_base_url()}/api/v1/accounts/{account_id}/conversations/{conversation_id}/toggle_typing_status"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            headers=_get_headers(),
            json={"typing_status": status}
        )
        response.raise_for_status()


# --- Labels (Etiquetas) ---

async def chatwoot_get_labels(account_id: str, conversation_id: str) -> list:
    """
    Obtem as etiquetas de uma conversa

    Args:
        account_id: ID da conta no Chatwoot
        conversation_id: ID da conversa

    Returns:
        Lista de etiquetas
    """
    url = f"{_get_base_url()}/api/v1/accounts/{account_id}/conversations/{conversation_id}/labels"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=_get_headers())
        response.raise_for_status()
        return response.json().get("payload", [])


async def chatwoot_add_label(
    account_id: str,
    conversation_id: str,
    labels: list
) -> dict:
    """
    Adiciona etiquetas a uma conversa

    Args:
        account_id: ID da conta no Chatwoot
        conversation_id: ID da conversa
        labels: Lista de etiquetas para adicionar

    Returns:
        Resposta da API do Chatwoot
    """
    url = f"{_get_base_url()}/api/v1/accounts/{account_id}/conversations/{conversation_id}/labels"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            headers=_get_headers(),
            json={"labels": labels}
        )
        response.raise_for_status()
        return response.json()


# --- Download ---

async def chatwoot_download_attachment(attachment_url: str) -> bytes:
    """
    Baixa um anexo (audio, imagem, etc.)

    Args:
        attachment_url: URL do anexo

    Returns:
        Dados do anexo em bytes

    Raises:
        ValueError: Se a URL nao for segura (prevencao SSRF)
    """
    # Validacao de seguranca contra SSRF
    if not _is_safe_attachment_url(attachment_url):
        raise ValueError(f"URL de anexo nao permitida: {attachment_url}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            attachment_url,
            headers=_get_headers_multipart()
        )
        response.raise_for_status()
        return response.content


# --- Compatibilidade (para transicao gradual) ---

class ChatwootService:
    """Classe de compatibilidade - usar funcoes diretamente"""

    def __init__(self):
        self.base_url = _get_base_url()
        self.api_token = Config.CHATWOOT_API_TOKEN
        self.headers = _get_headers()

    async def send_message(self, account_id: str, conversation_id: str, content: str) -> dict:
        return await chatwoot_send_message(account_id, conversation_id, content)

    async def send_audio(self, account_id: str, conversation_id: str, audio_data: bytes, filename: str = "audio.mp3") -> dict:
        return await chatwoot_send_audio(account_id, conversation_id, audio_data, filename)

    async def send_file(self, account_id: str, conversation_id: str, file_data: bytes, filename: str, content_type: str = "application/octet-stream") -> dict:
        return await chatwoot_send_file(account_id, conversation_id, file_data, filename, content_type)

    async def react_to_message(self, account_id: str, conversation_id: str, message_id: str, emoji: str) -> dict:
        return await chatwoot_react_to_message(account_id, conversation_id, message_id, emoji)

    async def mark_as_read(self, account_id: str, conversation_id: str) -> None:
        return await chatwoot_mark_as_read(account_id, conversation_id)

    async def set_typing_status(self, account_id: str, conversation_id: str, status: str = "on") -> None:
        return await chatwoot_set_typing_status(account_id, conversation_id, status)

    async def get_labels(self, account_id: str, conversation_id: str) -> list:
        return await chatwoot_get_labels(account_id, conversation_id)

    async def add_label(self, account_id: str, conversation_id: str, labels: list) -> dict:
        return await chatwoot_add_label(account_id, conversation_id, labels)

    async def download_attachment(self, attachment_url: str) -> bytes:
        return await chatwoot_download_attachment(attachment_url)


# Instancia global para compatibilidade
chatwoot_service = ChatwootService()
