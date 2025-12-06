"""
Ferramentas RAG especificas do Multi-Agente
Cada agente pode ter comportamento diferente na busca
"""
from typing import Optional, Annotated
from langchain_core.tools import tool

from src.services.rag_multi_infoprodutos import (
    rag_multi_service,
    rag_multi_log_pergunta_sem_resposta_sync,
    rag_multi_listar_produtos_sync,
    rag_multi_get_produto_sync
)


# --- Helpers de RAG ---

def _rewrite_query_multi(pergunta: str, agente: str = None) -> str:
    """
    Query Rewriting: Expande perguntas vagas para melhorar a busca.
    Personalizado por agente para contexto mais preciso.
    """
    import requests
    from src.config import Config

    # Perguntas curtas (ate 5 palavras) precisam ser expandidas
    if len(pergunta.split()) <= 5:
        try:
            # Contexto especifico por agente
            contexto_agente = {
                "vendas": "Voce esta ajudando o agente de VENDAS de cursos online e infoprodutos. Foque em expandir para preco, modulos, horas de conteudo, bonus e garantia.",
                "suporte": "Voce esta ajudando o agente de SUPORTE de uma plataforma de cursos. Foque em expandir para solucoes de problemas de acesso, login e plataforma.",
                "agendamento": "Voce esta ajudando o agente de AGENDAMENTO de mentorias e consultorias. Foque em expandir para horarios, datas e disponibilidade.",
            }

            contexto = contexto_agente.get(agente, "Voce esta ajudando um agente geral.")

            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {Config.OPENAI_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "temperature": 0,
                    "max_tokens": 150,
                    "messages": [
                        {
                            "role": "system",
                            "content": f"""Voce e um assistente que reformula perguntas de clientes para busca em uma empresa de INFOPRODUTOS (cursos online, mentorias, consultorias).

{contexto}

REGRA IMPORTANTE: Mantenha SEMPRE os termos especificos da pergunta original (nomes de cursos, produtos, etc.)

Sua tarefa: Expandir a pergunta para incluir contexto relevante ao agente.

Exemplos para VENDAS:
- "quanto custa?" → "Qual o preco e valor do curso? Quais as formas de pagamento?"
- "quantas horas?" → "Qual a carga horaria total do curso? Quantas horas de conteudo?"
- "tem bonus?" → "Quais bonus estao inclusos no curso? O que vem junto?"
- "qual garantia?" → "Qual o prazo de garantia? Como funciona o reembolso?"
- "quantos modulos?" → "Quantos modulos tem o curso? Qual o conteudo programatico?"
- "quantos emails?" → "Quantos emails estao inclusos? Qual a estrutura de emails?"

Retorne APENAS a pergunta reformulada, sem explicacoes."""
                        },
                        {
                            "role": "user",
                            "content": f"Reformule esta pergunta: {pergunta}"
                        }
                    ]
                },
                timeout=10.0
            )
            response.raise_for_status()
            data = response.json()
            rewritten = data["choices"][0]["message"]["content"].strip()
            print(f"[RAG Multi] Query rewriting ({agente}): '{pergunta}' → '{rewritten}'")
            return rewritten
        except Exception as e:
            print(f"[RAG Multi] Erro no query rewriting: {e}")
            return pergunta

    return pergunta


