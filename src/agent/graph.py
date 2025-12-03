"""
Agente Secretaria IA usando LangGraph

Paradigma: Funcional + LangGraph StateGraph
"""
from typing import TypedDict, Annotated, Sequence

import operator

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode  # noqa: F401 - usado em create_tools_node

from src.config import Config
from src.agent.tools import ALL_TOOLS, set_context
from src.agent.prompts import get_system_prompt, TEXT_FORMAT_PROMPT
from src.services.database import db_get_message_history, db_add_message_to_history


# --- Estado do Agente ---

class AgentState(TypedDict):
    """Estado do agente"""
    messages: Annotated[Sequence[BaseMessage], operator.add]
    phone: str
    account_id: str
    conversation_id: str
    message_id: str
    telegram_chat_id: str
    is_audio_message: bool


# --- Funcoes de LLM ---

def get_llm(model_provider: str = "openrouter"):
    """
    Retorna o modelo LLM configurado

    Args:
        model_provider: Provedor do modelo ("openrouter", "google" ou "openai")

    Returns:
        Instancia do LLM configurado
    """
    if model_provider == "openrouter":
        return ChatOpenAI(
            model=Config.OPENROUTER_MODEL,
            api_key=Config.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
            temperature=0.7,
            default_headers={
                "HTTP-Referer": "https://github.com/secretaria-ia",
                "X-Title": "Secretaria IA"
            }
        )
    elif model_provider == "google":
        return ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            google_api_key=Config.GOOGLE_API_KEY,
            temperature=0.7
        )
    else:
        return ChatOpenAI(
            model="gpt-4o",
            api_key=Config.OPENAI_API_KEY,
            temperature=0.7
        )


# --- Funcoes do Grafo (Nos) ---

def create_agent_node(llm_with_tools):
    """
    Cria a funcao do no do agente

    Args:
        llm_with_tools: LLM com ferramentas vinculadas

    Returns:
        Funcao async do no
    """
    async def agent_node(state: AgentState) -> dict:
        """No do agente que processa mensagens"""
        messages = state["messages"]

        # Log das ferramentas disponiveis
        print(f"Ferramentas disponiveis: {[t.name for t in ALL_TOOLS]}")

        response = await llm_with_tools.ainvoke(messages)

        # Log detalhado da resposta
        print(f"Resposta do LLM:")
        print(f"   - Tipo: {type(response)}")
        print(f"   - Conteudo: {response.content[:200] if response.content else 'vazio'}...")
        if hasattr(response, "tool_calls"):
            print(f"   - Tool calls: {response.tool_calls}")
        else:
            print(f"   - Tool calls: NENHUM (atributo nao existe)")
        if hasattr(response, "additional_kwargs"):
            print(f"   - additional_kwargs: {response.additional_kwargs}")

        return {"messages": [response]}

    return agent_node


def should_continue(state: AgentState) -> str:
    """
    Decide se deve continuar para ferramentas ou finalizar

    Args:
        state: Estado atual do agente

    Returns:
        "tools" ou END
    """
    last_message = state["messages"][-1]

    # Se a ultima mensagem tem tool_calls, vai para as ferramentas
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"

    return END


def create_tools_node(tools):
    """
    Cria a funcao do no de ferramentas

    Args:
        tools: Lista de ferramentas disponiveis

    Returns:
        Funcao async do no
    """
    async def tools_node(state: AgentState) -> dict:
        """No de ferramentas com logging"""
        last_message = state["messages"][-1]
        tool_calls = last_message.tool_calls if hasattr(last_message, "tool_calls") else []

        print(f"Ferramentas chamadas: {[tc['name'] for tc in tool_calls]}")
        for tc in tool_calls:
            print(f"   - {tc['name']}: {tc['args']}")

        # Usa o ToolNode padrao
        tool_node = ToolNode(tools)
        try:
            result = await tool_node.ainvoke(state)
            print(f"Resultado das ferramentas: {result}")
            return result
        except Exception as e:
            print(f"Erro nas ferramentas: {e}")
            import traceback
            traceback.print_exc()
            raise

    return tools_node


# --- Construcao do Grafo ---

def build_agent_graph(model_provider: str = "openrouter", tools: list = None) -> StateGraph:
    """
    Constroi o grafo do agente

    Args:
        model_provider: Provedor do modelo
        tools: Lista de ferramentas (usa ALL_TOOLS se None)

    Returns:
        Grafo compilado
    """
    if tools is None:
        tools = ALL_TOOLS

    # LLM com ferramentas
    llm = get_llm(model_provider)
    llm_with_tools = llm.bind_tools(tools)

    # Cria os nos
    agent_node = create_agent_node(llm_with_tools)
    tools_node = create_tools_node(tools)

    # Constroi o grafo
    workflow = StateGraph(AgentState)

    # Adiciona os nos
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tools_node)

    # Define o ponto de entrada
    workflow.set_entry_point("agent")

    # Adiciona as arestas condicionais
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            END: END
        }
    )

    # Ferramentas sempre voltam para o agente
    workflow.add_edge("tools", "agent")

    return workflow.compile()


