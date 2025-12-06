#!/usr/bin/env python3
"""
Script para popular a base de conhecimento do RAG Multi-Agente com PRODUTOS

NOVA ESTRUTURA SIMPLIFICADA:
- Produtos sao cadastrados na tabela 'produtos_catalogo'
- Documentos referenciam apenas 'produto_id' no metadata
- Nome do produto e buscado na tabela de catalogo

Execute: python scripts/popular_rag_multi_produtos.py

IMPORTANTE: Execute apos migrate_rag_multi.py
"""
import asyncio
import sys
sys.path.insert(0, '.')

from src.services.database import get_db_service
from src.services.rag_multi_infoprodutos import get_rag_multi_service, rag_multi_add_produto_sync

# ============================================
# PRODUTOS DO INFOPRODUTOR - RAFAEL OLIVEIRA
# ============================================
# Estrutura:
# - produto_id: slug unico para filtrar
# - produto_tipo: curso, mentoria, consultoria, evento
# - produto_nome: nome para exibicao
# - documentos: lista de docs deste produto

PRODUTOS = [
    # =========================================================================
    # CURSO: METODO 6 EM 7 SIMPLIFICADO
    # =========================================================================
    {
        "produto_id": "metodo-6-em-7",
        "produto_tipo": "curso",
        "produto_nome": "Metodo 6 em 7 Simplificado",
        "documentos": [
            {
                "titulo": "Metodo 6 em 7 - Visao Geral",
                "categoria": "vendas",
                "conteudo": """Metodo 6 em 7 Simplificado

O curso mais completo para voce fazer seu primeiro 6 em 7 (R$ 100.000 em 7 dias).

Este e o carro-chefe do Rafael Oliveira, desenvolvido apos anos de experiencia e mais de 50 lancamentos realizados.

Para quem e indicado:
- Iniciantes que querem comecar no digital
- Profissionais que querem monetizar conhecimento
- Empreendedores buscando escalar online
- Coaches, consultores, professores

Para quem NAO e indicado:
- Quem busca resultados sem esforco
- Quem nao tem tempo para implementar
- Quem nao tem um conhecimento para ensinar

Resultados dos alunos:
- 78% fazem pelo menos 1 lancamento durante o curso
- Media de faturamento do primeiro lancamento: R$ 47.000
- Alunos de destaque ja faturaram mais de R$ 500.000"""
            },
            {
                "titulo": "Metodo 6 em 7 - Conteudo e Modulos",
                "categoria": "vendas",
                "conteudo": """Metodo 6 em 7 - Conteudo Programatico

9 MODULOS COMPLETOS:

Modulo 1: Mentalidade do Infoprodutor de Sucesso
- Crenvas limitantes que te impedem de lancar
- Como pensar como um infoprodutor de 6 digitos
- Planejamento e metas realistas

Modulo 2: Escolhendo seu Nicho Lucrativo
- Criterios para validar um nicho
- Analise de concorrencia
- Encontrando seu diferencial

Modulo 3: Criando sua Oferta Irresistivel
- Estrutura de oferta que converte
- Precificacao estrategica
- Bonus que aumentam o valor percebido

Modulo 4: Estrutura do Lancamento Perfeito
- Cronograma de 45 dias
- Equipe minima necessaria
- Ferramentas e plataformas

Modulo 5: Captacao de Leads
- Iscas digitais que convertem
- Landing pages de alta conversao
- Estrategias de trafego para CPL

Modulo 6: Semana de Aquecimento
- Conteudo de Pre-Lancamento (CPL)
- Lives estrategicas
- Gerando antecipacao

Modulo 7: Abertura do Carrinho
- O evento de lancamento
- Webinario de vendas
- Primeiras 24h decisivas

Modulo 8: Fechamento com Escassez
- Gatilhos de urgencia eticos
- Remarketing de carrinho
- Ultimas 48h que fazem diferenca

Modulo 9: Pos-venda e Retencao
- Onboarding do aluno
- Reduzindo reembolsos
- Preparando o proximo lancamento

CARGA HORARIA: 60 horas de conteudo gravado + lives mensais"""
            },
            {
                "titulo": "Metodo 6 em 7 - Preco e Condicoes",
                "categoria": "vendas",
                "conteudo": """Metodo 6 em 7 - Investimento

VALOR:
- A vista (PIX/Boleto): R$ 1.997,00 (com 5% desconto no PIX)
- Parcelado: 12x de R$ 197,00 no cartao

O QUE ESTA INCLUSO:
- Acesso vitalicio a todos os 9 modulos
- Atualizacoes gratuitas para sempre
- Certificado de conclusao
- Todos os bonus listados

BONUS EXCLUSIVOS (valor de R$ 2.500):
1. Templates de copy prontos para usar
2. Planilha de planejamento de lancamento
3. Acesso a comunidade VIP no Telegram
4. 3 lives mensais de tira-duvidas com Rafael
5. Checklist do lancamento perfeito
6. Swipe file com emails de lancamento

GARANTIA:
7 dias de garantia incondicional.
Se voce nao gostar do curso por QUALQUER motivo, devolvemos 100% do seu dinheiro. Sem perguntas, sem burocracia.

ACESSO:
- Liberacao imediata apos confirmacao do pagamento
- Plataforma disponivel 24h por dia
- Acesso via computador, tablet ou celular
- Opcao de download das aulas"""
            },
            {
                "titulo": "Metodo 6 em 7 - Bonus Detalhados",
                "categoria": "vendas",
                "conteudo": """Metodo 6 em 7 - Bonus Exclusivos

BONUS 1: Templates de Copy (Valor: R$ 497)
- 15 modelos de emails de lancamento
- Scripts de VSL (Video Sales Letter)
- Headlines testadas e validadas
- Copy de pagina de vendas completa

BONUS 2: Planilha de Planejamento (Valor: R$ 297)
- Cronograma de 45 dias pre-configurado
- Checklist de tarefas por fase
- Controle de metricas e KPIs
- Dashboard de acompanhamento

BONUS 3: Comunidade VIP Telegram (Valor: R$ 997)
- Networking com outros lancadores
- Avisos de oportunidades
- Parcerias e co-producoes
- Suporte entre alunos

BONUS 4: Lives Mensais (Valor: R$ 497)
- 3 encontros ao vivo por mes
- Tira-duvidas direto com Rafael
- Analise de lancamentos de alunos
- Tendencias e novidades do mercado

BONUS 5: Checklist do Lancamento (Valor: R$ 197)
- Lista de verificacao dia-a-dia
- Nao esqueca nenhuma etapa
- Baseado em +50 lancamentos

TOTAL EM BONUS: R$ 2.485
Voce leva TUDO isso junto com o curso!"""
            },
        ]
    },

    # =========================================================================
    # CURSO: TRAFEGO DESCOMPLICADO
    # =========================================================================
    {
        "produto_id": "trafego-descomplicado",
        "produto_tipo": "curso",
        "produto_nome": "Trafego Descomplicado",
        "documentos": [
            {
                "titulo": "Trafego Descomplicado - Visao Geral",
                "categoria": "vendas",
                "conteudo": """Trafego Descomplicado

Aprenda a criar campanhas de trafego pago que convertem, mesmo comecando do zero.

O Trafego Descomplicado e o curso ideal para quem quer dominar anuncios online e parar de perder dinheiro com campanhas que nao funcionam.

Para quem e:
- Infoprodutores que querem escalar com trafego pago
- Gestores de trafego iniciantes
- Empreendedores que gastam em anuncios sem resultado
- Afiliados que querem vender mais

Diferenciais do curso:
- Foco em INFOPRODUTOS (nao e trafego generico)
- Estrategias para lancamentos E perpetuo
- Do basico ao avancado em uma trilha logica
- Exemplos reais de campanhas que funcionaram

Resultados esperados:
- Reduzir seu custo por lead em ate 50%
- Escalar campanhas com ROI positivo
- Parar de desperdicar verba em testes"""
            },
            {
                "titulo": "Trafego Descomplicado - Conteudo",
                "categoria": "vendas",
                "conteudo": """Trafego Descomplicado - Conteudo Programatico

MODULO 1: Fundamentos do Trafego Pago
- Como funcionam os leiloes de anuncios
- Pixel e eventos de conversao
- Metricas essenciais (CPM, CPC, CPL, CPA)

MODULO 2: Meta Ads (Facebook e Instagram)
- Estrutura de campanhas
- Objetivos de campanha corretos
- Segmentacao de publicos
- Lookalike e remarketing
- Criativos que convertem

MODULO 3: Google Ads
- Rede de pesquisa para infoprodutores
- YouTube Ads
- Display e remarketing
- Palavras-chave negativas

MODULO 4: Estrategia para Lancamentos
- Fase de captacao (CPL)
- Fase de aquecimento
- Carrinho aberto
- Remarketing de recuperacao

MODULO 5: Estrategia para Perpetuo
- Funil de vendas no automatico
- Escalando com controle
- Otimizacao continua

MODULO 6: Otimizacao e Escala
- Leitura de metricas
- Quando pausar e quando escalar
- Testes A/B eficientes
- Gestao de orcamento

CARGA HORARIA: 40 horas de conteudo"""
            },
            {
                "titulo": "Trafego Descomplicado - Preco e Condicoes",
                "categoria": "vendas",
                "conteudo": """Trafego Descomplicado - Investimento

VALOR:
- A vista (PIX/Boleto): R$ 997,00
- Parcelado: 12x de R$ 97,00 no cartao

O QUE ESTA INCLUSO:
- Acesso vitalicio a plataforma
- 40 horas de conteudo
- Atualizacoes quando as plataformas mudarem
- Certificado de conclusao
- Todos os bonus

BONUS:
1. Biblioteca de Criativos Validados
   - +50 modelos de anuncios que converteram
   - Formatos: imagem, carrossel, video

2. Swipe File com 100 Headlines
   - Headlines testadas em campanhas reais
   - Organizadas por tipo de campanha

3. Grupo de Networking
   - Troca de experiencias com outros gestores
   - Compartilhamento de resultados

PRE-REQUISITOS: Nenhum!
O curso e do zero ao avancado. Voce nao precisa saber nada de trafego para comecar.

GARANTIA: 7 dias de garantia incondicional."""
            },
        ]
    },

    # =========================================================================
    # CURSO: COPY QUE VENDE
    # =========================================================================
    {
        "produto_id": "copy-que-vende",
        "produto_tipo": "curso",
        "produto_nome": "Copy que Vende",
        "documentos": [
            {
                "titulo": "Copy que Vende - Visao Geral",
                "categoria": "vendas",
                "conteudo": """Copy que Vende

Domine a arte da persuasao escrita e multiplique suas conversoes.

Copywriting e a habilidade MAIS importante do marketing digital. Com Copy que Vende, voce vai aprender a escrever textos que vendem enquanto voce dorme.

Para quem e:
- Infoprodutores que escrevem suas proprias copies
- Copywriters iniciantes
- Gestores de trafego que criam anuncios
- Qualquer pessoa que vende pela internet

O que voce vai conseguir:
- Escrever paginas de vendas que convertem
- Criar emails que as pessoas abrem E clicam
- Fazer anuncios que param o scroll
- Dominar os gatilhos mentais

Por que copy e tao importante:
- Uma boa copy pode dobrar suas vendas
- E a diferenca entre anuncio caro e anuncio lucrativo
- Voce para de depender de copywriters externos"""
            },
            {
                "titulo": "Copy que Vende - Conteudo",
                "categoria": "vendas",
                "conteudo": """Copy que Vende - Conteudo Programatico

10 MODULOS:

1. Fundamentos da Copywriting
   - O que e copy e por que funciona
   - Principios da persuasao
   - Etica na copy

2. Pesquisa de Publico-Alvo
   - Como entrar na mente do cliente
   - Entrevistas e pesquisas
   - Construindo a persona compradora

3. Headlines Magneticas
   - Formulas de headlines que funcionam
   - Testes e validacao
   - Headlines para cada formato

4. Storytelling para Vendas
   - Estrutura de historias que vendem
   - Jornada do heroi aplicada
   - Conectando emocionalmente

5. Gatilhos Mentais na Pratica
   - Escassez, urgencia, prova social
   - Autoridade, reciprocidade
   - Como usar sem ser apelativo

6. Estruturas de Copy (AIDA, PAS, 4Ps)
   - Quando usar cada estrutura
   - Exemplos praticos
   - Adaptando ao seu produto

7. Copy para Paginas de Vendas
   - Estrutura completa de VSL
   - Elementos essenciais
   - Above the fold

8. Copy para Emails
   - Sequencias de lancamento
   - Emails de carrinho
   - Relacionamento

9. Copy para Anuncios
   - Facebook/Instagram
   - Google
   - YouTube

10. VSL - Video Sales Letter
    - Roteiro completo
    - Gravacao e edicao
    - Otimizacao"""
            },
            {
                "titulo": "Copy que Vende - Preco e Condicoes",
                "categoria": "vendas",
                "conteudo": """Copy que Vende - Investimento

VALOR:
- A vista (PIX/Boleto): R$ 497,00
- Parcelado: 12x de R$ 47,00 no cartao

O QUE ESTA INCLUSO:
- 10 modulos completos
- Acesso vitalicio
- Certificado
- Bonus exclusivos

BONUS:
1. 50 Templates de Email Prontos
   - Sequencias de lancamento
   - Emails de venda
   - Relacionamento

2. Checklist de Revisao de Copy
   - Nunca mais publique copy ruim
   - Verificacao passo-a-passo

3. Exemplos Reais Comentados
   - Copies que venderam milhoes
   - Analise detalhada do que funciona

GARANTIA: 7 dias de garantia incondicional.

Este e o curso com MELHOR custo-beneficio para quem quer aprender copy!"""
            },
        ]
    },

    # =========================================================================
    # MENTORIA: PREMIUM INDIVIDUAL
    # =========================================================================
    {
        "produto_id": "mentoria-individual",
        "produto_tipo": "mentoria",
        "produto_nome": "Mentoria Premium Individual",
        "documentos": [
            {
                "titulo": "Mentoria Individual - Visao Geral",
                "categoria": "vendas",
                "conteudo": """Mentoria Premium Individual

Acompanhamento PERSONALIZADO com Rafael Oliveira para acelerar seus resultados.

A Mentoria Individual e para quem quer atencao exclusiva e um plano 100% personalizado para seu negocio.

Diferencial:
- Voce tem acesso DIRETO ao Rafael
- Plano feito especificamente para voce
- Acompanhamento proximo das suas metricas
- Correcao de rota em tempo real

Para quem e indicado:
- Infoprodutores que ja tem produto
- Quem ja faturou pelo menos R$ 10.000 com digital
- Quem quer escalar rapidamente
- Quem precisa de orientacao personalizada

Para quem NAO e indicado:
- Iniciantes absolutos (veja Acelerador Digital)
- Quem nao tem tempo para implementar
- Quem busca formulas prontas

Resultados dos mentorados:
- Media de crescimento: 3x o faturamento em 3 meses
- Mentorados que sairam de 5 para 6 digitos mensais
- Cases de lancamentos de R$ 200.000+"""
            },
            {
                "titulo": "Mentoria Individual - Como Funciona",
                "categoria": "vendas",
                "conteudo": """Mentoria Premium Individual - Formato

O QUE ESTA INCLUSO:

1. Sessoes Individuais (4x por mes)
   - 1 hora cada sessao via Zoom
   - Gravacao disponivel para rever
   - Tercas ou quintas, horario a combinar

2. Acesso Direto via WhatsApp
   - Fale com Rafael quando precisar
   - Resposta em ate 24h
   - Para duvidas rapidas e urgencias

3. Analise Completa do Negocio
   - Diagnostico inicial detalhado
   - Identificacao de gargalos
   - Oportunidades de crescimento

4. Plano de Acao Personalizado
   - Estrategia feita para seu negocio
   - Cronograma de implementacao
   - Metas claras e mensuraveis

5. Revisao de Materiais
   - Copies revisadas
   - Paginas de vendas
   - Estrategia de lancamento

6. Acompanhamento de Metricas
   - Analise semanal de resultados
   - Ajustes de rota
   - Otimizacao continua

DURACAO: 3 meses (renovavel)

VAGAS: Apenas 10 mentorados simultaneos
(para garantir qualidade do acompanhamento)"""
            },
            {
                "titulo": "Mentoria Individual - Preco e Condicoes",
                "categoria": "vendas",
                "conteudo": """Mentoria Premium Individual - Investimento

VALOR:
- Mensal: R$ 3.000/mes
- Trimestral a vista: R$ 7.500 (economia de R$ 1.500!)

FORMA DE PAGAMENTO:
- PIX ou transferencia: valor integral
- Cartao de credito: parcela mensal

PRE-REQUISITOS PARA ENTRAR:
1. Ter um produto ou ideia validada
2. Ter tempo para implementar (minimo 15h/semana)
3. Comprometimento com os encontros
4. Passar pela entrevista de selecao

PROCESSO DE SELECAO:
1. Agende uma entrevista (30 min)
2. Conversamos sobre seu negocio
3. Avaliamos se a mentoria e adequada
4. Se aprovado, enviamos contrato
5. Inicio na semana seguinte

Por que tem selecao?
Porque queremos garantir que voce vai ter resultados. Nao aceitamos qualquer pessoa - apenas quem esta pronto para crescer.

GARANTIA: Proporcional aos encontros nao realizados.

PROXIMA TURMA: Vagas abertas! Agende sua entrevista."""
            },
        ]
    },

    # =========================================================================
    # MENTORIA: ACELERADOR DIGITAL (GRUPO)
    # =========================================================================
    {
        "produto_id": "acelerador-digital",
        "produto_tipo": "mentoria",
        "produto_nome": "Acelerador Digital",
        "documentos": [
            {
                "titulo": "Acelerador Digital - Visao Geral",
                "categoria": "vendas",
                "conteudo": """Acelerador Digital - Mentoria em Grupo

Mentoria em grupo para quem quer resultados com investimento mais acessivel.

O Acelerador Digital e a opcao ideal para quem esta comecando ou quer acelerar sem o investimento da mentoria individual.

Diferenciais:
- Encontros semanais AO VIVO com Rafael
- Networking com outros empreendedores
- Investimento acessivel
- Metodologia testada em +500 alunos

Para quem e indicado:
- Iniciantes que querem direcao
- Quem tem ideia mas nao sabe por onde comecar
- Quem quer aprender com casos de outros alunos
- Quem busca comunidade

O que voce vai conquistar:
- Clareza no seu posicionamento
- Primeiro (ou proximo) lancamento estruturado
- Networking com empreendedores do mesmo nivel
- Acompanhamento semanal

Resultados do Acelerador:
- 78% dos alunos fazem pelo menos 1 lancamento
- Media de faturamento: R$ 47.000/mes apos 6 meses
- +500 alunos formados"""
            },
            {
                "titulo": "Acelerador Digital - Como Funciona",
                "categoria": "vendas",
                "conteudo": """Acelerador Digital - Formato

ENCONTROS SEMANAIS:
- Toda quarta-feira as 20h (horario de Brasilia)
- Duracao: 2 horas
- Via Zoom (com gravacao)
- Temas rotativos + hotseats

ESTRUTURA DOS ENCONTROS:
- 1h: Conteudo/tema da semana
- 30min: Hotseat (analise de casos)
- 30min: Perguntas e respostas

GRUPO NO TELEGRAM:
- Networking 24h
- Avisos e lembretes
- Troca de experiencias
- Suporte entre membros

HOTSEATS ROTATIVOS:
- Cada semana, 2-3 alunos sao analisados
- Voce mostra seu projeto/duvida
- Rafael e o grupo dao feedback
- Todos aprendem com todos

DESAFIOS MENSAIS:
- Metas claras para o mes
- Premiacao para quem bater
- Gamificacao que gera resultados

DURACAO: 6 meses

BONUS PARA MEMBROS:
- Acesso a TODOS os cursos do Rafael
- 1 sessao individual de onboarding
- Kit de templates exclusivo"""
            },
            {
                "titulo": "Acelerador Digital - Preco e Condicoes",
                "categoria": "vendas",
                "conteudo": """Acelerador Digital - Investimento

VALOR:
- Mensal: R$ 497/mes (6 parcelas)
- Semestral a vista: R$ 2.497 (economia de R$ 485!)

FORMA DE PAGAMENTO:
- PIX/Boleto: valor a vista
- Cartao: mensal ou a vista

O QUE ESTA INCLUSO:
- 24 encontros ao vivo (6 meses)
- Gravacoes de todas as sessoes
- Grupo VIP no Telegram
- Todos os cursos do Rafael (bonus)
- Sessao individual de onboarding
- Kit de templates

GARANTIA:
- 7 dias para testar
- Se nao gostar, devolvemos 100%
- Basta participar do primeiro encontro

PROXIMA TURMA:
- Turmas iniciam todo dia 1
- Vagas limitadas a 50 pessoas por turma
- Garanta sua vaga!

PRE-REQUISITOS: Nenhum!
O Acelerador aceita iniciantes. Voce so precisa ter vontade de aprender e implementar."""
            },
        ]
    },

    # =========================================================================
    # CONSULTORIA: LANCAMENTO
    # =========================================================================
    {
        "produto_id": "consultoria-lancamento",
        "produto_tipo": "consultoria",
        "produto_nome": "Consultoria de Lancamento",
        "documentos": [
            {
                "titulo": "Consultoria Lancamento - Visao Geral",
                "categoria": "vendas",
                "conteudo": """Consultoria de Lancamento

Planejamento COMPLETO do seu lancamento com acompanhamento do Rafael.

A Consultoria de Lancamento e para quem quer um lancamento profissional, com estrategia validada e acompanhamento de perto.

O que e:
- Rafael planeja SEU lancamento do zero
- Voce recebe um plano detalhado
- Acompanhamento durante toda execucao
- Suporte para ajustes em tempo real

Para quem e:
- Lancamentos acima de R$ 100.000 de meta
- Infoprodutores experientes
- Quem tem equipe para executar
- Quem quer maximizar resultados

Diferenciais:
- Estrategia personalizada (nao e template)
- Experiencia de +50 lancamentos
- Acompanhamento proximo
- Foco em RESULTADO

Resultados de consultorias anteriores:
- Lancamento de R$ 300.000 (nicho saude)
- Lancamento de R$ 180.000 (nicho financas)
- Lancamento de R$ 450.000 (nicho marketing)"""
            },
            {
                "titulo": "Consultoria Lancamento - Entregaveis",
                "categoria": "vendas",
                "conteudo": """Consultoria de Lancamento - O que voce recebe

FASE 1: DIAGNOSTICO (Semana 1)
- Reuniao de 2 horas para entender seu negocio
- Analise do seu publico e produto
- Definicao de metas realistas
- Identificacao de diferenciais

FASE 2: PLANEJAMENTO (Semana 2)
- Plano de lancamento completo em documento
- Cronograma dia-a-dia de 45 dias
- Estrategia de conteudo para aquecimento
- Definicao de ofertas e bonus

FASE 3: ACOMPANHAMENTO (Semanas 3-6)
- 4 reunioes de acompanhamento (1h cada)
- Revisao de todos os materiais
- Ajustes de estrategia em tempo real
- Suporte via WhatsApp ilimitado

FASE 4: POS-LANCAMENTO
- Analise de resultados
- Relatorio de metricas
- Plano de melhorias para proximo lancamento
- Reuniao de fechamento

MATERIAIS QUE SERAO REVISADOS:
- Copy de pagina de vendas
- Sequencia de emails
- Roteiro de lives/webinario
- Criativos de anuncios
- Estrategia de trafego

DURACAO TOTAL: 45 dias"""
            },
            {
                "titulo": "Consultoria Lancamento - Preco e Condicoes",
                "categoria": "vendas",
                "conteudo": """Consultoria de Lancamento - Investimento

VALOR: R$ 15.000

FORMA DE PAGAMENTO:
- A vista (PIX): R$ 15.000
- Parcelado: 3x de R$ 5.500

CRONOGRAMA DE PAGAMENTO:
- 50% na contratacao
- 50% no inicio do lancamento

O QUE ESTA INCLUSO:
- Diagnostico inicial (2h)
- Plano de lancamento completo
- 4 reunioes de acompanhamento
- Suporte WhatsApp durante o periodo
- Revisao de materiais
- Analise pos-lancamento

O QUE NAO ESTA INCLUSO:
- Execucao (voce ou sua equipe executa)
- Verba de trafego
- Ferramentas e plataformas
- Producao de video/design

IDEAL PARA:
- Meta de lancamento: R$ 100.000+
- Quem tem equipe para executar
- Lancamentos importantes

DISPONIBILIDADE:
- Apenas 2 consultorias por mes
- Agende com antecedencia"""
            },
        ]
    },

    # =========================================================================
    # CONSULTORIA: FUNIL PERPETUO
    # =========================================================================
    {
        "produto_id": "consultoria-perpetuo",
        "produto_tipo": "consultoria",
        "produto_nome": "Consultoria de Funil Perpetuo",
        "documentos": [
            {
                "titulo": "Consultoria Perpetuo - Visao Geral",
                "categoria": "vendas",
                "conteudo": """Consultoria de Funil Perpetuo

Monte um funil que vende TODOS OS DIAS no automatico.

A Consultoria de Funil Perpetuo e para quem quer parar de depender de lancamentos e ter receita previsivel.

O que e Funil Perpetuo:
- Vendas automaticas 24/7
- Leads entram, compram sem voce fazer nada
- Receita recorrente e previsivel
- Escala com trafego pago

Para quem e:
- Quem ja tem produto validado
- Quem quer receita entre lancamentos
- Quem quer automatizar vendas
- Quem tem orcamento para trafego

Beneficios do perpetuo:
- Vendas todos os dias
- Fluxo de caixa estavel
- Menos estresse que lancamentos
- Escalavel com trafego

Resultados de funis criados:
- Funil de R$ 50.000/mes (nicho emagrecimento)
- Funil de R$ 30.000/mes (nicho produtividade)
- Funil de R$ 80.000/mes (nicho investimentos)"""
            },
            {
                "titulo": "Consultoria Perpetuo - Entregaveis",
                "categoria": "vendas",
                "conteudo": """Consultoria de Funil Perpetuo - Entregaveis

VOCE RECEBE:

1. Mapeamento Completo do Funil
   - Desenho visual do funil
   - Cada etapa detalhada
   - Metricas esperadas por etapa

2. Estrutura de Emails (Sequencia de 21 dias)
   - 21 emails escritos
   - Sequencia de relacionamento
   - Sequencia de vendas
   - Emails de recuperacao

3. Copy da Pagina de Vendas
   - Estrutura completa
   - Briefing detalhado
   - Revisao da sua copy

4. Estrategia de Trafego Perpetuo
   - Publicos recomendados
   - Orcamento inicial
   - Estrategia de escala
   - Metricas-alvo

5. Setup Tecnico Orientado
   - Passo a passo de configuracao
   - Integracao entre ferramentas
   - Automacoes necessarias

FORMATO DE ENTREGA:
- Reunioes: 4 encontros de 1h
- Documentos: Entregues por etapa
- Suporte: 60 dias pos-entrega

DURACAO: 30 dias para entrega completa"""
            },
            {
                "titulo": "Consultoria Perpetuo - Preco e Condicoes",
                "categoria": "vendas",
                "conteudo": """Consultoria de Funil Perpetuo - Investimento

VALOR: R$ 8.000

FORMA DE PAGAMENTO:
- A vista (PIX): R$ 8.000
- Parcelado: 2x de R$ 4.400

CRONOGRAMA:
- 50% na contratacao
- 50% na entrega final

O QUE ESTA INCLUSO:
- Mapeamento do funil
- 21 emails escritos
- Briefing/revisao de copy
- Estrategia de trafego
- Setup tecnico orientado
- 4 reunioes de alinhamento
- 60 dias de suporte pos-entrega

O QUE NAO ESTA INCLUSO:
- Verba de trafego pago
- Ferramentas (email, pagina, etc)
- Producao de video
- Design grafico

PRE-REQUISITOS:
- Produto ja validado
- Investimento em trafego (minimo R$ 3.000/mes)
- Ferramentas basicas contratadas

SUPORTE POS-ENTREGA:
60 dias para ajustes e duvidas sobre o funil."""
            },
        ]
    },
]

