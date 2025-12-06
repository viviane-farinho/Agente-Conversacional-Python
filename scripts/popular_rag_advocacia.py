"""
Script para popular a base de conhecimento do RAG Advocacia

Executa:
    python scripts/popular_rag_advocacia.py

Este script popula:
1. Áreas de atuação com prompts e keywords
2. Serviços por área
3. Documentos de exemplo na base de conhecimento
4. Prompts dos agentes suporte e agendamento
"""
import asyncio
import sys
import os

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.database import db_connect
from src.services.rag_advocacia import (
    rag_advocacia_init_tables,
    rag_advocacia_add_area,
    rag_advocacia_add_servico,
    rag_advocacia_add_document,
    rag_advocacia_set_prompt
)


# ============================================================================
# ÁREAS DE ATUAÇÃO
# ============================================================================

AREAS = [
    {
        "area_id": "previdenciario",
        "nome": "Direito Previdenciário",
        "descricao": "Aposentadorias, benefícios do INSS, pensões e auxílios",
        "keywords": [
            "aposentadoria", "aposentar", "inss", "benefício", "beneficio",
            "pensão", "pensao", "auxílio", "auxilio", "invalidez",
            "bpc", "loas", "tempo de contribuição", "contribuição",
            "previdência", "previdencia", "previdenciário", "previdenciario",
            "direito previdenciário", "direito previdenciario",
            "segurado", "carência", "incapacidade", "afastamento",
            "perícia", "pericia", "aposentadoria por idade", "aposentadoria por tempo"
        ],
        "prompt_vendas": """Você é um assistente de qualificação em Direito Previdenciário do nosso escritório.

SCRIPT DE QUALIFICAÇÃO SDR:
1. IDENTIFICAR: "Qual benefício você está buscando? Aposentadoria, auxílio-doença, BPC/LOAS?"
2. TEMPO: "Há quanto tempo você contribui para o INSS?" ou "Há quanto tempo está afastado?"
3. SITUAÇÃO: "Você já deu entrada no pedido? Foi negado?"
4. DOCUMENTAÇÃO: "Você tem em mãos sua carteira de trabalho e carnês de contribuição?"
5. QUALIFICAR: Baseado nas respostas, identifique se é um caso válido

INFORMAÇÕES DISPONÍVEIS (USE APENAS ESTAS):
{contexto}

⚠️ REGRAS IMPORTANTES - SIGA RIGOROSAMENTE:
1. NUNCA invente informações que não estejam no contexto acima
2. Se não encontrar a informação no contexto, diga: "Não tenho essa informação específica, mas posso agendar uma consulta com nosso especialista para esclarecer suas dúvidas."
3. NÃO forneça detalhes técnicos sobre benefícios que não estejam no contexto
4. Seja empático, muitos clientes estão em situação difícil
5. NÃO dê pareceres definitivos, apenas qualifique o lead
6. Foque em entender o caso e agendar consulta
7. Use linguagem simples, evite juridiquês

QUANDO NÃO SOUBER A RESPOSTA:
Essa é uma dúvida importante! Para dar uma resposta precisa sobre seu caso, sugiro agendarmos uma consulta com nosso especialista em previdenciário. Posso verificar os horários disponíveis?""",
        "ordem": 1
    },
    {
        "area_id": "trabalhista",
        "nome": "Direito Trabalhista",
        "descricao": "Rescisões, verbas trabalhistas, assédio, horas extras",
        "keywords": [
            "demissão", "demissao", "demitido", "rescisão", "rescisao",
            "trabalho", "trabalhista", "direito trabalhista",
            "férias", "ferias", "13", "décimo terceiro", "fgts",
            "horas extras", "hora extra", "assédio", "assedio",
            "patrão", "patrao", "empregador", "carteira assinada",
            "registro", "CLT", "salário", "salario", "justa causa",
            "aviso prévio", "aviso previo", "acordo",
            "verbas rescisórias", "verbas rescisorias", "acidente trabalho"
        ],
        "prompt_vendas": """Você é um especialista em Direito Trabalhista do nosso escritório.

SCRIPT DE QUALIFICAÇÃO SDR:
1. SITUAÇÃO: "Você ainda está trabalhando ou já foi desligado?"
2. TEMPO: "Há quanto tempo trabalhou/trabalha na empresa?"
3. PROBLEMA: "Qual o principal problema? Verbas não pagas, demissão injusta, assédio?"
4. PRAZO: "Quando ocorreu a demissão/problema?" (IMPORTANTE: prazo de 2 anos!)
5. DOCUMENTAÇÃO: "Você tem carteira de trabalho, holerites, e-mails?"

INFORMAÇÕES DISPONÍVEIS:
{contexto}

REGRAS:
- ATENÇÃO ao prazo de 2 anos para entrar com ação trabalhista
- Seja empático com situações de assédio
- Não prometa valores, apenas qualifique
- Sugira agendamento urgente se prazo estiver acabando""",
        "ordem": 2
    },
    {
        "area_id": "familia",
        "nome": "Direito de Família",
        "descricao": "Divórcio, pensão alimentícia, guarda, inventário",
        "keywords": [
            "divórcio", "divorcio", "separação", "separacao", "separar",
            "guarda", "filho", "filha", "filhos", "criança", "crianca",
            "pensão alimentícia", "pensao alimenticia", "pensão", "pensao",
            "alimentos", "custódia", "custodia", "casamento",
            "união estável", "uniao estavel", "inventário", "inventario",
            "herança", "heranca", "partilha", "bens", "patrimônio",
            "patrimonio", "testamento", "sucessão", "sucessao"
        ],
        "prompt_vendas": """Você é um especialista em Direito de Família do nosso escritório.

SCRIPT DE QUALIFICAÇÃO SDR:
1. SITUAÇÃO: "Você precisa de ajuda com divórcio, guarda, pensão ou inventário?"
2. CONSENSO: "A outra parte concorda ou será litigioso?"
3. FILHOS: "Há filhos menores de idade envolvidos?"
4. BENS: "Há bens a serem partilhados (imóveis, veículos, etc.)?"
5. URGÊNCIA: "Há alguma situação urgente? Violência, risco aos filhos?"

INFORMAÇÕES DISPONÍVEIS:
{contexto}

REGRAS:
- Seja muito sensível, são situações emocionalmente difíceis
- Priorize casos com violência ou risco aos filhos
- Não tome partido, mantenha neutralidade profissional
- Divórcio consensual é mais rápido e barato - informe isso""",
        "ordem": 3
    },
    {
        "area_id": "consumidor",
        "nome": "Direito do Consumidor",
        "descricao": "Problemas com empresas, produtos, serviços, cobranças indevidas",
        "keywords": [
            "consumidor", "produto", "defeito", "empresa", "cobrança",
            "cobranca", "indevida", "serasa", "spc", "nome sujo",
            "negativação", "negativacao", "negativado", "negativada",
            "devolução", "devolucao", "garantia", "propaganda enganosa",
            "contrato", "cancelar", "reembolso", "estorno",
            "reclamação", "reclamacao", "procon", "danos morais",
            "plano de saúde", "plano de saude", "banco", "cartão",
            "cartao", "empréstimo", "emprestimo"
        ],
        "prompt_vendas": """Você é um especialista em Direito do Consumidor do nosso escritório.

SCRIPT DE QUALIFICAÇÃO SDR:
1. PROBLEMA: "Qual empresa e qual foi o problema?"
2. QUANDO: "Quando isso aconteceu?"
3. TENTATIVA: "Você já tentou resolver diretamente com a empresa? Abriu reclamação?"
4. PROVAS: "Você tem prints, notas fiscais, contratos, protocolos?"
5. VALOR: "Qual o valor envolvido ou prejuízo sofrido?"

INFORMAÇÕES DISPONÍVEIS:
{contexto}

REGRAS:
- Casos de nome sujo indevido têm urgência
- Verifique se cliente já tentou SAC/Ouvidoria/Procon
- Casos pequenos podem não compensar ação judicial
- Danos morais dependem da gravidade do caso""",
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
            "despejo", "locação", "locacao", "usucapião", "usucapiao",
            "vizinho", "barulho", "condomínio", "condominio"
        ],
        "prompt_vendas": """Você é um especialista em Direito Civil do nosso escritório.

SCRIPT DE QUALIFICAÇÃO SDR:
1. NATUREZA: "É sobre contrato, imóvel, indenização ou cobrança?"
2. PARTES: "Quem são as partes envolvidas?"
3. VALOR: "Qual o valor envolvido na questão?"
4. DOCUMENTAÇÃO: "Você tem o contrato ou documentos relacionados?"
5. PRAZO: "Quando ocorreu o fato? Há quanto tempo está tentando resolver?"

INFORMAÇÕES DISPONÍVEIS:
{contexto}

REGRAS:
- Verifique prazos de prescrição
- Contratos devem ser analisados com cuidado
- Questões de imóvel podem envolver registro
- Avalie se vale a pena judicializar pelo valor""",
        "ordem": 5
    }
]


