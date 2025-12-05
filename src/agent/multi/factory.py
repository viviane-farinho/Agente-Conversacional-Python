"""
Factory para seleção do sistema de agentes.
Permite A/B testing entre o agente simples e o sistema multi-agente.
"""
import hashlib
from typing import Literal, Optional
from enum import Enum

from src.services.database import db_get_config


class AgentMode(str, Enum):
    """Modos de agente disponíveis."""
    SIMPLE = "simple"  # Agente único atual
    MULTI = "multi"    # Sistema multi-agente com supervisor


class AgentFactory:
    """
    Factory para criar o agente apropriado baseado em configuração.
    Suporta A/B testing com rollout gradual.
    """

    @staticmethod
    async def get_mode() -> AgentMode:
        """
        Obtém o modo de agente configurado.

        Returns:
            AgentMode configurado (default: SIMPLE)
        """
        mode = await db_get_config("agent_mode")

        if mode == "multi":
            return AgentMode.MULTI
        return AgentMode.SIMPLE

    @staticmethod
    async def get_rollout_percentage() -> int:
        """
        Obtém a porcentagem de rollout para o modo multi.

        Returns:
            Porcentagem (0-100) de usuários no modo multi
        """
        percentage = await db_get_config("agent_multi_rollout_percentage")

        if percentage:
            try:
                return min(100, max(0, int(percentage)))
            except ValueError:
                pass
        return 0

    @staticmethod
    def should_use_multi(phone: str, percentage: int) -> bool:
        """
        Decide se um usuário específico deve usar o modo multi.
        Usa hash do telefone para distribuição consistente.

        Args:
            phone: Telefone do usuário
            percentage: Porcentagem de rollout (0-100)

        Returns:
            True se deve usar multi, False caso contrário
        """
        if percentage >= 100:
            return True
        if percentage <= 0:
            return False

        # Hash do telefone para distribuição consistente
        phone_hash = hashlib.md5(phone.encode()).hexdigest()
        hash_value = int(phone_hash[:8], 16) % 100

        return hash_value < percentage

    @staticmethod
    async def get_agent(phone: str = None, force_mode: AgentMode = None):
        """
        Retorna o agente apropriado baseado na configuração.

        Args:
            phone: Telefone do usuário (para A/B testing)
            force_mode: Força um modo específico (ignora configuração)

        Returns:
            Instância do agente (SecretaryAgent ou SupervisorAgent)
        """
        # Se modo forçado, usa ele
        if force_mode:
            mode = force_mode
        else:
            # Obtém modo configurado
            mode = await AgentFactory.get_mode()

            # Se modo é "multi" com rollout gradual
            if mode == AgentMode.MULTI and phone:
                percentage = await AgentFactory.get_rollout_percentage()
                if percentage < 100:
                    if not AgentFactory.should_use_multi(phone, percentage):
                        mode = AgentMode.SIMPLE

        # Retorna agente apropriado
        if mode == AgentMode.MULTI:
            from .supervisor import SupervisorAgent
            return SupervisorAgent()
        else:
            from src.agent.graph import SecretaryAgent
            return SecretaryAgent()

    @staticmethod
    async def process_message(
        message: str,
        phone: str,
        account_id: str,
        conversation_id: str,
        message_id: str,
        telegram_chat_id: str,
        is_audio_message: bool = False,
        force_mode: AgentMode = None
    ) -> str:
        """
        Processa uma mensagem usando o agente apropriado.

        Args:
            message: Mensagem do usuário
            phone: Telefone do usuário
            account_id: ID da conta Chatwoot
            conversation_id: ID da conversa
            message_id: ID da mensagem
            telegram_chat_id: ID do chat Telegram
            is_audio_message: Se é mensagem de áudio
            force_mode: Força modo específico

        Returns:
            Resposta do agente
        """
        agent = await AgentFactory.get_agent(phone, force_mode)

        mode_name = "MULTI" if isinstance(agent, type) and agent.__class__.__name__ == "SupervisorAgent" else "SIMPLE"
        print(f"[Factory] Usando modo: {mode_name} para {phone}")

        return await agent.process_message(
            message=message,
            phone=phone,
            account_id=account_id,
            conversation_id=conversation_id,
            message_id=message_id,
            telegram_chat_id=telegram_chat_id,
            is_audio_message=is_audio_message
        )


# Função de conveniência
async def process_with_factory(
    message: str,
    phone: str,
    account_id: str,
    conversation_id: str,
    message_id: str,
    telegram_chat_id: str,
    is_audio_message: bool = False
) -> str:
    """Processa mensagem usando o factory."""
    return await AgentFactory.process_message(
        message=message,
        phone=phone,
        account_id=account_id,
        conversation_id=conversation_id,
        message_id=message_id,
        telegram_chat_id=telegram_chat_id,
        is_audio_message=is_audio_message
    )
