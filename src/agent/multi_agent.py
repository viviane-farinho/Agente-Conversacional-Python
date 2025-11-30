"""
Sistema Multi-Agente com LangGraph
Suporta roteamento entre sub-agentes especializados
"""
from typing import TypedDict, Annotated, Sequence, Optional, List, Dict, Any
from datetime import datetime
import operator
import json

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END

from src.config import Config
from src.agent.tools import ALL_TOOLS, set_context
from src.services.database import get_db_service
from src.services.tenant import Agente, SubAgente, AgenteVinculado, get_tenant_service


class MultiAgentState(TypedDict):
    """Estado do sistema multi-agente"""
    messages: Annotated[Sequence[BaseMessage], operator.add]
    # Contexto da conversa
    phone: str
    account_id: str
    conversation_id: str
    message_id: str
    telegram_chat_id: str
    is_audio_message: bool
    # Contexto do tenant/agente
    tenant_id: int
    agente_id: int
    agente_config: Dict[str, Any]
    # Roteamento
    current_intent: str
    current_sub_agent: Optional[str]
    sub_agent_response: Optional[str]
    # Agentes vinculados (novo)
    current_linked_agent: Optional[Dict[str, Any]]  # Agente vinculado ativo
    transfer_mode: Optional[str]  # 'interno' ou 'externo'
    transfer_context: Optional[Dict[str, Any]]  # Contexto para transferência
    # Dados do paciente extraídos
    patient_data: Dict[str, Any]


