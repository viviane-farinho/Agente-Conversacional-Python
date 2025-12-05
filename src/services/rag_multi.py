"""
Servico de RAG (Retrieval-Augmented Generation) para Multi-Agente
Permite aos agentes especializados buscar informacoes na base de conhecimento

Paradigma: Funcional
Separado do RAG simples para permitir evolucao independente
"""
import json
from typing import Optional, List

import asyncpg
import httpx
import requests
import psycopg2
from psycopg2.extras import RealDictCursor

from src.config import Config
from src.services.database import db_get_pool


# --- Estado Global ---

_initialized: bool = False
_embedding_model: str = "text-embedding-3-small"
_embedding_dimension: int = 1536


def _parse_metadata(metadata) -> dict:
    """Parse metadata que pode vir como dict ou string JSON"""
    if metadata is None:
        return {}
    if isinstance(metadata, dict):
        return metadata
    try:
        return json.loads(metadata)
    except (json.JSONDecodeError, TypeError):
        return {}


# --- Helpers de Embedding ---

async def _get_embedding_async(text: str) -> List[float]:
    """
    Gera embedding usando OpenAI API (async)

    Args:
        text: Texto para gerar embedding

    Returns:
        Lista de floats representando o embedding
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {Config.OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": _embedding_model,
                "input": text
            },
            timeout=30.0
        )
        response.raise_for_status()
        data = response.json()
        return data["data"][0]["embedding"]


def _get_embedding_sync(text: str) -> List[float]:
    """
    Gera embedding usando OpenAI API (sync)

    Args:
        text: Texto para gerar embedding

    Returns:
        Lista de floats representando o embedding
    """
    response = requests.post(
        "https://api.openai.com/v1/embeddings",
        headers={
            "Authorization": f"Bearer {Config.OPENAI_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": _embedding_model,
            "input": text
        },
        timeout=30.0
    )
    response.raise_for_status()
    data = response.json()
    return data["data"][0]["embedding"]


def _get_connection_string() -> str:
    """Retorna a connection string do banco"""
    if Config.DATABASE_URL:
        return Config.DATABASE_URL
    return f"postgresql://{Config.POSTGRES_USER}:{Config.POSTGRES_PASSWORD}@{Config.POSTGRES_HOST}:{Config.POSTGRES_PORT}/{Config.POSTGRES_DB}"


# --- Inicializacao ---

async def rag_multi_init_tables() -> bool:
    """
    Cria as tabelas necessarias para RAG do Multi-Agente

    Returns:
        True se inicializou com sucesso
    """
    global _initialized

    try:
        pool = await db_get_pool()

        async with pool.acquire() as conn:
            # Habilita extensao pgvector
            try:
                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            except Exception as e:
                print(f"[RAG Multi] Aviso: Nao foi possivel criar extensao vector: {e}")
                print("Para usar RAG, habilite a extensao 'vector' no Supabase Dashboard")
                return False

            # Tabela de catalogo de produtos (nova estrutura simplificada)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS produtos_catalogo (
                    id SERIAL PRIMARY KEY,
                    produto_id VARCHAR(100) UNIQUE NOT NULL,
                    nome VARCHAR(255) NOT NULL,
                    tipo VARCHAR(50) NOT NULL,
                    descricao TEXT,
                    ativo BOOLEAN DEFAULT TRUE,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            # Indice para busca por tipo
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_produtos_catalogo_tipo
                ON produtos_catalogo(tipo)
            """)

            # Indice para produtos ativos
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_produtos_catalogo_ativo
                ON produtos_catalogo(ativo)
            """)

            # Tabela de documentos do Multi-Agente
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS empresa_documentos_multi (
                    id SERIAL PRIMARY KEY,
                    titulo VARCHAR(255) NOT NULL,
                    categoria VARCHAR(100),
                    agente VARCHAR(50),
                    conteudo TEXT NOT NULL,
                    embedding vector(1536),
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            # Indice para categoria
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_documentos_multi_categoria
                ON empresa_documentos_multi(categoria)
            """)

            # Indice para agente
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_documentos_multi_agente
                ON empresa_documentos_multi(agente)
            """)

            # Indice vetorial (se houver dados)
            try:
                count = await conn.fetchval("SELECT COUNT(*) FROM empresa_documentos_multi")
                if count > 0:
                    await conn.execute("""
                        CREATE INDEX IF NOT EXISTS idx_documentos_multi_embedding
                        ON empresa_documentos_multi
                        USING ivfflat (embedding vector_cosine_ops)
                        WITH (lists = 100)
                    """)
            except Exception:
                pass

            # Tabela de perguntas sem resposta do Multi-Agente (para feedback loop)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS perguntas_sem_resposta_multi (
                    id SERIAL PRIMARY KEY,
                    pergunta TEXT NOT NULL,
                    telefone VARCHAR(50),
                    conversation_id VARCHAR(100),
                    agente VARCHAR(50),
                    motivo VARCHAR(100) DEFAULT 'nao_encontrado',
                    query_expandida TEXT,
                    docs_encontrados INTEGER DEFAULT 0,
                    resolvido BOOLEAN DEFAULT FALSE,
                    documento_criado_id INTEGER REFERENCES empresa_documentos_multi(id),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            # Indice para perguntas nao resolvidas
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_perguntas_multi_sem_resposta_resolvido
                ON perguntas_sem_resposta_multi(resolvido, created_at DESC)
            """)

            # Indice para agente
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_perguntas_multi_agente
                ON perguntas_sem_resposta_multi(agente)
            """)

            _initialized = True
            print("[RAG Multi] Tabelas inicializadas com sucesso")
            return True

    except Exception as e:
        print(f"[RAG Multi] Erro ao inicializar: {e}")
        _initialized = False
        return False


# --- CRUD de Documentos ---

async def rag_multi_add_document(
    titulo: str,
    conteudo: str,
    categoria: str = "geral",
    agente: str = None,
    metadata: dict = None
) -> int:
    """
    Adiciona um documento a base de conhecimento do Multi-Agente

    Args:
        titulo: Titulo do documento
        conteudo: Conteudo do documento
        categoria: Categoria (ex: servicos, horarios, precos)
        agente: Agente especifico (vendas, suporte, agendamento) ou None para todos
        metadata: Metadados adicionais

    Returns:
        ID do documento criado
    """
    pool = await db_get_pool()

    # Gera embedding
    embedding = await _get_embedding_async(f"{titulo}\n{conteudo}")

    async with pool.acquire() as conn:
        result = await conn.fetchrow("""
            INSERT INTO empresa_documentos_multi (titulo, categoria, agente, conteudo, embedding, metadata)
            VALUES ($1, $2, $3, $4, $5::vector, $6::jsonb)
            RETURNING id
        """, titulo, categoria, agente, conteudo, str(embedding), json.dumps(metadata or {}))

        return result["id"]


async def rag_multi_update_document(
    doc_id: int,
    titulo: str = None,
    conteudo: str = None,
    categoria: str = None,
    agente: str = None,
    metadata: dict = None
) -> bool:
    """
    Atualiza um documento existente

    Args:
        doc_id: ID do documento
        titulo: Novo titulo
        conteudo: Novo conteudo
        categoria: Nova categoria
        agente: Novo agente
        metadata: Novos metadados

    Returns:
        True se atualizou com sucesso
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        # Busca documento atual
        current = await conn.fetchrow(
            "SELECT * FROM empresa_documentos_multi WHERE id = $1",
            doc_id
        )
        if not current:
            return False

        # Usa valores atuais se nao fornecidos
        titulo = titulo or current["titulo"]
        conteudo = conteudo or current["conteudo"]
        categoria = categoria or current["categoria"]
        agente = agente if agente is not None else current["agente"]
        metadata = metadata or (json.loads(current["metadata"]) if current["metadata"] else {})

        # Regenera embedding
        embedding = await _get_embedding_async(f"{titulo}\n{conteudo}")

        await conn.execute("""
            UPDATE empresa_documentos_multi
            SET titulo = $1, categoria = $2, agente = $3, conteudo = $4,
                embedding = $5::vector, metadata = $6::jsonb,
                updated_at = NOW()
            WHERE id = $7
        """, titulo, categoria, agente, conteudo, str(embedding), json.dumps(metadata), doc_id)

        return True


