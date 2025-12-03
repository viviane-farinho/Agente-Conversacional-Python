"""
Servico de RAG (Retrieval-Augmented Generation)
Permite ao agente buscar informacoes da empresa em uma base de conhecimento

Paradigma: Funcional
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

async def rag_init_tables() -> bool:
    """
    Cria as tabelas necessarias para RAG

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
                print(f"Aviso: Nao foi possivel criar extensao vector: {e}")
                print("Para usar RAG, habilite a extensao 'vector' no Supabase Dashboard")
                return False

            # Tabela de documentos
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS empresa_documentos (
                    id SERIAL PRIMARY KEY,
                    titulo VARCHAR(255) NOT NULL,
                    categoria VARCHAR(100),
                    conteudo TEXT NOT NULL,
                    embedding vector(1536),
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            # Indice para categoria
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_documentos_categoria
                ON empresa_documentos(categoria)
            """)

            # Indice vetorial (se houver dados)
            try:
                count = await conn.fetchval("SELECT COUNT(*) FROM empresa_documentos")
                if count > 0:
                    await conn.execute("""
                        CREATE INDEX IF NOT EXISTS idx_documentos_embedding
                        ON empresa_documentos
                        USING ivfflat (embedding vector_cosine_ops)
                        WITH (lists = 100)
                    """)
            except Exception:
                pass

            _initialized = True
            return True

    except Exception as e:
        print(f"Erro ao inicializar RAG: {e}")
        _initialized = False
        return False


# --- CRUD de Documentos ---

async def rag_add_document(
    titulo: str,
    conteudo: str,
    categoria: str = "geral",
    metadata: dict = None
) -> int:
    """
    Adiciona um documento a base de conhecimento

    Args:
        titulo: Titulo do documento
        conteudo: Conteudo do documento
        categoria: Categoria (ex: servicos, horarios, precos)
        metadata: Metadados adicionais

    Returns:
        ID do documento criado
    """
    pool = await db_get_pool()

    # Gera embedding
    embedding = await _get_embedding_async(f"{titulo}\n{conteudo}")

    async with pool.acquire() as conn:
        result = await conn.fetchrow("""
            INSERT INTO empresa_documentos (titulo, categoria, conteudo, embedding, metadata)
            VALUES ($1, $2, $3, $4::vector, $5::jsonb)
            RETURNING id
        """, titulo, categoria, conteudo, str(embedding), json.dumps(metadata or {}))

        return result["id"]


async def rag_update_document(
    doc_id: int,
    titulo: str = None,
    conteudo: str = None,
    categoria: str = None,
    metadata: dict = None
) -> bool:
    """
    Atualiza um documento existente

    Args:
        doc_id: ID do documento
        titulo: Novo titulo
        conteudo: Novo conteudo
        categoria: Nova categoria
        metadata: Novos metadados

    Returns:
        True se atualizou com sucesso
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        # Busca documento atual
        current = await conn.fetchrow(
            "SELECT * FROM empresa_documentos WHERE id = $1",
            doc_id
        )
        if not current:
            return False

        # Usa valores atuais se nao fornecidos
        titulo = titulo or current["titulo"]
        conteudo = conteudo or current["conteudo"]
        categoria = categoria or current["categoria"]
        metadata = metadata or (json.loads(current["metadata"]) if current["metadata"] else {})

        # Regenera embedding
        embedding = await _get_embedding_async(f"{titulo}\n{conteudo}")

        await conn.execute("""
            UPDATE empresa_documentos
            SET titulo = $1, categoria = $2, conteudo = $3,
                embedding = $4::vector, metadata = $5::jsonb,
                updated_at = NOW()
            WHERE id = $6
        """, titulo, categoria, conteudo, str(embedding), json.dumps(metadata), doc_id)

        return True


async def rag_delete_document(doc_id: int) -> bool:
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
            "DELETE FROM empresa_documentos WHERE id = $1",
            doc_id
        )
        return "DELETE 1" in result


