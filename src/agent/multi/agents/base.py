"""
Classe base para agentes especializados.
"""
from abc import ABC, abstractmethod
from typing import List, Optional
from langchain_core.messages import SystemMessage, AIMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import ToolNode

from src.config import Config
from src.services.database import db_agentes_buscar_por_tipo
from src.agent.tools import ALL_TOOLS
from ..state import SupervisorState


class BaseSpecializedAgent(ABC):
    """
    Classe base para todos os agentes especializados.
    Cada agente herda desta classe e define seu comportamento específico.
    """

    def __init__(self):
        self.tipo: str = self.get_tipo()
        self.tools: List = self.get_tools()
        self._config_cache: Optional[dict] = None

    @abstractmethod
    def get_tipo(self) -> str:
        """Retorna o tipo do agente (ex: 'vendas', 'suporte')."""
        pass

    @abstractmethod
    def get_default_prompt(self) -> str:
        """Retorna o prompt padrão do agente."""
        pass

    def get_tools(self) -> List:
        """
        Retorna as ferramentas disponíveis para o agente.
        Pode ser sobrescrito para filtrar ferramentas específicas.
        """
        return ALL_TOOLS

    def get_llm(self):
        """Retorna o LLM configurado para o agente."""
        return ChatOpenAI(
            model=Config.OPENROUTER_MODEL,
            api_key=Config.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
            temperature=0.7,
            default_headers={
                "HTTP-Referer": "https://github.com/secretaria-ia",
                "X-Title": f"Secretaria IA - {self.tipo.title()}"
            }
        )

    async def get_config(self) -> Optional[dict]:
        """Carrega configuração do agente do banco de dados."""
        if self._config_cache is None:
            self._config_cache = await db_agentes_buscar_por_tipo(self.tipo)
        return self._config_cache

    async def get_system_prompt(self) -> str:
        """
        Retorna o prompt do sistema para o agente.
        Usa o prompt do banco se disponível, senão usa o padrão.
        """
        config = await self.get_config()

        if config and config.get("prompt_sistema"):
            return config["prompt_sistema"]

        return self.get_default_prompt()

    async def is_active(self) -> bool:
        """Verifica se o agente está ativo."""
        config = await self.get_config()
        if config:
            return config.get("ativo", True)
        return True

    def create_node(self):
        """
        Cria a função do nó para o grafo LangGraph.
        """
        async def agent_node(state: SupervisorState) -> dict:
            """Nó do agente especializado."""
            # Verifica se está ativo
            if not await self.is_active():
                return {
                    "messages": [AIMessage(content="Este serviço não está disponível no momento.")],
                    "aguardando_resposta_usuario": True
                }

            # Obtém prompt do sistema
            system_prompt = await self.get_system_prompt()

            # Prepara LLM com ferramentas
            llm = self.get_llm()
            tools = self.get_tools()

            if tools:
                llm_with_tools = llm.bind_tools(tools)
            else:
                llm_with_tools = llm

            # Prepara mensagens
            messages = [
                SystemMessage(content=system_prompt),
                *state["messages"]
            ]

            # Invoca LLM
            response = await llm_with_tools.ainvoke(messages)

            print(f"[{self.tipo.title()}] Resposta: {response.content[:100]}...")

            # Loop para executar ferramentas (suporta múltiplas iterações)
            all_new_messages = []
            current_response = response
            max_iterations = 5  # Evita loops infinitos
            iteration = 0

            while hasattr(current_response, "tool_calls") and current_response.tool_calls and iteration < max_iterations:
                iteration += 1
                tool_names = [tc['name'] for tc in current_response.tool_calls]
                print(f"[{self.tipo.title()}] Executando ferramentas (iter {iteration}): {tool_names}")

                try:
                    tool_node = ToolNode(tools)

                    # Adiciona resposta do LLM ao estado temporário
                    temp_state = {**state, "messages": state["messages"] + all_new_messages + [current_response]}
                    tool_result = await tool_node.ainvoke(temp_state)

                    # Adiciona mensagens (resposta LLM + resultados das ferramentas)
                    all_new_messages.append(current_response)
                    tool_messages = tool_result.get("messages", [])
                    all_new_messages.extend(tool_messages)

                    # Invoca LLM novamente com resultado das ferramentas
                    all_messages = messages + all_new_messages
                    current_response = await llm_with_tools.ainvoke(all_messages)

                except Exception as tool_error:
                    print(f"[{self.tipo.title()}] Erro ao executar ferramenta: {tool_error}")
                    # Se houve erro na ferramenta, retorna mensagem amigável
                    from langchain_core.messages import AIMessage
                    error_response = AIMessage(content="Desculpe, houve um problema ao processar sua solicitação. Vou transferir para um atendente humano.")
                    all_new_messages.append(current_response)
                    all_new_messages.append(error_response)
                    return {
                        "messages": all_new_messages,
                        "resposta_final": error_response.content,
                        "aguardando_resposta_usuario": True
                    }

            # Adiciona resposta final
            if all_new_messages:
                all_new_messages.append(current_response)
                return {
                    "messages": all_new_messages,
                    "resposta_final": current_response.content,
                    "aguardando_resposta_usuario": True
                }

            # Atualiza contexto específico do agente
            contexto_key = f"contexto_{self.tipo}"
            contexto_atual = state.get(contexto_key) or {}
            contexto_atualizado = self.extrair_contexto(response.content, contexto_atual)

            return {
                "messages": [response],
                "resposta_final": response.content,
                contexto_key: contexto_atualizado,
                "aguardando_resposta_usuario": True
            }

        return agent_node

    def extrair_contexto(self, resposta: str, contexto_atual: dict) -> dict:
        """
        Extrai informações relevantes da resposta para manter contexto.
        Pode ser sobrescrito por agentes específicos.
        """
        return contexto_atual
