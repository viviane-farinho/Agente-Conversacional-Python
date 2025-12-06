"""
Supervisor para Sistema Multi-Agente de Advocacia

Este módulo implementa o supervisor que roteia as mensagens para os agentes:
- vendas: Quando detecta área do direito ou interesse em serviços
- suporte: Quando são dúvidas gerais sobre o escritório
- agendamento: Quando o cliente quer agendar consulta

Arquitetura:
1. Supervisor recebe mensagem
2. Classifica a intenção (vendas/suporte/agendamento)
3. Roteia para o agente apropriado
4. Retorna resposta ao usuário

Uso:
    from src.agent.advocacia import create_advocacia_graph

    graph = create_advocacia_graph()
    result = await graph.ainvoke({
        "messages": [HumanMessage(content="Quero me aposentar")]
    })
"""

from typing import TypedDict, Annotated, Literal, List, Optional
import operator

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END

from src.config import Config
from src.agent.advocacia.area_detector import detect_areas_sync
from src.agent.advocacia.agents.vendas import vendas_node
from src.agent.advocacia.agents.suporte import suporte_node
from src.agent.advocacia.agents.agendamento import agendamento_node


# ============================================================================
# Estado do Grafo
# ============================================================================

class AdvocaciaState(TypedDict):
    """Estado compartilhado entre os agentes."""
    messages: Annotated[List[BaseMessage], operator.add]
    next_agent: Optional[str]
    last_agent: Optional[str]
    detected_areas: Optional[List[str]]
    telefone: Optional[str]


# ============================================================================
# Prompt do Supervisor
# ============================================================================

SUPERVISOR_PROMPT = """Você é o supervisor de um escritório de advocacia.
Sua função é analisar a mensagem do cliente e decidir qual agente deve responder.

AGENTES DISPONÍVEIS:
1. vendas - Para questões sobre áreas do direito (previdenciário, trabalhista, família, etc.)
   Use quando o cliente menciona: aposentadoria, demissão, divórcio, processos, direitos, etc.

2. suporte - Para dúvidas gerais sobre o escritório
   Use quando o cliente pergunta: horários, localização, formas de pagamento, etc.

3. agendamento - Para agendar consultas
   Use quando o cliente quer: agendar, marcar consulta, horário disponível, etc.

REGRAS:
- Se detectar área do direito → vendas
- Se for dúvida geral → suporte
- Se quiser agendar → agendamento
- Na dúvida entre vendas e suporte → vendas

MENSAGEM DO CLIENTE:
{mensagem}

ÁREAS DETECTADAS POR KEYWORDS:
{areas_detectadas}

Responda APENAS com o nome do agente: vendas, suporte ou agendamento"""


# ============================================================================
# Funções do Grafo
# ============================================================================

def classify_intent(state: AdvocaciaState) -> AdvocaciaState:
    """
    Classifica a intenção do usuário e decide qual agente usar.
    """
    messages = state.get("messages", [])

    # Pega última mensagem do usuário
    last_user_msg = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_user_msg = msg.content
            break

    if not last_user_msg:
        state["next_agent"] = "suporte"
        return state

    # Detecta áreas por keywords
    areas = detect_areas_sync(last_user_msg)
    state["detected_areas"] = areas

    # Se detectou área do direito, vai para vendas
    if areas:
        state["next_agent"] = "vendas"
        return state

    # Verifica keywords de agendamento
    agendamento_keywords = [
        "agendar", "agenda", "marcar", "consulta", "horário", "horario",
        "disponível", "disponivel", "atendimento", "visita"
    ]
    msg_lower = last_user_msg.lower()
    if any(kw in msg_lower for kw in agendamento_keywords):
        state["next_agent"] = "agendamento"
        return state

    # Verifica keywords de suporte
    suporte_keywords = [
        "onde fica", "endereço", "endereco", "telefone", "contato",
        "horário de funcionamento", "funcionamento", "pagamento",
        "valor", "preço", "preco", "quanto custa"
    ]
    if any(kw in msg_lower for kw in suporte_keywords):
        state["next_agent"] = "suporte"
        return state

    # Usa LLM para classificar casos ambíguos
    try:
        llm = ChatOpenAI(
            model="gpt-4o-mini",  # Modelo rápido para classificação
            temperature=0,
            api_key=Config.OPENAI_API_KEY
        )

        prompt = SUPERVISOR_PROMPT.format(
            mensagem=last_user_msg,
            areas_detectadas=areas if areas else "Nenhuma"
        )

        response = llm.invoke(prompt)
        agent = response.content.strip().lower()

        if agent in ["vendas", "suporte", "agendamento"]:
            state["next_agent"] = agent
        else:
            # Default para vendas se não reconhecer
            state["next_agent"] = "vendas"

    except Exception as e:
        print(f"[Supervisor] Erro na classificação: {e}")
        # Default para vendas em caso de erro
        state["next_agent"] = "vendas"

    return state