# ============================================================================
# SERVIÇOS POR ÁREA
# ============================================================================

SERVICOS = [
    # Previdenciário
    {"servico_id": "aposentadoria_idade", "area_id": "previdenciario", "nome": "Aposentadoria por Idade", "descricao": "Para quem atingiu idade mínima e tempo de contribuição"},
    {"servico_id": "aposentadoria_tempo", "area_id": "previdenciario", "nome": "Aposentadoria por Tempo de Contribuição", "descricao": "Para quem completou o tempo mínimo de contribuição"},
    {"servico_id": "aposentadoria_invalidez", "area_id": "previdenciario", "nome": "Aposentadoria por Invalidez", "descricao": "Para incapacidade permanente para o trabalho"},
    {"servico_id": "auxilio_doenca", "area_id": "previdenciario", "nome": "Auxílio-Doença", "descricao": "Benefício para incapacidade temporária"},
    {"servico_id": "bpc_loas", "area_id": "previdenciario", "nome": "BPC/LOAS", "descricao": "Benefício assistencial para idosos e deficientes"},
    {"servico_id": "pensao_morte", "area_id": "previdenciario", "nome": "Pensão por Morte", "descricao": "Benefício para dependentes de segurado falecido"},
    {"servico_id": "revisao_beneficio", "area_id": "previdenciario", "nome": "Revisão de Benefício", "descricao": "Revisão de valor de aposentadoria ou benefício"},

    # Trabalhista
    {"servico_id": "rescisao_indireta", "area_id": "trabalhista", "nome": "Rescisão Indireta", "descricao": "Quando o empregador comete falta grave"},
    {"servico_id": "verbas_rescisorias", "area_id": "trabalhista", "nome": "Verbas Rescisórias", "descricao": "Cobrança de verbas não pagas na demissão"},
    {"servico_id": "horas_extras", "area_id": "trabalhista", "nome": "Horas Extras", "descricao": "Cobrança de horas extras não pagas"},
    {"servico_id": "assedio_moral", "area_id": "trabalhista", "nome": "Assédio Moral/Sexual", "descricao": "Indenização por assédio no trabalho"},
    {"servico_id": "acidente_trabalho", "area_id": "trabalhista", "nome": "Acidente de Trabalho", "descricao": "Indenização por acidente ou doença ocupacional"},
    {"servico_id": "reconhecimento_vinculo", "area_id": "trabalhista", "nome": "Reconhecimento de Vínculo", "descricao": "Para quem trabalhou sem carteira assinada"},

    # Família
    {"servico_id": "divorcio_consensual", "area_id": "familia", "nome": "Divórcio Consensual", "descricao": "Divórcio quando ambos concordam"},
    {"servico_id": "divorcio_litigioso", "area_id": "familia", "nome": "Divórcio Litigioso", "descricao": "Divórcio quando há conflito entre as partes"},
    {"servico_id": "guarda_filhos", "area_id": "familia", "nome": "Guarda de Filhos", "descricao": "Definição ou modificação de guarda"},
    {"servico_id": "pensao_alimenticia", "area_id": "familia", "nome": "Pensão Alimentícia", "descricao": "Fixação, revisão ou execução de alimentos"},
    {"servico_id": "inventario", "area_id": "familia", "nome": "Inventário", "descricao": "Partilha de bens de pessoa falecida"},
    {"servico_id": "uniao_estavel", "area_id": "familia", "nome": "União Estável", "descricao": "Reconhecimento ou dissolução de união estável"},

    # Consumidor
    {"servico_id": "negativacao_indevida", "area_id": "consumidor", "nome": "Negativação Indevida", "descricao": "Nome negativado indevidamente em SPC/Serasa"},
    {"servico_id": "cobranca_indevida", "area_id": "consumidor", "nome": "Cobrança Indevida", "descricao": "Cobrança de valores não devidos"},
    {"servico_id": "produto_defeituoso", "area_id": "consumidor", "nome": "Produto Defeituoso", "descricao": "Produto com vício ou defeito"},
    {"servico_id": "plano_saude", "area_id": "consumidor", "nome": "Plano de Saúde", "descricao": "Negativa de cobertura ou reajuste abusivo"},
    {"servico_id": "contratos_bancarios", "area_id": "consumidor", "nome": "Contratos Bancários", "descricao": "Revisão de juros e cláusulas abusivas"},

    # Civil
    {"servico_id": "contratos", "area_id": "civil", "nome": "Contratos", "descricao": "Elaboração, análise e rescisão de contratos"},
    {"servico_id": "indenizacao", "area_id": "civil", "nome": "Indenização", "descricao": "Ações de indenização por danos"},
    {"servico_id": "cobranca", "area_id": "civil", "nome": "Cobrança", "descricao": "Cobrança judicial de dívidas"},
    {"servico_id": "despejo", "area_id": "civil", "nome": "Despejo", "descricao": "Ação de despejo por falta de pagamento"},
    {"servico_id": "usucapiao", "area_id": "civil", "nome": "Usucapião", "descricao": "Aquisição de propriedade por posse prolongada"}
]


