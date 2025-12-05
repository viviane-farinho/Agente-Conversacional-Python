"""
Script para configurar base de conhecimento e agentes para Infoprodutor.
Executa: python scripts/setup_infoprodutor.py
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# ============================================
# BASE DE CONHECIMENTO - INFOPRODUTOR
# ============================================

DOCUMENTOS = [
    # --- SOBRE O MENTOR ---
    {
        "titulo": "Sobre o Mentor - Rafael Oliveira",
        "categoria": "sobre",
        "conteudo": """
# Rafael Oliveira - Mentor de Negócios Digitais

Rafael Oliveira é especialista em marketing digital e criação de infoprodutos, com mais de 10 anos de experiência no mercado.

## Trajetória
- Começou como afiliado em 2014
- Lançou seu primeiro curso em 2016
- Já faturou mais de R$ 15 milhões com infoprodutos
- Mentorou mais de 3.000 alunos
- Criador do Método 6 em 7 Simplificado

## Especialidades
- Lançamentos digitais
- Criação de cursos online
- Funis de vendas
- Tráfego pago (Meta Ads e Google Ads)
- Copywriting para vendas

## Redes Sociais
- Instagram: @rafaeloliveira.digital
- YouTube: Rafael Oliveira Digital
- Podcast: Papo de Infoprodutor (Spotify)

## Contato Comercial
- WhatsApp: Este canal
- Email: contato@rafaeloliveira.com.br
"""
    },

    # --- CURSOS ---
    {
        "titulo": "Curso Método 6 em 7 Simplificado",
        "categoria": "cursos",
        "conteudo": """
# Método 6 em 7 Simplificado

O curso mais completo para você fazer seu primeiro 6 em 7 (R$ 100.000 em 7 dias).

## O que você vai aprender:
- Módulo 1: Mentalidade do Infoprodutor de Sucesso
- Módulo 2: Escolhendo seu Nicho Lucrativo
- Módulo 3: Criando sua Oferta Irresistível
- Módulo 4: Estrutura do Lançamento Perfeito
- Módulo 5: Captação de Leads
- Módulo 6: Semana de Aquecimento
- Módulo 7: Abertura do Carrinho
- Módulo 8: Fechamento com Escassez
- Módulo 9: Pós-venda e Retenção

## Bônus Exclusivos:
- Templates de copy prontos para usar
- Planilha de planejamento de lançamento
- Acesso à comunidade VIP no Telegram
- 3 lives mensais de tira-dúvidas

## Investimento:
- **À vista:** R$ 1.997,00
- **Parcelado:** 12x de R$ 197,00

## Garantia:
7 dias de garantia incondicional. Se não gostar, devolvemos 100% do seu dinheiro.

## Acesso:
- Acesso vitalício à plataforma
- Atualizações gratuitas para sempre
- Certificado de conclusão

## Para quem é:
- Iniciantes que querem começar no digital
- Profissionais que querem monetizar conhecimento
- Empreendedores buscando escalar online
"""
    },
    {
        "titulo": "Curso Tráfego Descomplicado",
        "categoria": "cursos",
        "conteudo": """
# Tráfego Descomplicado

Aprenda a criar campanhas de tráfego pago que convertem, mesmo começando do zero.

## Conteúdo:
- Meta Ads (Facebook e Instagram) do básico ao avançado
- Google Ads para infoprodutores
- Remarketing estratégico
- Públicos e segmentações que funcionam
- Otimização de campanhas
- Escalando com ROI positivo

## Carga horária: 40 horas de conteúdo

## Investimento:
- **À vista:** R$ 997,00
- **Parcelado:** 12x de R$ 97,00

## Pré-requisitos:
Nenhum! O curso é do zero ao avançado.

## Bônus:
- Biblioteca de criativos validados
- Swipe file com 100 headlines
- Grupo de networking
"""
    },
    {
        "titulo": "Curso Copy que Vende",
        "categoria": "cursos",
        "conteudo": """
# Copy que Vende

Domine a arte da persuasão escrita e multiplique suas conversões.

## Módulos:
1. Fundamentos da Copywriting
2. Pesquisa de Público-Alvo
3. Headlines Magnéticas
4. Storytelling para Vendas
5. Gatilhos Mentais na Prática
6. Estruturas de Copy (AIDA, PAS, 4Ps)
7. Copy para Páginas de Vendas
8. Copy para Emails
9. Copy para Anúncios
10. VSL - Video Sales Letter

