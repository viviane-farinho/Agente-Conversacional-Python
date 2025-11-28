"""
Módulo de serviços
"""
from src.services.chatwoot import chatwoot_service, ChatwootService
from src.services.database import db_service, get_db_service, DatabaseService
from src.services.google_calendar import get_calendar_service, GoogleCalendarService
from src.services.google_drive import get_drive_service, GoogleDriveService
from src.services.telegram import telegram_service, TelegramService
from src.services.audio import audio_service, AudioService

__all__ = [
    "chatwoot_service",
    "ChatwootService",
    "db_service",
    "get_db_service",
    "DatabaseService",
    "get_calendar_service",
    "GoogleCalendarService",
    "get_drive_service",
    "GoogleDriveService",
    "telegram_service",
    "TelegramService",
    "audio_service",
    "AudioService"
]