async def rag_multi_delete_document(doc_id: int) -> bool:
    """
    Remove um documento

    Args:
        doc_id: ID do documento

    Returns:
        True se removeu com sucesso
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM empresa_documentos_multi WHERE id = $1",
            doc_id
        )
        return "DELETE 1" in result


async def rag_multi_list_documents(
    categoria: str = None,
    agente: str = None,
    limit: int = 50
) -> List[dict]:
    """
    Lista todos os documentos

    Args:
        categoria: Filtrar por categoria
        agente: Filtrar por agente
        limit: Numero maximo de resultados

    Returns:
        Lista de documentos
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        query = "SELECT id, titulo, categoria, agente, conteudo, metadata, created_at FROM empresa_documentos_multi WHERE 1=1"
        params = []

        if categoria:
            params.append(categoria)
            query += f" AND categoria = ${len(params)}"

        if agente:
            params.append(agente)
            query += f" AND (agente = ${len(params)} OR agente IS NULL)"

        params.append(limit)
        query += f" ORDER BY created_at DESC LIMIT ${len(params)}"

        rows = await conn.fetch(query, *params)

        return [
            {
                "id": row["id"],
                "titulo": row["titulo"],
                "categoria": row["categoria"],
                "agente": row["agente"],
                "conteudo": row["conteudo"],
                "metadata": _parse_metadata(row["metadata"]),
                "created_at": row["created_at"].isoformat()
            }
            for row in rows
        ]