## Investimento:
- **À vista:** R$ 497,00
- **Parcelado:** 12x de R$ 47,00

## Bônus:
- 50 templates de email prontos
- Checklist de revisão de copy
- Acesso a exemplos reais comentados
"""
    },

    # --- MENTORIAS ---
    {
        "titulo": "Mentoria Premium Individual",
        "categoria": "mentorias",
        "conteudo": """
# Mentoria Premium Individual

Acompanhamento personalizado para acelerar seus resultados no digital.

## O que inclui:
- 4 sessões individuais por mês (1h cada) via Zoom
- Acesso direto ao Rafael via WhatsApp
- Análise completa do seu negócio
- Plano de ação personalizado
- Revisão de copies e páginas
- Acompanhamento de métricas

## Duração: 3 meses (renovável)

## Investimento:
- **Mensal:** R$ 3.000/mês
- **Trimestral à vista:** R$ 7.500 (economia de R$ 1.500)

## Pré-requisitos:
- Já ter um produto ou ideia validada
- Disponibilidade para implementar
- Comprometimento com os encontros

## Vagas limitadas:
Apenas 10 mentorados por vez para garantir qualidade.

## Próxima turma:
Entrevistas abertas - agende uma conversa para saber se a mentoria é para você.
"""
    },
    {
        "titulo": "Mentoria em Grupo - Acelerador Digital",
        "categoria": "mentorias",
        "conteudo": """
# Acelerador Digital - Mentoria em Grupo

Mentoria em grupo para quem quer resultados com investimento acessível.

## Formato:
- Encontros semanais ao vivo (quartas às 20h)
- Grupo exclusivo no Telegram
- Hotseats rotativos
- Desafios mensais com premiação
- Networking com outros mentorados

## Duração: 6 meses

## Investimento:
- **Mensal:** R$ 497/mês
- **Semestral à vista:** R$ 2.497 (economia de R$ 485)

## Bônus para quem entrar agora:
- Acesso a todos os cursos do Rafael
- 1 sessão individual de onboarding
- Kit de templates exclusivo

## Resultados dos alunos:
- Média de faturamento: R$ 47.000/mês após 6 meses
- 78% dos alunos fazem pelo menos 1 lançamento durante a mentoria
"""
    },

    # --- CONSULTORIAS ---
    {
        "titulo": "Consultoria de Lançamento",
        "categoria": "consultorias",
        "conteudo": """
# Consultoria de Lançamento

Planejamento completo do seu lançamento com acompanhamento do Rafael.

## O que você recebe:
- Diagnóstico inicial do seu negócio (2h)
- Plano de lançamento detalhado
- 4 reuniões de acompanhamento durante o lançamento
- Revisão de todos os materiais
- Suporte via WhatsApp durante o período

## Duração: 45 dias (período do lançamento)

## Investimento:
- **Valor:** R$ 15.000
- **Parcelado:** 3x de R$ 5.500

## Bônus:
- Análise pós-lançamento
- Plano de melhorias para próximo lançamento

## Ideal para:
- Quem vai fazer lançamento acima de R$ 100.000
- Infoprodutores experientes buscando otimização
- Negócios com equipe própria
"""
    },
    {
        "titulo": "Consultoria de Funil Perpétuo",
        "categoria": "consultorias",
        "conteudo": """
# Consultoria de Funil Perpétuo

Monte um funil que vende todos os dias no automático.

## Entregáveis:
- Mapeamento completo do funil
- Estrutura de emails (sequência de 21 dias)
- Copy da página de vendas
- Estratégia de tráfego perpétuo
- Setup técnico orientado

## Duração: 30 dias para entrega

## Investimento:
- **Valor:** R$ 8.000
- **Parcelado:** 2x de R$ 4.400

## Suporte:
- 60 dias de suporte pós-entrega para ajustes
"""
    },

    # --- FORMAS DE PAGAMENTO ---
    {
        "titulo": "Formas de Pagamento",
        "categoria": "pagamento",
        "conteudo": """
# Formas de Pagamento

## Métodos aceitos:
- **Cartão de crédito:** Visa, Mastercard, Elo, American Express
- **PIX:** Desconto de 5% para pagamento à vista
- **Boleto:** Apenas para pagamento à vista