def _grade_documents_multi(pergunta: str, documentos: list, agente: str = None) -> list:
    """
    Grading de Documentos: Avalia se os documentos retornados sao relevantes.
    Personalizado por agente para criterios diferentes.
    """
    import requests
    from src.config import Config

    if not documentos:
        return []

    # Criterios especificos por agente
    criterios_agente = {
        "vendas": "Considere relevante se o documento contem informacoes sobre cursos/mentorias/consultorias: precos, modulos, horas de conteudo, bonus, garantia, o que inclui.",
        "suporte": "Considere relevante se o documento ajuda a RESOLVER PROBLEMAS: tutoriais, FAQs, solucoes, procedimentos.",
        "agendamento": "Considere relevante se o documento ajuda com AGENDAMENTO: horarios, profissionais, disponibilidade.",
    }

    criterio = criterios_agente.get(agente, "Considere relevante se o documento responde a pergunta do cliente.")

    # Prepara o contexto dos documentos
    docs_text = ""
    for i, doc in enumerate(documentos):
        docs_text += f"\n[Documento {i+1}]\nTitulo: {doc['titulo']}\nConteudo: {doc['conteudo'][:500]}...\n"

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {Config.OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o-mini",
                "temperature": 0,
                "max_tokens": 100,
                "messages": [
                    {
                        "role": "system",
                        "content": f"""Voce e um avaliador que determina se documentos sao relevantes para responder uma pergunta.

{criterio}

Analise cada documento e retorne APENAS os numeros dos documentos relevantes, separados por virgula.
Se nenhum for relevante, retorne "nenhum".

Exemplo de resposta: "1,3" (se docs 1 e 3 forem relevantes)
Exemplo de resposta: "nenhum" (se nenhum for relevante)"""
                    },
                    {
                        "role": "user",
                        "content": f"Pergunta do cliente: {pergunta}\n\nDocumentos encontrados:{docs_text}\n\nQuais documentos sao relevantes para responder esta pergunta?"
                    }
                ]
            },
            timeout=10.0
        )
        response.raise_for_status()
        data = response.json()
        result = data["choices"][0]["message"]["content"].strip().lower()

        if result == "nenhum":
            print(f"[RAG Multi] Grading ({agente}): Nenhum documento relevante para '{pergunta}'")
            return []

        # Parse dos indices relevantes
        try:
            indices = [int(x.strip()) - 1 for x in result.split(",")]
            relevant_docs = [documentos[i] for i in indices if 0 <= i < len(documentos)]
            print(f"[RAG Multi] Grading ({agente}): {len(relevant_docs)}/{len(documentos)} documentos relevantes")
            return relevant_docs
        except:
            # Se nao conseguir parsear, retorna todos (fallback)
            return documentos

    except Exception as e:
        print(f"[RAG Multi] Erro no grading: {e}")
        return documentos  # Fallback: retorna todos


# --- Ferramentas de Produto (VENDAS) ---

@tool
def listar_produtos() -> str:
    """
    Lista todos os produtos/servicos disponiveis para venda.

    Use esta ferramenta para:
    - Mostrar opcoes ao cliente quando ele nao especificar um produto
    - Listar cursos, mentorias e consultorias disponiveis
    - Quando o cliente perguntar "o que voces tem?" ou "quais cursos?"
    """
    try:
        produtos = rag_multi_listar_produtos_sync()

        if not produtos:
            return "Nenhum produto cadastrado no momento."

        # Agrupa por tipo
        por_tipo = {}
        for p in produtos:
            tipo = p["produto_tipo"] or "outros"
            if tipo not in por_tipo:
                por_tipo[tipo] = []
            por_tipo[tipo].append(p)

        # Formata resposta
        response = "PRODUTOS DISPONIVEIS:\n\n"

        ordem_tipos = ["curso", "mentoria", "consultoria", "evento", "outros"]
        for tipo in ordem_tipos:
            if tipo in por_tipo:
                tipo_label = tipo.upper() + "S" if tipo != "outros" else "OUTROS"
                response += f"**{tipo_label}:**\n"
                for p in por_tipo[tipo]:
                    response += f"- {p['produto_nome']} (ID: {p['produto_id']})\n"
                response += "\n"

        return response

    except Exception as e:
        print(f"[RAG Multi] Erro ao listar produtos: {e}")
        return "Erro ao listar produtos. Tente novamente."


