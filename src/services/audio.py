"""
Servico de processamento de audio
Transcricao (Whisper) e Sintese (ElevenLabs)

Paradigma: Funcional
"""
import re
from io import BytesIO

import httpx
import openai

from src.config import Config


# --- Transcricao (Speech-to-Text) ---

async def transcribe_audio(audio_data: bytes, language: str = "pt") -> str:
    """
    Transcreve audio para texto usando OpenAI Whisper

    Args:
        audio_data: Dados do audio em bytes
        language: Codigo do idioma

    Returns:
        Texto transcrito
    """
    client = openai.AsyncOpenAI(api_key=Config.OPENAI_API_KEY)

    # Cria um objeto de arquivo em memoria
    audio_file = BytesIO(audio_data)
    audio_file.name = "audio.ogg"

    response = await client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        language=language
    )

    return response.text


# --- Sintese (Text-to-Speech) ---

async def text_to_speech(
    text: str,
    voice_id: str = None,
    model_id: str = "eleven_flash_v2_5"
) -> bytes:
    """
    Converte texto para audio usando ElevenLabs

    Args:
        text: Texto para converter
        voice_id: ID da voz (usa padrao se nao fornecido)
        model_id: ID do modelo de voz

    Returns:
        Dados do audio em bytes (MP3)
    """
    if voice_id is None:
        voice_id = Config.ELEVENLABS_VOICE_ID

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    headers = {
        "xi-api-key": Config.ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }

    params = {
        "output_format": "mp3_44100_32"
    }

    body = {
        "text": text,
        "model_id": model_id
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            url,
            headers=headers,
            params=params,
            json=body
        )
        response.raise_for_status()
        return response.content


# --- Formatacao ---

def format_text_for_tts(text: str) -> str:
    """
    Formata texto para melhor qualidade de TTS

    Converte datas, horas, telefones e enderecos para formato falado

    Args:
        text: Texto original

    Returns:
        Texto formatado para TTS
    """
    result = text

    # Remove emojis
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE
    )
    result = emoji_pattern.sub("", result)

    # Formata horarios (10:00 -> dez horas)
    def format_time(match):
        hour = int(match.group(1))
        minute = int(match.group(2))

        hours_text = {
            1: "uma", 2: "duas", 3: "tres", 4: "quatro", 5: "cinco",
            6: "seis", 7: "sete", 8: "oito", 9: "nove", 10: "dez",
            11: "onze", 12: "doze", 13: "treze", 14: "quatorze",
            15: "quinze", 16: "dezesseis", 17: "dezessete", 18: "dezoito",
            19: "dezenove", 20: "vinte", 21: "vinte e uma",
            22: "vinte e duas", 23: "vinte e tres", 0: "zero"
        }

        if minute == 0:
            return f"{hours_text.get(hour, str(hour))} horas"
        elif minute == 30:
            return f"{hours_text.get(hour, str(hour))} e meia"
        else:
            return f"{hours_text.get(hour, str(hour))} e {minute}"

    result = re.sub(r"(\d{1,2}):(\d{2})", format_time, result)

    # Formata abreviacoes de endereco
    abbreviations = {
        r"\bAv\.": "Avenida",
        r"\bR\.": "Rua",
        r"\bDr\.": "Doutor",
        r"\bDra\.": "Doutora",
        r"\bProf\.": "Professor",
        r"\bProfa\.": "Professora",
    }

    for abbr, full in abbreviations.items():
        result = re.sub(abbr, full, result)

    # Adiciona pausa no inicio
    result = f"<speak><break time='1.0s'/>{result}</speak>"

    return result


# --- Compatibilidade (para transicao gradual) ---
# Mantém a classe para não quebrar imports existentes

class AudioService:
    """Classe de compatibilidade - usar funcoes diretamente"""

    async def transcribe_audio(self, audio_data: bytes, language: str = "pt") -> str:
        return await transcribe_audio(audio_data, language)

    async def text_to_speech(self, text: str, voice_id: str = None, model_id: str = "eleven_flash_v2_5") -> bytes:
        return await text_to_speech(text, voice_id, model_id)

    def format_text_for_tts(self, text: str) -> str:
        return format_text_for_tts(text)


# Instancia global para compatibilidade
audio_service = AudioService()