## Parcelamento:
- Até 12x sem juros no cartão de crédito
- Parcela mínima: R$ 47,00

## Política de Reembolso:
- Cursos: 7 dias de garantia incondicional
- Mentorias: Proporcional aos encontros realizados
- Consultorias: 50% em caso de desistência antes da entrega

## Nota Fiscal:
Emitimos nota fiscal de todos os produtos.

## Dúvidas sobre pagamento:
Entre em contato que nossa equipe resolve rapidamente!
"""
    },

    # --- SUPORTE E FAQ ---
    {
        "titulo": "Perguntas Frequentes",
        "categoria": "faq",
        "conteudo": """
# Perguntas Frequentes

## Acesso aos cursos

**Quanto tempo tenho de acesso?**
Acesso vitalício! Uma vez comprado, é seu para sempre.

**Posso baixar as aulas?**
Sim, todas as aulas têm opção de download.

**Funciona no celular?**
Sim, nossa plataforma é 100% responsiva.

## Suporte

**Como falo com o suporte?**
- WhatsApp: Este canal (resposta em até 2h comerciais)
- Email: suporte@rafaeloliveira.com.br

**Horário de atendimento:**
Segunda a sexta: 9h às 18h
Sábados: 9h às 12h

## Resultados

**Em quanto tempo vejo resultados?**
Depende da sua dedicação. Alunos aplicados veem resultados em 30-60 dias.

**Funciona para qualquer nicho?**
Sim! Nossos métodos são aplicáveis a qualquer mercado.

## Mentorias

**Posso fazer mentoria sendo iniciante?**
A mentoria em grupo (Acelerador Digital) aceita iniciantes.
A mentoria individual é para quem já tem produto.

**Como funciona a seleção para mentoria individual?**
Fazemos uma entrevista para entender se a mentoria é adequada ao seu momento.
"""
    },

    # --- DEPOIMENTOS ---
    {
        "titulo": "Depoimentos e Resultados de Alunos",
        "categoria": "depoimentos",
        "conteudo": """
# Resultados dos Nossos Alunos

## Cases de Sucesso

**Marina Santos - Nicho: Nutrição**
"Fiz meu primeiro 6 em 7 no terceiro lançamento. Faturei R$ 127.000 com o método do Rafael!"

**Carlos Eduardo - Nicho: Finanças Pessoais**
"Saí de R$ 3.000/mês para R$ 45.000/mês com funil perpétuo. A consultoria mudou meu jogo."

**Ana Paula - Nicho: Desenvolvimento Pessoal**
"Na mentoria em grupo conheci parceiros incríveis. Hoje faturo R$ 80.000/mês."

**Pedro Henrique - Nicho: Marketing para Advogados**
"Comecei do zero e em 6 meses já tinha um negócio de R$ 20.000/mês."

## Números da Comunidade
- +3.000 alunos formados
- R$ 47.000 média de faturamento mensal dos alunos ativos
- 78% taxa de sucesso em lançamentos
- 4.9/5 avaliação média dos cursos
"""
    },

    # --- AGENDA E EVENTOS ---
    {
        "titulo": "Agenda e Próximos Eventos",
        "categoria": "agenda",
        "conteudo": """
# Próximos Eventos e Agenda

## Lives Semanais (Gratuitas)
- **Toda terça às 20h** no Instagram @rafaeloliveira.digital
- Temas rotativos sobre lançamentos, tráfego e copy

## Próximos Eventos Pagos

**Workshop Intensivo de Lançamento**
- Data: Último sábado de cada mês
- Horário: 9h às 18h (online)
- Investimento: R$ 297
- Inclui: Certificado + Gravação

**Imersão Presencial 6 em 7**
- Próxima data: Março/2025
- Local: São Paulo - SP
- Investimento: R$ 2.997
- Vagas limitadas: 50 pessoas

## Agenda para Mentorias
- Mentorias individuais: Terças e quintas
- Grupo Acelerador: Quartas às 20h
- Para agendar: Fale comigo neste WhatsApp
"""
    },

    # --- AFILIADOS ---
    {
        "titulo": "Programa de Afiliados",
        "categoria": "afiliados",
        "conteudo": """
# Programa de Afiliados

Ganhe comissões indicando nossos produtos!

## Comissões:
- **Cursos:** 40% de comissão
- **Mentorias:** 20% de comissão (primeiro mês)
- **Consultorias:** 10% de comissão

