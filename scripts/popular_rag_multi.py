#!/usr/bin/env python3
"""
Script para popular a base de conhecimento do RAG Multi-Agente
Base de conhecimento do INFOPRODUTOR (Rafael Oliveira)

Execute: python scripts/popular_rag_multi.py
"""
import asyncio
import sys
sys.path.insert(0, '.')

from src.services.database import get_db_service
from src.services.rag_multi import get_rag_multi_service

# ============================================
# DOCUMENTOS DO INFOPRODUTOR - RAFAEL OLIVEIRA
# ============================================
# agente = None significa disponivel para todos os agentes
# agente = "vendas" | "suporte" | "agendamento" significa especifico para aquele agente

DOCUMENTOS = [
    # =========================================================================
    # SOBRE O MENTOR (disponivel para todos)
    # =========================================================================
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
- Podcast: Papo de Infoprodutor (Spotify)

Contato Comercial:
- WhatsApp: Este canal
- Email: contato@rafaeloliveira.com.br"""
    },

    # =========================================================================
    # CURSOS (para VENDAS)
    # =========================================================================
    {
        "titulo": "Curso Metodo 6 em 7 Simplificado",
        "categoria": "cursos",
        "agente": "vendas",
        "conteudo": """Metodo 6 em 7 Simplificado

O curso mais completo para voce fazer seu primeiro 6 em 7 (R$ 100.000 em 7 dias).

O que voce vai aprender:
- Modulo 1: Mentalidade do Infoprodutor de Sucesso
- Modulo 2: Escolhendo seu Nicho Lucrativo
- Modulo 3: Criando sua Oferta Irresistivel
- Modulo 4: Estrutura do Lancamento Perfeito
- Modulo 5: Captacao de Leads
- Modulo 6: Semana de Aquecimento
- Modulo 7: Abertura do Carrinho
- Modulo 8: Fechamento com Escassez
- Modulo 9: Pos-venda e Retencao

Bonus Exclusivos:
- Templates de copy prontos para usar
- Planilha de planejamento de lancamento
- Acesso a comunidade VIP no Telegram
- 3 lives mensais de tira-duvidas

Investimento:
- A vista: R$ 1.997,00
- Parcelado: 12x de R$ 197,00

Garantia: 7 dias de garantia incondicional. Se nao gostar, devolvemos 100% do seu dinheiro.

Acesso:
- Acesso vitalicio a plataforma
- Atualizacoes gratuitas para sempre
- Certificado de conclusao

Para quem e:
- Iniciantes que querem comecar no digital
- Profissionais que querem monetizar conhecimento
- Empreendedores buscando escalar online"""
    },
    {
        "titulo": "Curso Trafego Descomplicado",
        "categoria": "cursos",
        "agente": "vendas",
        "conteudo": """Trafego Descomplicado

Aprenda a criar campanhas de trafego pago que convertem, mesmo comecando do zero.

Conteudo:
- Meta Ads (Facebook e Instagram) do basico ao avancado
- Google Ads para infoprodutores
- Remarketing estrategico
- Publicos e segmentacoes que funcionam
- Otimizacao de campanhas
- Escalando com ROI positivo

Carga horaria: 40 horas de conteudo

Investimento:
- A vista: R$ 997,00
- Parcelado: 12x de R$ 97,00

Pre-requisitos: Nenhum! O curso e do zero ao avancado.

Bonus:
- Biblioteca de criativos validados
- Swipe file com 100 headlines
- Grupo de networking"""
    },
    {
        "titulo": "Curso Copy que Vende",
        "categoria": "cursos",
        "agente": "vendas",
        "conteudo": """Copy que Vende

Domine a arte da persuasao escrita e multiplique suas conversoes.

Modulos:
1. Fundamentos da Copywriting
2. Pesquisa de Publico-Alvo
3. Headlines Magneticas
4. Storytelling para Vendas
5. Gatilhos Mentais na Pratica
6. Estruturas de Copy (AIDA, PAS, 4Ps)
7. Copy para Paginas de Vendas
8. Copy para Emails
9. Copy para Anuncios
10. VSL - Video Sales Letter

Investimento:
- A vista: R$ 497,00
- Parcelado: 12x de R$ 47,00

Bonus:
- 50 templates de email prontos
- Checklist de revisao de copy
- Acesso a exemplos reais comentados"""
    },

    # =========================================================================
    # MENTORIAS (para VENDAS)
    # =========================================================================
    {
        "titulo": "Mentoria Premium Individual",
        "categoria": "mentorias",
        "agente": "vendas",
        "conteudo": """Mentoria Premium Individual

Acompanhamento personalizado para acelerar seus resultados no digital.

O que inclui:
- 4 sessoes individuais por mes (1h cada) via Zoom
- Acesso direto ao Rafael via WhatsApp
- Analise completa do seu negocio
- Plano de acao personalizado
- Revisao de copies e paginas
- Acompanhamento de metricas

Duracao: 3 meses (renovavel)

Investimento:
- Mensal: R$ 3.000/mes
- Trimestral a vista: R$ 7.500 (economia de R$ 1.500)

Pre-requisitos:
- Ja ter um produto ou ideia validada
- Disponibilidade para implementar
- Comprometimento com os encontros

Vagas limitadas: Apenas 10 mentorados por vez para garantir qualidade.

Proxima turma: Entrevistas abertas - agende uma conversa para saber se a mentoria e para voce."""
    },
    {
        "titulo": "Mentoria em Grupo - Acelerador Digital",
        "categoria": "mentorias",
        "agente": "vendas",
        "conteudo": """Acelerador Digital - Mentoria em Grupo

Mentoria em grupo para quem quer resultados com investimento acessivel.

Formato:
- Encontros semanais ao vivo (quartas as 20h)
- Grupo exclusivo no Telegram
- Hotseats rotativos
- Desafios mensais com premiacao
- Networking com outros mentorados

Duracao: 6 meses

Investimento:
- Mensal: R$ 497/mes
- Semestral a vista: R$ 2.497 (economia de R$ 485)

Bonus para quem entrar agora:
- Acesso a todos os cursos do Rafael
- 1 sessao individual de onboarding
- Kit de templates exclusivo

Resultados dos alunos:
- Media de faturamento: R$ 47.000/mes apos 6 meses
- 78% dos alunos fazem pelo menos 1 lancamento durante a mentoria"""
    },

    # =========================================================================
    # CONSULTORIAS (para VENDAS)
    # =========================================================================
    {
        "titulo": "Consultoria de Lancamento",
        "categoria": "consultorias",
        "agente": "vendas",
        "conteudo": """Consultoria de Lancamento

Planejamento completo do seu lancamento com acompanhamento do Rafael.

O que voce recebe:
- Diagnostico inicial do seu negocio (2h)
- Plano de lancamento detalhado
- 4 reunioes de acompanhamento durante o lancamento
- Revisao de todos os materiais
- Suporte via WhatsApp durante o periodo

Duracao: 45 dias (periodo do lancamento)

Investimento:
- Valor: R$ 15.000
- Parcelado: 3x de R$ 5.500

Bonus:
- Analise pos-lancamento
- Plano de melhorias para proximo lancamento

Ideal para:
- Quem vai fazer lancamento acima de R$ 100.000
- Infoprodutores experientes buscando otimizacao
- Negocios com equipe propria"""
    },
    {
        "titulo": "Consultoria de Funil Perpetuo",
        "categoria": "consultorias",
        "agente": "vendas",
        "conteudo": """Consultoria de Funil Perpetuo

Monte um funil que vende todos os dias no automatico.

Entregaveis:
- Mapeamento completo do funil
- Estrutura de emails (sequencia de 21 dias)
- Copy da pagina de vendas
- Estrategia de trafego perpetuo
- Setup tecnico orientado

Duracao: 30 dias para entrega

Investimento:
- Valor: R$ 8.000
- Parcelado: 2x de R$ 4.400

Suporte: 60 dias de suporte pos-entrega para ajustes"""
    },

    # =========================================================================
    # FORMAS DE PAGAMENTO (para VENDAS)
    # =========================================================================
    {
        "titulo": "Formas de Pagamento",
        "categoria": "pagamento",
        "agente": "vendas",
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

    # =========================================================================
    # DEPOIMENTOS E RESULTADOS (para VENDAS)
    # =========================================================================
    {
        "titulo": "Depoimentos e Resultados de Alunos",
        "categoria": "depoimentos",
        "agente": "vendas",
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

    # =========================================================================
    # PROGRAMA DE AFILIADOS (para VENDAS)
    # =========================================================================
    {
        "titulo": "Programa de Afiliados",
        "categoria": "afiliados",
        "agente": "vendas",
        "conteudo": """Programa de Afiliados

Ganhe comissoes indicando nossos produtos!

Comissoes:
- Cursos: 40% de comissao
- Mentorias: 20% de comissao (primeiro mes)
- Consultorias: 10% de comissao

Como funciona:
1. Cadastre-se em rafaeloliveira.com.br/afiliados
2. Pegue seu link exclusivo
3. Divulgue para sua audiencia
4. Receba comissoes a cada venda

Pagamentos:
- Pagamento todo dia 15
- Minimo para saque: R$ 100
- Via PIX ou transferencia bancaria

Materiais de divulgacao:
- Banners prontos
- Copies para WhatsApp
- Emails swipe files
- Criativos para anuncios

Suporte para afiliados: Grupo exclusivo + lives mensais de estrategias"""
    },

    # =========================================================================
    # FAQ E SUPORTE (para SUPORTE)
    # =========================================================================
    {
        "titulo": "Perguntas Frequentes - FAQ",
        "categoria": "faq",
        "agente": "suporte",
        "conteudo": """Perguntas Frequentes

ACESSO AOS CURSOS:

Quanto tempo tenho de acesso?
Acesso vitalicio! Uma vez comprado, e seu para sempre.

Posso baixar as aulas?
Sim, todas as aulas tem opcao de download.

Funciona no celular?
Sim, nossa plataforma e 100% responsiva.

SUPORTE:

Como falo com o suporte?
- WhatsApp: Este canal (resposta em ate 2h comerciais)
- Email: suporte@rafaeloliveira.com.br

Horario de atendimento:
Segunda a sexta: 9h as 18h
Sabados: 9h as 12h

RESULTADOS:

Em quanto tempo vejo resultados?
Depende da sua dedicacao. Alunos aplicados veem resultados em 30-60 dias.

Funciona para qualquer nicho?
Sim! Nossos metodos sao aplicaveis a qualquer mercado.

MENTORIAS:

Posso fazer mentoria sendo iniciante?
A mentoria em grupo (Acelerador Digital) aceita iniciantes.
A mentoria individual e para quem ja tem produto.

Como funciona a selecao para mentoria individual?
Fazemos uma entrevista para entender se a mentoria e adequada ao seu momento."""
    },
    {
        "titulo": "Problemas de Acesso a Plataforma",
        "categoria": "problemas",
        "agente": "suporte",
        "conteudo": """Solucoes para Problemas de Acesso

PROBLEMA: Esqueci minha senha
SOLUCAO: Acesse rafaeloliveira.com.br/recuperar-senha e siga as instrucoes.

PROBLEMA: Nao recebi o acesso apos a compra
SOLUCAO:
1. Verifique a caixa de spam/promocoes
2. Aguarde ate 24h uteis para processamento
3. Se persistir, envie o comprovante de pagamento aqui

PROBLEMA: Erro ao acessar a plataforma
SOLUCAO:
1. Limpe o cache do navegador
2. Tente outro navegador (Chrome, Firefox)
3. Tente em modo anonimo
4. Se persistir, envie print do erro

PROBLEMA: Aula nao carrega ou video trava
SOLUCAO:
1. Verifique sua conexao com internet
2. Reduza a qualidade do video
3. Tente baixar a aula para assistir offline
4. Limpe o cache do navegador

PROBLEMA: Modulos bloqueados
SOLUCAO: Alguns cursos tem liberacao gradual. Verifique na pagina do curso a data de liberacao do proximo modulo.

Para problemas nao listados, escale para atendimento humano."""
    },
    {
        "titulo": "Politica de Reembolso Detalhada",
        "categoria": "problemas",
        "agente": "suporte",
        "conteudo": """Politica de Reembolso

CURSOS ONLINE:
- Prazo: Ate 7 dias corridos apos a compra
- Condicao: Nenhuma - garantia incondicional
- Processo: Solicite via WhatsApp ou email
- Prazo de estorno: 7-10 dias uteis para cartao, 3 dias uteis para PIX

MENTORIAS:
- Prazo: Proporcional aos encontros nao realizados
- Condicao: Solicitacao antes do proximo encontro
- Processo: Agendamos uma conversa para entender o motivo

CONSULTORIAS:
- Antes do inicio: Reembolso de 80%
- Apos inicio sem entrega: Reembolso de 50%
- Apos entrega: Sem reembolso

COMO SOLICITAR REEMBOLSO:
1. Envie mensagem neste WhatsApp
2. Informe: Nome, email da compra, produto
3. Aguarde confirmacao em ate 24h
4. Estorno sera processado

Importante: Nao pedimos justificativa para reembolso de cursos dentro do prazo de garantia."""
    },

    # =========================================================================
    # AGENDA E EVENTOS (para AGENDAMENTO)
    # =========================================================================
    {
        "titulo": "Agenda e Proximos Eventos",
        "categoria": "agenda",
        "agente": "agendamento",
        "conteudo": """Proximos Eventos e Agenda

LIVES SEMANAIS (Gratuitas):
- Toda terca as 20h no Instagram @rafaeloliveira.digital
- Temas rotativos sobre lancamentos, trafego e copy

PROXIMOS EVENTOS PAGOS:

Workshop Intensivo de Lancamento:
- Data: Ultimo sabado de cada mes
- Horario: 9h as 18h (online)
- Investimento: R$ 297
- Inclui: Certificado + Gravacao

Imersao Presencial 6 em 7:
- Proxima data: Marco/2025
- Local: Sao Paulo - SP
- Investimento: R$ 2.997
- Vagas limitadas: 50 pessoas

AGENDA PARA MENTORIAS:
- Mentorias individuais: Tercas e quintas
- Grupo Acelerador: Quartas as 20h
- Para agendar: Fale comigo neste WhatsApp"""
    },
    {
        "titulo": "Como Agendar Entrevista para Mentoria",
        "categoria": "agenda",
        "agente": "agendamento",
        "conteudo": """Agendamento de Entrevista para Mentoria

TIPOS DE ENTREVISTA:

1. Entrevista para Mentoria Individual
   - Duracao: 30 minutos
   - Objetivo: Conhecer voce e seu negocio
   - Disponibilidade: Tercas e quintas, 10h as 17h

2. Apresentacao Acelerador Digital (Grupo)
   - Duracao: 20 minutos
   - Objetivo: Explicar o formato da mentoria em grupo
   - Disponibilidade: Segunda a sexta, 14h as 18h

DADOS NECESSARIOS PARA AGENDAR:
- Nome completo
- Email
- Telefone/WhatsApp
- Breve descricao do seu negocio atual
- Data e horario preferido

COMO FUNCIONA:
1. Voce me passa os dados acima
2. Eu verifico a disponibilidade
3. Confirmo o horario e envio o link do Zoom
4. Voce recebe lembrete 1h antes

O QUE PREPARAR PARA A ENTREVISTA:
- Resumo do seu negocio ou ideia
- Seus objetivos para os proximos 6 meses
- Principais desafios atuais
- Duvidas que queira tirar"""
    },
    {
        "titulo": "Reagendamento e Cancelamento de Reunioes",
        "categoria": "agenda",
        "agente": "agendamento",
        "conteudo": """Politica de Reagendamento e Cancelamento

REAGENDAMENTO:
- Avise com pelo menos 24h de antecedencia
- Maximo de 2 reagendamentos por reuniao
- Reagendamento sujeito a disponibilidade

CANCELAMENTO:
- Avise o mais rapido possivel
- Sem custo para cancelamento de entrevistas
- Para sessoes pagas, consulte politica de reembolso

ATRASOS:
- Tolerancia de 10 minutos
- Apos 10 min sem aviso, reuniao pode ser cancelada
- Conte como 1 dos 2 reagendamentos permitidos

COMO REAGENDAR OU CANCELAR:
1. Envie mensagem neste WhatsApp
2. Informe: Nome, data original, motivo
3. Sugerimos 2-3 novos horarios
4. Confirmo a nova data

NO-SHOW (Falta sem aviso):
- 1a falta: Aviso
- 2a falta: Necessario remarcar com 50% de antecedencia paga
- 3a falta: Bloqueio temporario de agendamentos"""
    },
]


async def popular_base():
    """Popula a base de conhecimento do Multi-Agente com dados do Infoprodutor"""
    print("=" * 60)
    print("POPULANDO BASE RAG MULTI-AGENTE - INFOPRODUTOR")
    print("=" * 60)

    # Conecta ao banco
    print("\n[1/3] Conectando ao banco de dados...")
    db = await get_db_service()
    rag = await get_rag_multi_service(db.pool)

    if not rag.initialized:
        print("ERRO: RAG Multi nao inicializado.")
        print("Execute primeiro: python scripts/migrate_rag_multi.py")
        return

    print("    Conectado!")

    # Insere documentos
    print(f"\n[2/3] Inserindo {len(DOCUMENTOS)} documentos...\n")

    contagem = {"vendas": 0, "suporte": 0, "agendamento": 0, "geral": 0}

    for i, doc in enumerate(DOCUMENTOS, 1):
        try:
            doc_id = await rag.add_document(
                titulo=doc["titulo"],
                conteudo=doc["conteudo"],
                categoria=doc["categoria"],
                agente=doc.get("agente")
            )
            agente_label = doc.get("agente") or "geral"
            contagem[agente_label] = contagem.get(agente_label, 0) + 1
            print(f"  [{i}/{len(DOCUMENTOS)}] {doc['titulo'][:40]}... ({agente_label}) -> ID: {doc_id}")
        except Exception as e:
            print(f"  [{i}/{len(DOCUMENTOS)}] ERRO: {doc['titulo'][:30]}... -> {e}")

    # Resumo
    print(f"\n[3/3] Resumo:")
    print(f"    - Documentos gerais (todos agentes): {contagem['geral']}")
    print(f"    - Documentos para Vendas: {contagem['vendas']}")
    print(f"    - Documentos para Suporte: {contagem['suporte']}")
    print(f"    - Documentos para Agendamento: {contagem['agendamento']}")
    print(f"    - TOTAL: {sum(contagem.values())}")

    print("\n" + "=" * 60)
    print("BASE INFOPRODUTOR POPULADA COM SUCESSO!")
    print("=" * 60)

    # Fecha conexao
    await db.disconnect()


if __name__ == "__main__":
    asyncio.run(popular_base())
