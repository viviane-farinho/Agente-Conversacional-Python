"""
Servico de RAG (Retrieval-Augmented Generation) para Advocacia
Sistema independente com prompt dinamico por area de atuacao

Paradigma: Funcional
Totalmente separado dos demais RAGs para permitir evolucao independente
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

async def rag_advocacia_init_tables() -> bool:
    """
    Cria as tabelas necessarias para RAG de Advocacia

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
                print(f"[RAG Advocacia] Aviso: Nao foi possivel criar extensao vector: {e}")
                return False

            # 1. Tabela de Areas de Atuacao (com prompt e keywords)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS areas_atuacao_advocacia (
                    id VARCHAR(50) PRIMARY KEY,
                    nome VARCHAR(255) NOT NULL,
                    descricao TEXT,
                    prompt_vendas TEXT NOT NULL,
                    keywords TEXT[] DEFAULT '{}',
                    ativo BOOLEAN DEFAULT TRUE,
                    ordem INTEGER DEFAULT 0,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            # Indice para areas ativas
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_areas_advocacia_ativo
                ON areas_atuacao_advocacia(ativo, ordem)
            """)

            # 2. Tabela de Servicos por Area
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS servicos_advocacia (
                    id VARCHAR(50) PRIMARY KEY,
                    area_id VARCHAR(50) REFERENCES areas_atuacao_advocacia(id),
                    nome VARCHAR(255) NOT NULL,
                    descricao TEXT,
                    ativo BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            # Indice para servicos por area
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_servicos_advocacia_area
                ON servicos_advocacia(area_id)
            """)

            # 3. Tabela de Documentos (Base de Conhecimento)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS documentos_advocacia (
                    id SERIAL PRIMARY KEY,
                    titulo VARCHAR(255) NOT NULL,
                    conteudo TEXT NOT NULL,
                    area_id VARCHAR(50) REFERENCES areas_atuacao_advocacia(id),
                    servico_id VARCHAR(50) REFERENCES servicos_advocacia(id),
                    agente VARCHAR(50) DEFAULT 'vendas',
                    embedding vector(1536),
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            # Indices para documentos
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_docs_advocacia_area
                ON documentos_advocacia(area_id)
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_docs_advocacia_servico
                ON documentos_advocacia(servico_id)
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_docs_advocacia_agente
                ON documentos_advocacia(agente)
            """)

            # Indice vetorial (se houver dados)
            try:
                count = await conn.fetchval("SELECT COUNT(*) FROM documentos_advocacia")
                if count > 0:
                    await conn.execute("""
                        CREATE INDEX IF NOT EXISTS idx_docs_advocacia_embedding
                        ON documentos_advocacia
                        USING ivfflat (embedding vector_cosine_ops)
                        WITH (lists = 100)
                    """)
            except Exception:
                pass

            # 4. Tabela de Prompts Genericos (suporte/agendamento)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS prompts_advocacia (
                    agente VARCHAR(50) PRIMARY KEY,
                    prompt TEXT NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            # 5. Tabela de Perguntas sem Resposta (feedback loop)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS perguntas_sem_resposta_advocacia (
                    id SERIAL PRIMARY KEY,
                    pergunta TEXT NOT NULL,
                    telefone VARCHAR(50),
                    conversation_id VARCHAR(100),
                    agente VARCHAR(50),
                    area_id VARCHAR(50),
                    motivo VARCHAR(100) DEFAULT 'nao_encontrado',
                    query_expandida TEXT,
                    docs_encontrados INTEGER DEFAULT 0,
                    resolvido BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            # Indices para perguntas sem resposta
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_perguntas_advocacia_resolvido
                ON perguntas_sem_resposta_advocacia(resolvido, created_at DESC)
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_perguntas_advocacia_agente
                ON perguntas_sem_resposta_advocacia(agente)
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_perguntas_advocacia_area
                ON perguntas_sem_resposta_advocacia(area_id)
            """)

            _initialized = True
            print("[RAG Advocacia] Tabelas inicializadas com sucesso")
            return True

    except Exception as e:
        print(f"[RAG Advocacia] Erro ao inicializar: {e}")
        _initialized = False
        return False


# --- CRUD de Areas de Atuacao ---