# ============================================================================
# DOCUMENTOS DE EXEMPLO
# ============================================================================

DOCUMENTOS = [
    # Previdenciário
    {
        "titulo": "Requisitos para Aposentadoria por Idade",
        "area_id": "previdenciario",
        "servico_id": "aposentadoria_idade",
        "conteudo": """A aposentadoria por idade exige:

IDADE MÍNIMA:
- Homens: 65 anos
- Mulheres: 62 anos

TEMPO DE CONTRIBUIÇÃO:
- Mínimo de 15 anos de contribuição ao INSS

DOCUMENTOS NECESSÁRIOS:
- RG e CPF
- Carteira de trabalho
- Carnês de contribuição (se autônomo)
- Certidão de nascimento ou casamento

VALOR DO BENEFÍCIO:
- 60% da média salarial + 2% por ano que exceder 15 anos de contribuição

Nosso escritório analisa seu histórico contributivo para garantir o melhor benefício possível.""",
        "categoria": "requisitos",
        "agente": "vendas"
    },
    {
        "titulo": "O que é BPC/LOAS e quem tem direito",
        "area_id": "previdenciario",
        "servico_id": "bpc_loas",
        "conteudo": """O BPC (Benefício de Prestação Continuada) é um benefício assistencial no valor de 1 salário mínimo.

QUEM TEM DIREITO:
1. Idosos com 65 anos ou mais
2. Pessoas com deficiência de qualquer idade

REQUISITOS:
- Renda familiar per capita de até 1/4 do salário mínimo
- Não é necessário ter contribuído ao INSS
- Estar inscrito no CadÚnico

DOCUMENTOS:
- RG e CPF
- Comprovante de residência
- Comprovante de renda familiar
- Laudo médico (para deficientes)

IMPORTANTE:
- O BPC não gera pensão por morte
- Não dá direito a 13º salário
- Deve ser revisado a cada 2 anos

Ajudamos você a comprovar os requisitos e dar entrada no benefício.""",
        "categoria": "requisitos",
        "agente": "vendas"
    },

    # Trabalhista
    {
        "titulo": "Prazo para entrar com Ação Trabalhista",
        "area_id": "trabalhista",
        "servico_id": "verbas_rescisorias",
        "conteudo": """ATENÇÃO AO PRAZO!

O trabalhador tem o prazo de 2 ANOS após o término do contrato para entrar com ação trabalhista.

IMPORTANTE:
- O prazo começa a contar da data da demissão
- Pode cobrar os últimos 5 anos trabalhados
- Após 2 anos, perde o direito de reclamar na justiça

EXEMPLO:
Se você foi demitido em 01/01/2023, tem até 01/01/2025 para entrar com ação.
Pode cobrar direitos desde 01/01/2018 (5 anos antes da demissão).

SE O PRAZO ESTÁ ACABANDO:
- Agende uma consulta urgente
- Junte todos os documentos que tiver
- Não deixe para a última hora

Nosso escritório faz análise gratuita do seu caso.""",
        "categoria": "prazo",
        "agente": "vendas"
    },
    {
        "titulo": "Verbas devidas na Rescisão",
        "area_id": "trabalhista",
        "servico_id": "verbas_rescisorias",
        "conteudo": """Na demissão sem justa causa, você tem direito a:

VERBAS RESCISÓRIAS:
- Saldo de salário
- Aviso prévio (trabalhado ou indenizado)
- 13º salário proporcional
- Férias vencidas + 1/3
- Férias proporcionais + 1/3
- FGTS + multa de 40%
- Seguro-desemprego (se cumprir requisitos)

PRAZO DE PAGAMENTO:
- Até 10 dias corridos após o término do contrato

SE NÃO PAGAR NO PRAZO:
- Multa de 1 salário por dia de atraso (limitado a 1 salário)

DOCUMENTOS PARA CONSULTA:
- Carteira de trabalho
- Termo de rescisão
- Últimos holerites
- Extrato do FGTS

Analisamos seu termo de rescisão gratuitamente.""",
        "categoria": "direitos",
        "agente": "vendas"
    },

    # Família
    {
        "titulo": "Tipos de Divórcio",
        "area_id": "familia",
        "servico_id": "divorcio_consensual",
        "conteudo": """Existem dois tipos de divórcio:

1. DIVÓRCIO CONSENSUAL
Quando o casal concorda em tudo:
- Pode ser feito em cartório (se não houver filhos menores)
- Mais rápido e mais barato
- Precisa de advogado para ambos
- Prazo: 30 a 60 dias

2. DIVÓRCIO LITIGIOSO
Quando há conflito:
- Obrigatoriamente judicial
- Mais demorado e custoso
- Cada parte com seu advogado
- Prazo: 6 meses a 2 anos

O QUE É DECIDIDO:
- Partilha de bens
- Guarda dos filhos
- Pensão alimentícia
- Uso do nome de casado

DOCUMENTOS NECESSÁRIOS:
- Certidão de casamento
- RG e CPF
- Documentos dos bens
- Certidão de nascimento dos filhos

Ajudamos você a escolher a melhor opção para seu caso.""",
        "categoria": "tipos",
        "agente": "vendas"
    },

    # Informações gerais (suporte)
    {
        "titulo": "Sobre nosso escritório",
        "area_id": None,
        "servico_id": None,
        "conteudo": """Somos um escritório de advocacia especializado em defender os direitos do cidadão.

ÁREAS DE ATUAÇÃO:
- Direito Previdenciário (aposentadorias, INSS)
- Direito Trabalhista (rescisões, verbas)
- Direito de Família (divórcio, guarda, pensão)
- Direito do Consumidor (cobranças, danos)
- Direito Civil (contratos, indenizações)

DIFERENCIAIS:
- Primeira consulta gratuita
- Atendimento humanizado
- Equipe especializada
- Acompanhamento do caso

HORÁRIO DE FUNCIONAMENTO:
- Segunda a Sexta: 9h às 18h
- Sábado: 9h às 12h

FORMAS DE PAGAMENTO:
- À vista com desconto
- Parcelamento no cartão
- Honorários após ganho da causa (em alguns casos)""",
        "categoria": "institucional",
        "agente": "suporte"
    },
    {
        "titulo": "Como funciona a consulta",
        "area_id": None,
        "servico_id": None,
        "conteudo": """A primeira consulta serve para:

1. ENTENDER SEU CASO
Você nos conta sua situação e apresenta documentos.

2. ANALISAR POSSIBILIDADES
Nossa equipe avalia as opções jurídicas disponíveis.

3. ESCLARECER DÚVIDAS
Tiramos todas as suas dúvidas sobre o processo.

4. APRESENTAR PROPOSTA
Se houver possibilidade de ação, apresentamos valores e prazos.

DOCUMENTOS PARA TRAZER:
- Documento de identidade
- Documentos relacionados ao caso
- Comprovante de residência

DURAÇÃO:
- Aproximadamente 30 a 60 minutos

CUSTO:
- Primeira consulta é gratuita para análise inicial

AGENDAMENTO:
- Por telefone, WhatsApp ou neste chat""",
        "categoria": "institucional",
        "agente": "suporte"
    }
]


