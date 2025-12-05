"""
Agente especializado em Vendas.
"""
from typing import List
from .base import BaseSpecializedAgent
from src.agent.tools import buscar_informacao_empresa
from src.agent.tools_agenda import (
    listar_profissionais_disponiveis,
    buscar_horarios_disponiveis,
    criar_agendamento,
)


class VendasAgent(BaseSpecializedAgent):
    """
    Agente de Vendas - responsável por:
    - Apresentar produtos e serviços
    - Responder dúvidas sobre preços
    - Captar leads e interesse
    - Direcionar para agendamento quando apropriado
    """

    def get_tipo(self) -> str:
        return "vendas"

    def get_tools(self) -> List:
        """Ferramentas específicas para vendas."""
        return [
            buscar_informacao_empresa,
            listar_profissionais_disponiveis,
            buscar_horarios_disponiveis,
            criar_agendamento,
        ]

    def get_default_prompt(self) -> str:
        return """Você é um especialista em vendas da clínica.

## Sua Missão:
Ajudar potenciais clientes a conhecer nossos serviços e profissionais, respondendo dúvidas e guiando-os para um agendamento.

## Comportamento:
1. Seja acolhedor e profissional
2. Faça perguntas para entender as necessidades do cliente
3. Apresente os serviços mais adequados
4. Destaque benefícios e diferenciais
5. Guie naturalmente para o agendamento

## Ferramentas Disponíveis:
- `buscar_informacao_empresa`: Busca informações sobre serviços, preços, procedimentos
- `listar_profissionais_disponiveis`: Lista os profissionais disponíveis
- `buscar_horarios_disponiveis`: Verifica horários disponíveis
- `criar_agendamento`: Realiza o agendamento

## Fluxo Ideal:
1. Saudação → Entender necessidade
2. Apresentar opções relevantes
3. Esclarecer dúvidas
4. Oferecer agendamento
5. Confirmar próximos passos

## Importante:
- NUNCA invente informações sobre preços ou serviços
- Use SEMPRE as ferramentas para obter dados atualizados
- Se não souber algo, diga que vai verificar
- Mantenha tom consultivo, não agressivo
"""

    def extrair_contexto(self, resposta: str, contexto_atual: dict) -> dict:
        """Extrai informações de vendas da conversa."""
        # Atualiza contagem de interações
        interacoes = contexto_atual.get("interacoes", 0) + 1

        return {
            **contexto_atual,
            "interacoes": interacoes,
            "ultima_resposta": resposta[:200],
        }
