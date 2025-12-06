"""
Script para testar o RAG Advocacia

Executa:
    python scripts/testar_rag_advocacia.py

Este script testa:
1. Detecção de áreas por keywords
2. Busca na base de conhecimento
3. Sistema multi-agente completo
"""
import asyncio
import sys
import os

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.database import db_connect
from src.agent.advocacia.area_detector import (
    detect_areas,
    detect_areas_by_keywords,
    test_detection
)
from src.agent.advocacia import create_advocacia_graph
from src.services.rag_advocacia import rag_advocacia_search_sync
from langchain_core.messages import HumanMessage


# ============================================================================
# CASOS DE TESTE
# ============================================================================

CASOS_TESTE = [
    # Previdenciário
    {"msg": "Quero me aposentar por idade", "area_esperada": "previdenciario"},
    {"msg": "Meu benefício do INSS foi negado", "area_esperada": "previdenciario"},
    {"msg": "O que é BPC LOAS?", "area_esperada": "previdenciario"},

    # Trabalhista
    {"msg": "Fui demitido e não recebi minhas verbas", "area_esperada": "trabalhista"},
    {"msg": "Meu patrão não paga horas extras", "area_esperada": "trabalhista"},
    {"msg": "Sofro assédio no trabalho", "area_esperada": "trabalhista"},

    # Família
    {"msg": "Quero me separar do meu marido", "area_esperada": "familia"},
    {"msg": "Preciso de pensão alimentícia para meu filho", "area_esperada": "familia"},
    {"msg": "Como faço inventário?", "area_esperada": "familia"},

    # Consumidor
    {"msg": "Meu nome foi negativado indevidamente", "area_esperada": "consumidor"},
    {"msg": "Comprei um produto com defeito", "area_esperada": "consumidor"},
    {"msg": "O plano de saúde negou minha cirurgia", "area_esperada": "consumidor"},

    # Civil
    {"msg": "Preciso de um contrato de locação", "area_esperada": "civil"},
    {"msg": "Quero cobrar uma dívida", "area_esperada": "civil"},

    # Genérico/Suporte
    {"msg": "Qual o horário de funcionamento?", "area_esperada": None},
    {"msg": "Onde fica o escritório?", "area_esperada": None},

    # Agendamento
    {"msg": "Quero agendar uma consulta", "area_esperada": None},
]


async def testar_deteccao_areas():
    """Testa a detecção de áreas"""
    print("\n" + "=" * 60)
    print("TESTE: DETECÇÃO DE ÁREAS")
    print("=" * 60)

    acertos = 0
    erros = 0

    for caso in CASOS_TESTE:
        msg = caso["msg"]
        esperada = caso["area_esperada"]

        # Testa por keywords
        areas_keywords = detect_areas_by_keywords(msg)

        # Verifica resultado
        if esperada is None:
            # Não deve detectar área
            passou = len(areas_keywords) == 0
        else:
            # Deve detectar a área esperada
            passou = esperada in areas_keywords

        status = "✓" if passou else "✗"
        if passou:
            acertos += 1
        else:
            erros += 1

        print(f"\n{status} \"{msg[:40]}...\"")
        print(f"   Esperado: {esperada or 'nenhuma'}")
        print(f"   Detectado: {areas_keywords or 'nenhuma'}")

    print(f"\n{'=' * 60}")
    print(f"RESULTADO: {acertos}/{len(CASOS_TESTE)} acertos ({acertos/len(CASOS_TESTE)*100:.0f}%)")

    return acertos == len(CASOS_TESTE)


async def testar_busca_rag():
    """Testa a busca no RAG"""
    print("\n" + "=" * 60)
    print("TESTE: BUSCA NO RAG")
    print("=" * 60)

    queries = [
        ("aposentadoria por idade requisitos", ["previdenciario"]),
        ("verbas rescisórias demissão", ["trabalhista"]),
        ("tipos de divórcio", ["familia"]),
        ("horário funcionamento", None),
    ]

    for query, areas in queries:
        print(f"\n• Query: \"{query}\"")
        print(f"  Áreas: {areas or 'todas'}")

        results = rag_advocacia_search_sync(
            query=query,
            area_ids=areas,
            limit=3
        )

        if results:
            print(f"  Resultados: {len(results)}")
            for doc in results[:2]:
                print(f"    - {doc['titulo'][:40]}...")
        else:
            print("  Nenhum resultado encontrado")


async def testar_agente_completo():
    """Testa o sistema multi-agente completo"""
    print("\n" + "=" * 60)
    print("TESTE: SISTEMA MULTI-AGENTE")
    print("=" * 60)

    mensagens_teste = [
        "Olá, quero me aposentar por idade. Tenho 63 anos e trabalhei 20 anos.",
        "Fui demitido há 1 ano e não recebi minhas verbas rescisórias",
        "Qual o horário de funcionamento do escritório?",
        "Quero agendar uma consulta"
    ]

    graph = create_advocacia_graph()

    for msg in mensagens_teste:
        print(f"\n{'─' * 50}")
        print(f"USUÁRIO: {msg}")

        try:
            result = await graph.ainvoke({
                "messages": [HumanMessage(content=msg)],
                "next_agent": None,
                "last_agent": None,
                "detected_areas": None,
                "telefone": None
            })

            # Pega resposta
            response = None
            for m in reversed(result["messages"]):
                if hasattr(m, "content") and not isinstance(m, HumanMessage):
                    response = m.content
                    break

            print(f"\nAGENTE USADO: {result.get('last_agent', 'desconhecido')}")
            print(f"ÁREAS DETECTADAS: {result.get('detected_areas', [])}")
            print(f"\nRESPOSTA: {response[:300]}..." if response and len(response) > 300 else f"\nRESPOSTA: {response}")

        except Exception as e:
            print(f"\nERRO: {e}")


async def main():
    """Executa todos os testes"""
    print("=" * 60)
    print("TESTES DO RAG ADVOCACIA")
    print("=" * 60)

    # Conecta ao banco
    print("\nConectando ao banco de dados...")
    await db_connect()
    print("Conectado!")

    # Menu de opções
    print("\nOpções de teste:")
    print("1. Testar detecção de áreas")
    print("2. Testar busca no RAG")
    print("3. Testar sistema multi-agente")
    print("4. Executar todos os testes")
    print("5. Sair")

    opcao = input("\nEscolha uma opção: ").strip()

    if opcao == "1":
        await testar_deteccao_areas()
    elif opcao == "2":
        await testar_busca_rag()
    elif opcao == "3":
        await testar_agente_completo()
    elif opcao == "4":
        await testar_deteccao_areas()
        await testar_busca_rag()
        await testar_agente_completo()
    else:
        print("Saindo...")

    print("\n" + "=" * 60)
    print("TESTES CONCLUÍDOS")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