async def rag_advocacia_add_area(
    area_id: str,
    nome: str,
    prompt_vendas: str,
    keywords: List[str] = None,
    descricao: str = None,
    ordem: int = 0
) -> str:
    """
    Adiciona uma area de atuacao

    Args:
        area_id: ID unico da area (slug, ex: previdenciario)
        nome: Nome de exibicao (ex: Direito Previdenciario)
        prompt_vendas: Prompt para o agente de vendas dessa area
        keywords: Lista de palavras-chave para deteccao automatica
        descricao: Descricao da area
        ordem: Ordem de exibicao

    Returns:
        ID da area criada
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO areas_atuacao_advocacia (id, nome, descricao, prompt_vendas, keywords, ordem)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (id) DO UPDATE SET
                nome = EXCLUDED.nome,
                descricao = EXCLUDED.descricao,
                prompt_vendas = EXCLUDED.prompt_vendas,
                keywords = EXCLUDED.keywords,
                ordem = EXCLUDED.ordem,
                updated_at = NOW()
        """, area_id, nome, descricao, prompt_vendas, keywords or [], ordem)

        return area_id


def rag_advocacia_add_area_sync(
    area_id: str,
    nome: str,
    prompt_vendas: str,
    keywords: List[str] = None,
    descricao: str = None,
    ordem: int = 0
) -> str:
    """Adiciona uma area de atuacao (sync)"""
    conn_string = _get_connection_string()
    conn = psycopg2.connect(conn_string)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO areas_atuacao_advocacia (id, nome, descricao, prompt_vendas, keywords, ordem)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    nome = EXCLUDED.nome,
                    descricao = EXCLUDED.descricao,
                    prompt_vendas = EXCLUDED.prompt_vendas,
                    keywords = EXCLUDED.keywords,
                    ordem = EXCLUDED.ordem,
                    updated_at = NOW()
            """, (area_id, nome, descricao, prompt_vendas, keywords or [], ordem))
            conn.commit()
            return area_id
    finally:
        conn.close()


async def rag_advocacia_update_area(
    area_id: str,
    nome: str = None,
    descricao: str = None,
    prompt_vendas: str = None,
    keywords: List[str] = None,
    ativo: bool = None,
    ordem: int = None
) -> bool:
    """Atualiza uma area existente"""
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        # Busca area atual
        current = await conn.fetchrow(
            "SELECT * FROM areas_atuacao_advocacia WHERE id = $1",
            area_id
        )
        if not current:
            return False

        # Usa valores atuais se nao fornecidos
        nome = nome or current["nome"]
        descricao = descricao if descricao is not None else current["descricao"]
        prompt_vendas = prompt_vendas or current["prompt_vendas"]
        keywords = keywords if keywords is not None else current["keywords"]
        ativo = ativo if ativo is not None else current["ativo"]
        ordem = ordem if ordem is not None else current["ordem"]

        await conn.execute("""
            UPDATE areas_atuacao_advocacia
            SET nome = $2, descricao = $3, prompt_vendas = $4,
                keywords = $5, ativo = $6, ordem = $7, updated_at = NOW()
            WHERE id = $1
        """, area_id, nome, descricao, prompt_vendas, keywords, ativo, ordem)

        return True


async def rag_advocacia_list_areas(apenas_ativas: bool = True) -> List[dict]:
    """
    Lista todas as areas de atuacao

    Args:
        apenas_ativas: Se True, retorna apenas areas ativas

    Returns:
        Lista de areas
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        if apenas_ativas:
            rows = await conn.fetch("""
                SELECT id, nome, descricao, prompt_vendas, keywords, ativo, ordem
                FROM areas_atuacao_advocacia
                WHERE ativo = TRUE
                ORDER BY ordem, nome
            """)
        else:
            rows = await conn.fetch("""
                SELECT id, nome, descricao, prompt_vendas, keywords, ativo, ordem
                FROM areas_atuacao_advocacia
                ORDER BY ordem, nome
            """)

        return [
            {
                "id": row["id"],
                "nome": row["nome"],
                "descricao": row["descricao"],
                "prompt_vendas": row["prompt_vendas"],
                "keywords": row["keywords"] or [],
                "ativo": row["ativo"],
                "ordem": row["ordem"]
            }
            for row in rows
        ]