# ============================================
# DOCUMENTOS GERAIS (sem produto_id)
# ============================================
DOCUMENTOS_GERAIS = [
    {
        "titulo": "Sobre o Mentor - Rafael Oliveira",
        "categoria": "sobre",
        "agente": None,
        "conteudo": """Rafael Oliveira - Mentor de Negocios Digitais

Rafael Oliveira e especialista em marketing digital e criacao de infoprodutos, com mais de 10 anos de experiencia no mercado.

Trajetoria:
- Comecou como afiliado em 2014
- Lancou seu primeiro curso em 2016
- Ja faturou mais de R$ 15 milhoes com infoprodutos
- Mentorou mais de 3.000 alunos
- Criador do Metodo 6 em 7 Simplificado

Especialidades:
- Lancamentos digitais
- Criacao de cursos online
- Funis de vendas
- Trafego pago (Meta Ads e Google Ads)
- Copywriting para vendas

Redes Sociais:
- Instagram: @rafaeloliveira.digital
- YouTube: Rafael Oliveira Digital
- Podcast: Papo de Infoprodutor (Spotify)"""
    },
    {
        "titulo": "Formas de Pagamento",
        "categoria": "pagamento",
        "agente": None,
        "conteudo": """Formas de Pagamento

Metodos aceitos:
- Cartao de credito: Visa, Mastercard, Elo, American Express
- PIX: Desconto de 5% para pagamento a vista
- Boleto: Apenas para pagamento a vista

Parcelamento:
- Ate 12x sem juros no cartao de credito
- Parcela minima: R$ 47,00

Politica de Reembolso:
- Cursos: 7 dias de garantia incondicional
- Mentorias: Proporcional aos encontros realizados
- Consultorias: 50% em caso de desistencia antes da entrega

Nota Fiscal: Emitimos nota fiscal de todos os produtos.

Duvidas sobre pagamento: Entre em contato que nossa equipe resolve rapidamente!"""
    },
    {
        "titulo": "Depoimentos e Resultados de Alunos",
        "categoria": "depoimentos",
        "agente": None,
        "conteudo": """Resultados dos Nossos Alunos

Cases de Sucesso:

Marina Santos - Nicho: Nutricao
"Fiz meu primeiro 6 em 7 no terceiro lancamento. Faturei R$ 127.000 com o metodo do Rafael!"

Carlos Eduardo - Nicho: Financas Pessoais
"Sai de R$ 3.000/mes para R$ 45.000/mes com funil perpetuo. A consultoria mudou meu jogo."

Ana Paula - Nicho: Desenvolvimento Pessoal
"Na mentoria em grupo conheci parceiros incriveis. Hoje faturo R$ 80.000/mes."

Pedro Henrique - Nicho: Marketing para Advogados
"Comecei do zero e em 6 meses ja tinha um negocio de R$ 20.000/mes."

Numeros da Comunidade:
- +3.000 alunos formados
- R$ 47.000 media de faturamento mensal dos alunos ativos
- 78% taxa de sucesso em lancamentos
- 4.9/5 avaliacao media dos cursos"""
    },
]


