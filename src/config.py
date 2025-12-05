"""
Configurações do sistema - Secretária IA para Clínica Médica
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Chatwoot
    CHATWOOT_URL = os.getenv("CHATWOOT_URL", "https://chatwoot.qmarka.com")
    CHATWOOT_API_TOKEN = os.getenv("CHATWOOT_API_TOKEN")

    # Google Calendar
    GOOGLE_CALENDAR_CREDENTIALS_FILE = os.getenv("GOOGLE_CALENDAR_CREDENTIALS_FILE", "credentials.json")
    GOOGLE_CALENDAR_TOKEN_FILE = os.getenv("GOOGLE_CALENDAR_TOKEN_FILE", "token.json")

    # Google Drive
    GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "1HpHWnaeglYnzDbqKwBu2NGjefVT1ihVL")

    # PostgreSQL/Supabase
    DATABASE_URL = os.getenv("DATABASE_URL")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_USER = os.getenv("POSTGRES_USER")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
    POSTGRES_DB = os.getenv("POSTGRES_DB")

    # OpenAI
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    # OpenRouter
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")

    # Google Gemini (direto)
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

    # ElevenLabs
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
    ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "33B4UnXyTNbgLmdEDh5P")

    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

    # Servidor
    SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
    SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))

    # Tempo de espera para mensagens encavaladas (segundos)
    MESSAGE_QUEUE_WAIT_TIME = int(os.getenv("MESSAGE_QUEUE_WAIT_TIME", "3"))

    # Histórico de mensagens
    CONTEXT_WINDOW_LENGTH = int(os.getenv("CONTEXT_WINDOW_LENGTH", "50"))

    # Admin Authentication
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")  # MUDAR EM PRODUÇÃO!

    # Webhook Security
    CHATWOOT_WEBHOOK_SECRET = os.getenv("CHATWOOT_WEBHOOK_SECRET", "")


# Informações da empresa
EMPRESA_INFO = {
    "name": "Clínica Moreira",
    "address": "Av. das Palmeiras, 1500 - Jardim América, São Paulo - SP, CEP: 04567-000",
    "phone": "(11) 4456-7890",
    "whatsapp": "(11) 99999-9999",
    "email": "contato@clinicamoreira.com.br",
    "website": "www.clinicamoreira.com.br",
    "hours": {
        "weekdays": "08h às 19h",
        "saturday": "08h às 19h",
        "sunday": "Fechado",
        "holidays": "Fechado"
    },
    "consultation_price": "R$ 500,00",
    "payment_methods": ["PIX", "dinheiro", "cartão de débito", "cartão de crédito"],
    "insurance": ["Bradesco Saúde", "Unimed", "SulAmérica", "Amil"]
}

# Profissionais e suas agendas
PROFESSIONALS = [
    {
        "name": "Dr. João Paulo Ferreira",
        "role": "Médico",
        "specialty": "Clínico Geral",
        "calendar_id": "4b337bce41cf3172e7ef138556ecf0b596d666a3c2ab4982e43cc3156c86c5a6@group.calendar.google.com"
    },
    {
        "name": "Dr. Roberto Almeida",
        "role": "Médico",
        "specialty": "Cardiologia",
        "calendar_id": "4b337bce41cf3172e7ef138556ecf0b596d666a3c2ab4982e43cc3156c86c5a6@group.calendar.google.com"
    },
    {
        "name": "Dra. Ana Silva",
        "role": "Dentista",
        "specialty": "Clínica Geral",
        "calendar_id": "4b337bce41cf3172e7ef138556ecf0b596d666a3c2ab4982e43cc3156c86c5a6@group.calendar.google.com"
    },
    {
        "name": "Dra. Carla Mendes",
        "role": "Dentista",
        "specialty": "Odontopediatria",
        "calendar_id": "4b337bce41cf3172e7ef138556ecf0b596d666a3c2ab4982e43cc3156c86c5a6@group.calendar.google.com"
    }
]
