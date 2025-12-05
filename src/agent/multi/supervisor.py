"""
Supervisor para o sistema multi-agente.
Usa structured_output para decisões confiáveis de roteamento.
"""
from typing import Literal
from langchain_core.messages import SystemMessage, AIMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END

from src.config import Config
from src.services.database import db_agentes_buscar_por_tipo
from .state import SupervisorState, SupervisorDecision


SUPERVISOR_SYSTEM_PROMPT = """Você é o Supervisor de uma equipe de agentes especializados.

Sua função é analisar a mensagem do usuário e decidir qual agente deve processá-la.

## Agentes Disponíveis:

1. **vendas** - Para:
   - Perguntas sobre produtos, serviços e preços
   - Interesse em contratar/comprar algo
   - Dúvidas sobre planos e pacotes
   - Promoções e descontos

2. **suporte** - Para:
   - Problemas técnicos
   - Reclamações
   - Dúvidas sobre uso do serviço
   - Problemas com atendimento anterior

3. **agendamento** - Para:
   - Marcar, remarcar ou cancelar consultas/sessões
   - Verificar disponibilidade de horários
   - Consultar agenda
   - Confirmação de agendamentos

4. **finalizar** - Quando:
   - A conversa foi concluída naturalmente
   - O usuário se despediu
   - Não há mais ações necessárias

## Regras:

1. Analise o CONTEXTO COMPLETO da conversa, não apenas a última mensagem
2. Se a intenção for ambígua, escolha o agente mais provável
3. Saudações iniciais devem ir para 'vendas' (primeiro contato)
4. Se você puder responder diretamente sem delegar, use 'resposta_direta'
5. Forneça contexto útil para o próximo agente em 'contexto_para_agente'

Histórico de roteamento desta conversa: {historico_roteamento}
"""


def get_supervisor_llm():
    """Retorna LLM configurado para o Supervisor com structured_output."""
    llm = ChatOpenAI(
        model=Config.OPENROUTER_MODEL,
        api_key=Config.OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
        temperature=0.3,  # Mais determinístico para roteamento
        default_headers={
            "HTTP-Referer": "https://github.com/secretaria-ia",
            "X-Title": "Secretaria IA - Supervisor"
        }
    )
    return llm.with_structured_output(SupervisorDecision)


async def supervisor_node(state: SupervisorState) -> dict:
    """
    Nó do Supervisor - analisa e decide roteamento.
    Usa structured_output para garantir resposta no formato SupervisorDecision.
    """
    # Carrega configuração do supervisor do banco (se existir)
    supervisor_config = await db_agentes_buscar_por_tipo("supervisor")

    # Usa prompt customizado se disponível, senão usa o padrão
    base_prompt = SUPERVISOR_SYSTEM_PROMPT
    if supervisor_config and supervisor_config.get("prompt_sistema"):
        base_prompt = supervisor_config["prompt_sistema"]

    # Formata o prompt com o histórico
    historico = " -> ".join(state.get("historico_roteamento", ["supervisor"]))
    system_prompt = base_prompt.format(historico_roteamento=historico)

    # Prepara mensagens para o LLM
    messages = [
        SystemMessage(content=system_prompt),
        *state["messages"]
    ]

    # Obtém decisão estruturada
    llm = get_supervisor_llm()
    decisao: SupervisorDecision = await llm.ainvoke(messages)

    print(f"[Supervisor] Decisão: {decisao.proximo_agente} - {decisao.razao}")

    # Atualiza estado
    novo_historico = state.get("historico_roteamento", []) + [decisao.proximo_agente]
    turnos = state.get("turnos", 0) + 1

    updates = {
        "agente_atual": decisao.proximo_agente,
        "historico_roteamento": novo_historico,
        "turnos": turnos,
    }

    # Se tem resposta direta do supervisor
    if decisao.resposta_direta:
        updates["resposta_final"] = decisao.resposta_direta
        updates["messages"] = [AIMessage(content=decisao.resposta_direta)]

    return updates


def roteamento_supervisor(state: SupervisorState) -> Literal["vendas", "suporte", "agendamento", "finalizar"]:
    """
    Função de roteamento baseada na decisão do supervisor.
    """
    agente = state.get("agente_atual", "finalizar")

    # Se já tem resposta final, finaliza
    if state.get("resposta_final"):
        return "finalizar"

    return agente


async def node_finalizar(state: SupervisorState) -> dict:
    """
    Nó final - prepara a resposta para envio.
    """
    # Se já tem resposta final, usa ela
    if state.get("resposta_final"):
        return {"conversa_finalizada": True}

    # Pega última mensagem do agente como resposta
    messages = state.get("messages", [])
    if messages:
        last_msg = messages[-1]
        if hasattr(last_msg, "content"):
            return {
                "resposta_final": last_msg.content,
                "conversa_finalizada": True
            }

    return {
        "resposta_final": "Desculpe, não consegui processar sua mensagem.",
        "conversa_finalizada": True
    }


def criar_grafo_multi_agente(agentes_nodes: dict = None) -> StateGraph:
    """
    Cria o grafo do sistema multi-agente.

    Args:
        agentes_nodes: Dicionário com os nós dos agentes especializados
                      {"vendas": node_func, "suporte": node_func, "agendamento": node_func}

    Returns:
        Grafo compilado
    """
    from .agents import get_agent_nodes

    if agentes_nodes is None:
        agentes_nodes = get_agent_nodes()

    # Cria o grafo
    workflow = StateGraph(SupervisorState)

    # Adiciona nós
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("vendas", agentes_nodes["vendas"])
    workflow.add_node("suporte", agentes_nodes["suporte"])
    workflow.add_node("agendamento", agentes_nodes["agendamento"])
    workflow.add_node("finalizar", node_finalizar)

    # Define entrada
    workflow.set_entry_point("supervisor")

    # Roteamento do supervisor
    workflow.add_conditional_edges(
        "supervisor",
        roteamento_supervisor,
        {
            "vendas": "vendas",
            "suporte": "suporte",
            "agendamento": "agendamento",
            "finalizar": "finalizar"
        }
    )

    # Agentes voltam para o supervisor (para possível re-roteamento)
    workflow.add_edge("vendas", "supervisor")
    workflow.add_edge("suporte", "supervisor")
    workflow.add_edge("agendamento", "supervisor")

    # Finalizar encerra
    workflow.add_edge("finalizar", END)

    return workflow.compile()


class SupervisorAgent:
    """Classe wrapper para o sistema multi-agente."""

    def __init__(self):
        self.graph = criar_grafo_multi_agente()

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
        Processa uma mensagem usando o sistema multi-agente.
        """
        from .state import criar_estado_inicial
        from src.agent.tools import set_context
        from src.agent.graph import load_history, save_to_history
        from langchain_core.messages import HumanMessage

        # Define contexto para as ferramentas
        set_context(
            account_id=account_id,
            conversation_id=conversation_id,
            message_id=message_id,
            phone=phone,
            telegram_chat_id=telegram_chat_id
        )

        # Carrega histórico
        history = await load_history(phone)

        # Cria estado inicial
        state = criar_estado_inicial(
            sender_phone=phone,
            conversation_id=conversation_id,
            account_id=account_id,
            mensagem_usuario=message
        )

        # Adiciona histórico às mensagens
        state["messages"] = history + [HumanMessage(content=message)]

        # Executa o grafo
        result = await self.graph.ainvoke(state)

        # Obtém resposta
        response = result.get("resposta_final", "Desculpe, não consegui processar.")

        # Salva no histórico
        await save_to_history(phone, "human", message)
        await save_to_history(phone, "assistant", response)

        return response