async def rag_list_documents(categoria: str = None, limit: int = 50) -> List[dict]:
    """
    Lista todos os documentos

    Args:
        categoria: Filtrar por categoria
        limit: Numero maximo de resultados

    Returns:
        Lista de documentos
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        if categoria:
            rows = await conn.fetch("""
                SELECT id, titulo, categoria, conteudo, metadata, created_at
                FROM empresa_documentos
                WHERE categoria = $1
                ORDER BY created_at DESC
                LIMIT $2
            """, categoria, limit)
        else:
            rows = await conn.fetch("""
                SELECT id, titulo, categoria, conteudo, metadata, created_at
                FROM empresa_documentos
                ORDER BY created_at DESC
                LIMIT $1
            """, limit)

        return [
            {
                "id": row["id"],
                "titulo": row["titulo"],
                "categoria": row["categoria"],
                "conteudo": row["conteudo"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                "created_at": row["created_at"].isoformat()
            }
            for row in rows
        ]


async def rag_get_categories() -> List[str]:
    """
    Retorna todas as categorias existentes

    Returns:
        Lista de categorias
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT DISTINCT categoria
            FROM empresa_documentos
            WHERE categoria IS NOT NULL
            ORDER BY categoria
        """)
        return [row["categoria"] for row in rows]


# --- Busca Semantica ---

async def rag_search_async(
    query: str,
    limit: int = 5,
    categoria: str = None,
    similarity_threshold: float = 0.7
) -> List[dict]:
    """
    Busca documentos similares a query (async)

    Args:
        query: Pergunta ou termo de busca
        limit: Numero maximo de resultados
        categoria: Filtrar por categoria
        similarity_threshold: Threshold minimo de similaridade

    Returns:
        Lista de documentos relevantes
    """
    pool = await db_get_pool()

    # Gera embedding da query
    query_embedding = await _get_embedding_async(query)

    async with pool.acquire() as conn:
        if categoria:
            rows = await conn.fetch("""
                SELECT
                    id, titulo, categoria, conteudo, metadata,
                    1 - (embedding <=> $1::vector) as similarity
                FROM empresa_documentos
                WHERE categoria = $2
                AND 1 - (embedding <=> $1::vector) > $3
                ORDER BY embedding <=> $1::vector
                LIMIT $4
            """, str(query_embedding), categoria, similarity_threshold, limit)
        else:
            rows = await conn.fetch("""
                SELECT
                    id, titulo, categoria, conteudo, metadata,
                    1 - (embedding <=> $1::vector) as similarity
                FROM empresa_documentos
                WHERE 1 - (embedding <=> $1::vector) > $2
                ORDER BY embedding <=> $1::vector
                LIMIT $3
            """, str(query_embedding), similarity_threshold, limit)

        return [
            {
                "id": row["id"],
                "titulo": row["titulo"],
                "categoria": row["categoria"],
                "conteudo": row["conteudo"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                "similarity": float(row["similarity"])
            }
            for row in rows
        ]


def rag_search_sync(
    query: str,
    limit: int = 5,
    categoria: str = None,
    similarity_threshold: float = 0.3
) -> List[dict]:
    """
    Busca hibrida: combina busca semantica + full-text search (sync)

    Args:
        query: Pergunta ou termo de busca
        limit: Numero maximo de resultados
        categoria: Filtrar por categoria
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
            # Busca hibrida: semantic + fulltext
            if categoria:
                cur.execute("""
                    WITH semantic AS (
                        SELECT id, 1 - (embedding <=> %s::vector) as semantic_score
                        FROM empresa_documentos
                        WHERE categoria = %s
                    ),
                    fulltext AS (
                        SELECT id,
                               COALESCE(ts_rank(
                                   to_tsvector('portuguese', titulo || ' ' || conteudo),
                                   plainto_tsquery('portuguese', %s)
                               ), 0) as fulltext_score
                        FROM empresa_documentos
                        WHERE categoria = %s
                    )
                    SELECT
                        d.id, d.titulo, d.categoria, d.conteudo, d.metadata,
                        s.semantic_score,
                        f.fulltext_score,
                        (0.7 * s.semantic_score + 0.3 * LEAST(f.fulltext_score * 2, 1)) as combined_score
                    FROM empresa_documentos d
                    JOIN semantic s ON d.id = s.id
                    JOIN fulltext f ON d.id = f.id
                    WHERE (0.7 * s.semantic_score + 0.3 * LEAST(f.fulltext_score * 2, 1)) > %s
                    ORDER BY combined_score DESC
                    LIMIT %s
                """, (str(query_embedding), categoria, query, categoria, similarity_threshold, limit))
            else:
                cur.execute("""
                    WITH semantic AS (
                        SELECT id, 1 - (embedding <=> %s::vector) as semantic_score
                        FROM empresa_documentos
                    ),
                    fulltext AS (
                        SELECT id,
                               COALESCE(ts_rank(
                                   to_tsvector('portuguese', titulo || ' ' || conteudo),
                                   plainto_tsquery('portuguese', %s)
                               ), 0) as fulltext_score
                        FROM empresa_documentos
                    )
                    SELECT
                        d.id, d.titulo, d.categoria, d.conteudo, d.metadata,
                        s.semantic_score,
                        f.fulltext_score,
                        (0.7 * s.semantic_score + 0.3 * LEAST(f.fulltext_score * 2, 1)) as combined_score
                    FROM empresa_documentos d
                    JOIN semantic s ON d.id = s.id
                    JOIN fulltext f ON d.id = f.id
                    WHERE (0.7 * s.semantic_score + 0.3 * LEAST(f.fulltext_score * 2, 1)) > %s
                    ORDER BY combined_score DESC
                    LIMIT %s
                """, (str(query_embedding), query, similarity_threshold, limit))

            rows = cur.fetchall()

            return [
                {
                    "id": row["id"],
                    "titulo": row["titulo"],
                    "categoria": row["categoria"],
                    "conteudo": row["conteudo"],
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                    "similarity": float(row["combined_score"]),
                    "semantic_score": float(row["semantic_score"]),
                    "fulltext_score": float(row["fulltext_score"])
                }
                for row in rows
            ]
    finally:
        conn.close()