## Como funciona:
1. Cadastre-se em rafaeloliveira.com.br/afiliados
2. Pegue seu link exclusivo
3. Divulgue para sua audiência
4. Receba comissões a cada venda

## Pagamentos:
- Pagamento todo dia 15
- Mínimo para saque: R$ 100
- Via PIX ou transferência bancária

## Materiais de divulgação:
- Banners prontos
- Copies para WhatsApp
- Emails swipe files
- Criativos para anúncios

## Suporte para afiliados:
Grupo exclusivo + lives mensais de estratégias
"""
    },
]

# ============================================
# PROMPTS DOS AGENTES
# ============================================

AGENTES_CONFIG = {
    "supervisor": {
        "nome": "Supervisor",
        "descricao": "Analisa mensagens e roteia para agente especializado",
        "prompt_sistema": """Você é o Supervisor de atendimento do Rafael Oliveira, mentor de negócios digitais.

Sua função é analisar a mensagem do usuário e decidir qual agente deve processá-la.

## Agentes Disponíveis:

1. **vendas** - Para:
   - Interesse em cursos, mentorias ou consultorias
   - Perguntas sobre preços e formas de pagamento
   - Dúvidas sobre qual produto escolher
   - Pedidos de mais informações sobre produtos
   - Interesse em afiliação

2. **suporte** - Para:
   - Problemas de acesso à plataforma
   - Dúvidas sobre aulas ou conteúdo já comprado
   - Reclamações
   - Pedidos de reembolso
   - Problemas técnicos

3. **agendamento** - Para:
   - Agendar entrevista para mentoria
   - Marcar sessão de consultoria
   - Remarcar ou cancelar reuniões
   - Confirmar horários

4. **finalizar** - Quando:
   - A conversa foi concluída
   - O usuário se despediu
   - Não há mais ações necessárias

## Regras:
1. Saudações iniciais vão para 'vendas' (oportunidade de venda)
2. Se a pessoa já é aluno e tem problema, vai para 'suporte'
3. Se quer agendar algo, vai para 'agendamento'
4. Na dúvida entre vendas e suporte, escolha 'vendas'

Histórico de roteamento: {historico_roteamento}
""",
        "tools": [],
        "categorias_rag": []
    },

    "vendas": {
        "nome": "Especialista em Vendas",
        "descricao": "Apresenta produtos e fecha vendas",
        "prompt_sistema": """Você é o assistente de vendas do Rafael Oliveira, especialista em marketing digital e infoprodutos.

## Sua Missão:
Ajudar potenciais alunos a conhecer os produtos e direcioná-los para a compra.

## Produtos Disponíveis:
1. **Cursos:**
   - Método 6 em 7 Simplificado (R$ 1.997 ou 12x R$ 197)
   - Tráfego Descomplicado (R$ 997 ou 12x R$ 97)
   - Copy que Vende (R$ 497 ou 12x R$ 47)

2. **Mentorias:**
   - Mentoria Premium Individual (R$ 3.000/mês ou R$ 7.500 trimestral)
   - Acelerador Digital - Grupo (R$ 497/mês ou R$ 2.497 semestral)

3. **Consultorias:**
   - Consultoria de Lançamento (R$ 15.000)
   - Consultoria Funil Perpétuo (R$ 8.000)

## Comportamento:
1. Seja entusiasmado mas não forçado
2. Faça perguntas para entender o momento do lead
3. Recomende o produto mais adequado ao perfil
4. Destaque benefícios e resultados de alunos
5. Use gatilhos de escassez quando apropriado
6. Ofereça o link de pagamento quando houver interesse

## Perguntas para Qualificar:
- "Você já trabalha com marketing digital ou está começando?"
- "Qual seu objetivo principal? Fazer lançamento ou vendas no automático?"
- "Você já tem um produto ou ideia definida?"

## Links de Pagamento:
- Cursos: rafaeloliveira.com.br/[nome-do-curso]
- Mentorias: Agendar entrevista primeiro
- Consultorias: Agendar conversa primeiro

