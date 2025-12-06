"""
Script de migração para criar tabelas do RAG Advocacia

Executa:
    python scripts/migrate_rag_advocacia.py

Este script:
1. Cria as tabelas do sistema RAG para advocacia:
   - areas_atuacao_advocacia (áreas do direito com prompts e keywords)
   - servicos_advocacia (serviços por área)
   - documentos_advocacia (base de conhecimento)
   - prompts_advocacia (prompts dos agentes suporte/agendamento)
   - perguntas_sem_resposta_advocacia (perguntas não respondidas)

2. Opcionalmente popula com áreas exemplo
"""
import asyncio
import sys
import os

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.database import db_connect, db_get_pool
from src.services.rag_advocacia import (
    rag_advocacia_init_tables,
    rag_advocacia_add_area,
    rag_advocacia_set_prompt
)


# Áreas de atuação exemplo com keywords para detecção
AREAS_EXEMPLO = [
    {
        "area_id": "previdenciario",
        "nome": "Direito Previdenciário",
        "descricao": "Aposentadorias, benefícios do INSS, pensões e auxílios",
        "keywords": [
            "aposentadoria", "aposentar", "inss", "benefício", "beneficio",
            "pensão", "pensao", "auxílio", "auxilio", "invalidez",
            "bpc", "loas", "tempo de contribuição", "contribuição",
            "previdência", "previdencia", "segurado", "carência",
            "incapacidade", "afastamento", "perícia", "pericia"
        ],
        "prompt_vendas": """Você é um especialista em Direito Previdenciário.

SCRIPT DE QUALIFICAÇÃO SDR:
1. Identifique o benefício que o cliente busca
2. Pergunte há quanto tempo contribui ou trabalhou
3. Verifique se já deu entrada no pedido
4. Se negado, pergunte o motivo da negativa
5. Qualifique o lead e ofereça agendamento

INFORMAÇÕES DISPONÍVEIS:
{contexto}

RESPONDA de forma empática e profissional, focando em qualificar o lead.""",
        "ordem": 1
    },
    {
        "area_id": "trabalhista",
        "nome": "Direito Trabalhista",
        "descricao": "Rescisões, verbas trabalhistas, assédio, horas extras",
        "keywords": [
            "demissão", "demissao", "rescisão", "rescisao", "trabalho",
            "trabalhista", "férias", "ferias", "13", "décimo terceiro",
            "fgts", "horas extras", "assédio", "assedio", "patrão",
            "empregador", "carteira assinada", "registro", "CLT",
            "salário", "salario", "justa causa", "aviso prévio"
        ],
        "prompt_vendas": """Você é um especialista em Direito Trabalhista.

SCRIPT DE QUALIFICAÇÃO SDR:
1. Identifique a situação trabalhista atual
2. Pergunte quando ocorreu a demissão/problema
3. Verifique quais verbas podem estar pendentes
4. Confirme se tem documentos (carteira, holerites)
5. Qualifique o lead e ofereça agendamento

INFORMAÇÕES DISPONÍVEIS:
{contexto}

RESPONDA de forma empática e profissional, focando em qualificar o lead.""",
        "ordem": 2
    },
    {
        "area_id": "familia",
        "nome": "Direito de Família",
        "descricao": "Divórcio, pensão alimentícia, guarda, inventário",
        "keywords": [
            "divórcio", "divorcio", "separação", "separacao", "guarda",
            "pensão alimentícia", "pensao alimenticia", "alimentos",
            "filho", "filha", "criança", "custódia", "custodia",
            "casamento", "união estável", "uniao estavel", "inventário",
            "inventario", "herança", "heranca", "partilha", "bens"
        ],
        "prompt_vendas": """Você é um especialista em Direito de Família.

SCRIPT DE QUALIFICAÇÃO SDR:
1. Identifique a situação familiar (divórcio, guarda, pensão)
2. Pergunte se é consensual ou litigioso
3. Verifique se há filhos menores envolvidos
4. Confirme questões sobre bens a partilhar
5. Qualifique o lead e ofereça agendamento

INFORMAÇÕES DISPONÍVEIS:
{contexto}

RESPONDA de forma empática e sensível, focando em qualificar o lead.""",
        "ordem": 3
    },
    {
        "area_id": "consumidor",
        "nome": "Direito do Consumidor",
        "descricao": "Problemas com empresas, produtos, serviços, cobranças indevidas",
        "keywords": [
            "consumidor", "produto", "defeito", "empresa", "cobrança",
            "cobranca", "indevida", "serasa", "spc", "nome sujo",
            "negativação", "negativacao", "devolução", "devolucao",
            "garantia", "propaganda enganosa", "contrato", "cancelar",
            "reembolso", "estorno", "reclamação", "reclamacao"
        ],
        "prompt_vendas": """Você é um especialista em Direito do Consumidor.

SCRIPT DE QUALIFICAÇÃO SDR:
1. Identifique o problema com a empresa/produto
2. Pergunte quando ocorreu e qual empresa
3. Verifique se já tentou resolver diretamente
4. Confirme se tem provas (prints, notas, contratos)
5. Qualifique o lead e ofereça agendamento

INFORMAÇÕES DISPONÍVEIS:
{contexto}

RESPONDA de forma empática e profissional, focando em qualificar o lead.""",
        "ordem": 4
    },
    {
        "area_id": "civil",
        "nome": "Direito Civil",
        "descricao": "Contratos, indenizações, cobranças, propriedade",
        "keywords": [
            "contrato", "indenização", "indenizacao", "danos morais",
            "danos materiais", "cobrança", "cobranca", "dívida", "divida",
            "acordo", "propriedade", "imóvel", "imovel", "aluguel",
            "despejo", "locação", "locacao", "usucapião", "usucapiao"
        ],
        "prompt_vendas": """Você é um especialista em Direito Civil.

SCRIPT DE QUALIFICAÇÃO SDR:
1. Identifique a natureza do problema civil
2. Pergunte sobre valores e partes envolvidas
3. Verifique se há contrato ou documentação
4. Confirme o prazo desde o ocorrido
5. Qualifique o lead e ofereça agendamento

INFORMAÇÕES DISPONÍVEIS:
{contexto}

RESPONDA de forma empática e profissional, focando em qualificar o lead.""",
        "ordem": 5
    }
]