def route_to_agent(state: AdvocaciaState) -> Literal["vendas", "suporte", "agendamento"]:
    """
    Função de roteamento baseada no next_agent.
    """
    return state.get("next_agent", "suporte")


# ============================================================================
# Criação do Grafo
# ============================================================================

def create_advocacia_graph() -> StateGraph:
    """
    Cria o grafo LangGraph para o sistema multi-agente de advocacia.

    Estrutura:
    START → classify → route → [vendas|suporte|agendamento] → END

    Returns:
        Grafo compilado pronto para uso
    """
    # Cria o grafo
    workflow = StateGraph(AdvocaciaState)

    # Adiciona nós
    workflow.add_node("classify", classify_intent)
    workflow.add_node("vendas", vendas_node)
    workflow.add_node("suporte", suporte_node)
    workflow.add_node("agendamento", agendamento_node)

    # Define entrada
    workflow.set_entry_point("classify")

    # Adiciona roteamento condicional
    workflow.add_conditional_edges(
        "classify",
        route_to_agent,
        {
            "vendas": "vendas",
            "suporte": "suporte",
            "agendamento": "agendamento"
        }
    )

    # Todos os agentes vão para END
    workflow.add_edge("vendas", END)
    workflow.add_edge("suporte", END)
    workflow.add_edge("agendamento", END)

    # Compila
    graph = workflow.compile()

    return graph


# ============================================================================
# Função de conveniência para uso direto
# ============================================================================

async def run_advocacia_agent(
    message: str,
    history: Optional[List[BaseMessage]] = None,
    telefone: Optional[str] = None
) -> dict:
    """
    Executa o sistema multi-agente de advocacia.

    Args:
        message: Mensagem do usuário
        history: Histórico de mensagens (opcional)
        telefone: Telefone do usuário (opcional)

    Returns:
        Dict com resultado da execução
    """
    # Prepara mensagens
    messages = history or []
    messages.append(HumanMessage(content=message))

    # Cria estado inicial
    initial_state = {
        "messages": messages,
        "next_agent": None,
        "last_agent": None,
        "detected_areas": None,
        "telefone": telefone
    }

    # Cria e executa grafo
    graph = create_advocacia_graph()
    result = await graph.ainvoke(initial_state)

    # Extrai resposta
    response_messages = result.get("messages", [])
    last_ai_msg = None
    for msg in reversed(response_messages):
        if isinstance(msg, AIMessage):
            last_ai_msg = msg.content
            break

    return {
        "response": last_ai_msg,
        "messages": response_messages,
        "agent_used": result.get("last_agent"),
        "areas_detected": result.get("detected_areas", [])
    }


def run_advocacia_agent_sync(
    message: str,
    history: Optional[List[BaseMessage]] = None,
    telefone: Optional[str] = None
) -> dict:
    """
    Versão síncrona do run_advocacia_agent.
    """
    import asyncio
    return asyncio.run(run_advocacia_agent(message, history, telefone))


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    "AdvocaciaState",
    "create_advocacia_graph",
    "run_advocacia_agent",
    "run_advocacia_agent_sync"
]
