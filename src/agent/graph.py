"""
Agente Secretária IA usando LangGraph
"""
from typing import TypedDict, Annotated, Sequence
from datetime import datetime
import operator

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from src.config import Config
from src.agent.tools import ALL_TOOLS, set_context
from src.agent.prompts import get_system_prompt, TEXT_FORMAT_PROMPT
from src.services.database import get_db_service


class AgentState(TypedDict):
    """Estado do agente"""
    messages: Annotated[Sequence[BaseMessage], operator.add]
    phone: str
    account_id: str
    conversation_id: str
    message_id: str
    telegram_chat_id: str
    is_audio_message: bool


class SecretaryAgent:
    """Agente Secretária IA com LangGraph"""

    def __init__(self, model_provider: str = "openrouter"):
        """
        Inicializa o agente

        Args:
            model_provider: Provedor do modelo ("openrouter", "google" ou "openai")
        """
        self.model_provider = model_provider
        self.tools = ALL_TOOLS
        self.graph = self._build_graph()

    def _get_llm(self):
        """Retorna o modelo LLM configurado"""
        if self.model_provider == "openrouter":
            # OpenRouter usa API compatível com OpenAI
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
        elif self.model_provider == "google":
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

    def _build_graph(self) -> StateGraph:
        """Constrói o grafo do agente"""

        # LLM com ferramentas
        llm = self._get_llm()
        llm_with_tools = llm.bind_tools(self.tools)

        async def agent_node(state: AgentState) -> dict:
            """Nó do agente que processa mensagens"""
            messages = state["messages"]
            response = await llm_with_tools.ainvoke(messages)
            return {"messages": [response]}

        def should_continue(state: AgentState) -> str:
            """Decide se deve continuar para ferramentas ou finalizar"""
            last_message = state["messages"][-1]

            # Se a última mensagem tem tool_calls, vai para as ferramentas
            if hasattr(last_message, "tool_calls") and last_message.tool_calls:
                return "tools"

            return END

        # Constrói o grafo
        workflow = StateGraph(AgentState)

        # Adiciona os nós
        workflow.add_node("agent", agent_node)
        workflow.add_node("tools", ToolNode(self.tools))

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

    async def _load_history(self, phone: str) -> list[BaseMessage]:
        """Carrega o histórico de mensagens do banco de dados"""
        db = await get_db_service()
        history = await db.get_message_history(phone)

        messages = []
        for msg in history:
            if msg["role"] == "human":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))

        return messages

    async def _save_to_history(self, phone: str, role: str, content: str):
        """Salva uma mensagem no histórico"""
        db = await get_db_service()
        await db.add_message_to_history(phone, role, content)

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
        """
        Processa uma mensagem do usuário

        Args:
            message: Mensagem do usuário
            phone: Telefone do usuário
            account_id: ID da conta no Chatwoot
            conversation_id: ID da conversa
            message_id: ID da mensagem
            telegram_chat_id: ID do chat do Telegram para alertas
            is_audio_message: Se a mensagem original era um áudio

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

        # Carrega o histórico
        history = await self._load_history(phone)

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

        # Executa o grafo
        result = await self.graph.ainvoke(initial_state)

        # Obtém a resposta final
        last_message = result["messages"][-1]
        response = last_message.content if hasattr(last_message, "content") else str(last_message)

        # Salva no histórico
        await self._save_to_history(phone, "human", message)
        await self._save_to_history(phone, "assistant", response)

        return response

    async def format_response_for_whatsapp(self, text: str) -> str:
        """
        Formata a resposta para WhatsApp

        Args:
            text: Texto original

        Returns:
            Texto formatado
        """
        llm = self._get_llm()

        messages = [
            SystemMessage(content=TEXT_FORMAT_PROMPT),
            HumanMessage(content=text)
        ]

        response = await llm.ainvoke(messages)
        return response.content


# Instância global do agente
_agent = None


def get_agent(model_provider: str = "openrouter") -> SecretaryAgent:
    """Retorna a instância do agente"""
    global _agent
    if _agent is None:
        _agent = SecretaryAgent(model_provider=model_provider)
    return _agent