async def rag_multi_get_categories() -> List[str]:
    """
    Retorna todas as categorias existentes

    Returns:
        Lista de categorias
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT DISTINCT categoria
            FROM empresa_documentos_multi
            WHERE categoria IS NOT NULL
            ORDER BY categoria
        """)
        return [row["categoria"] for row in rows]


# --- Perguntas Sem Resposta (Feedback Loop) ---

def rag_multi_log_pergunta_sem_resposta_sync(
    pergunta: str,
    agente: str = None,
    motivo: str = "nao_encontrado",
    query_expandida: str = None,
    docs_encontrados: int = 0,
    telefone: str = None,
    conversation_id: str = None
) -> int:
    """
    Registra uma pergunta que o RAG nao conseguiu responder (sync)

    Args:
        pergunta: Pergunta original do usuario
        agente: Agente que fez a busca (vendas, suporte, etc)
        motivo: Motivo da falha (nao_encontrado, grading_rejeitou, etc)
        query_expandida: Query apos rewriting
        docs_encontrados: Quantidade de docs encontrados antes do grading
        telefone: Telefone do contato (opcional)
        conversation_id: ID da conversa (opcional)

    Returns:
        ID do registro criado
    """
    conn_string = _get_connection_string()
    conn = psycopg2.connect(conn_string)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO perguntas_sem_resposta_multi
                (pergunta, agente, motivo, query_expandida, docs_encontrados, telefone, conversation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (pergunta, agente, motivo, query_expandida, docs_encontrados, telefone, conversation_id))
            result = cur.fetchone()
            conn.commit()
            print(f"[RAG Multi] Pergunta sem resposta registrada: '{pergunta[:50]}...' (agente: {agente}, motivo: {motivo})")
            return result[0] if result else 0
    except Exception as e:
        print(f"[RAG Multi] Erro ao registrar pergunta sem resposta: {e}")
        return 0
    finally:
        conn.close()