@tool
def buscar_info_produto(
    pergunta: Annotated[str, "Pergunta sobre o produto"],
    produto_id: Annotated[str, "ID do produto (ex: metodo-6-em-7, trafego-descomplicado)"]
) -> str:
    """
    Busca informacoes sobre um produto ESPECIFICO.

    IMPORTANTE: Use esta ferramenta quando o cliente ja indicou qual produto quer saber.
    O produto_id deve ser um dos IDs retornados por listar_produtos.

    Exemplos de produto_id:
    - metodo-6-em-7
    - trafego-descomplicado
    - copy-que-vende
    - mentoria-individual
    - acelerador-digital
    - consultoria-lancamento
    - consultoria-perpetuo
    """
    try:
        agente = "vendas"

        # 1. Query Rewriting
        query_expandida = _rewrite_query_multi(pergunta, agente)

        # 2. Busca filtrada por produto_id
        print(f"[RAG Multi] Buscando info do produto '{produto_id}': {pergunta}")

        try:
            results = rag_multi_service.search_sync(
                query=query_expandida,
                limit=5,
                agente=agente,
                produto_id=produto_id,
                similarity_threshold=0.25
            )
        except Exception as db_error:
            print(f"[RAG Multi] Erro no banco: {db_error}")
            return "Base de conhecimento nao configurada."

        # 2.1 Fallback: busca sem filtro de produto (docs gerais)
        if not results:
            print(f"[RAG Multi] Fallback: buscando sem filtro de produto")
            results = rag_multi_service.search_sync(
                query=query_expandida,
                limit=5,
                agente=agente,
                produto_id=None,
                similarity_threshold=0.25
            )

        if not results:
            try:
                rag_multi_log_pergunta_sem_resposta_sync(
                    pergunta=pergunta,
                    agente=agente,
                    motivo="nao_encontrado",
                    query_expandida=f"[produto:{produto_id}] {query_expandida}",
                    docs_encontrados=0
                )
            except:
                pass
            return f"Nao encontrei informacoes sobre '{produto_id}'. Verifique se o ID do produto esta correto usando listar_produtos."

        # 3. Grading
        relevant_docs = _grade_documents_multi(pergunta, results, agente)

        if not relevant_docs:
            try:
                rag_multi_log_pergunta_sem_resposta_sync(
                    pergunta=pergunta,
                    agente=agente,
                    motivo="grading_rejeitou",
                    query_expandida=f"[produto:{produto_id}] {query_expandida}",
                    docs_encontrados=len(results)
                )
            except:
                pass
            return "Encontrei documentos, mas nenhum responde sua pergunta especifica. Pode reformular?"

        # 4. Busca nome do produto na tabela de catalogo
        produto_info = rag_multi_get_produto_sync(produto_id)
        produto_nome = produto_info["produto_nome"] if produto_info else produto_id

        # 5. Formata resposta
        response = f"Informacoes sobre **{produto_nome}**:\n\n"
        for doc in relevant_docs[:3]:
            response += f"**{doc['titulo']}**\n"
            response += f"{doc['conteudo']}\n\n"

        return response

    except Exception as e:
        print(f"[RAG Multi] Erro geral em buscar_info_produto: {e}")
        return f"Erro ao buscar informacoes: {str(e)}"


# --- Ferramentas por Agente ---

