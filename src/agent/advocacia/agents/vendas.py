"""
Agente de Vendas para Advocacia

Este agente é responsável por:
1. Detectar a área do direito do cliente
2. Carregar o prompt específico da área (com script SDR)
3. Buscar informações relevantes na base de conhecimento
4. Qualificar o lead e direcionar para agendamento

Fluxo:
1. Recebe mensagem do supervisor
2. Detecta área(s) do direito (keywords + LLM fallback)
3. Carrega prompt da área do banco de dados
4. Busca contexto no RAG filtrado por área
5. Responde com qualificação SDR
"""

from typing import List, Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.prebuilt import create_react_agent

from src.config import Config
from src.agent.advocacia.area_detector import detect_areas, detect_areas_sync
from src.agent.advocacia.tools import get_vendas_tools
from src.services.rag_advocacia import (
    rag_advocacia_get_area_prompt_sync,
    rag_advocacia_search_sync
)


# Prompt padrão caso não tenha prompt configurado no banco
DEFAULT_VENDAS_PROMPT = """Você é um assistente de qualificação do escritório de advocacia.

OBJETIVO:
Qualificar o lead e entender suas necessidades jurídicas para agendamento de consulta.

SCRIPT DE QUALIFICAÇÃO:
1. Identifique a situação/problema do cliente
2. Faça perguntas para entender o caso
3. Verifique se o cliente tem documentação
4. Ofereça agendamento de consulta

INFORMAÇÕES DISPONÍVEIS (USE APENAS ESTAS):
{contexto}

⚠️ REGRAS IMPORTANTES - SIGA RIGOROSAMENTE:
1. NUNCA invente informações que não estejam no contexto acima
2. Se não encontrar a informação no contexto, diga: "Não tenho essa informação específica, mas posso agendar uma consulta com nosso especialista para esclarecer suas dúvidas."
3. NÃO forneça detalhes técnicos/jurídicos que não estejam explicitamente no contexto
4. Seu papel é QUALIFICAR e AGENDAR, não dar consultoria jurídica
5. Seja empático e profissional
6. Foque em entender a situação do cliente e direcioná-lo para consulta

QUANDO NÃO SOUBER A RESPOSTA:
"Essa é uma dúvida importante! Para dar uma resposta precisa sobre seu caso, sugiro agendarmos uma consulta com nosso especialista. Posso verificar os horários disponíveis?"

Responda de forma clara e objetiva."""


def _build_vendas_prompt(area_ids: List[str], query: str) -> str:
    """
    Constrói o prompt do agente de vendas.

    1. Carrega prompts das áreas detectadas
    2. Busca contexto no RAG
    3. Combina tudo em um prompt final
    """
    prompts_areas = []
    contextos = []

    for area_id in area_ids:
        # Carrega prompt da área
        prompt_area = rag_advocacia_get_area_prompt_sync(area_id)
        if prompt_area:
            prompts_areas.append(f"[{area_id.upper()}]\n{prompt_area}")

        # Busca contexto no RAG
        docs = rag_advocacia_search_sync(
            query=query,
            area_ids=[area_id],
            agente="vendas",
            limit=3,
            similarity_threshold=0.3
        )
        if docs:
            for doc in docs:
                contextos.append(f"- {doc['titulo']}: {doc['conteudo'][:300]}...")

    # Se não tem prompt específico, usa default
    if not prompts_areas:
        base_prompt = DEFAULT_VENDAS_PROMPT
    else:
        # Combina prompts das áreas
        base_prompt = "\n\n---\n\n".join(prompts_areas)

    # Monta contexto
    contexto_str = "\n".join(contextos) if contextos else "Nenhuma informação específica encontrada."

    # Substitui placeholder de contexto
    final_prompt = base_prompt.replace("{contexto}", contexto_str)

    return final_prompt


async def create_vendas_agent(
    area_ids: Optional[List[str]] = None,
    query: Optional[str] = None
):
    """
    Cria o agente de vendas com contexto específico.

    Args:
        area_ids: Áreas do direito detectadas
        query: Pergunta do cliente (para buscar contexto)

    Returns:
        Agente LangGraph configurado
    """
    # Se não passou áreas e tem query, detecta
    if not area_ids and query:
        area_ids = await detect_areas(query)

    # Garante que area_ids é lista
    area_ids = area_ids or []

    # Monta prompt
    system_prompt = _build_vendas_prompt(area_ids, query or "")

    # Cria LLM
    llm = ChatOpenAI(
        model=Config.OPENAI_MODEL,
        temperature=0.7,
        api_key=Config.OPENAI_API_KEY
    )

    # Ferramentas com áreas pré-configuradas
    tools = get_vendas_tools(area_ids=area_ids)

    # Cria agente
    agent = create_react_agent(
        model=llm,
        tools=tools,
        state_modifier=system_prompt
    )

    return agent


def create_vendas_agent_sync(
    area_ids: Optional[List[str]] = None,
    query: Optional[str] = None
):
    """
    Versão síncrona do create_vendas_agent.
    """
    # Se não passou áreas e tem query, detecta
    if not area_ids and query:
        area_ids = detect_areas_sync(query)

    area_ids = area_ids or []

    # Monta prompt
    system_prompt = _build_vendas_prompt(area_ids, query or "")

    # Cria LLM
    llm = ChatOpenAI(
        model=Config.OPENAI_MODEL,
        temperature=0.7,
        api_key=Config.OPENAI_API_KEY
    )

    # Ferramentas
    tools = get_vendas_tools(area_ids=area_ids)

    # Cria agente
    agent = create_react_agent(
        model=llm,
        tools=tools,
        state_modifier=system_prompt
    )

    return agent


# ============================================================================
# Funções auxiliares para o grafo
# ============================================================================

async def vendas_node(state: dict) -> dict:
    """
    Nó do agente de vendas para o grafo LangGraph.

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

    # Detecta áreas
    area_ids = await detect_areas(last_user_msg)

    # Salva áreas detectadas no estado
    state["detected_areas"] = area_ids

    # Cria agente com contexto
    agent = await create_vendas_agent(area_ids=area_ids, query=last_user_msg)

    # Executa agente
    result = await agent.ainvoke({"messages": messages})

    # Atualiza estado
    state["messages"] = result["messages"]
    state["last_agent"] = "vendas"

    return state


def get_vendas_info(area_ids: List[str]) -> dict:
    """
    Retorna informações sobre o agente de vendas.

    Args:
        area_ids: Áreas detectadas

    Returns:
        Dict com info do agente
    """
    return {
        "agente": "vendas",
        "areas_detectadas": area_ids,
        "descricao": "Agente de vendas especializado em qualificação de leads jurídicos"
    }