def build_multi_agent_graph(agente: Agente) -> StateGraph:
    """
    Constrói o grafo multi-agente para um agente específico

    Args:
        agente: Configuração do agente do banco de dados

    Returns:
        Grafo compilado do LangGraph
    """

    # LLM configurado para o agente
    def get_llm(temperature: float = None):
        return ChatOpenAI(
            model=agente.modelo_llm,
            api_key=Config.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
            temperature=temperature or agente.temperatura,
            default_headers={
                "HTTP-Referer": "https://github.com/secretaria-ia",
                "X-Title": "Secretaria IA Multi-Agent"
            }
        )

    # =============================================
    # NÓS DO GRAFO
    # =============================================

    async def router_node(state: MultiAgentState) -> dict:
        """
        Nó roteador: analisa a mensagem e decide qual sub-agente ou agente vinculado usar

        Prioridade:
        1. Sub-agentes (pertence ao mesmo agente)
        2. Agentes vinculados (agentes independentes conectados)
        3. Agente principal
        """
        messages = state["messages"]
        sub_agentes = agente.sub_agentes
        agentes_vinculados = agente.agentes_vinculados

        # Se não há sub-agentes nem agentes vinculados, vai direto para o agente principal
        if not sub_agentes and not agentes_vinculados:
            return {
                "current_intent": "geral",
                "current_sub_agent": None,
                "current_linked_agent": None,
                "transfer_mode": None
            }

        # Monta prompt para classificação de intent
        intent_options = []

        # Adiciona sub-agentes
        for sa in sub_agentes:
            intent_options.append(f"- {sa.tipo}: {sa.descricao or sa.nome}")
            if sa.condicao_ativacao:
                intent_options.append(f"  Palavras-chave: {sa.condicao_ativacao}")

        # Adiciona agentes vinculados
        for av in agentes_vinculados:
            intent_options.append(f"- {av.agente_tipo}: {av.agente_nome}")
            if av.condicao_ativacao:
                intent_options.append(f"  Palavras-chave: {av.condicao_ativacao}")

        classification_prompt = f"""Analise a mensagem do usuário e classifique a intenção.

Opções de intenção disponíveis:
{chr(10).join(intent_options)}
- geral: Qualquer outra coisa não específica

Responda APENAS com o tipo da intenção (ex: agendamento, financeiro, suporte, geral).
Não inclua explicações, apenas a palavra do tipo.

Mensagem do usuário: {messages[-1].content if messages else ''}"""

        llm = get_llm(temperature=0.1)  # Baixa temperatura para classificação
        response = await llm.ainvoke([HumanMessage(content=classification_prompt)])

        intent = response.content.strip().lower()

        # Primeiro verifica sub-agentes (prioridade)
        sub_agent = None
        for sa in sub_agentes:
            if sa.tipo.lower() == intent:
                sub_agent = sa.tipo
                break

        # Se não encontrou sub-agente, verifica agentes vinculados
        linked_agent = None
        transfer_mode = None
        if not sub_agent:
            for av in agentes_vinculados:
                if av.agente_tipo.lower() == intent:
                    linked_agent = {
                        "id": av.agente_id,
                        "nome": av.agente_nome,
                        "tipo": av.agente_tipo,
                        "system_prompt": av.system_prompt,
                        "ferramentas": av.ferramentas,
                        "manter_contexto": av.manter_contexto,
                        "chatwoot_account_id": av.chatwoot_account_id,
                        "chatwoot_inbox_id": av.chatwoot_inbox_id
                    }
                    transfer_mode = av.modo_transferencia
                    break

        print(f"🎯 Router: Intent={intent}, Sub-agent={sub_agent}, Linked-agent={linked_agent}")

        return {
            "current_intent": intent,
            "current_sub_agent": sub_agent,
            "current_linked_agent": linked_agent,
            "transfer_mode": transfer_mode
        }

    async def main_agent_node(state: MultiAgentState) -> dict:
        """
        Nó do agente principal

        Usa o system_prompt do agente configurado ou o padrão
        """
        from src.agent.prompts import get_system_prompt
        from langgraph.prebuilt import ToolNode

        messages = state["messages"]
        phone = state["phone"]
        conversation_id = state["conversation_id"]

        # System prompt: usa o do banco ou gera o padrão
        if agente.system_prompt:
            # Substitui variáveis no prompt
            system_prompt = agente.system_prompt.format(
                phone=phone,
                conversation_id=conversation_id,
                data_atual=datetime.now().strftime("%A, %d de %B de %Y, %H:%M"),
                **agente.info_empresa
            )
        else:
            system_prompt = get_system_prompt(phone, conversation_id)

        # Prepara mensagens com system prompt
        full_messages = [SystemMessage(content=system_prompt)] + list(messages)

        # LLM com ferramentas
        llm = get_llm()
        llm_with_tools = llm.bind_tools(ALL_TOOLS)

        print(f"🤖 Main Agent processando...")
        response = await llm_with_tools.ainvoke(full_messages)

        # Se tem tool calls, executa
        if hasattr(response, "tool_calls") and response.tool_calls:
            print(f"🔧 Ferramentas chamadas: {[tc['name'] for tc in response.tool_calls]}")

            tool_node = ToolNode(ALL_TOOLS)
            tool_result = await tool_node.ainvoke({"messages": [response]})

            # Processa resultado das ferramentas
            new_messages = [response] + tool_result.get("messages", [])

            # Chama LLM novamente com resultado das ferramentas
            response = await llm_with_tools.ainvoke(full_messages + new_messages)

            # Loop se ainda tiver tool calls (máximo 5 iterações)
            iterations = 0
            while hasattr(response, "tool_calls") and response.tool_calls and iterations < 5:
                iterations += 1
                print(f"🔧 Ferramentas (iteração {iterations}): {[tc['name'] for tc in response.tool_calls]}")

                tool_result = await tool_node.ainvoke({"messages": [response]})
                new_messages = new_messages + [response] + tool_result.get("messages", [])
                response = await llm_with_tools.ainvoke(full_messages + new_messages)

        return {
            "messages": [response],
            "sub_agent_response": response.content
        }

    async def sub_agent_node(state: MultiAgentState) -> dict:
        """
        Nó de sub-agente especializado

        Usa o prompt específico do sub-agente se disponível
        """
        from langgraph.prebuilt import ToolNode

        messages = state["messages"]
        current_sub_agent = state.get("current_sub_agent")
        phone = state["phone"]
        conversation_id = state["conversation_id"]

        # Encontra o sub-agente
        sub_agente = None
        for sa in agente.sub_agentes:
            if sa.tipo == current_sub_agent:
                sub_agente = sa
                break

        if not sub_agente:
            # Fallback para agente principal
            return await main_agent_node(state)

        # System prompt do sub-agente
        if sub_agente.system_prompt:
            system_prompt = sub_agente.system_prompt.format(
                phone=phone,
                conversation_id=conversation_id,
                data_atual=datetime.now().strftime("%A, %d de %B de %Y, %H:%M"),
                **agente.info_empresa
            )
        else:
            # Usa prompt do agente principal
            from src.agent.prompts import get_system_prompt
            system_prompt = get_system_prompt(phone, conversation_id)

        # Filtra ferramentas se especificadas
        tools_to_use = ALL_TOOLS
        if sub_agente.ferramentas:
            tools_to_use = [t for t in ALL_TOOLS if t.name in sub_agente.ferramentas]
            if not tools_to_use:
                tools_to_use = ALL_TOOLS  # Fallback

        # Prepara mensagens
        full_messages = [SystemMessage(content=system_prompt)] + list(messages)

        # LLM com ferramentas do sub-agente
        llm = get_llm()
        llm_with_tools = llm.bind_tools(tools_to_use)

        print(f"🎭 Sub-agent '{sub_agente.nome}' processando...")
        response = await llm_with_tools.ainvoke(full_messages)

        # Executa ferramentas se necessário
        if hasattr(response, "tool_calls") and response.tool_calls:
            print(f"🔧 Ferramentas do sub-agent: {[tc['name'] for tc in response.tool_calls]}")

            tool_node = ToolNode(tools_to_use)
            tool_result = await tool_node.ainvoke({"messages": [response]})

            new_messages = [response] + tool_result.get("messages", [])
            response = await llm_with_tools.ainvoke(full_messages + new_messages)

            # Loop para múltiplas chamadas
            iterations = 0
            while hasattr(response, "tool_calls") and response.tool_calls and iterations < 5:
                iterations += 1
                tool_result = await tool_node.ainvoke({"messages": [response]})
                new_messages = new_messages + [response] + tool_result.get("messages", [])
                response = await llm_with_tools.ainvoke(full_messages + new_messages)

        return {
            "messages": [response],
            "sub_agent_response": response.content
        }

    async def linked_agent_node(state: MultiAgentState) -> dict:
        """
        Nó para agente vinculado

        Processa a mensagem usando o agente vinculado.
        Se modo_transferencia = 'externo', registra a transferência para acompanhamento.
        """
        from langgraph.prebuilt import ToolNode

        messages = state["messages"]
        linked_agent = state.get("current_linked_agent")
        phone = state["phone"]
        conversation_id = state["conversation_id"]
        transfer_mode = state.get("transfer_mode", "interno")

        if not linked_agent:
            # Fallback para agente principal
            return await main_agent_node(state)

        # System prompt do agente vinculado
        if linked_agent.get("system_prompt"):
            system_prompt = linked_agent["system_prompt"].format(
                phone=phone,
                conversation_id=conversation_id,
                data_atual=datetime.now().strftime("%A, %d de %B de %Y, %H:%M"),
                **agente.info_empresa
            )
        else:
            # Usa prompt do agente principal
            from src.agent.prompts import get_system_prompt
            system_prompt = get_system_prompt(phone, conversation_id)

        # Filtra ferramentas se especificadas
        tools_to_use = ALL_TOOLS
        if linked_agent.get("ferramentas"):
            tools_to_use = [t for t in ALL_TOOLS if t.name in linked_agent["ferramentas"]]
            if not tools_to_use:
                tools_to_use = ALL_TOOLS  # Fallback

        # Se manter_contexto = False, não passa histórico
        if linked_agent.get("manter_contexto", True):
            full_messages = [SystemMessage(content=system_prompt)] + list(messages)
        else:
            # Só passa a última mensagem
            full_messages = [SystemMessage(content=system_prompt), messages[-1]]

        # LLM com ferramentas do agente vinculado
        llm = get_llm()
        llm_with_tools = llm.bind_tools(tools_to_use)

        print(f"🔗 Linked-agent '{linked_agent['nome']}' processando (mode: {transfer_mode})...")
        response = await llm_with_tools.ainvoke(full_messages)

        # Executa ferramentas se necessário
        if hasattr(response, "tool_calls") and response.tool_calls:
            print(f"🔧 Ferramentas do linked-agent: {[tc['name'] for tc in response.tool_calls]}")

            tool_node = ToolNode(tools_to_use)
            tool_result = await tool_node.ainvoke({"messages": [response]})

            new_messages = [response] + tool_result.get("messages", [])
            response = await llm_with_tools.ainvoke(full_messages + new_messages)

            # Loop para múltiplas chamadas
            iterations = 0
            while hasattr(response, "tool_calls") and response.tool_calls and iterations < 5:
                iterations += 1
                tool_result = await tool_node.ainvoke({"messages": [response]})
                new_messages = new_messages + [response] + tool_result.get("messages", [])
                response = await llm_with_tools.ainvoke(full_messages + new_messages)

        # Se modo = 'externo' e o agente vinculado tem WhatsApp próprio,
        # podemos registrar a transferência para acompanhamento
        if transfer_mode == "externo" and linked_agent.get("chatwoot_account_id"):
            print(f"📤 Transferência externa para agente '{linked_agent['nome']}' - WhatsApp próprio disponível")
            # A transferência externa seria tratada pelo sistema de chatwoot
            # Aqui apenas retornamos a resposta do agente vinculado

        return {
            "messages": [response],
            "sub_agent_response": response.content,
            "transfer_context": {
                "linked_agent_id": linked_agent.get("id"),
                "linked_agent_nome": linked_agent.get("nome"),
                "transfer_mode": transfer_mode
            }
        }

    # =============================================
    # DECISÕES DE ROTEAMENTO
    # =============================================

    def route_after_router(state: MultiAgentState) -> str:
        """Decide para qual nó ir após o router"""
        sub_agent = state.get("current_sub_agent")
        linked_agent = state.get("current_linked_agent")

        # Primeiro verifica sub-agentes
        if sub_agent and agente.sub_agentes:
            for sa in agente.sub_agentes:
                if sa.tipo == sub_agent:
                    return "sub_agent"

        # Depois verifica agentes vinculados
        if linked_agent:
            return "linked_agent"

        return "main_agent"

    # =============================================
    # CONSTRUÇÃO DO GRAFO
    # =============================================

    workflow = StateGraph(MultiAgentState)

    # Adiciona nós
    workflow.add_node("router", router_node)
    workflow.add_node("main_agent", main_agent_node)
    workflow.add_node("sub_agent", sub_agent_node)
    workflow.add_node("linked_agent", linked_agent_node)

    # Define entrada
    workflow.set_entry_point("router")

    # Roteamento condicional após router
    workflow.add_conditional_edges(
        "router",
        route_after_router,
        {
            "main_agent": "main_agent",
            "sub_agent": "sub_agent",
            "linked_agent": "linked_agent"
        }
    )

    # Todos os agentes terminam
    workflow.add_edge("main_agent", END)
    workflow.add_edge("sub_agent", END)
    workflow.add_edge("linked_agent", END)

    return workflow.compile()