def rag_advocacia_list_areas_sync(apenas_ativas: bool = True) -> List[dict]:
    """Lista todas as areas de atuacao (sync)"""
    conn_string = _get_connection_string()
    conn = psycopg2.connect(conn_string)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if apenas_ativas:
                cur.execute("""
                    SELECT id, nome, descricao, prompt_vendas, keywords, ativo, ordem
                    FROM areas_atuacao_advocacia
                    WHERE ativo = TRUE
                    ORDER BY ordem, nome
                """)
            else:
                cur.execute("""
                    SELECT id, nome, descricao, prompt_vendas, keywords, ativo, ordem
                    FROM areas_atuacao_advocacia
                    ORDER BY ordem, nome
                """)
            rows = cur.fetchall()
            return [
                {
                    "id": row["id"],
                    "nome": row["nome"],
                    "descricao": row["descricao"],
                    "prompt_vendas": row["prompt_vendas"],
                    "keywords": row["keywords"] or [],
                    "ativo": row["ativo"],
                    "ordem": row["ordem"]
                }
                for row in rows
            ]
    finally:
        conn.close()


async def rag_advocacia_get_area(area_id: str) -> Optional[dict]:
    """Busca uma area pelo ID"""
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT id, nome, descricao, prompt_vendas, keywords, ativo, ordem
            FROM areas_atuacao_advocacia
            WHERE id = $1
        """, area_id)

        if not row:
            return None

        return {
            "id": row["id"],
            "nome": row["nome"],
            "descricao": row["descricao"],
            "prompt_vendas": row["prompt_vendas"],
            "keywords": row["keywords"] or [],
            "ativo": row["ativo"],
            "ordem": row["ordem"]
        }


def rag_advocacia_get_area_sync(area_id: str) -> Optional[dict]:
    """Busca uma area pelo ID (sync)"""
    conn_string = _get_connection_string()
    conn = psycopg2.connect(conn_string)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, nome, descricao, prompt_vendas, keywords, ativo, ordem
                FROM areas_atuacao_advocacia
                WHERE id = %s
            """, (area_id,))
            row = cur.fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "nome": row["nome"],
                "descricao": row["descricao"],
                "prompt_vendas": row["prompt_vendas"],
                "keywords": row["keywords"] or [],
                "ativo": row["ativo"],
                "ordem": row["ordem"]
            }
    finally:
        conn.close()


def rag_advocacia_get_area_prompt_sync(area_id: str) -> Optional[str]:
    """
    Busca o prompt de vendas de uma area especifica (sync)

    Args:
        area_id: ID da area

    Returns:
        Prompt de vendas ou None se nao encontrar
    """
    area = rag_advocacia_get_area_sync(area_id)
    if area:
        return area.get("prompt_vendas")
    return None


def rag_advocacia_get_keywords_por_area_sync() -> dict:
    """
    Retorna dicionario de keywords por area para deteccao rapida

    Returns:
        Dict no formato {area_id: [keywords]}
    """
    conn_string = _get_connection_string()
    conn = psycopg2.connect(conn_string)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, keywords
                FROM areas_atuacao_advocacia
                WHERE ativo = TRUE AND keywords IS NOT NULL AND array_length(keywords, 1) > 0
            """)
            rows = cur.fetchall()
            return {row["id"]: row["keywords"] for row in rows}
    finally:
        conn.close()


# --- CRUD de Servicos ---

async def rag_advocacia_add_servico(
    servico_id: str,
    area_id: str,
    nome: str,
    descricao: str = None
) -> str:
    """
    Adiciona um servico a uma area

    Args:
        servico_id: ID unico do servico (slug)
        area_id: ID da area a que pertence
        nome: Nome de exibicao
        descricao: Descricao do servico

    Returns:
        ID do servico criado
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO servicos_advocacia (id, area_id, nome, descricao)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (id) DO UPDATE SET
                area_id = EXCLUDED.area_id,
                nome = EXCLUDED.nome,
                descricao = EXCLUDED.descricao
        """, servico_id, area_id, nome, descricao)

        return servico_id


def rag_advocacia_add_servico_sync(
    servico_id: str,
    area_id: str,
    nome: str,
    descricao: str = None
) -> str:
    """Adiciona um servico (sync)"""
    conn_string = _get_connection_string()
    conn = psycopg2.connect(conn_string)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO servicos_advocacia (id, area_id, nome, descricao)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    area_id = EXCLUDED.area_id,
                    nome = EXCLUDED.nome,
                    descricao = EXCLUDED.descricao
            """, (servico_id, area_id, nome, descricao))
            conn.commit()
            return servico_id
    finally:
        conn.close()