# --- Compatibilidade (para transicao gradual) ---

class RAGService:
    """Classe de compatibilidade - usar funcoes diretamente"""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self.embedding_model = _embedding_model
        self.embedding_dimension = _embedding_dimension
        self.initialized = False

    async def connect(self, pool: asyncpg.Pool):
        self.pool = pool

    async def init_tables(self):
        self.initialized = await rag_init_tables()

    async def _get_embedding(self, text: str) -> List[float]:
        return await _get_embedding_async(text)

    async def add_document(self, titulo: str, conteudo: str, categoria: str = "geral", metadata: dict = None) -> int:
        return await rag_add_document(titulo, conteudo, categoria, metadata)

    async def update_document(self, doc_id: int, titulo: str = None, conteudo: str = None, categoria: str = None, metadata: dict = None) -> bool:
        return await rag_update_document(doc_id, titulo, conteudo, categoria, metadata)

    async def delete_document(self, doc_id: int) -> bool:
        return await rag_delete_document(doc_id)

    async def search(self, query: str, limit: int = 5, categoria: str = None, similarity_threshold: float = 0.7) -> List[dict]:
        return await rag_search_async(query, limit, categoria, similarity_threshold)

    async def list_documents(self, categoria: str = None, limit: int = 50) -> List[dict]:
        return await rag_list_documents(categoria, limit)

    async def get_categories(self) -> List[str]:
        return await rag_get_categories()

    def _get_embedding_sync(self, text: str) -> List[float]:
        return _get_embedding_sync(text)

    def search_sync(self, query: str, limit: int = 5, categoria: str = None, similarity_threshold: float = 0.3) -> List[dict]:
        return rag_search_sync(query, limit, categoria, similarity_threshold)


# Instancia global para compatibilidade
rag_service = RAGService()


async def get_rag_service(pool: asyncpg.Pool) -> RAGService:
    """Retorna o servico RAG conectado"""
    if rag_service.pool is None:
        await rag_service.connect(pool)
        await rag_service.init_tables()
    return rag_service