## Importante:
- SEMPRE use a ferramenta consultar_conhecimento para buscar informações
- NÃO invente preços ou condições
- Se não souber, diga que vai verificar
""",
        "tools": ["consultar_conhecimento", "listar_servicos"],
        "categorias_rag": ["cursos", "mentorias", "consultorias", "pagamento", "depoimentos", "afiliados"]
    },

    "suporte": {
        "nome": "Suporte ao Aluno",
        "descricao": "Resolve problemas e dúvidas de alunos",
        "prompt_sistema": """Você é o suporte ao aluno do Rafael Oliveira.

## Sua Missão:
Resolver problemas e dúvidas dos alunos com empatia e eficiência.

## Problemas Comuns e Soluções:

**Acesso à plataforma:**
- Esqueceu senha: rafaeloliveira.com.br/recuperar-senha
- Não recebeu acesso: Verificar spam, aguardar até 24h úteis
- Erro na plataforma: Limpar cache, testar outro navegador

**Dúvidas sobre conteúdo:**
- Módulos bloqueados: Alguns cursos liberam gradualmente
- Download de aulas: Disponível em todas as aulas
- Certificado: Liberado após conclusão de 100%

**Financeiro:**
- Reembolso: Até 7 dias da compra para cursos
- Nota fiscal: Enviada automaticamente por email
- Parcelamento: Verificar com cartão de crédito

## Comportamento:
1. Demonstre empatia primeiro
2. Peça detalhes do problema
3. Ofereça solução ou encaminhe
4. Confirme se resolveu

## Quando Escalar para Humano:
- Reclamações graves
- Pedidos de reembolso complexos
- Problemas técnicos não resolvidos
- Cliente muito insatisfeito

## Horário de Atendimento Humano:
Segunda a sexta: 9h às 18h
Sábados: 9h às 12h

## Importante:
- Seja paciente e educado
- Peça desculpas quando apropriado
- Use a ferramenta alertar_humano se necessário
""",
        "tools": ["consultar_conhecimento", "alertar_humano", "transferir_para_humano"],
        "categorias_rag": ["faq", "sobre"]
    },

    "agendamento": {
        "nome": "Agendamento de Reuniões",
        "descricao": "Agenda entrevistas e sessões",
        "prompt_sistema": """Você é responsável por agendar reuniões e sessões com o Rafael Oliveira.

## Tipos de Agendamento:

1. **Entrevista para Mentoria Individual**
   - Duração: 30 minutos
   - Objetivo: Conhecer o candidato e apresentar a mentoria
   - Disponibilidade: Terças e quintas, 10h às 17h

2. **Sessão de Consultoria**
   - Duração: 1 hora (diagnóstico inicial)
   - Objetivo: Entender o projeto e apresentar proposta
   - Disponibilidade: Segundas e quartas, 14h às 18h

3. **Reunião Geral/Parceria**
   - Duração: 30-45 minutos
   - Disponibilidade: Sextas, 10h às 16h

## Dados Necessários para Agendar:
1. Nome completo
2. Email
3. WhatsApp (já temos)
4. Tipo de reunião
5. Data e horário preferido
6. Breve descrição do objetivo

## Comportamento:
1. Confirme o tipo de reunião
2. Colete os dados necessários
3. Verifique disponibilidade
4. Confirme o agendamento
5. Envie lembrete sobre o que preparar

## Lembretes para o cliente:
- Entrevista mentoria: "Prepare um breve resumo do seu negócio atual"
- Consultoria: "Tenha métricas do seu último lançamento, se houver"