@tool
def buscar_informacao_vendas(
    pergunta: Annotated[str, "Pergunta ou termo de busca sobre produtos/servicos"],
    categoria: Annotated[Optional[str], "Categoria especifica (opcional): servicos, precos, procedimentos"] = None
) -> str:
    """
    Busca informacoes para o agente de VENDAS.
    Otimizado para encontrar: precos, servicos, beneficios, diferenciais.

    Use para responder sobre:
    - Precos e valores
    - Servicos oferecidos
    - Beneficios e diferenciais
    - Procedimentos disponiveis
    """
    try:
        agente = "vendas"

        # 1. Query Rewriting
        query_expandida = _rewrite_query_multi(pergunta, agente)

        # 2. Busca na base de conhecimento (filtra por agente)
        try:
            results = rag_multi_service.search_sync(
                query=query_expandida,
                limit=5,
                categoria=categoria,
                agente=agente,
                similarity_threshold=0.25
            )
        except Exception as db_error:
            print(f"[RAG Multi] Erro no banco (tabela pode nao existir): {db_error}")
            return "Base de conhecimento nao configurada. Execute: python scripts/migrate_rag_multi.py"

        # 2.1 Fallback: busca sem categoria
        if not results and categoria:
            print(f"[RAG Multi] Fallback vendas: buscando sem categoria")
            results = rag_multi_service.search_sync(
                query=query_expandida,
                limit=5,
                categoria=None,
                agente=agente,
                similarity_threshold=0.25
            )

        # 2.2 Fallback: busca sem filtro de agente
        if not results:
            print(f"[RAG Multi] Fallback vendas: buscando sem filtro de agente")
            results = rag_multi_service.search_sync(
                query=query_expandida,
                limit=5,
                categoria=categoria,
                agente=None,
                similarity_threshold=0.25
            )

        if not results:
            try:
                rag_multi_log_pergunta_sem_resposta_sync(
                    pergunta=pergunta,
                    agente=agente,
                    motivo="nao_encontrado",
                    query_expandida=query_expandida,
                    docs_encontrados=0
                )
            except:
                pass  # Ignora erro de log se tabela nao existir
            return "Nao encontrei informacoes sobre isso. Posso ajudar de outra forma?"

        # 3. Grading
        relevant_docs = _grade_documents_multi(pergunta, results, agente)

        if not relevant_docs:
            try:
                rag_multi_log_pergunta_sem_resposta_sync(
                    pergunta=pergunta,
                    agente=agente,
                    motivo="grading_rejeitou",
                    query_expandida=query_expandida,
                    docs_encontrados=len(results)
                )
            except:
                pass
            return "Encontrei alguns documentos, mas nenhum responde diretamente sua pergunta. Posso verificar de outra forma?"

        # 4. Formata resposta
        response = "Informacoes encontradas:\n\n"
        for doc in relevant_docs[:3]:
            response += f"**{doc['titulo']}** (categoria: {doc['categoria']})\n"
            response += f"{doc['conteudo']}\n\n"

        return response

    except Exception as e:
        print(f"[RAG Multi] Erro geral em vendas: {e}")
        return f"Erro ao buscar informacoes: {str(e)}"


@tool
def buscar_informacao_suporte(
    pergunta: Annotated[str, "Problema ou duvida do cliente"],
    categoria: Annotated[Optional[str], "Categoria especifica (opcional): faq, tutoriais, problemas"] = None
) -> str:
    """
    Busca informacoes para o agente de SUPORTE.
    Otimizado para encontrar: solucoes, FAQs, tutoriais, procedimentos.

    IMPORTANTE: Esta ferramenta DEVE ser chamada ANTES de responder qualquer duvida.

    Use para:
    - Resolver problemas reportados
    - Responder duvidas frequentes
    - Fornecer tutoriais e orientacoes
    """
    try:
        agente = "suporte"

        # 1. Query Rewriting
        query_expandida = _rewrite_query_multi(pergunta, agente)

        # 2. Busca na base de conhecimento
        results = rag_multi_service.search_sync(
            query=query_expandida,
            limit=5,
            categoria=categoria,
            agente=agente,
            similarity_threshold=0.25
        )

        # 2.1 Fallback: busca sem categoria
        if not results and categoria:
            print(f"[RAG Multi] Fallback suporte: buscando sem categoria")
            results = rag_multi_service.search_sync(
                query=query_expandida,
                limit=5,
                categoria=None,
                agente=agente,
                similarity_threshold=0.25
            )

        # 2.2 Fallback: busca sem filtro de agente
        if not results:
            print(f"[RAG Multi] Fallback suporte: buscando sem filtro de agente")
            results = rag_multi_service.search_sync(
                query=query_expandida,
                limit=5,
                categoria=categoria,
                agente=None,
                similarity_threshold=0.25
            )

        if not results:
            rag_multi_log_pergunta_sem_resposta_sync(
                pergunta=pergunta,
                agente=agente,
                motivo="nao_encontrado",
                query_expandida=query_expandida,
                docs_encontrados=0
            )
            return "NAO_ENCONTRADO: Nao encontrei solucao na base de conhecimento. Considere escalar para atendimento humano."

        # 3. Grading (mais rigoroso para suporte)
        relevant_docs = _grade_documents_multi(pergunta, results, agente)

        if not relevant_docs:
            rag_multi_log_pergunta_sem_resposta_sync(
                pergunta=pergunta,
                agente=agente,
                motivo="grading_rejeitou",
                query_expandida=query_expandida,
                docs_encontrados=len(results)
            )
            return "NAO_ENCONTRADO: Documentos encontrados nao resolvem o problema. Considere escalar para atendimento humano."

        # 4. Formata resposta
        response = "Solucao encontrada:\n\n"
        for doc in relevant_docs[:2]:  # Maximo 2 para suporte (mais focado)
            response += f"**{doc['titulo']}**\n"
            response += f"{doc['conteudo']}\n\n"

        return response

    except Exception as e:
        return f"Erro ao buscar informacoes: {str(e)}"