# Prompts dos agentes suporte e agendamento
PROMPTS_AGENTES = [
    {
        "agente": "suporte",
        "prompt": """Você é o assistente de suporte do escritório de advocacia.

OBJETIVO:
Responder dúvidas gerais sobre o escritório e seus serviços.

INFORMAÇÕES DISPONÍVEIS:
{contexto}

REGRAS:
1. Se a pergunta for sobre uma área específica do direito, direcione para vendas
2. Responda de forma clara e objetiva
3. Se não souber a resposta, ofereça falar com um atendente especializado

IMPORTANTE: Se não encontrar informações para responder, diga:
"Não encontrei informações específicas sobre isso. Deseja falar com nosso atendimento especializado?"
"""
    },
    {
        "agente": "agendamento",
        "prompt": """Você é o assistente de agendamento do escritório de advocacia.

OBJETIVO:
Ajudar o cliente a agendar uma consulta.

INFORMAÇÕES:
{contexto}

PROCESSO:
1. Confirme a área de interesse do cliente
2. Informe os horários disponíveis
3. Colete: nome completo, telefone, email
4. Confirme o agendamento

HORÁRIOS DISPONÍVEIS:
- Segunda a Sexta: 9h às 18h
- Sábado: 9h às 12h

Responda de forma cordial e eficiente.
"""
    }
]