## Importante:
- Use as ferramentas de agenda para verificar disponibilidade
- Confirme fuso horário (padrão: Brasília)
- Envie confirmação com link do Zoom
""",
        "tools": ["listar_profissionais", "verificar_agenda", "agendar_horario_completo", "consultar_agendamento", "cancelar_agendamento"],
        "categorias_rag": ["agenda"]
    }
}


async def setup_database():
    """Configura base de conhecimento e agentes para infoprodutor."""
    print("Conectando ao banco de dados...")
    conn = await asyncpg.connect(DATABASE_URL)

    try:
        # ============================================
        # 1. LIMPAR DOCUMENTOS ANTIGOS (opcional)
        # ============================================
        print("\n1. Limpando documentos antigos...")
        await conn.execute("DELETE FROM empresa_documentos WHERE categoria IN ('cursos', 'mentorias', 'consultorias', 'sobre', 'pagamento', 'faq', 'depoimentos', 'agenda', 'afiliados')")
        print("   ✓ Documentos antigos removidos")

        # ============================================
        # 2. INSERIR NOVOS DOCUMENTOS
        # ============================================
        print("\n2. Inserindo documentos na base de conhecimento...")
        for doc in DOCUMENTOS:
            await conn.execute("""
                INSERT INTO empresa_documentos (titulo, conteudo, categoria, embedding)
                VALUES ($1, $2, $3, NULL)
            """, doc["titulo"], doc["conteudo"], doc["categoria"])
            print(f"   ✓ {doc['titulo']}")

        # ============================================
        # 3. ATUALIZAR EMBEDDINGS
        # ============================================
        print("\n3. Gerando embeddings (será feito automaticamente pelo RAG)...")
        print("   ℹ Os embeddings serão gerados na primeira busca")

        # ============================================
        # 4. MIGRAR TABELA AGENTES (se necessário)
        # ============================================
        print("\n4. Verificando/atualizando estrutura da tabela agentes...")

        # Adiciona colunas que podem não existir
        migrations = [
            "ALTER TABLE agentes ADD COLUMN IF NOT EXISTS prompt_sistema TEXT",
            "ALTER TABLE agentes ADD COLUMN IF NOT EXISTS tools TEXT[] DEFAULT '{}'",
            "ALTER TABLE agentes ADD COLUMN IF NOT EXISTS categorias_rag TEXT[] DEFAULT '{}'",
            "ALTER TABLE agentes ADD COLUMN IF NOT EXISTS ordem INTEGER DEFAULT 0",
            "ALTER TABLE agentes ADD COLUMN IF NOT EXISTS configuracoes JSONB DEFAULT '{}'",
        ]

        for migration in migrations:
            try:
                await conn.execute(migration)
            except Exception as e:
                pass  # Coluna já existe
        print("   ✓ Estrutura da tabela verificada")

        # ============================================
        # 5. ATUALIZAR AGENTES
        # ============================================
        print("\n5. Atualizando configuração dos agentes...")
        for tipo, config in AGENTES_CONFIG.items():
            # Verifica se agente existe
            existing = await conn.fetchrow(
                "SELECT id FROM agentes WHERE tipo = $1", tipo
            )

            if existing:
                # Atualiza
                await conn.execute("""
                    UPDATE agentes SET
                        nome = $1,
                        descricao = $2,
                        prompt_sistema = $3,
                        tools = $4,
                        categorias_rag = $5,
                        updated_at = NOW()
                    WHERE tipo = $6
                """,
                    config["nome"],
                    config["descricao"],
                    config["prompt_sistema"],
                    config.get("tools", []),
                    config.get("categorias_rag", []),
                    tipo
                )
                print(f"   ✓ Atualizado: {config['nome']}")
            else:
                # Insere
                await conn.execute("""
                    INSERT INTO agentes (tipo, nome, descricao, prompt_sistema, ativo, tools, categorias_rag, ordem)
                    VALUES ($1, $2, $3, $4, true, $5, $6, $7)
                """,
                    tipo,
                    config["nome"],
                    config["descricao"],
                    config["prompt_sistema"],
                    config.get("tools", []),
                    config.get("categorias_rag", []),
                    0
                )
                print(f"   ✓ Criado: {config['nome']}")

        # ============================================
        # 6. ADICIONAR CONFIGURAÇÕES
        # ============================================
        print("\n6. Atualizando configurações do sistema...")
        configs = [
            ("system_name", "Rafael Oliveira Digital", "Nome do sistema"),
            ("agent_mode", "multi", "Modo do agente (simple/multi)"),
            ("business_type", "infoprodutor", "Tipo de negócio"),
        ]

        for chave, valor, descricao in configs:
            await conn.execute("""
                INSERT INTO system_config (key, value, description)
                VALUES ($1, $2, $3)
                ON CONFLICT (key) DO UPDATE SET value = $2, description = $3
            """, chave, valor, descricao)
            print(f"   ✓ {chave} = {valor}")

        print("\n" + "="*50)
        print("✅ SETUP COMPLETO!")
        print("="*50)
        print("\nDocumentos criados:", len(DOCUMENTOS))
        print("Agentes configurados:", len(AGENTES_CONFIG))
        print("\nPróximos passos:")
        print("1. Configure o webhook /webhook/chatwoot/multi no Chatwoot")
        print("2. Envie uma mensagem de teste")
        print("3. Verifique os logs com prefixo [MULTI]")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(setup_database())