async def rag_advocacia_list_servicos(area_id: str = None) -> List[dict]:
    """
    Lista servicos, opcionalmente filtrado por area

    Args:
        area_id: Filtrar por area (opcional)

    Returns:
        Lista de servicos
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        if area_id:
            rows = await conn.fetch("""
                SELECT s.id, s.area_id, s.nome, s.descricao, a.nome as area_nome
                FROM servicos_advocacia s
                JOIN areas_atuacao_advocacia a ON s.area_id = a.id
                WHERE s.area_id = $1 AND s.ativo = TRUE
                ORDER BY s.nome
            """, area_id)
        else:
            rows = await conn.fetch("""
                SELECT s.id, s.area_id, s.nome, s.descricao, a.nome as area_nome
                FROM servicos_advocacia s
                JOIN areas_atuacao_advocacia a ON s.area_id = a.id
                WHERE s.ativo = TRUE
                ORDER BY a.nome, s.nome
            """)

        return [
            {
                "id": row["id"],
                "area_id": row["area_id"],
                "area_nome": row["area_nome"],
                "nome": row["nome"],
                "descricao": row["descricao"]
            }
            for row in rows
        ]


def rag_advocacia_list_servicos_sync(area_id: str = None) -> List[dict]:
    """Lista servicos (sync)"""
    conn_string = _get_connection_string()
    conn = psycopg2.connect(conn_string)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if area_id:
                cur.execute("""
                    SELECT s.id, s.area_id, s.nome, s.descricao, a.nome as area_nome
                    FROM servicos_advocacia s
                    JOIN areas_atuacao_advocacia a ON s.area_id = a.id
                    WHERE s.area_id = %s AND s.ativo = TRUE
                    ORDER BY s.nome
                """, (area_id,))
            else:
                cur.execute("""
                    SELECT s.id, s.area_id, s.nome, s.descricao, a.nome as area_nome
                    FROM servicos_advocacia s
                    JOIN areas_atuacao_advocacia a ON s.area_id = a.id
                    WHERE s.ativo = TRUE
                    ORDER BY a.nome, s.nome
                """)
            rows = cur.fetchall()
            return [
                {
                    "id": row["id"],
                    "area_id": row["area_id"],
                    "area_nome": row["area_nome"],
                    "nome": row["nome"],
                    "descricao": row["descricao"]
                }
                for row in rows
            ]
    finally:
        conn.close()


# --- CRUD de Documentos ---

async def rag_advocacia_add_document(
    titulo: str,
    conteudo: str,
    area_id: str = None,
    servico_id: str = None,
    agente: str = "vendas",
    metadata: dict = None
) -> int:
    """
    Adiciona um documento a base de conhecimento

    Args:
        titulo: Titulo do documento
        conteudo: Conteudo do documento
        area_id: Area a que pertence (opcional)
        servico_id: Servico a que pertence (opcional)
        agente: Agente especifico (vendas, suporte, agendamento)
        metadata: Metadados adicionais

    Returns:
        ID do documento criado
    """
    pool = await db_get_pool()

    # Gera embedding
    embedding = await _get_embedding_async(f"{titulo}\n{conteudo}")

    async with pool.acquire() as conn:
        result = await conn.fetchrow("""
            INSERT INTO documentos_advocacia (titulo, conteudo, area_id, servico_id, agente, embedding, metadata)
            VALUES ($1, $2, $3, $4, $5, $6::vector, $7::jsonb)
            RETURNING id
        """, titulo, conteudo, area_id, servico_id, agente, str(embedding), json.dumps(metadata or {}))

        return result["id"]


def rag_advocacia_add_document_sync(
    titulo: str,
    conteudo: str,
    area_id: str = None,
    servico_id: str = None,
    agente: str = "vendas",
    metadata: dict = None
) -> int:
    """Adiciona um documento (sync)"""
    # Gera embedding
    embedding = _get_embedding_sync(f"{titulo}\n{conteudo}")

    conn_string = _get_connection_string()
    conn = psycopg2.connect(conn_string)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO documentos_advocacia (titulo, conteudo, area_id, servico_id, agente, embedding, metadata)
                VALUES (%s, %s, %s, %s, %s, %s::vector, %s::jsonb)
                RETURNING id
            """, (titulo, conteudo, area_id, servico_id, agente, str(embedding), json.dumps(metadata or {})))
            result = cur.fetchone()
            conn.commit()
            return result[0] if result else 0
    finally:
        conn.close()


