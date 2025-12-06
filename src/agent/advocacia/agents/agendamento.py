"""
Agente de Agendamento para Advocacia

Este agente é responsável por:
1. Coletar dados do cliente para agendamento
2. Informar horários disponíveis
3. Confirmar agendamento de consulta

Fluxo:
1. Recebe mensagem do supervisor (quando cliente quer agendar)
2. Coleta: nome, telefone, email, área de interesse
3. Confirma horário e data
4. Finaliza agendamento
"""

from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from src.config import Config
from src.agent.advocacia.tools import get_agendamento_tools
from src.services.rag_advocacia import rag_advocacia_get_prompt_sync


# Prompt padrão caso não tenha prompt configurado no banco
DEFAULT_AGENDAMENTO_PROMPT = """Você é o assistente de agendamento do escritório de advocacia.

OBJETIVO:
Ajudar o cliente a agendar uma consulta jurídica.

DADOS NECESSÁRIOS:
1. Nome completo
2. Telefone para contato
3. Email (opcional)
4. Área de interesse (se souber)
5. Breve descrição do caso

HORÁRIOS DISPONÍVEIS:
- Segunda a Sexta: 9h às 18h
- Sábado: 9h às 12h

PROCESSO:
1. Pergunte qual área de interesse (se não souber, está ok)
2. Colete os dados necessários um por um
3. Sugira horários disponíveis
4. Confirme o agendamento

REGRAS:
- Seja cordial e eficiente
- Não faça muitas perguntas de uma vez
- Confirme os dados antes de finalizar
- Informe que a equipe entrará em contato para confirmar

Responda de forma profissional e acolhedora."""


def _build_agendamento_prompt() -> str:
    """
    Constrói o prompt do agente de agendamento.
    """
    # Tenta carregar prompt do banco
    prompt_banco = rag_advocacia_get_prompt_sync("agendamento")

    return prompt_banco if prompt_banco else DEFAULT_AGENDAMENTO_PROMPT


async def create_agendamento_agent():
    """
    Cria o agente de agendamento.

    Returns:
        Agente LangGraph configurado
    """
    # Monta prompt
    system_prompt = _build_agendamento_prompt()

    # Cria LLM
    llm = ChatOpenAI(
        model=Config.OPENAI_MODEL,
        temperature=0.7,
        api_key=Config.OPENAI_API_KEY
    )

    # Ferramentas de agendamento (por enquanto vazio)
    tools = get_agendamento_tools()

    # Cria agente
    agent = create_react_agent(
        model=llm,
        tools=tools,
        state_modifier=system_prompt
    )

    return agent


def create_agendamento_agent_sync():
    """
    Versão síncrona do create_agendamento_agent.
    """
    system_prompt = _build_agendamento_prompt()

    llm = ChatOpenAI(
        model=Config.OPENAI_MODEL,
        temperature=0.7,
        api_key=Config.OPENAI_API_KEY
    )

    tools = get_agendamento_tools()

    agent = create_react_agent(
        model=llm,
        tools=tools,
        state_modifier=system_prompt
    )

    return agent


# ============================================================================
# Funções auxiliares para o grafo
# ============================================================================

async def agendamento_node(state: dict) -> dict:
    """
    Nó do agente de agendamento para o grafo LangGraph.

    Args:
        state: Estado do grafo com mensagens

    Returns:
        Estado atualizado com resposta do agente
    """
    messages = state.get("messages", [])

    # Cria agente
    agent = await create_agendamento_agent()

    # Executa agente
    result = await agent.ainvoke({"messages": messages})

    # Atualiza estado
    state["messages"] = result["messages"]
    state["last_agent"] = "agendamento"

    return state


def get_agendamento_info() -> dict:
    """
    Retorna informações sobre o agente de agendamento.

    Returns:
        Dict com info do agente
    """
    return {
        "agente": "agendamento",
        "descricao": "Agente de agendamento de consultas jurídicas"
    }


# ============================================================================
# Funções para extrair dados do agendamento
# ============================================================================

def extrair_dados_agendamento(messages: list) -> dict:
    """
    Extrai dados de agendamento das mensagens.

    Args:
        messages: Lista de mensagens da conversa

    Returns:
        Dict com dados extraídos (nome, telefone, email, etc.)
    """
    # Implementação futura: usar LLM para extrair dados estruturados
    # Por enquanto retorna vazio
    return {
        "nome": None,
        "telefone": None,
        "email": None,
        "area_interesse": None,
        "descricao_caso": None,
        "data_preferencia": None,
        "horario_preferencia": None
    }