# ============================================================================
# PROMPTS DOS AGENTES
# ============================================================================

PROMPTS_AGENTES = [
    {
        "agente": "suporte",
        "prompt": """Você é o assistente de suporte do escritório de advocacia.

OBJETIVO:
Responder dúvidas gerais sobre o escritório e seus serviços.

INFORMAÇÕES DISPONÍVEIS:
{contexto}

REGRAS:
1. Se a pergunta for sobre uma área específica do direito, transfira para vendas
2. Responda de forma clara e objetiva
3. Se não souber a resposta, use a frase abaixo

QUANDO NÃO SOUBER:
"Não encontrei informações específicas sobre isso. Deseja falar com nosso atendimento especializado?"

Seja sempre cordial e profissional."""
    },
    {
        "agente": "agendamento",
        "prompt": """Você é o assistente de agendamento do escritório de advocacia.

OBJETIVO:
Ajudar o cliente a agendar uma consulta jurídica.

DADOS NECESSÁRIOS:
1. Nome completo
2. Telefone para contato
3. Área de interesse (se souber)
4. Breve descrição do caso

HORÁRIOS DISPONÍVEIS:
- Segunda a Sexta: 9h às 18h
- Sábado: 9h às 12h

PROCESSO:
1. Pergunte a área de interesse (opcional)
2. Colete nome e telefone
3. Sugira horários
4. Confirme o agendamento

REGRAS:
- Seja cordial e eficiente
- Não faça muitas perguntas de uma vez
- Confirme os dados antes de finalizar
- Informe que a equipe entrará em contato

Responda de forma profissional e acolhedora."""
    }
]