async def rag_advocacia_update_document(
    doc_id: int,
    titulo: str = None,
    conteudo: str = None,
    area_id: str = None,
    servico_id: str = None,
    agente: str = None,
    metadata: dict = None
) -> bool:
    """Atualiza um documento existente"""
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        # Busca documento atual
        current = await conn.fetchrow(
            "SELECT * FROM documentos_advocacia WHERE id = $1",
            doc_id
        )
        if not current:
            return False

        # Usa valores atuais se nao fornecidos
        titulo = titulo or current["titulo"]
        conteudo = conteudo or current["conteudo"]
        area_id = area_id if area_id is not None else current["area_id"]
        servico_id = servico_id if servico_id is not None else current["servico_id"]
        agente = agente if agente is not None else current["agente"]
        metadata = metadata or _parse_metadata(current["metadata"])

        # Regenera embedding
        embedding = await _get_embedding_async(f"{titulo}\n{conteudo}")

        await conn.execute("""
            UPDATE documentos_advocacia
            SET titulo = $1, conteudo = $2, area_id = $3, servico_id = $4,
                agente = $5, embedding = $6::vector, metadata = $7::jsonb,
                updated_at = NOW()
            WHERE id = $8
        """, titulo, conteudo, area_id, servico_id, agente, str(embedding), json.dumps(metadata), doc_id)

        return True


async def rag_advocacia_delete_document(doc_id: int) -> bool:
    """Remove um documento"""
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM documentos_advocacia WHERE id = $1",
            doc_id
        )
        return "DELETE 1" in result


async def rag_advocacia_list_documents(
    area_id: str = None,
    servico_id: str = None,
    agente: str = None,
    limit: int = 50
) -> List[dict]:
    """
    Lista documentos com filtros opcionais

    Args:
        area_id: Filtrar por area
        servico_id: Filtrar por servico
        agente: Filtrar por agente
        limit: Numero maximo de resultados

    Returns:
        Lista de documentos
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        query = """
            SELECT d.id, d.titulo, d.conteudo, d.area_id, d.servico_id, d.agente,
                   d.metadata, d.created_at,
                   a.nome as area_nome, s.nome as servico_nome
            FROM documentos_advocacia d
            LEFT JOIN areas_atuacao_advocacia a ON d.area_id = a.id
            LEFT JOIN servicos_advocacia s ON d.servico_id = s.id
            WHERE 1=1
        """
        params = []

        if area_id:
            params.append(area_id)
            query += f" AND d.area_id = ${len(params)}"

        if servico_id:
            params.append(servico_id)
            query += f" AND d.servico_id = ${len(params)}"

        if agente:
            params.append(agente)
            query += f" AND d.agente = ${len(params)}"

        params.append(limit)
        query += f" ORDER BY d.created_at DESC LIMIT ${len(params)}"

        rows = await conn.fetch(query, *params)

        return [
            {
                "id": row["id"],
                "titulo": row["titulo"],
                "conteudo": row["conteudo"],
                "area_id": row["area_id"],
                "area_nome": row["area_nome"],
                "servico_id": row["servico_id"],
                "servico_nome": row["servico_nome"],
                "agente": row["agente"],
                "metadata": _parse_metadata(row["metadata"]),
                "created_at": row["created_at"].isoformat() if row["created_at"] else None
            }
            for row in rows
        ]


# --- Prompts Genericos ---

async def rag_advocacia_get_prompt(agente: str) -> Optional[str]:
    """
    Busca prompt generico para um agente

    Args:
        agente: Nome do agente (suporte, agendamento)

    Returns:
        Prompt do agente ou None
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        result = await conn.fetchval(
            "SELECT prompt FROM prompts_advocacia WHERE agente = $1",
            agente
        )
        return result


def rag_advocacia_get_prompt_sync(agente: str) -> Optional[str]:
    """Busca prompt generico (sync)"""
    conn_string = _get_connection_string()
    conn = psycopg2.connect(conn_string)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT prompt FROM prompts_advocacia WHERE agente = %s",
                (agente,)
            )
            result = cur.fetchone()
            return result[0] if result else None
    finally:
        conn.close()


