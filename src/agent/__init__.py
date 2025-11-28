"""
Módulo do Agente Secretária IA
"""
from src.agent.graph import SecretaryAgent, get_agent
from src.agent.tools import ALL_TOOLS, set_context
from src.agent.prompts import get_system_prompt

__all__ = [
    "SecretaryAgent",
    "get_agent",
    "ALL_TOOLS",
    "set_context",
    "get_system_prompt"
]
