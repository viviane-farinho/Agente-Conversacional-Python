"""
Script de teste do agente Secretária IA
Execute: python test_agent.py
"""
import asyncio
from src.config import Config
from src.agent.graph import SecretaryAgent
from src.agent.tools import set_context


async def test_agent():
    print("=" * 60)
    print("TESTE DO AGENTE SECRETÁRIA IA")
    print("=" * 60)

    # Verifica configuração
    if not Config.OPENROUTER_API_KEY:
        print("\n❌ ERRO: OPENROUTER_API_KEY não configurada!")
        print("   Configure no arquivo .env:")
        print("   OPENROUTER_API_KEY=sk-or-v1-sua-chave-aqui")
        print("\n   Obtenha sua chave em: https://openrouter.ai/keys")
        return

    print(f"\n✅ Usando modelo: {Config.OPENROUTER_MODEL}")
    print("✅ Inicializando agente...")

    # Cria o agente
    agent = SecretaryAgent(model_provider="openrouter")

    # Define contexto fake para teste
    set_context(
        account_id="1",
        conversation_id="123",
        message_id="456",
        phone="5511999999999",
        telegram_chat_id="123456"
    )

    # Mensagens de teste
    test_messages = [
        "Olá, boa tarde!",
        "Quais são os horários de funcionamento?",
        "Quero marcar uma consulta para amanhã às 10h",
    ]

    print("\n" + "-" * 60)
    print("INICIANDO TESTES DE CONVERSAÇÃO")
    print("-" * 60)

    for i, msg in enumerate(test_messages, 1):
        print(f"\n[Teste {i}] Usuário: {msg}")
        print("-" * 40)

        try:
            # Processa a mensagem (sem salvar no banco para teste)
            from langchain_core.messages import SystemMessage, HumanMessage
            from src.agent.prompts import get_system_prompt

            system_prompt = get_system_prompt("5511999999999", "123")
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=msg)
            ]

            # Estado inicial
            initial_state = {
                "messages": messages,
                "phone": "5511999999999",
                "account_id": "1",
                "conversation_id": "123",
                "message_id": "456",
                "telegram_chat_id": "123456",
                "is_audio_message": False
            }

            # Executa o grafo
            result = await agent.graph.ainvoke(initial_state)

            # Obtém resposta
            last_message = result["messages"][-1]
            response = last_message.content if hasattr(last_message, "content") else str(last_message)

            # Limita a resposta para exibição
            if len(response) > 500:
                response = response[:500] + "..."

            print(f"Agente: {response}")

        except Exception as e:
            print(f"❌ Erro: {e}")
            import traceback
            traceback.print_exc()

        print()

    print("=" * 60)
    print("TESTE CONCLUÍDO!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_agent())