async def rag_multi_log_pergunta_sem_resposta(
    pergunta: str,
    agente: str = None,
    motivo: str = "nao_encontrado",
    query_expandida: str = None,
    docs_encontrados: int = 0,
    telefone: str = None,
    conversation_id: str = None
) -> int:
    """
    Registra uma pergunta que o RAG nao conseguiu responder (async)
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        result = await conn.fetchrow("""
            INSERT INTO perguntas_sem_resposta_multi
            (pergunta, agente, motivo, query_expandida, docs_encontrados, telefone, conversation_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id
        """, pergunta, agente, motivo, query_expandida, docs_encontrados, telefone, conversation_id)

        print(f"[RAG Multi] Pergunta sem resposta registrada: '{pergunta[:50]}...' (agente: {agente}, motivo: {motivo})")
        return result["id"] if result else 0


async def rag_multi_listar_perguntas_sem_resposta(
    apenas_nao_resolvidas: bool = True,
    agente: str = None,
    limit: int = 50
) -> List[dict]:
    """
    Lista perguntas que o RAG nao conseguiu responder

    Args:
        apenas_nao_resolvidas: Se True, retorna apenas nao resolvidas
        agente: Filtrar por agente
        limit: Numero maximo de resultados

    Returns:
        Lista de perguntas
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        query = """
            SELECT id, pergunta, telefone, conversation_id, agente, motivo,
                   query_expandida, docs_encontrados, resolvido,
                   documento_criado_id, created_at
            FROM perguntas_sem_resposta_multi
            WHERE 1=1
        """
        params = []

        if apenas_nao_resolvidas:
            query += " AND resolvido = FALSE"

        if agente:
            params.append(agente)
            query += f" AND agente = ${len(params)}"

        params.append(limit)
        query += f" ORDER BY created_at DESC LIMIT ${len(params)}"

        rows = await conn.fetch(query, *params)

        return [
            {
                "id": row["id"],
                "pergunta": row["pergunta"],
                "telefone": row["telefone"],
                "conversation_id": row["conversation_id"],
                "agente": row["agente"],
                "motivo": row["motivo"],
                "query_expandida": row["query_expandida"],
                "docs_encontrados": row["docs_encontrados"],
                "resolvido": row["resolvido"],
                "documento_criado_id": row["documento_criado_id"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None
            }
            for row in rows
        ]


async def rag_multi_marcar_pergunta_resolvida(
    pergunta_id: int,
    documento_criado_id: int = None
) -> bool:
    """
    Marca uma pergunta como resolvida

    Args:
        pergunta_id: ID da pergunta
        documento_criado_id: ID do documento criado para resolver (opcional)

    Returns:
        True se atualizou com sucesso
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        result = await conn.execute("""
            UPDATE perguntas_sem_resposta_multi
            SET resolvido = TRUE, documento_criado_id = $2
            WHERE id = $1
        """, pergunta_id, documento_criado_id)

        return "UPDATE 1" in result


async def rag_multi_contar_perguntas_sem_resposta(agente: str = None) -> dict:
    """
    Retorna estatisticas de perguntas sem resposta

    Args:
        agente: Filtrar por agente (opcional)

    Returns:
        Dict com total, nao_resolvidas, por_motivo, por_agente
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        if agente:
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM perguntas_sem_resposta_multi WHERE agente = $1",
                agente
            )
            nao_resolvidas = await conn.fetchval(
                "SELECT COUNT(*) FROM perguntas_sem_resposta_multi WHERE resolvido = FALSE AND agente = $1",
                agente
            )
            rows = await conn.fetch("""
                SELECT motivo, COUNT(*) as count
                FROM perguntas_sem_resposta_multi
                WHERE resolvido = FALSE AND agente = $1
                GROUP BY motivo
            """, agente)
        else:
            total = await conn.fetchval("SELECT COUNT(*) FROM perguntas_sem_resposta_multi")
            nao_resolvidas = await conn.fetchval(
                "SELECT COUNT(*) FROM perguntas_sem_resposta_multi WHERE resolvido = FALSE"
            )
            rows = await conn.fetch("""
                SELECT motivo, COUNT(*) as count
                FROM perguntas_sem_resposta_multi
                WHERE resolvido = FALSE
                GROUP BY motivo
            """)

        por_motivo = {row["motivo"]: row["count"] for row in rows}

        # Agrupa por agente
        rows_agente = await conn.fetch("""
            SELECT agente, COUNT(*) as count
            FROM perguntas_sem_resposta_multi
            WHERE resolvido = FALSE
            GROUP BY agente
        """)
        por_agente = {row["agente"] or "geral": row["count"] for row in rows_agente}

        return {
            "total": total,
            "nao_resolvidas": nao_resolvidas,
            "resolvidas": total - nao_resolvidas,
            "por_motivo": por_motivo,
            "por_agente": por_agente
        }


# --- Busca Semantica ---

async def rag_multi_search_async(
    query: str,
    limit: int = 5,
    categoria: str = None,
    agente: str = None,
    similarity_threshold: float = 0.7
) -> List[dict]:
    """
    Busca documentos similares a query (async)

    Args:
        query: Pergunta ou termo de busca
        limit: Numero maximo de resultados
        categoria: Filtrar por categoria
        agente: Filtrar por agente (inclui docs sem agente definido)
        similarity_threshold: Threshold minimo de similaridade

    Returns:
        Lista de documentos relevantes
    """
    pool = await db_get_pool()

    # Gera embedding da query
    query_embedding = await _get_embedding_async(query)

    async with pool.acquire() as conn:
        # Constroi query dinamicamente
        base_query = """
            SELECT
                id, titulo, categoria, agente, conteudo, metadata,
                1 - (embedding <=> $1::vector) as similarity
            FROM empresa_documentos_multi
            WHERE 1 - (embedding <=> $1::vector) > $2
        """
        params = [str(query_embedding), similarity_threshold]

        if categoria:
            params.append(categoria)
            base_query += f" AND categoria = ${len(params)}"

        if agente:
            params.append(agente)
            base_query += f" AND (agente = ${len(params)} OR agente IS NULL)"

        params.append(limit)
        base_query += f" ORDER BY embedding <=> $1::vector LIMIT ${len(params)}"

        rows = await conn.fetch(base_query, *params)

        return [
            {
                "id": row["id"],
                "titulo": row["titulo"],
                "categoria": row["categoria"],
                "agente": row["agente"],
                "conteudo": row["conteudo"],
                "metadata": _parse_metadata(row["metadata"]),
                "similarity": float(row["similarity"])
            }
            for row in rows
        ]


def rag_multi_search_sync(
    query: str,
    limit: int = 5,
    categoria: str = None,
    agente: str = None,
    produto_id: str = None,
    similarity_threshold: float = 0.3
) -> List[dict]:
    """
    Busca hibrida: combina busca semantica + full-text search (sync)
    Com suporte a filtro por agente especializado e produto

    Args:
        query: Pergunta ou termo de busca
        limit: Numero maximo de resultados
        categoria: Filtrar por categoria
        agente: Filtrar por agente (inclui docs sem agente definido)
        produto_id: Filtrar por produto (via metadata->>'produto_id')
        similarity_threshold: Threshold minimo

    Returns:
        Lista de documentos relevantes
    """
    # Gera embedding
    query_embedding = _get_embedding_sync(query)
    conn_string = _get_connection_string()

    conn = psycopg2.connect(conn_string)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Constroi filtros
            where_clauses = []
            params_list = [str(query_embedding), query]

            if categoria:
                where_clauses.append(f"categoria = %s")
                params_list.append(categoria)

            if agente:
                where_clauses.append(f"(agente = %s OR agente IS NULL)")
                params_list.append(agente)

            if produto_id:
                where_clauses.append(f"(metadata->>'produto_id' = %s OR metadata->>'produto_id' IS NULL)")
                params_list.append(produto_id)

            where_sql = " AND " + " AND ".join(where_clauses) if where_clauses else ""

            # Busca hibrida: semantic + fulltext
            sql = f"""
                WITH semantic AS (
                    SELECT id, 1 - (embedding <=> %s::vector) as semantic_score
                    FROM empresa_documentos_multi
                    WHERE 1=1 {where_sql}
                ),
                fulltext AS (
                    SELECT id,
                           COALESCE(ts_rank(
                               to_tsvector('portuguese', titulo || ' ' || conteudo),
                               plainto_tsquery('portuguese', %s)
                           ), 0) as fulltext_score
                    FROM empresa_documentos_multi
                    WHERE 1=1 {where_sql}
                )
                SELECT
                    d.id, d.titulo, d.categoria, d.agente, d.conteudo, d.metadata,
                    s.semantic_score,
                    f.fulltext_score,
                    (0.7 * s.semantic_score + 0.3 * LEAST(f.fulltext_score * 2, 1)) as combined_score
                FROM empresa_documentos_multi d
                JOIN semantic s ON d.id = s.id
                JOIN fulltext f ON d.id = f.id
                WHERE (0.7 * s.semantic_score + 0.3 * LEAST(f.fulltext_score * 2, 1)) > %s
                ORDER BY combined_score DESC
                LIMIT %s
            """

            # Monta params na ordem correta
            final_params = []
            # Semantic CTE
            final_params.append(str(query_embedding))
            if categoria:
                final_params.append(categoria)
            if agente:
                final_params.append(agente)
            if produto_id:
                final_params.append(produto_id)
            # Fulltext CTE
            final_params.append(query)
            if categoria:
                final_params.append(categoria)
            if agente:
                final_params.append(agente)
            if produto_id:
                final_params.append(produto_id)
            # WHERE e ORDER
            final_params.append(similarity_threshold)
            final_params.append(limit)

            cur.execute(sql, final_params)
            rows = cur.fetchall()

            return [
                {
                    "id": row["id"],
                    "titulo": row["titulo"],
                    "categoria": row["categoria"],
                    "agente": row["agente"],
                    "conteudo": row["conteudo"],
                    "metadata": _parse_metadata(row["metadata"]),
                    "similarity": float(row["combined_score"]),
                    "semantic_score": float(row["semantic_score"]),
                    "fulltext_score": float(row["fulltext_score"])
                }
                for row in rows
            ]
    finally:
        conn.close()


# --- CRUD de Produtos (Catalogo) ---

async def rag_multi_add_produto(
    produto_id: str,
    nome: str,
    tipo: str,
    descricao: str = None,
    metadata: dict = None
) -> int:
    """
    Adiciona um produto ao catalogo

    Args:
        produto_id: ID unico do produto (slug, ex: metodo-6-em-7)
        nome: Nome de exibicao do produto
        tipo: Tipo do produto (curso, mentoria, consultoria, etc)
        descricao: Descricao breve do produto
        metadata: Metadados adicionais (preco, link, etc)

    Returns:
        ID do produto criado
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        result = await conn.fetchrow("""
            INSERT INTO produtos_catalogo (produto_id, nome, tipo, descricao, metadata)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            ON CONFLICT (produto_id) DO UPDATE SET
                nome = EXCLUDED.nome,
                tipo = EXCLUDED.tipo,
                descricao = EXCLUDED.descricao,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
            RETURNING id
        """, produto_id, nome, tipo, descricao, json.dumps(metadata or {}))

        return result["id"]


def rag_multi_add_produto_sync(
    produto_id: str,
    nome: str,
    tipo: str,
    descricao: str = None,
    metadata: dict = None
) -> int:
    """
    Adiciona um produto ao catalogo (sync)
    """
    conn_string = _get_connection_string()
    conn = psycopg2.connect(conn_string)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO produtos_catalogo (produto_id, nome, tipo, descricao, metadata)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (produto_id) DO UPDATE SET
                    nome = EXCLUDED.nome,
                    tipo = EXCLUDED.tipo,
                    descricao = EXCLUDED.descricao,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
                RETURNING id
            """, (produto_id, nome, tipo, descricao, json.dumps(metadata or {})))
            result = cur.fetchone()
            conn.commit()
            return result[0] if result else 0
    finally:
        conn.close()


