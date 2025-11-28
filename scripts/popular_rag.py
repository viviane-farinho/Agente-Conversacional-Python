#!/usr/bin/env python3
"""
Script para popular a base de conhecimento (RAG) com dados de exemplo
Execute: python scripts/popular_rag.py
"""
import asyncio
import sys
sys.path.insert(0, '.')

from src.services.database import get_db_service
from src.services.rag import get_rag_service

# Documentos de exemplo para a clínica
DOCUMENTOS = [
    # --- INFORMAÇÕES GERAIS ---
    {
        "titulo": "Sobre a Clínica",
        "categoria": "geral",
        "conteudo": """A Clínica Saúde Total é uma clínica médica e odontológica completa, oferecendo atendimento humanizado e de qualidade.
Contamos com profissionais especializados nas áreas de Clínica Geral, Cardiologia e Odontologia.
Nossa missão é proporcionar saúde e bem-estar aos nossos pacientes com atendimento personalizado."""
    },

    # --- HORÁRIOS ---
    {
        "titulo": "Horário de Funcionamento",
        "categoria": "horarios",
        "conteudo": """Horário de funcionamento da clínica:
- Segunda a Sexta-feira: 8h às 18h
- Sábados: 8h às 12h
- Domingos e Feriados: Fechado

Agendamentos podem ser feitos por WhatsApp a qualquer momento."""
    },

    # --- LOCALIZAÇÃO ---
    {
        "titulo": "Endereço e Como Chegar",
        "categoria": "localizacao",
        "conteudo": """Endereço: Rua das Flores, 123 - Centro - Brasília/DF
CEP: 70000-000

Pontos de referência: Ao lado do Shopping Central, em frente à Praça das Árvores.

Estacionamento: Estacionamento gratuito no local com 20 vagas.

Como chegar de transporte público:
- Metrô: Estação Central (5 min a pé)
- Ônibus: Linhas 101, 102, 103 (parada em frente)"""
    },

    # --- EQUIPE MÉDICA ---
    {
        "titulo": "Dr. João Paulo Ferreira - Clínico Geral",
        "categoria": "equipe",
        "conteudo": """Dr. João Paulo Ferreira
Especialidade: Médico Clínico Geral
CRM: 12345-DF

Formação: Medicina pela Universidade de Brasília (UnB)
Especialização: Medicina de Família e Comunidade

Atendimento:
- Segunda, Quarta e Sexta: 8h às 17h
- Duração da consulta: 30 minutos

Valor da consulta: R$ 150,00 (particular) ou convênios Unimed e Bradesco Saúde."""
    },
    {
        "titulo": "Dr. Roberto Almeida - Cardiologista",
        "categoria": "equipe",
        "conteudo": """Dr. Roberto Almeida
Especialidade: Médico Cardiologista
CRM: 54321-DF

Formação: Medicina pela USP
Especialização: Cardiologia pelo InCor

Atendimento:
- Terça e Quinta: 8h às 17h
- Duração da consulta: 40 minutos

Valor da consulta: R$ 250,00 (particular) ou convênios Unimed, Bradesco e SulAmérica.

Exames realizados: Eletrocardiograma, Teste ergométrico, Holter 24h."""
    },
    {
        "titulo": "Dra. Ana Silva - Dentista Clínica Geral",
        "categoria": "equipe",
        "conteudo": """Dra. Ana Silva
Especialidade: Dentista - Clínica Geral
CRO: 11111-DF

Formação: Odontologia pela UnB
Especialização: Dentística Restauradora

Atendimento:
- Segunda a Sexta: 8h às 18h
- Duração da consulta: 30-60 minutos (dependendo do procedimento)

Procedimentos: Limpeza, restaurações, extrações, clareamento dental, tratamento de canal.

Valor da avaliação: R$ 80,00
Limpeza dental: R$ 150,00"""
    },
    {
        "titulo": "Dra. Carla Mendes - Odontopediatra",
        "categoria": "equipe",
        "conteudo": """Dra. Carla Mendes
Especialidade: Dentista - Odontopediatria
CRO: 22222-DF

Formação: Odontologia pela UCB
Especialização: Odontopediatria

Atende crianças de 0 a 14 anos.

Atendimento:
- Segunda, Quarta e Sexta: 14h às 18h
- Sábados: 8h às 12h
- Duração da consulta: 30-45 minutos

Procedimentos: Primeira consulta do bebê, aplicação de flúor, selantes, restaurações, tratamento de cárie de mamadeira.

Valor da consulta: R$ 120,00"""
    },

    # --- PREÇOS ---
    {
        "titulo": "Tabela de Preços - Consultas",
        "categoria": "precos",
        "conteudo": """Valores das consultas (particular):

MÉDICAS:
- Clínico Geral (Dr. João Paulo): R$ 150,00
- Cardiologia (Dr. Roberto): R$ 250,00
- Retorno (até 30 dias): Gratuito

ODONTOLÓGICAS:
- Avaliação inicial: R$ 80,00
- Limpeza dental: R$ 150,00
- Clareamento dental: R$ 800,00
- Restauração simples: R$ 120,00
- Restauração composta: R$ 180,00
- Extração simples: R$ 150,00
- Tratamento de canal: A partir de R$ 400,00
- Consulta odontopediátrica: R$ 120,00

Formas de pagamento: Dinheiro, PIX, Cartão de débito, Cartão de crédito (até 3x sem juros)."""
    },

    # --- CONVÊNIOS ---
    {
        "titulo": "Convênios Aceitos",
        "categoria": "convenios",
        "conteudo": """Convênios aceitos na clínica:

MÉDICOS:
- Unimed (todas as categorias)
- Bradesco Saúde
- SulAmérica Saúde
- Amil
- Porto Seguro Saúde

ODONTOLÓGICOS:
- Odontoprev
- Metlife Dental
- Bradesco Dental
- SulAmérica Odonto

Para agendamento com convênio, tenha em mãos:
1. Carteirinha do convênio válida
2. Documento com foto
3. Guia de autorização (quando necessário)

Consultas particulares também disponíveis."""
    },

    # --- POLÍTICAS ---
    {
        "titulo": "Política de Agendamento e Cancelamento",
        "categoria": "politicas",
        "conteudo": """Regras de agendamento:

AGENDAMENTO:
- Agendamentos podem ser feitos por WhatsApp, telefone ou presencialmente
- Recomendamos agendar com pelo menos 2 dias de antecedência
- Para primeira consulta, chegar 15 minutos antes

CANCELAMENTO:
- Cancelamentos devem ser feitos com no mínimo 24 horas de antecedência
- Cancelamentos em cima da hora podem gerar cobrança de taxa de R$ 50,00
- Após 2 faltas sem aviso, o paciente pode ser bloqueado para novos agendamentos

REMARCAÇÃO:
- Remarcações são gratuitas se feitas com 24h de antecedência
- Sujeito à disponibilidade de horários

ATRASOS:
- Tolerância de 15 minutos de atraso
- Após esse período, a consulta pode ser remarcada"""
    },

    # --- PROCEDIMENTOS ---
    {
        "titulo": "Preparo para Exames de Sangue",
        "categoria": "procedimentos",
        "conteudo": """Orientações para exames de sangue:

JEJUM:
- Exames de glicemia e colesterol: Jejum de 8 a 12 horas
- Hemograma: Não precisa de jejum
- Durante o jejum, pode beber água normalmente

MEDICAMENTOS:
- Medicamentos de uso contínuo (pressão, diabetes, tireoide): Tomar normalmente
- Informar ao técnico todos os medicamentos em uso

ANTES DO EXAME:
- Evitar atividade física intensa nas 24h anteriores
- Não consumir bebida alcoólica nas 72h anteriores
- Dormir bem na noite anterior

RESULTADOS:
- Disponíveis em 2-3 dias úteis
- Retirar na recepção ou solicitar por e-mail"""
    },
    {
        "titulo": "Orientações Pós-Limpeza Dental",
        "categoria": "procedimentos",
        "conteudo": """Cuidados após limpeza dental:

PRIMEIRAS HORAS:
- Sensibilidade nos dentes é normal e passa em 24-48h
- Evitar alimentos muito quentes ou muito frios por 24h
- Gengiva pode ficar sensível - é normal

HIGIENE:
- Escove os dentes normalmente, mas com delicadeza
- Use escova de cerdas macias
- Fio dental pode ser usado normalmente

ALIMENTAÇÃO:
- Evitar alimentos que mancham (café, vinho, açaí) por 24h se fez polimento
- Evitar alimentos muito duros nas primeiras horas

RETORNO:
- Recomendamos limpeza a cada 6 meses
- Em caso de sangramento persistente, entre em contato"""
    },

    # --- CONTATO ---
    {
        "titulo": "Canais de Contato",
        "categoria": "contato",
        "conteudo": """Formas de entrar em contato:

WhatsApp: (61) 99958-5087 (atendimento 24h por IA)
Telefone fixo: (61) 3333-4444 (horário comercial)
E-mail: contato@clinicasaudetotal.com.br

Redes sociais:
- Instagram: @clinicasaudetotal
- Facebook: /clinicasaudetotal

Para emergências fora do horário de funcionamento, procure o pronto-socorro mais próximo."""
    }
]