# ============================================================================
# FUNÇÃO PRINCIPAL
# ============================================================================

async def popular():
    """Popula a base de conhecimento do RAG Advocacia"""
    print("=" * 60)
    print("POPULAR RAG ADVOCACIA")
    print("=" * 60)

    # Conecta ao banco
    print("\n[1/5] Conectando ao banco de dados...")
    await db_connect()
    print("      ✓ Conectado!")

    # Garante que tabelas existem
    print("\n[2/5] Verificando tabelas...")
    await rag_advocacia_init_tables()
    print("      ✓ Tabelas verificadas!")

    # Popula áreas
    print("\n[3/5] Populando áreas de atuação...")
    for area in AREAS:
        try:
            await rag_advocacia_add_area(
                area_id=area["area_id"],
                nome=area["nome"],
                prompt_vendas=area["prompt_vendas"],
                keywords=area["keywords"],
                descricao=area["descricao"],
                ordem=area["ordem"]
            )
            print(f"      ✓ {area['nome']}")
        except Exception as e:
            if "duplicate" in str(e).lower():
                print(f"      → {area['nome']} (já existe)")
            else:
                print(f"      ✗ {area['nome']}: {e}")

    # Popula serviços
    print("\n[4/5] Populando serviços...")
    for servico in SERVICOS:
        try:
            await rag_advocacia_add_servico(
                servico_id=servico["servico_id"],
                area_id=servico["area_id"],
                nome=servico["nome"],
                descricao=servico["descricao"]
            )
            print(f"      ✓ {servico['nome']}")
        except Exception as e:
            if "duplicate" in str(e).lower():
                print(f"      → {servico['nome']} (já existe)")
            else:
                print(f"      ✗ {servico['nome']}: {e}")

    # Popula documentos
    print("\n[5/5] Populando documentos...")
    for doc in DOCUMENTOS:
        try:
            # Categoria vai dentro do metadata
            metadata = {"categoria": doc.get("categoria")} if doc.get("categoria") else {}
            await rag_advocacia_add_document(
                titulo=doc["titulo"],
                conteudo=doc["conteudo"],
                area_id=doc.get("area_id"),
                servico_id=doc.get("servico_id"),
                agente=doc.get("agente"),
                metadata=metadata
            )
            print(f"      ✓ {doc['titulo'][:40]}...")
        except Exception as e:
            if "duplicate" in str(e).lower():
                print(f"      → {doc['titulo'][:40]}... (já existe)")
            else:
                print(f"      ✗ {doc['titulo'][:40]}...: {e}")

    # Popula prompts dos agentes
    print("\n[EXTRA] Populando prompts dos agentes...")
    for prompt_data in PROMPTS_AGENTES:
        try:
            await rag_advocacia_set_prompt(
                agente=prompt_data["agente"],
                prompt=prompt_data["prompt"]
            )
            print(f"      ✓ Agente: {prompt_data['agente']}")
        except Exception as e:
            print(f"      ✗ Agente {prompt_data['agente']}: {e}")

    print("\n" + "=" * 60)
    print("POPULAÇÃO CONCLUÍDA!")
    print("=" * 60)

    print(f"\nResumo:")
    print(f"  - {len(AREAS)} áreas de atuação")
    print(f"  - {len(SERVICOS)} serviços")
    print(f"  - {len(DOCUMENTOS)} documentos")
    print(f"  - {len(PROMPTS_AGENTES)} prompts de agentes")

    print("\nPróximos passos:")
    print("  1. Teste o sistema com: python scripts/testar_rag_advocacia.py")
    print("  2. Adicione mais documentos conforme necessário")
    print("  3. Ajuste os prompts das áreas no banco de dados")


if __name__ == "__main__":
    asyncio.run(popular())
