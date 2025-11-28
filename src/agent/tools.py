"""
Ferramentas do Agente Secretária IA
"""
import asyncio
from typing import Optional, Annotated
from langchain_core.tools import tool
from datetime import datetime

from src.services.google_calendar import get_calendar_service
from src.services.google_drive import get_drive_service
from src.services.chatwoot import chatwoot_service
from src.services.telegram import telegram_service
from src.services.rag import get_rag_service
from src.services.database import get_db_service


# Variáveis de contexto (serão definidas pelo agente)
_context = {
    "account_id": None,
    "conversation_id": None,
    "message_id": None,
    "phone": None,
    "telegram_chat_id": None,
    "db_pool": None  # Pool de conexões do banco
}


def set_context(
    account_id: str,
    conversation_id: str,
    message_id: str,
    phone: str,
    telegram_chat_id: str,
    db_pool=None
):
    """Define o contexto para as ferramentas"""
    _context["account_id"] = account_id
    _context["conversation_id"] = conversation_id
    _context["message_id"] = message_id
    _context["phone"] = phone
    _context["telegram_chat_id"] = telegram_chat_id
    _context["db_pool"] = db_pool


def _run_async(coro):
    """Executa uma coroutine de forma síncrona"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Cria uma task e aguarda o resultado
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)


# --- Ferramentas do Google Calendar ---

@tool
def criar_evento(
    calendar_id: Annotated[str, "ID do calendário Google (incluindo @group.calendar.google.com)"],
    summary: Annotated[str, "Título do evento (nome do paciente)"],
    start: Annotated[str, "Data/hora de início no formato ISO 8601 (ex: 2025-01-15T10:00:00)"],
    end: Annotated[str, "Data/hora de término no formato ISO 8601 (ex: 2025-01-15T10:30:00)"],
    description: Annotated[str, "Descrição com telefone, data nascimento e informações adicionais"]
) -> str:
    """
    Cria um evento/consulta no Google Calendar.
    Use para agendar novas consultas.
    Sempre inclua na descrição: telefone, nome completo, data de nascimento e ID da conversa.
    """
    try:
        service = get_calendar_service()
        result = service.create_event(
            calendar_id=calendar_id,
            summary=summary,
            start=start,
            end=end,
            description=description
        )
        return f"Evento criado com sucesso! ID: {result['id']}"
    except Exception as e:
        return f"Erro ao criar evento: {str(e)}"


@tool
def buscar_evento(
    calendar_id: Annotated[str, "ID do calendário Google"],
    event_id: Annotated[str, "ID do evento a buscar"]
) -> str:
    """
    Busca um evento específico pelo ID.
    Use quando precisar dos detalhes de um evento já agendado.
    """
    try:
        service = get_calendar_service()
        event = service.get_event(calendar_id, event_id)
        return (
            f"Evento encontrado:\n"
            f"Título: {event.get('summary', 'Sem título')}\n"
            f"Início: {event['start'].get('dateTime', event['start'].get('date'))}\n"
            f"Fim: {event['end'].get('dateTime', event['end'].get('date'))}\n"
            f"Descrição: {event.get('description', 'Sem descrição')}"
        )
    except Exception as e:
        return f"Erro ao buscar evento: {str(e)}"


@tool
def buscar_todos_os_eventos(
    calendar_id: Annotated[str, "ID do calendário Google"],
    after: Annotated[str, "Data/hora mínima no formato ISO 8601 (ex: 2025-01-15T00:00:00)"],
    before: Annotated[str, "Data/hora máxima no formato ISO 8601 (ex: 2025-01-15T23:59:59)"]
) -> str:
    """
    Lista todos os eventos em um período específico.
    Use para verificar disponibilidade de horários em uma data.
    As datas devem ser no formato completo ISO 8601.
    """
    try:
        service = get_calendar_service()

        # Adiciona timezone se não tiver
        if not after.endswith("Z") and "+" not in after and "-" not in after[-6:]:
            after = f"{after}-03:00"
        if not before.endswith("Z") and "+" not in before and "-" not in before[-6:]:
            before = f"{before}-03:00"

        events = service.list_events(calendar_id, after, before)

        if not events:
            return "Nenhum evento encontrado no período especificado. Todos os horários estão disponíveis."

        result = "Eventos encontrados:\n\n"
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            result += (
                f"- {event.get('summary', 'Sem título')}\n"
                f"  Início: {start}\n"
                f"  ID: {event['id']}\n\n"
            )
        return result
    except Exception as e:
        return f"Erro ao buscar eventos: {str(e)}"


@tool
def atualizar_evento(
    calendar_id: Annotated[str, "ID do calendário Google"],
    event_id: Annotated[str, "ID do evento a atualizar"],
    summary: Annotated[Optional[str], "Novo título (opcional)"] = None,
    start: Annotated[Optional[str], "Nova data/hora de início (opcional)"] = None,
    end: Annotated[Optional[str], "Nova data/hora de término (opcional)"] = None,
    description: Annotated[Optional[str], "Nova descrição (opcional)"] = None
) -> str:
    """
    Atualiza um evento existente.
    Use para remarcar consultas ou adicionar [CONFIRMADO] ao título.
    Passe apenas os campos que deseja atualizar.
    """
    try:
        service = get_calendar_service()

        # Adiciona timezone se necessário
        if start and not start.endswith("Z") and "+" not in start and "-" not in start[-6:]:
            start = f"{start}-03:00"
        if end and not end.endswith("Z") and "+" not in end and "-" not in end[-6:]:
            end = f"{end}-03:00"

        result = service.update_event(
            calendar_id=calendar_id,
            event_id=event_id,
            summary=summary,
            start=start,
            end=end,
            description=description
        )
        return f"Evento atualizado com sucesso! ID: {result['id']}"
    except Exception as e:
        return f"Erro ao atualizar evento: {str(e)}"


@tool
def deletar_evento(
    calendar_id: Annotated[str, "ID do calendário Google"],
    event_id: Annotated[str, "ID do evento a deletar"]
) -> str:
    """
    Deleta/cancela um evento.
    Use para cancelar consultas.
    """
    try:
        service = get_calendar_service()
        service.delete_event(calendar_id, event_id)
        return "Evento deletado com sucesso!"
    except Exception as e:
        return f"Erro ao deletar evento: {str(e)}"


# --- Ferramentas do Google Drive ---

@tool
def listar_arquivos() -> str:
    """
    Lista os arquivos disponíveis na pasta do Google Drive.
    Use para ver quais arquivos podem ser enviados ao paciente.
    """
    try:
        service = get_drive_service()
        files = service.list_files()

        if not files:
            return "Nenhum arquivo encontrado na pasta."

        result = "Arquivos disponíveis:\n\n"
        for file in files:
            result += f"- {file['name']}\n  ID: {file['id']}\n  Tipo: {file['mimeType']}\n\n"
        return result
    except Exception as e:
        return f"Erro ao listar arquivos: {str(e)}"


@tool
def baixar_e_enviar_arquivo(
    file_id: Annotated[str, "ID do arquivo no Google Drive"]
) -> str:
    """
    Baixa um arquivo do Google Drive e envia para o paciente.
    Use quando o paciente solicitar um documento, como pedido de exame.
    IMPORTANTE: Use apenas UMA VEZ para evitar envio duplicado.
    """
    async def _execute():
        drive_service = get_drive_service()
        file_data, filename, mime_type = drive_service.download_file(file_id)

        await chatwoot_service.send_file(
            account_id=_context["account_id"],
            conversation_id=_context["conversation_id"],
            file_data=file_data,
            filename=filename,
            content_type=mime_type
        )
        return filename

    try:
        filename = _run_async(_execute())
        return f"Arquivo '{filename}' enviado com sucesso!"
    except Exception as e:
        return f"Erro ao enviar arquivo: {str(e)}"


# --- Ferramentas de Comunicação ---

@tool
def reagir_mensagem(
    emoji: Annotated[str, "Emoji para reagir (ex: 😀, 👀, ❤️)"]
) -> str:
    """
    Reage à mensagem do usuário com um emoji.
    Use em momentos relevantes da conversa:
    - Início: 😀
    - Quando vai buscar algo: 👀
    - Agradecimentos: ❤️
    """
    async def _execute():
        await chatwoot_service.react_to_message(
            account_id=_context["account_id"],
            conversation_id=_context["conversation_id"],
            message_id=_context["message_id"],
            emoji=emoji
        )

    try:
        _run_async(_execute())
        return "Reação enviada!"
    except Exception as e:
        return f"Erro ao reagir: {str(e)}"


@tool
def escalar_humano(
    nome: Annotated[str, "Nome do paciente (se disponível)"] = ""
) -> str:
    """
    Direciona o atendimento para um humano.
    Use quando:
    - Houver urgência médica
    - Assuntos fora do escopo da clínica
    - Paciente insatisfeito
    - Pedido de atendimento humano
    """
    async def _execute():
        # Adiciona etiqueta agente-off
        labels = await chatwoot_service.get_labels(
            _context["account_id"],
            _context["conversation_id"]
        )
        labels.append("agente-off")
        await chatwoot_service.add_label(
            _context["account_id"],
            _context["conversation_id"],
            list(set(labels))
        )

        # Envia alerta no Telegram
        await telegram_service.send_escalation_alert(
            patient_name=nome,
            patient_phone=_context["phone"],
            last_message="",
            chat_id=_context["telegram_chat_id"]
        )

    try:
        _run_async(_execute())
        return "Atendimento escalado para humano. A etiqueta 'agente-off' foi adicionada."
    except Exception as e:
        return f"Erro ao escalar: {str(e)}"


@tool
def enviar_alerta_de_cancelamento(
    texto: Annotated[str, "Informações sobre o cancelamento (nome, data, hora)"]
) -> str:
    """
    Envia alerta de cancelamento de consulta via Telegram.
    Use após cancelar um evento no calendário.
    """
    async def _execute():
        await telegram_service.send_message(
            text=texto,
            chat_id=_context["telegram_chat_id"],
            parse_mode=None
        )

    try:
        _run_async(_execute())
        return "Alerta de cancelamento enviado!"
    except Exception as e:
        return f"Erro ao enviar alerta: {str(e)}"


@tool
def refletir(
    pensamento: Annotated[str, "Reflexão sobre a situação atual ou próximos passos"]
) -> str:
    """
    Ferramenta para refletir sobre algo.
    Não obtém novas informações nem altera dados.
    Use para raciocínio complexo ou memória em cache.
    """
    return f"Reflexão registrada: {pensamento}"


# --- Ferramentas de RAG (Base de Conhecimento) ---

@tool
def buscar_informacao_empresa(
    pergunta: Annotated[str, "Pergunta ou termo de busca sobre a empresa/clínica"],
    categoria: Annotated[Optional[str], "Categoria específica (opcional): servicos, horarios, precos, equipe, localizacao, convenios, procedimentos"] = None
) -> str:
    """
    Busca informações sobre a empresa/clínica na base de conhecimento.
    Use SEMPRE que o paciente perguntar sobre:
    - Serviços oferecidos
    - Preços e valores
    - Horários de funcionamento
    - Localização e endereço
    - Equipe e profissionais
    - Convênios aceitos
    - Procedimentos e exames
    - Dúvidas gerais sobre a clínica

    Esta ferramenta busca na base de dados interna da empresa.
    """
    try:
        # Importa o serviço RAG
        from src.services.rag import rag_service

        # Usa o método síncrono que não depende do asyncio
        # Threshold baixo (0.3) para capturar variações na forma de perguntar
        results = rag_service.search_sync(
            query=pergunta,
            limit=3,
            categoria=categoria,
            similarity_threshold=0.3
        )

        if not results:
            return "Não encontrei informações específicas sobre isso na base de conhecimento. Sugiro escalar para um atendente humano se a dúvida persistir."

        response = "Informações encontradas:\n\n"
        for doc in results:
            response += f"**{doc['titulo']}** (categoria: {doc['categoria']})\n"
            response += f"{doc['conteudo']}\n\n"

        return response
    except Exception as e:
        return f"Erro ao buscar informações: {str(e)}"


# Importa ferramentas de agenda do banco de dados
from src.agent.tools_agenda import AGENDA_TOOLS

# Lista de todas as ferramentas (sem Google Calendar, usando agenda do banco)
ALL_TOOLS = [
    # Ferramentas de agenda (banco de dados local)
    *AGENDA_TOOLS,
    # Ferramentas de arquivos
    listar_arquivos,
    baixar_e_enviar_arquivo,
    # Ferramentas de comunicacao
    reagir_mensagem,
    escalar_humano,
    enviar_alerta_de_cancelamento,
    # Ferramentas auxiliares
    refletir,
    buscar_informacao_empresa
]

# Ferramentas antigas do Google Calendar (mantidas para compatibilidade)
GOOGLE_CALENDAR_TOOLS = [
    criar_evento,
    buscar_evento,
    buscar_todos_os_eventos,
    atualizar_evento,
    deletar_evento
]