def rag_multi_listar_produtos_sync() -> List[dict]:
    """
    Lista todos os produtos do catalogo (sync)

    Returns:
        Lista de produtos com id, nome, tipo e descricao
    """
    conn_string = _get_connection_string()
    conn = psycopg2.connect(conn_string)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT produto_id, nome, tipo, descricao, metadata
                FROM produtos_catalogo
                WHERE ativo = TRUE
                ORDER BY tipo, nome
            """)
            rows = cur.fetchall()
            return [
                {
                    "produto_id": row["produto_id"],
                    "produto_nome": row["nome"],
                    "produto_tipo": row["tipo"],
                    "descricao": row["descricao"],
                    "metadata": _parse_metadata(row["metadata"])
                }
                for row in rows
            ]
    finally:
        conn.close()


async def rag_multi_listar_produtos_async() -> List[dict]:
    """
    Lista todos os produtos do catalogo (async)

    Returns:
        Lista de produtos com id, nome, tipo e descricao
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT produto_id, nome, tipo, descricao, metadata
            FROM produtos_catalogo
            WHERE ativo = TRUE
            ORDER BY tipo, nome
        """)
        return [
            {
                "produto_id": row["produto_id"],
                "produto_nome": row["nome"],
                "produto_tipo": row["tipo"],
                "descricao": row["descricao"],
                "metadata": _parse_metadata(row["metadata"])
            }
            for row in rows
        ]


def rag_multi_get_produto_sync(produto_id: str) -> dict:
    """
    Busca um produto pelo ID (sync)

    Args:
        produto_id: ID do produto

    Returns:
        Dados do produto ou None
    """
    conn_string = _get_connection_string()
    conn = psycopg2.connect(conn_string)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT produto_id, nome, tipo, descricao, metadata
                FROM produtos_catalogo
                WHERE produto_id = %s AND ativo = TRUE
            """, (produto_id,))
            row = cur.fetchone()
            if row:
                return {
                    "produto_id": row["produto_id"],
                    "produto_nome": row["nome"],
                    "produto_tipo": row["tipo"],
                    "descricao": row["descricao"],
                    "metadata": _parse_metadata(row["metadata"])
                }
            return None
    finally:
        conn.close()


