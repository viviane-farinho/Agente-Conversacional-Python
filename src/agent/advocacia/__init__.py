"""
Módulo de agentes para Advocacia

Este módulo contém o sistema multi-agente especializado para escritórios de advocacia.

Estrutura:
- supervisor.py: Supervisor que roteia para vendas/suporte/agendamento
- area_detector.py: Detector de áreas do direito (keywords + LLM fallback)
- tools.py: Ferramentas RAG para busca na base de conhecimento
- agents/: Agentes especializados
  - vendas.py: Agente de vendas com detecção de área
  - suporte.py: Agente de suporte geral
  - agendamento.py: Agente de agendamento

Uso:
    from src.agent.advocacia import create_advocacia_graph

    graph = create_advocacia_graph()
    result = await graph.ainvoke({"messages": [HumanMessage(content="...")]})
"""

from .supervisor import create_advocacia_graph, AdvocaciaState

__all__ = [
    "create_advocacia_graph",
    "AdvocaciaState"
]
