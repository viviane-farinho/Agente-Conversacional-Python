"""
Estado compartilhado para o sistema multi-agente com Supervisor.
"""
from typing import TypedDict, Annotated, Literal, Optional, List
from pydantic import BaseModel, Field
from langgraph.graph.message import add_messages


class SupervisorDecision(BaseModel):
    """
    Decisão estruturada do Supervisor.
    Usa structured_output para garantir respostas consistentes do LLM.
    """
    proximo_agente: Literal["vendas", "suporte", "agendamento", "finalizar"] = Field(
        description="Qual agente deve processar a mensagem. Use 'finalizar' quando a conversa estiver concluída."
    )

    razao: str = Field(
        description="Breve explicação do porquê dessa decisão de roteamento."
    )

    contexto_para_agente: Optional[str] = Field(
        default=None,
        description="Contexto adicional ou instruções específicas para o próximo agente."
    )

    resposta_direta: Optional[str] = Field(
        default=None,
        description="Se o supervisor pode responder diretamente sem delegar, coloque a resposta aqui."
    )


class SupervisorState(TypedDict):
    """
    Estado global compartilhado entre todos os agentes.
    O Supervisor mantém controle sobre esse estado.
    """
    # Histórico de mensagens (usa add_messages para merge automático)
    messages: Annotated[list, add_messages]

    # Informações do usuário/conversa
    sender_phone: str
    conversation_id: str
    account_id: str

    # Estado do roteamento
    agente_atual: str  # supervisor, vendas, suporte, agendamento
    historico_roteamento: List[str]  # ["supervisor", "vendas", "supervisor", ...]

    # Contexto acumulado pelos agentes
    contexto_vendas: Optional[dict]  # info de produtos, preços mencionados
    contexto_suporte: Optional[dict]  # problema identificado, passos tentados
    contexto_agendamento: Optional[dict]  # profissional escolhido, data/hora

    # Controle de fluxo
    aguardando_resposta_usuario: bool
    conversa_finalizada: bool

    # Resposta final a enviar
    resposta_final: Optional[str]

    # Metadados
    turnos: int  # quantas vezes o supervisor roteou


def criar_estado_inicial(
    sender_phone: str,
    conversation_id: str,
    account_id: str,
    mensagem_usuario: str
) -> SupervisorState:
    """
    Cria o estado inicial para uma nova interação.
    """
    from langchain_core.messages import HumanMessage

    return SupervisorState(
        messages=[HumanMessage(content=mensagem_usuario)],
        sender_phone=sender_phone,
        conversation_id=conversation_id,
        account_id=account_id,
        agente_atual="supervisor",
        historico_roteamento=["supervisor"],
        contexto_vendas=None,
        contexto_suporte=None,
        contexto_agendamento=None,
        aguardando_resposta_usuario=False,
        conversa_finalizada=False,
        resposta_final=None,
        turnos=0
    )
