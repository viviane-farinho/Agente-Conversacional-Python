"""
Agente de Suporte para Advocacia

Este agente é responsável por:
1. Responder dúvidas gerais sobre o escritório
2. Informações que não são específicas de uma área do direito
3. Quando não encontrar informação, oferecer atendimento humano

Fluxo:
1. Recebe mensagem do supervisor (quando não é sobre área específica)
2. Busca informações gerais no RAG
3. Responde ou oferece atendimento especializado
"""

from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from src.config import Config
from src.agent.advocacia.tools import get_suporte_tools
from src.services.rag_advocacia import (
    rag_advocacia_get_prompt_sync,
    rag_advocacia_search_sync
)


# Prompt padrão caso não tenha prompt configurado no banco
DEFAULT_SUPORTE_PROMPT = """Você é o assistente de suporte do escritório de advocacia.

OBJETIVO:
Responder dúvidas gerais sobre o escritório e seus serviços.

INFORMAÇÕES DISPONÍVEIS:
{contexto}

REGRAS:
1. Se a pergunta for sobre uma área específica do direito, informe que vai transferir para um especialista
2. Responda de forma clara e objetiva
3. Se não souber a resposta, use a frase abaixo

QUANDO NÃO SOUBER:
"Não encontrei informações específicas sobre isso. Deseja falar com nosso atendimento especializado?"

Seja sempre cordial e profissional."""


def _build_suporte_prompt(query: str) -> str:
    """
    Constrói o prompt do agente de suporte.
    """
    # Tenta carregar prompt do banco
    prompt_banco = rag_advocacia_get_prompt_sync("suporte")

    base_prompt = prompt_banco if prompt_banco else DEFAULT_SUPORTE_PROMPT

    # Busca contexto no RAG
    docs = rag_advocacia_search_sync(
        query=query,
        area_ids=None,
        agente="suporte",
        limit=5,
        similarity_threshold=0.3
    )

    contextos = []
    if docs:
        for doc in docs:
            contextos.append(f"- {doc['titulo']}: {doc['conteudo'][:300]}...")

    contexto_str = "\n".join(contextos) if contextos else "Nenhuma informação encontrada."

    # Substitui placeholder
    final_prompt = base_prompt.replace("{contexto}", contexto_str)

    return final_prompt


async def create_suporte_agent(query: Optional[str] = None):
    """
    Cria o agente de suporte.

    Args:
        query: Pergunta do cliente (para buscar contexto)

    Returns:
        Agente LangGraph configurado
    """
    # Monta prompt
    system_prompt = _build_suporte_prompt(query or "")

    # Cria LLM
    llm = ChatOpenAI(
        model=Config.OPENAI_MODEL,
        temperature=0.7,
        api_key=Config.OPENAI_API_KEY
    )

    # Ferramentas de suporte
    tools = get_suporte_tools()

    # Cria agente
    agent = create_react_agent(
        model=llm,
        tools=tools,
        state_modifier=system_prompt
    )

    return agent


def create_suporte_agent_sync(query: Optional[str] = None):
    """
    Versão síncrona do create_suporte_agent.
    """
    system_prompt = _build_suporte_prompt(query or "")

    llm = ChatOpenAI(
        model=Config.OPENAI_MODEL,
        temperature=0.7,
        api_key=Config.OPENAI_API_KEY
    )

    tools = get_suporte_tools()

    agent = create_react_agent(
        model=llm,
        tools=tools,
        state_modifier=system_prompt
    )

    return agent


# ============================================================================
# Funções auxiliares para o grafo
# ============================================================================

async def suporte_node(state: dict) -> dict:
    """
    Nó do agente de suporte para o grafo LangGraph.

    Args:
        state: Estado do grafo com mensagens

    Returns:
        Estado atualizado com resposta do agente
    """
    messages = state.get("messages", [])

    # Pega última mensagem do usuário
    last_user_msg = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_user_msg = msg.content
            break

    if not last_user_msg:
        return state

    # Cria agente com contexto
    agent = await create_suporte_agent(query=last_user_msg)

    # Executa agente
    result = await agent.ainvoke({"messages": messages})

    # Atualiza estado
    state["messages"] = result["messages"]
    state["last_agent"] = "suporte"

    return state


def get_suporte_info() -> dict:
    """
    Retorna informações sobre o agente de suporte.

    Returns:
        Dict com info do agente
    """
    return {
        "agente": "suporte",
        "descricao": "Agente de suporte para dúvidas gerais sobre o escritório"
    }
