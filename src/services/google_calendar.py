"""
Serviço de integração com Google Calendar
"""
import os
from datetime import datetime
from typing import Optional
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle

from src.config import Config

SCOPES = ["https://www.googleapis.com/auth/calendar"]


class GoogleCalendarService:
    """Serviço para interação com a API do Google Calendar"""

    def __init__(self):
        self.service = None
        self._authenticate()

    def _authenticate(self):
        """Autentica com o Google Calendar"""
        creds = None

        # Verifica se existe token salvo
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
                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_file, SCOPES
                )
                creds = flow.run_local_server(port=0)

            # Salva as credenciais
            with open(token_file, "wb") as token:
                pickle.dump(creds, token)

        self.service = build("calendar", "v3", credentials=creds)

    def create_event(
        self,
        calendar_id: str,
        summary: str,
        start: str,
        end: str,
        description: Optional[str] = None
    ) -> dict:
        """
        Cria um evento no calendário

        Args:
            calendar_id: ID do calendário
            summary: Título do evento
            start: Data/hora de início (ISO 8601)
            end: Data/hora de término (ISO 8601)
            description: Descrição do evento

        Returns:
            Dados do evento criado
        """
        event = {
            "summary": summary,
            "start": {
                "dateTime": start,
                "timeZone": "America/Sao_Paulo"
            },
            "end": {
                "dateTime": end,
                "timeZone": "America/Sao_Paulo"
            }
        }

        if description:
            event["description"] = description

        result = self.service.events().insert(
            calendarId=calendar_id,
            body=event
        ).execute()

        return result

    def get_event(self, calendar_id: str, event_id: str) -> dict:
        """
        Busca um evento específico

        Args:
            calendar_id: ID do calendário
            event_id: ID do evento

        Returns:
            Dados do evento
        """
        return self.service.events().get(
            calendarId=calendar_id,
            eventId=event_id
        ).execute()

    def list_events(
        self,
        calendar_id: str,
        time_min: str,
        time_max: str
    ) -> list:
        """
        Lista eventos em um período específico

        Args:
            calendar_id: ID do calendário
            time_min: Data/hora mínima (ISO 8601)
            time_max: Data/hora máxima (ISO 8601)

        Returns:
            Lista de eventos
        """
        events_result = self.service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        return events_result.get("items", [])

    def update_event(
        self,
        calendar_id: str,
        event_id: str,
        summary: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        description: Optional[str] = None
    ) -> dict:
        """
        Atualiza um evento existente

        Args:
            calendar_id: ID do calendário
            event_id: ID do evento
            summary: Novo título (opcional)
            start: Nova data/hora de início (opcional)
            end: Nova data/hora de término (opcional)
            description: Nova descrição (opcional)

        Returns:
            Dados do evento atualizado
        """
        # Busca o evento atual
        event = self.get_event(calendar_id, event_id)

        # Atualiza apenas os campos fornecidos
        if summary:
            event["summary"] = summary
        if start:
            event["start"] = {
                "dateTime": start,
                "timeZone": "America/Sao_Paulo"
            }
        if end:
            event["end"] = {
                "dateTime": end,
                "timeZone": "America/Sao_Paulo"
            }
        if description:
            event["description"] = description

        return self.service.events().update(
            calendarId=calendar_id,
            eventId=event_id,
            body=event
        ).execute()

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        """
        Deleta um evento

        Args:
            calendar_id: ID do calendário
            event_id: ID do evento
        """
        self.service.events().delete(
            calendarId=calendar_id,
            eventId=event_id
        ).execute()

    def get_free_slots(
        self,
        calendar_id: str,
        date: str,
        slot_duration_minutes: int = 30,
        work_start_hour: int = 8,
        work_end_hour: int = 19
    ) -> list:
        """
        Retorna os horários disponíveis em uma data

        Args:
            calendar_id: ID do calendário
            date: Data no formato YYYY-MM-DD
            slot_duration_minutes: Duração de cada slot em minutos
            work_start_hour: Hora de início do expediente
            work_end_hour: Hora de fim do expediente

        Returns:
            Lista de horários disponíveis
        """
        from datetime import timedelta

        # Define o período do dia
        time_min = f"{date}T{work_start_hour:02d}:00:00-03:00"
        time_max = f"{date}T{work_end_hour:02d}:00:00-03:00"

        # Busca eventos existentes
        events = self.list_events(calendar_id, time_min, time_max)

        # Cria lista de todos os slots possíveis
        all_slots = []
        current = datetime.fromisoformat(time_min)
        end = datetime.fromisoformat(time_max)

        while current < end:
            all_slots.append(current.isoformat())
            current += timedelta(minutes=slot_duration_minutes)

        # Remove slots ocupados
        busy_slots = set()
        for event in events:
            event_start = datetime.fromisoformat(
                event["start"].get("dateTime", event["start"].get("date"))
            )
            event_end = datetime.fromisoformat(
                event["end"].get("dateTime", event["end"].get("date"))
            )

            # Marca todos os slots que se sobrepõem ao evento
            for slot in all_slots:
                slot_time = datetime.fromisoformat(slot)
                slot_end = slot_time + timedelta(minutes=slot_duration_minutes)

                if slot_time < event_end and slot_end > event_start:
                    busy_slots.add(slot)

        # Retorna apenas os slots livres
        free_slots = [slot for slot in all_slots if slot not in busy_slots]
        return free_slots


# Instância global do serviço (será inicializada sob demanda)
_calendar_service = None


def get_calendar_service() -> GoogleCalendarService:
    """Retorna a instância do serviço de calendário"""
    global _calendar_service
    if _calendar_service is None:
        _calendar_service = GoogleCalendarService()
    return _calendar_service
