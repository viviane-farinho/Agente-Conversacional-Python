"""
Agentes especializados para o sistema multi-agente.
"""
from .base import BaseSpecializedAgent
from .vendas import VendasAgent
from .suporte import SuporteAgent
from .agendamento import AgendamentoAgent


def get_agent_nodes() -> dict:
    """
    Retorna os nós dos agentes para o grafo.
    """
    vendas = VendasAgent()
    suporte = SuporteAgent()
    agendamento = AgendamentoAgent()

    return {
        "vendas": vendas.create_node(),
        "suporte": suporte.create_node(),
        "agendamento": agendamento.create_node(),
    }


__all__ = [
    "BaseSpecializedAgent",
    "VendasAgent",
    "SuporteAgent",
    "AgendamentoAgent",
    "get_agent_nodes",
]
