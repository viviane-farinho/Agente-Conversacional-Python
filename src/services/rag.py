"""
Serviço de RAG (Retrieval-Augmented Generation)
Permite ao agente buscar informações da empresa em uma base de conhecimento
"""
import json
from typing import Optional
import asyncpg
import httpx
import requests

from src.config import Config


class RAGService:
    """Serviço para busca semântica em documentos da empresa"""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self.embedding_model = "text-embedding-3-small"  # OpenAI embedding model
        self.embedding_dimension = 1536
        self.initialized = False

    async def connect(self, pool: asyncpg.Pool):
        """Usa o pool de conexões existente"""
        self.pool = pool

    async def init_tables(self):
        """Cria as tabelas necessárias para RAG"""
        try:
            async with self.pool.acquire() as conn:
                # Habilita a extensão pgvector (necessário no Supabase)
                # No Supabase, pode ser necessário habilitar via dashboard
                try:
                    await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                except Exception as e:
                    print(f"Aviso: Não foi possível criar extensão vector: {e}")
                    print("Para usar RAG, habilite a extensão 'vector' no Supabase Dashboard:")
                    print("  Database > Extensions > Buscar 'vector' > Enable")
                    return

                # Tabela de documentos da empresa
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

                # Índice para busca por categoria (sempre funciona)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_documentos_categoria
                    ON empresa_documentos(categoria)
                """)

                # Índice para busca vetorial eficiente (pode falhar se tabela vazia)
                try:
                    # Verifica se há documentos para criar índice ivfflat
                    count = await conn.fetchval("SELECT COUNT(*) FROM empresa_documentos")
                    if count > 0:
                        await conn.execute("""
                            CREATE INDEX IF NOT EXISTS idx_documentos_embedding
                            ON empresa_documentos
                            USING ivfflat (embedding vector_cosine_ops)
                            WITH (lists = 100)
                        """)
                except Exception:
                    # ivfflat precisa de dados, ignora erro
                    pass

                self.initialized = True
        except Exception as e:
            print(f"Erro ao inicializar RAG: {e}")
            self.initialized = False

    async def _get_embedding(self, text: str) -> list[float]:
        """Gera embedding usando OpenAI API"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {Config.OPENAI_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.embedding_model,
                    "input": text
                },
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]

    async def add_document(
        self,
        titulo: str,
        conteudo: str,
        categoria: str = "geral",
        metadata: dict = None
    ) -> int:
        """
        Adiciona um documento à base de conhecimento

        Args:
            titulo: Título do documento
            conteudo: Conteúdo do documento
            categoria: Categoria (ex: servicos, horarios, precos, equipe, localizacao)
            metadata: Metadados adicionais em JSON

        Returns:
            ID do documento criado
        """
        # Gera embedding do conteúdo
        embedding = await self._get_embedding(f"{titulo}\n{conteudo}")

        async with self.pool.acquire() as conn:
            result = await conn.fetchrow("""
                INSERT INTO empresa_documentos (titulo, categoria, conteudo, embedding, metadata)
                VALUES ($1, $2, $3, $4::vector, $5::jsonb)
                RETURNING id
            """, titulo, categoria, conteudo, str(embedding), json.dumps(metadata or {}))

            return result["id"]

    async def update_document(
        self,
        doc_id: int,
        titulo: str = None,
        conteudo: str = None,
        categoria: str = None,
        metadata: dict = None
    ) -> bool:
        """Atualiza um documento existente"""
        async with self.pool.acquire() as conn:
            # Busca documento atual
            current = await conn.fetchrow(
                "SELECT * FROM empresa_documentos WHERE id = $1",
                doc_id
            )
            if not current:
                return False

            # Usa valores atuais se não fornecidos
            titulo = titulo or current["titulo"]
            conteudo = conteudo or current["conteudo"]
            categoria = categoria or current["categoria"]
            metadata = metadata or (json.loads(current["metadata"]) if current["metadata"] else {})

            # Regenera embedding se o conteúdo mudou
            embedding = await self._get_embedding(f"{titulo}\n{conteudo}")

            await conn.execute("""
                UPDATE empresa_documentos
                SET titulo = $1, categoria = $2, conteudo = $3,
                    embedding = $4::vector, metadata = $5::jsonb,
                    updated_at = NOW()
                WHERE id = $6
            """, titulo, categoria, conteudo, str(embedding), json.dumps(metadata), doc_id)

            return True

    async def delete_document(self, doc_id: int) -> bool:
        """Remove um documento"""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM empresa_documentos WHERE id = $1",
                doc_id
            )
            return "DELETE 1" in result

    async def search(
        self,
        query: str,
        limit: int = 5,
        categoria: str = None,
        similarity_threshold: float = 0.7
    ) -> list[dict]:
        """
        Busca documentos similares à query

        Args:
            query: Pergunta ou termo de busca
            limit: Número máximo de resultados
            categoria: Filtrar por categoria específica
            similarity_threshold: Threshold mínimo de similaridade (0-1)

        Returns:
            Lista de documentos relevantes com score de similaridade
        """
        # Gera embedding da query
        query_embedding = await self._get_embedding(query)

        async with self.pool.acquire() as conn:
            # Busca por similaridade de cosseno
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

    async def list_documents(self, categoria: str = None, limit: int = 50) -> list[dict]:
        """Lista todos os documentos (para gestão)"""
        async with self.pool.acquire() as conn:
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

    async def get_categories(self) -> list[str]:
        """Retorna todas as categorias existentes"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT categoria
                FROM empresa_documentos
                WHERE categoria IS NOT NULL
                ORDER BY categoria
            """)
            return [row["categoria"] for row in rows]


    def _get_embedding_sync(self, text: str) -> list[float]:
        """Gera embedding usando OpenAI API (versão síncrona)"""
        response = requests.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {Config.OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": self.embedding_model,
                "input": text
            },
            timeout=30.0
        )
        response.raise_for_status()
        data = response.json()
        return data["data"][0]["embedding"]

    def search_sync(
        self,
        query: str,
        limit: int = 5,
        categoria: str = None,
        similarity_threshold: float = 0.3
    ) -> list[dict]:
        """
        Busca híbrida: combina busca semântica (embeddings) + full-text search

        A busca híbrida melhora a precisão combinando:
        - Semantic search: entende a intenção/contexto
        - Full-text search: encontra nomes e termos exatos

        Args:
            query: Pergunta ou termo de busca
            limit: Número máximo de resultados
            categoria: Filtrar por categoria específica
            similarity_threshold: Threshold mínimo para score combinado (0-1)

        Returns:
            Lista de documentos relevantes com score combinado
        """
        import psycopg2
        from psycopg2.extras import RealDictCursor

        # Gera embedding da query (síncrono)
        query_embedding = self._get_embedding_sync(query)

        # Monta a connection string a partir das configurações
        conn_string = Config.DATABASE_URL
        if not conn_string:
            conn_string = f"postgresql://{Config.POSTGRES_USER}:{Config.POSTGRES_PASSWORD}@{Config.POSTGRES_HOST}:{Config.POSTGRES_PORT}/{Config.POSTGRES_DB}"

        # Conexão síncrona direta
        conn = psycopg2.connect(conn_string)
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Busca híbrida: combina semantic similarity + full-text rank
                # Score final = 0.7 * semantic + 0.3 * fulltext (prioriza semântico para sinônimos)
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


# Instância global
rag_service = RAGService()


async def get_rag_service(pool: asyncpg.Pool) -> RAGService:
    """Retorna o serviço RAG conectado"""
    if rag_service.pool is None:
        await rag_service.connect(pool)
        await rag_service.init_tables()
    return rag_service