# --- Classe de Compatibilidade ---

class RAGMultiService:
    """Classe de compatibilidade para RAG do Multi-Agente"""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self.embedding_model = _embedding_model
        self.embedding_dimension = _embedding_dimension
        self.initialized = False

    async def connect(self, pool: asyncpg.Pool):
        self.pool = pool

    async def init_tables(self):
        self.initialized = await rag_multi_init_tables()

    async def _get_embedding(self, text: str) -> List[float]:
        return await _get_embedding_async(text)

    async def add_document(
        self,
        titulo: str,
        conteudo: str,
        categoria: str = "geral",
        agente: str = None,
        metadata: dict = None
    ) -> int:
        return await rag_multi_add_document(titulo, conteudo, categoria, agente, metadata)

    async def update_document(
        self,
        doc_id: int,
        titulo: str = None,
        conteudo: str = None,
        categoria: str = None,
        agente: str = None,
        metadata: dict = None
    ) -> bool:
        return await rag_multi_update_document(doc_id, titulo, conteudo, categoria, agente, metadata)

    async def delete_document(self, doc_id: int) -> bool:
        return await rag_multi_delete_document(doc_id)

    async def search(
        self,
        query: str,
        limit: int = 5,
        categoria: str = None,
        agente: str = None,
        similarity_threshold: float = 0.7
    ) -> List[dict]:
        return await rag_multi_search_async(query, limit, categoria, agente, similarity_threshold)

    async def list_documents(self, categoria: str = None, agente: str = None, limit: int = 50) -> List[dict]:
        return await rag_multi_list_documents(categoria, agente, limit)

    async def get_categories(self) -> List[str]:
        return await rag_multi_get_categories()

    def _get_embedding_sync(self, text: str) -> List[float]:
        return _get_embedding_sync(text)

    def search_sync(
        self,
        query: str,
        limit: int = 5,
        categoria: str = None,
        agente: str = None,
        produto_id: str = None,
        similarity_threshold: float = 0.3
    ) -> List[dict]:
        return rag_multi_search_sync(query, limit, categoria, agente, produto_id, similarity_threshold)


# Instancia global para compatibilidade
rag_multi_service = RAGMultiService()


async def get_rag_multi_service(pool: asyncpg.Pool) -> RAGMultiService:
    """Retorna o servico RAG Multi-Agente conectado"""
    if rag_multi_service.pool is None:
        await rag_multi_service.connect(pool)
        await rag_multi_service.init_tables()
    return rag_multi_service