class MultiAgentRunner:
    """
    Runner para o sistema multi-agente

    Gerencia a criação de grafos por agente e execução
    """

    # Cache de grafos por agente_id
    _graph_cache: Dict[int, StateGraph] = {}

    def __init__(self):
        pass

    async def get_graph(self, agente: Agente) -> StateGraph:
        """Obtém ou cria o grafo para um agente"""
        if agente.id not in self._graph_cache:
            self._graph_cache[agente.id] = build_multi_agent_graph(agente)
        return self._graph_cache[agente.id]

    def invalidate_cache(self, agente_id: int = None):
        """Invalida o cache de grafos"""
        if agente_id:
            self._graph_cache.pop(agente_id, None)
        else:
            self._graph_cache.clear()

    async def process_message(
        self,
        agente: Agente,
        message: str,
        phone: str,
        account_id: str,
        conversation_id: str,
        message_id: str,
        telegram_chat_id: str,
        is_audio_message: bool = False
    ) -> str:
        """
        Processa uma mensagem usando o sistema multi-agente

        Args:
            agente: Configuração do agente
            message: Mensagem do usuário
            phone: Telefone do usuário
            account_id: ID da conta Chatwoot
            conversation_id: ID da conversa
            message_id: ID da mensagem
            telegram_chat_id: Chat ID do Telegram
            is_audio_message: Se é mensagem de áudio

        Returns:
            Resposta do agente
        """
        # Define contexto das ferramentas
        set_context(
            account_id=account_id,
            conversation_id=conversation_id,
            message_id=message_id,
            phone=phone,
            telegram_chat_id=telegram_chat_id
        )

        # Carrega histórico
        db = await get_db_service()
        history = await db.get_message_history(phone)

        messages = []
        for msg in history:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))

        # Adiciona mensagem atual
        messages.append(HumanMessage(content=message))

        # Estado inicial
        initial_state: MultiAgentState = {
            "messages": messages,
            "phone": phone,
            "account_id": account_id,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "telegram_chat_id": telegram_chat_id,
            "is_audio_message": is_audio_message,
            "tenant_id": agente.tenant_id,
            "agente_id": agente.id,
            "agente_config": {
                "nome": agente.nome,
                "modelo_llm": agente.modelo_llm,
                "temperatura": agente.temperatura,
                "info_empresa": agente.info_empresa
            },
            "current_intent": "",
            "current_sub_agent": None,
            "sub_agent_response": None,
            "current_linked_agent": None,
            "transfer_mode": None,
            "transfer_context": None,
            "patient_data": {}
        }

        # Obtém ou cria o grafo
        graph = await self.get_graph(agente)

        # Executa
        print(f"🚀 Multi-agent processando para agente '{agente.nome}' (ID: {agente.id})")
        result = await graph.ainvoke(initial_state)

        # Obtém resposta
        last_message = result["messages"][-1]
        response = last_message.content if hasattr(last_message, "content") else str(last_message)

        # Salva no histórico
        await db.add_message_to_history(phone, "user", message)
        await db.add_message_to_history(phone, "assistant", response)

        print(f"✅ Resposta gerada (intent: {result.get('current_intent', 'N/A')})")

        return response


# Instância global
multi_agent_runner = MultiAgentRunner()


async def get_multi_agent_runner() -> MultiAgentRunner:
    """Retorna a instância do runner multi-agente"""
    return multi_agent_runner