async def popular_produtos():
    """Popula a base com documentos organizados por produto"""
    print("=" * 60)
    print("POPULANDO BASE RAG MULTI-AGENTE - PRODUTOS")
    print("=" * 60)

    # Conecta ao banco
    print("\n[1/5] Conectando ao banco de dados...")
    db = await get_db_service()
    rag = await get_rag_multi_service(db.pool)

    if not rag.initialized:
        print("ERRO: RAG Multi nao inicializado.")
        print("Execute primeiro: python scripts/migrate_rag_multi.py")
        return

    print("    Conectado!")

    # Contadores
    total_docs = 0
    produtos_inseridos = []

    # PASSO 1: Cadastra produtos na tabela de catalogo
    print(f"\n[2/5] Cadastrando PRODUTOS no catalogo...\n")

    for produto in PRODUTOS:
        produto_id = produto["produto_id"]
        produto_tipo = produto["produto_tipo"]
        produto_nome = produto["produto_nome"]

        try:
            # Cadastra o produto na tabela produtos_catalogo
            rag_multi_add_produto_sync(
                produto_id=produto_id,
                nome=produto_nome,
                tipo=produto_tipo,
                descricao=f"{produto_tipo.title()}: {produto_nome}"
            )
            print(f"  [OK] {produto_nome} ({produto_tipo}) -> ID: {produto_id}")
            produtos_inseridos.append({
                "id": produto_id,
                "nome": produto_nome,
                "tipo": produto_tipo,
                "docs": len(produto["documentos"])
            })
        except Exception as e:
            print(f"  [ERRO] {produto_nome}: {e}")

    # PASSO 2: Insere documentos de cada produto
    print(f"\n[3/5] Inserindo DOCUMENTOS por produto...\n")

    for produto in PRODUTOS:
        produto_id = produto["produto_id"]
        produto_tipo = produto["produto_tipo"]
        produto_nome = produto["produto_nome"]

        print(f"\n  [{produto_tipo.upper()}] {produto_nome}")
        print(f"  ID: {produto_id}")
        print(f"  Documentos: {len(produto['documentos'])}")

        for doc in produto["documentos"]:
            try:
                # NOVO: Metadata simplificado - apenas produto_id e produto_tipo
                # O nome do produto e buscado na tabela produtos_catalogo
                metadata = {
                    "produto_id": produto_id,
                    "produto_tipo": produto_tipo
                }

                doc_id = await rag.add_document(
                    titulo=doc["titulo"],
                    conteudo=doc["conteudo"],
                    categoria=doc["categoria"],
                    agente="vendas",  # Produtos sao para vendas
                    metadata=metadata
                )
                print(f"    -> {doc['titulo'][:50]}... (ID: {doc_id})")
                total_docs += 1

            except Exception as e:
                print(f"    ERRO: {doc['titulo'][:30]}... -> {e}")

    # Insere documentos gerais
    print(f"\n[4/5] Inserindo documentos GERAIS (sem produto)...\n")

    for doc in DOCUMENTOS_GERAIS:
        try:
            doc_id = await rag.add_document(
                titulo=doc["titulo"],
                conteudo=doc["conteudo"],
                categoria=doc["categoria"],
                agente=doc.get("agente"),
                metadata={}  # Sem produto_id
            )
            print(f"  -> {doc['titulo'][:50]}... (ID: {doc_id})")
            total_docs += 1
        except Exception as e:
            print(f"  ERRO: {doc['titulo'][:30]}... -> {e}")

    # Resumo
    print(f"\n[5/5] Resumo:")
    print(f"\n  PRODUTOS NO CATALOGO:")
    for p in produtos_inseridos:
        print(f"    - {p['nome']} ({p['tipo']}): {p['docs']} docs [ID: {p['id']}]")

    print(f"\n  DOCUMENTOS GERAIS: {len(DOCUMENTOS_GERAIS)}")
    print(f"\n  TOTAL DE DOCUMENTOS: {total_docs}")

    print("\n" + "=" * 60)
    print("PRODUTOS CADASTRADOS COM SUCESSO!")
    print("=" * 60)

    print("\n[NOVA ESTRUTURA]")
    print("- Produtos cadastrados na tabela 'produtos_catalogo'")
    print("- Documentos referenciam apenas 'produto_id' no metadata")
    print("- Nome do produto e buscado dinamicamente")

    print("\nPRODUTOS DISPONIVEIS PARA FILTRO:")
    for p in produtos_inseridos:
        print(f"  - {p['id']} ({p['nome']})")

    # Fecha conexao
    await db.disconnect()


if __name__ == "__main__":
    asyncio.run(popular_produtos())