async def migrate(popular_exemplo: bool = False):
    """Executa a migração"""
    print("=" * 60)
    print("MIGRAÇÃO RAG ADVOCACIA")
    print("=" * 60)

    # Inicializa conexão com banco
    print("\n[1/3] Conectando ao banco de dados...")
    await db_connect()
    print("      ✓ Conectado!")

    # Cria tabelas do RAG Advocacia
    print("\n[2/3] Criando tabelas do RAG Advocacia...")
    success = await rag_advocacia_init_tables()

    if success:
        print("      ✓ Tabelas criadas com sucesso!")
        print("        - areas_atuacao_advocacia")
        print("        - servicos_advocacia")
        print("        - documentos_advocacia")
        print("        - prompts_advocacia")
        print("        - perguntas_sem_resposta_advocacia")
    else:
        print("      ✗ ERRO: Falha ao criar tabelas")
        return False

    # Popular com dados exemplo (opcional)
    if popular_exemplo:
        print("\n[3/3] Populando com dados exemplo...")
        await popular_dados_exemplo()
    else:
        print("\n[3/3] Pulando população de dados (use --popular para popular).")

    print("\n" + "=" * 60)
    print("MIGRAÇÃO CONCLUÍDA COM SUCESSO!")
    print("=" * 60)

    print("\nPróximos passos:")
    print("1. Execute 'python scripts/popular_rag_advocacia.py' para popular a base")
    print("2. Ou adicione dados via API/admin")
    print("3. Configure os prompts de cada área no banco")

    return True


async def popular_dados_exemplo():
    """Popula com dados exemplo"""

    # 1. Criar áreas de atuação
    print("\n      Criando áreas de atuação...")
    for area in AREAS_EXEMPLO:
        try:
            await rag_advocacia_add_area(
                area_id=area["area_id"],
                nome=area["nome"],
                prompt_vendas=area["prompt_vendas"],
                keywords=area["keywords"],
                descricao=area["descricao"],
                ordem=area["ordem"]
            )
            print(f"        ✓ {area['nome']}")
        except Exception as e:
            # Pode já existir
            if "duplicate key" in str(e).lower() or "already exists" in str(e).lower():
                print(f"        → {area['nome']} (já existe)")
            else:
                print(f"        ✗ {area['nome']}: {e}")

    # 2. Criar prompts dos agentes
    print("\n      Criando prompts dos agentes...")
    for prompt_data in PROMPTS_AGENTES:
        try:
            await rag_advocacia_set_prompt(
                agente=prompt_data["agente"],
                prompt=prompt_data["prompt"]
            )
            print(f"        ✓ Agente: {prompt_data['agente']}")
        except Exception as e:
            print(f"        ✗ Agente {prompt_data['agente']}: {e}")

    print("\n      ✓ Dados exemplo populados!")
    print(f"        - {len(AREAS_EXEMPLO)} áreas de atuação")
    print(f"        - {len(PROMPTS_AGENTES)} prompts de agentes")


async def listar_areas():
    """Lista as áreas cadastradas"""
    from src.services.rag_advocacia import rag_advocacia_list_areas

    await db_connect()
    areas = await rag_advocacia_list_areas()

    print("\n" + "=" * 60)
    print("ÁREAS DE ATUAÇÃO CADASTRADAS")
    print("=" * 60)

    if not areas:
        print("\nNenhuma área cadastrada.")
        return

    for area in areas:
        print(f"\n[{area['area_id']}] {area['nome']}")
        print(f"    Descrição: {area.get('descricao', '-')}")
        print(f"    Keywords: {len(area.get('keywords', []))} palavras-chave")
        print(f"    Ativo: {'Sim' if area.get('ativo') else 'Não'}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Migração RAG Advocacia")
    parser.add_argument("--popular", action="store_true",
                        help="Popular com dados exemplo (áreas, prompts)")
    parser.add_argument("--listar", action="store_true",
                        help="Listar áreas cadastradas")
    args = parser.parse_args()

    if args.listar:
        asyncio.run(listar_areas())
    else:
        asyncio.run(migrate(popular_exemplo=args.popular))