async def popular_base():
    """Popula a base de conhecimento com os documentos de exemplo"""
    print("🚀 Iniciando população da base de conhecimento...")

    # Conecta ao banco
    db = await get_db_service()
    rag = await get_rag_service(db.pool)

    if not rag.initialized:
        print("❌ RAG não inicializado. Verifique se a extensão 'vector' está habilitada no Supabase.")
        print("   Acesse: Database > Extensions > Buscar 'vector' > Enable")
        return

    print(f"✅ Conectado ao banco de dados")
    print(f"📝 Inserindo {len(DOCUMENTOS)} documentos...\n")

    for i, doc in enumerate(DOCUMENTOS, 1):
        try:
            doc_id = await rag.add_document(
                titulo=doc["titulo"],
                conteudo=doc["conteudo"],
                categoria=doc["categoria"]
            )
            print(f"  [{i}/{len(DOCUMENTOS)}] ✅ {doc['titulo']} (ID: {doc_id})")
        except Exception as e:
            print(f"  [{i}/{len(DOCUMENTOS)}] ❌ {doc['titulo']}: {e}")

    print("\n✅ Base de conhecimento populada com sucesso!")
    print("\n📊 Resumo por categoria:")

    categorias = await rag.get_categories()
    for cat in categorias:
        docs = await rag.list_documents(categoria=cat)
        print(f"   - {cat}: {len(docs)} documento(s)")

    # Fecha conexão
    await db.disconnect()


if __name__ == "__main__":
    asyncio.run(popular_base())
