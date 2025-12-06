"""
Agentes especializados para Advocacia
"""

from .vendas import create_vendas_agent
from .suporte import create_suporte_agent
from .agendamento import create_agendamento_agent

__all__ = [
    "create_vendas_agent",
    "create_suporte_agent",
    "create_agendamento_agent"
]