# --- Funcoes de Historico ---

async def load_history(phone: str) -> list[BaseMessage]:
    """
    Carrega o historico de mensagens do banco de dados

    Args:
        phone: Telefone do usuario

    Returns:
        Lista de mensagens do historico
    """
    history = await db_get_message_history(phone)

    messages = []
    for msg in history:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))

    return messages


async def save_to_history(phone: str, role: str, content: str) -> None:
    """
    Salva uma mensagem no historico

    Args:
        phone: Telefone do usuario
        role: Papel (human/assistant)
        content: Conteudo da mensagem
    """
    await db_add_message_to_history(phone, role, content)


# --- Processamento de Mensagens ---

async def process_message(
    message: str,
    phone: str,
    account_id: str,
    conversation_id: str,
    message_id: str,
    telegram_chat_id: str,
    is_audio_message: bool = False,
    model_provider: str = "openrouter"
) -> str:
    """
    Processa uma mensagem do usuario

    Args:
        message: Mensagem do usuario
        phone: Telefone do usuario
        account_id: ID da conta no Chatwoot
        conversation_id: ID da conversa
        message_id: ID da mensagem
        telegram_chat_id: ID do chat do Telegram para alertas
        is_audio_message: Se a mensagem original era um audio
        model_provider: Provedor do modelo

    Returns:
        Resposta do agente
    """
    # Define o contexto para as ferramentas
    set_context(
        account_id=account_id,
        conversation_id=conversation_id,
        message_id=message_id,
        phone=phone,
        telegram_chat_id=telegram_chat_id
    )

    # Carrega o historico
    history = await load_history(phone)

    # Monta o prompt do sistema
    system_prompt = get_system_prompt(phone, conversation_id)

    # Monta as mensagens
    messages = [
        SystemMessage(content=system_prompt),
        *history,
        HumanMessage(content=message)
    ]

    # Estado inicial
    initial_state = {
        "messages": messages,
        "phone": phone,
        "account_id": account_id,
        "conversation_id": conversation_id,
        "message_id": message_id,
        "telegram_chat_id": telegram_chat_id,
        "is_audio_message": is_audio_message
    }

    # Constroi e executa o grafo
    graph = build_agent_graph(model_provider)
    result = await graph.ainvoke(initial_state)

    # Obtem a resposta final
    last_message = result["messages"][-1]
    response = last_message.content if hasattr(last_message, "content") else str(last_message)

    # Salva no historico
    await save_to_history(phone, "human", message)
    await save_to_history(phone, "assistant", response)

    return response


async def format_response_for_whatsapp(text: str, model_provider: str = "openrouter") -> str:
    """
    Formata a resposta para WhatsApp

    Args:
        text: Texto original
        model_provider: Provedor do modelo

    Returns:
        Texto formatado
    """
    llm = get_llm(model_provider)

    messages = [
        SystemMessage(content=TEXT_FORMAT_PROMPT),
        HumanMessage(content=text)
    ]

    response = await llm.ainvoke(messages)
    return response.content


# --- Compatibilidade (para transicao gradual) ---

class SecretaryAgent:
    """Classe de compatibilidade - usar funcoes diretamente"""

    def __init__(self, model_provider: str = "openrouter"):
        self.model_provider = model_provider
        self.tools = ALL_TOOLS
        self.graph = build_agent_graph(model_provider, ALL_TOOLS)

    def _get_llm(self):
        return get_llm(self.model_provider)

    def _build_graph(self) -> StateGraph:
        return build_agent_graph(self.model_provider, self.tools)

    async def _load_history(self, phone: str) -> list[BaseMessage]:
        return await load_history(phone)

    async def _save_to_history(self, phone: str, role: str, content: str):
        await save_to_history(phone, role, content)

    async def process_message(
        self,
        message: str,
        phone: str,
        account_id: str,
        conversation_id: str,
        message_id: str,
        telegram_chat_id: str,
        is_audio_message: bool = False
    ) -> str:
        return await process_message(
            message, phone, account_id, conversation_id,
            message_id, telegram_chat_id, is_audio_message,
            self.model_provider
        )

    async def format_response_for_whatsapp(self, text: str) -> str:
        return await format_response_for_whatsapp(text, self.model_provider)


# Instancia global do agente
_agent = None


def get_agent(model_provider: str = "openrouter") -> SecretaryAgent:
    """Retorna a instancia do agente (sempre recria para pegar atualizacoes)"""
    global _agent
    # Sempre recria o agente para pegar atualizacoes no prompt e ferramentas
    _agent = SecretaryAgent(model_provider=model_provider)
    return _agent
