"""
Serviço de integração com Google Drive
"""
import os
import io
from typing import Optional
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import pickle

from src.config import Config

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly"
]


class GoogleDriveService:
    """Serviço para interação com a API do Google Drive"""

    def __init__(self):
        self.service = None
        self._authenticate()

    def _authenticate(self):
        """Autentica com o Google Drive"""
        creds = None

        # Verifica se existe token salvo (pode compartilhar com Calendar)
        token_file = Config.GOOGLE_CALENDAR_TOKEN_FILE
        if os.path.exists(token_file):
            with open(token_file, "rb") as token:
                creds = pickle.load(token)

        # Se não há credenciais válidas, solicita login
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                credentials_file = Config.GOOGLE_CALENDAR_CREDENTIALS_FILE
                if not os.path.exists(credentials_file):
                    raise FileNotFoundError(
                        f"Arquivo de credenciais não encontrado: {credentials_file}. "
                        "Baixe o arquivo credentials.json do Google Cloud Console."
                    )

                # Combina escopos do Calendar e Drive
                all_scopes = SCOPES + ["https://www.googleapis.com/auth/calendar"]

                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_file, all_scopes
                )
                creds = flow.run_local_server(port=0)

            # Salva as credenciais
            with open(token_file, "wb") as token:
                pickle.dump(creds, token)

        self.service = build("drive", "v3", credentials=creds)

    def list_files(
        self,
        folder_id: Optional[str] = None,
        query: Optional[str] = None
    ) -> list:
        """
        Lista arquivos em uma pasta do Google Drive

        Args:
            folder_id: ID da pasta (opcional, usa padrão se não fornecido)
            query: Query adicional para filtrar arquivos

        Returns:
            Lista de arquivos com id, name, mimeType
        """
        if folder_id is None:
            folder_id = Config.GOOGLE_DRIVE_FOLDER_ID

        q = f"'{folder_id}' in parents and trashed = false"
        if query:
            q += f" and {query}"

        results = self.service.files().list(
            q=q,
            fields="files(id, name, mimeType, size, createdTime, modifiedTime)",
            orderBy="name"
        ).execute()

        return results.get("files", [])

    def get_file_metadata(self, file_id: str) -> dict:
        """
        Obtém metadados de um arquivo

        Args:
            file_id: ID do arquivo

        Returns:
            Metadados do arquivo
        """
        return self.service.files().get(
            fileId=file_id,
            fields="id, name, mimeType, size, createdTime, modifiedTime"
        ).execute()

    def download_file(self, file_id: str) -> tuple[bytes, str, str]:
        """
        Baixa um arquivo do Google Drive

        Args:
            file_id: ID do arquivo

        Returns:
            Tupla com (conteúdo em bytes, nome do arquivo, tipo MIME)
        """
        # Obtém metadados
        metadata = self.get_file_metadata(file_id)
        filename = metadata["name"]
        mime_type = metadata["mimeType"]

        # Baixa o arquivo
        request = self.service.files().get_media(fileId=file_id)
        file_buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(file_buffer, request)

        done = False
        while not done:
            status, done = downloader.next_chunk()

        file_buffer.seek(0)
        return file_buffer.read(), filename, mime_type

    def search_files(
        self,
        name_contains: str,
        folder_id: Optional[str] = None
    ) -> list:
        """
        Busca arquivos pelo nome

        Args:
            name_contains: Texto que o nome deve conter
            folder_id: ID da pasta para limitar a busca

        Returns:
            Lista de arquivos encontrados
        """
        if folder_id is None:
            folder_id = Config.GOOGLE_DRIVE_FOLDER_ID

        q = f"'{folder_id}' in parents and name contains '{name_contains}' and trashed = false"

        results = self.service.files().list(
            q=q,
            fields="files(id, name, mimeType, size)",
            orderBy="name"
        ).execute()

        return results.get("files", [])


# Instância global do serviço (será inicializada sob demanda)
_drive_service = None


def get_drive_service() -> GoogleDriveService:
    """Retorna a instância do serviço de Drive"""
    global _drive_service
    if _drive_service is None:
        _drive_service = GoogleDriveService()
    return _drive_service