async def rag_advocacia_set_prompt(agente: str, prompt: str) -> bool:
    """
    Define/atualiza prompt generico de um agente

    Args:
        agente: Nome do agente
        prompt: Conteudo do prompt

    Returns:
        True se salvou com sucesso
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO prompts_advocacia (agente, prompt)
            VALUES ($1, $2)
            ON CONFLICT (agente) DO UPDATE SET
                prompt = EXCLUDED.prompt,
                updated_at = NOW()
        """, agente, prompt)

        return True


def rag_advocacia_set_prompt_sync(agente: str, prompt: str) -> bool:
    """Define/atualiza prompt generico (sync)"""
    conn_string = _get_connection_string()
    conn = psycopg2.connect(conn_string)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO prompts_advocacia (agente, prompt)
                VALUES (%s, %s)
                ON CONFLICT (agente) DO UPDATE SET
                    prompt = EXCLUDED.prompt,
                    updated_at = NOW()
            """, (agente, prompt))
            conn.commit()
            return True
    finally:
        conn.close()


# --- Perguntas sem Resposta (Feedback Loop) ---

def rag_advocacia_log_pergunta_sem_resposta_sync(
    pergunta: str,
    agente: str = None,
    area_id: str = None,
    motivo: str = "nao_encontrado",
    query_expandida: str = None,
    docs_encontrados: int = 0,
    telefone: str = None,
    conversation_id: str = None
) -> int:
    """
    Registra uma pergunta que o RAG nao conseguiu responder (sync)

    Returns:
        ID do registro criado
    """
    conn_string = _get_connection_string()
    conn = psycopg2.connect(conn_string)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO perguntas_sem_resposta_advocacia
                (pergunta, agente, area_id, motivo, query_expandida, docs_encontrados, telefone, conversation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (pergunta, agente, area_id, motivo, query_expandida, docs_encontrados, telefone, conversation_id))
            result = cur.fetchone()
            conn.commit()
            print(f"[RAG Advocacia] Pergunta sem resposta registrada: '{pergunta[:50]}...' (agente: {agente}, area: {area_id})")
            return result[0] if result else 0
    except Exception as e:
        print(f"[RAG Advocacia] Erro ao registrar pergunta sem resposta: {e}")
        return 0
    finally:
        conn.close()


async def rag_advocacia_log_pergunta_sem_resposta(
    pergunta: str,
    agente: str = None,
    area_id: str = None,
    motivo: str = "nao_encontrado",
    query_expandida: str = None,
    docs_encontrados: int = 0,
    telefone: str = None,
    conversation_id: str = None
) -> int:
    """Registra uma pergunta sem resposta (async)"""
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        result = await conn.fetchrow("""
            INSERT INTO perguntas_sem_resposta_advocacia
            (pergunta, agente, area_id, motivo, query_expandida, docs_encontrados, telefone, conversation_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
        """, pergunta, agente, area_id, motivo, query_expandida, docs_encontrados, telefone, conversation_id)

        print(f"[RAG Advocacia] Pergunta sem resposta registrada: '{pergunta[:50]}...' (agente: {agente}, area: {area_id})")
        return result["id"] if result else 0


async def rag_advocacia_listar_perguntas_sem_resposta(
    apenas_nao_resolvidas: bool = True,
    agente: str = None,
    area_id: str = None,
    limit: int = 50
) -> List[dict]:
    """Lista perguntas sem resposta"""
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        query = """
            SELECT id, pergunta, telefone, conversation_id, agente, area_id, motivo,
                   query_expandida, docs_encontrados, resolvido, created_at
            FROM perguntas_sem_resposta_advocacia
            WHERE 1=1
        """
        params = []

        if apenas_nao_resolvidas:
            query += " AND resolvido = FALSE"

        if agente:
            params.append(agente)
            query += f" AND agente = ${len(params)}"

        if area_id:
            params.append(area_id)
            query += f" AND area_id = ${len(params)}"

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
                "area_id": row["area_id"],
                "motivo": row["motivo"],
                "query_expandida": row["query_expandida"],
                "docs_encontrados": row["docs_encontrados"],
                "resolvido": row["resolvido"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None
            }
            for row in rows
        ]


# --- Busca Semantica ---

async def rag_advocacia_search_async(
    query: str,
    area_ids: List[str] = None,
    servico_id: str = None,
    agente: str = None,
    limit: int = 5,
    similarity_threshold: float = 0.7
) -> List[dict]:
    """
    Busca documentos similares a query (async)

    Args:
        query: Pergunta ou termo de busca
        area_ids: Lista de areas para filtrar (pode ser multiplas)
        servico_id: Filtrar por servico
        agente: Filtrar por agente
        limit: Numero maximo de resultados
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
                d.id, d.titulo, d.conteudo, d.area_id, d.servico_id, d.agente, d.metadata,
                a.nome as area_nome, s.nome as servico_nome,
                1 - (d.embedding <=> $1::vector) as similarity
            FROM documentos_advocacia d
            LEFT JOIN areas_atuacao_advocacia a ON d.area_id = a.id
            LEFT JOIN servicos_advocacia s ON d.servico_id = s.id
            WHERE 1 - (d.embedding <=> $1::vector) > $2
        """
        params = [str(query_embedding), similarity_threshold]

        if area_ids and len(area_ids) > 0:
            params.append(area_ids)
            base_query += f" AND (d.area_id = ANY(${len(params)}) OR d.area_id IS NULL)"

        if servico_id:
            params.append(servico_id)
            base_query += f" AND d.servico_id = ${len(params)}"

        if agente:
            params.append(agente)
            base_query += f" AND d.agente = ${len(params)}"

        params.append(limit)
        base_query += f" ORDER BY d.embedding <=> $1::vector LIMIT ${len(params)}"

        rows = await conn.fetch(base_query, *params)

        return [
            {
                "id": row["id"],
                "titulo": row["titulo"],
                "conteudo": row["conteudo"],
                "area_id": row["area_id"],
                "area_nome": row["area_nome"],
                "servico_id": row["servico_id"],
                "servico_nome": row["servico_nome"],
                "agente": row["agente"],
                "metadata": _parse_metadata(row["metadata"]),
                "similarity": float(row["similarity"])
            }
            for row in rows
        ]


def rag_advocacia_search_sync(
    query: str,
    area_ids: List[str] = None,
    servico_id: str = None,
    agente: str = None,
    limit: int = 5,
    similarity_threshold: float = 0.3
) -> List[dict]:
    """
    Busca hibrida: combina busca semantica + full-text search (sync)

    Args:
        query: Pergunta ou termo de busca
        area_ids: Lista de areas para filtrar
        servico_id: Filtrar por servico
        agente: Filtrar por agente
        limit: Numero maximo de resultados
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
            params_semantic = [str(query_embedding)]
            params_fulltext = [query]

            if area_ids and len(area_ids) > 0:
                where_clauses.append("(area_id = ANY(%s) OR area_id IS NULL)")
                params_semantic.append(area_ids)
                params_fulltext.append(area_ids)

            if servico_id:
                where_clauses.append("servico_id = %s")
                params_semantic.append(servico_id)
                params_fulltext.append(servico_id)

            if agente:
                where_clauses.append("agente = %s")
                params_semantic.append(agente)
                params_fulltext.append(agente)

            where_sql = " AND " + " AND ".join(where_clauses) if where_clauses else ""

            # Busca hibrida: semantic + fulltext
            sql = f"""
                WITH semantic AS (
                    SELECT id, 1 - (embedding <=> %s::vector) as semantic_score
                    FROM documentos_advocacia
                    WHERE 1=1 {where_sql}
                ),
                fulltext AS (
                    SELECT id,
                           COALESCE(ts_rank(
                               to_tsvector('portuguese', titulo || ' ' || conteudo),
                               plainto_tsquery('portuguese', %s)
                           ), 0) as fulltext_score
                    FROM documentos_advocacia
                    WHERE 1=1 {where_sql}
                )
                SELECT
                    d.id, d.titulo, d.conteudo, d.area_id, d.servico_id, d.agente, d.metadata,
                    a.nome as area_nome, s.nome as servico_nome,
                    sem.semantic_score,
                    ft.fulltext_score,
                    (0.7 * sem.semantic_score + 0.3 * LEAST(ft.fulltext_score * 2, 1)) as combined_score
                FROM documentos_advocacia d
                LEFT JOIN areas_atuacao_advocacia a ON d.area_id = a.id
                LEFT JOIN servicos_advocacia s ON d.servico_id = s.id
                JOIN semantic sem ON d.id = sem.id
                JOIN fulltext ft ON d.id = ft.id
                WHERE (0.7 * sem.semantic_score + 0.3 * LEAST(ft.fulltext_score * 2, 1)) > %s
                ORDER BY combined_score DESC
                LIMIT %s
            """

            # Monta params na ordem correta
            final_params = params_semantic + params_fulltext + [similarity_threshold, limit]

            cur.execute(sql, final_params)
            rows = cur.fetchall()

            return [
                {
                    "id": row["id"],
                    "titulo": row["titulo"],
                    "conteudo": row["conteudo"],
                    "area_id": row["area_id"],
                    "area_nome": row["area_nome"],
                    "servico_id": row["servico_id"],
                    "servico_nome": row["servico_nome"],
                    "agente": row["agente"],
                    "metadata": _parse_metadata(row["metadata"]),
                    "similarity": float(row["combined_score"]),
                    "semantic_score": float(row["semantic_score"]),
                    "fulltext_score": float(row["fulltext_score"])
                }
                for row in rows
            ]
    finally:
        conn.close()


# --- Classe de Compatibilidade ---

class RAGAdvocaciaService:
    """Classe de compatibilidade para RAG de Advocacia"""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self.embedding_model = _embedding_model
        self.embedding_dimension = _embedding_dimension
        self.initialized = False

    async def connect(self, pool: asyncpg.Pool):
        self.pool = pool

    async def init_tables(self):
        self.initialized = await rag_advocacia_init_tables()

    async def _get_embedding(self, text: str) -> List[float]:
        return await _get_embedding_async(text)

    # Areas
    async def add_area(self, area_id: str, nome: str, prompt_vendas: str,
                       keywords: List[str] = None, descricao: str = None, ordem: int = 0) -> str:
        return await rag_advocacia_add_area(area_id, nome, prompt_vendas, keywords, descricao, ordem)

    async def list_areas(self, apenas_ativas: bool = True) -> List[dict]:
        return await rag_advocacia_list_areas(apenas_ativas)

    async def get_area(self, area_id: str) -> Optional[dict]:
        return await rag_advocacia_get_area(area_id)

    # Servicos
    async def add_servico(self, servico_id: str, area_id: str, nome: str, descricao: str = None) -> str:
        return await rag_advocacia_add_servico(servico_id, area_id, nome, descricao)

    async def list_servicos(self, area_id: str = None) -> List[dict]:
        return await rag_advocacia_list_servicos(area_id)

    # Documentos
    async def add_document(self, titulo: str, conteudo: str, area_id: str = None,
                          servico_id: str = None, agente: str = "vendas", metadata: dict = None) -> int:
        return await rag_advocacia_add_document(titulo, conteudo, area_id, servico_id, agente, metadata)

    async def update_document(self, doc_id: int, titulo: str = None, conteudo: str = None,
                             area_id: str = None, servico_id: str = None,
                             agente: str = None, metadata: dict = None) -> bool:
        return await rag_advocacia_update_document(doc_id, titulo, conteudo, area_id, servico_id, agente, metadata)

    async def delete_document(self, doc_id: int) -> bool:
        return await rag_advocacia_delete_document(doc_id)

    async def list_documents(self, area_id: str = None, servico_id: str = None,
                            agente: str = None, limit: int = 50) -> List[dict]:
        return await rag_advocacia_list_documents(area_id, servico_id, agente, limit)

    # Busca
    async def search(self, query: str, area_ids: List[str] = None, servico_id: str = None,
                    agente: str = None, limit: int = 5, similarity_threshold: float = 0.7) -> List[dict]:
        return await rag_advocacia_search_async(query, area_ids, servico_id, agente, limit, similarity_threshold)

    def search_sync(self, query: str, area_ids: List[str] = None, servico_id: str = None,
                   agente: str = None, limit: int = 5, similarity_threshold: float = 0.3) -> List[dict]:
        return rag_advocacia_search_sync(query, area_ids, servico_id, agente, limit, similarity_threshold)

    # Prompts
    async def get_prompt(self, agente: str) -> Optional[str]:
        return await rag_advocacia_get_prompt(agente)

    async def set_prompt(self, agente: str, prompt: str) -> bool:
        return await rag_advocacia_set_prompt(agente, prompt)


# Instancia global para compatibilidade
rag_advocacia_service = RAGAdvocaciaService()


async def get_rag_advocacia_service(pool: asyncpg.Pool) -> RAGAdvocaciaService:
    """Retorna o servico RAG Advocacia conectado"""
    if rag_advocacia_service.pool is None:
        await rag_advocacia_service.connect(pool)
        await rag_advocacia_service.init_tables()
    return rag_advocacia_service