@tool
def buscar_informacao_agendamento(
    pergunta: Annotated[str, "Duvida sobre agendamento, horarios ou profissionais"],
    categoria: Annotated[Optional[str], "Categoria especifica (opcional): horarios, profissionais, politicas"] = None
) -> str:
    """
    Busca informacoes para o agente de AGENDAMENTO.
    Otimizado para: horarios, profissionais, politicas de agendamento.

    Use para:
    - Informacoes sobre horarios de funcionamento
    - Politicas de cancelamento/remarcacao
    - Informacoes sobre profissionais
    """
    try:
        agente = "agendamento"

        # 1. Query Rewriting
        query_expandida = _rewrite_query_multi(pergunta, agente)

        # 2. Busca na base de conhecimento
        results = rag_multi_service.search_sync(
            query=query_expandida,
            limit=5,
            categoria=categoria,
            agente=agente,
            similarity_threshold=0.25
        )

        # 2.1 Fallback
        if not results:
            results = rag_multi_service.search_sync(
                query=query_expandida,
                limit=5,
                categoria=None,
                agente=None,
                similarity_threshold=0.25
            )

        if not results:
            rag_multi_log_pergunta_sem_resposta_sync(
                pergunta=pergunta,
                agente=agente,
                motivo="nao_encontrado",
                query_expandida=query_expandida,
                docs_encontrados=0
            )
            return "Nao encontrei essa informacao. Posso ajudar com o agendamento diretamente?"

        # 3. Grading
        relevant_docs = _grade_documents_multi(pergunta, results, agente)

        if not relevant_docs:
            rag_multi_log_pergunta_sem_resposta_sync(
                pergunta=pergunta,
                agente=agente,
                motivo="grading_rejeitou",
                query_expandida=query_expandida,
                docs_encontrados=len(results)
            )
            return "Nao encontrei informacao especifica. Posso ajudar com o agendamento diretamente?"

        # 4. Formata resposta
        response = "Informacoes:\n\n"
        for doc in relevant_docs[:2]:
            response += f"**{doc['titulo']}**\n"
            response += f"{doc['conteudo']}\n\n"

        return response

    except Exception as e:
        return f"Erro ao buscar informacoes: {str(e)}"


# --- Ferramentas exportadas por agente ---

# Vendas: ferramentas de produto + busca geral (fallback)
VENDAS_RAG_TOOLS = [listar_produtos, buscar_info_produto, buscar_informacao_vendas]

# Suporte e Agendamento: sem alteracao
SUPORTE_RAG_TOOLS = [buscar_informacao_suporte]
AGENDAMENTO_RAG_TOOLS = [buscar_informacao_agendamento]
