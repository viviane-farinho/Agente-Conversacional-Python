"""
Serviço de banco de dados PostgreSQL/Supabase
Gerencia fila de mensagens e histórico de conversas
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional
import asyncpg

from src.config import Config


class DatabaseService:
    """Serviço para interação com PostgreSQL/Supabase"""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Estabelece conexão com o banco de dados"""
        if Config.DATABASE_URL:
            self.pool = await asyncpg.create_pool(Config.DATABASE_URL)
        else:
            self.pool = await asyncpg.create_pool(
                host=Config.POSTGRES_HOST,
                port=int(Config.POSTGRES_PORT),
                user=Config.POSTGRES_USER,
                password=Config.POSTGRES_PASSWORD,
                database=Config.POSTGRES_DB
            )

    async def disconnect(self):
        """Fecha a conexão com o banco de dados"""
        if self.pool:
            await self.pool.close()

    async def init_tables(self):
        """Cria as tabelas necessárias se não existirem"""
        async with self.pool.acquire() as conn:
            # Tabela de fila de mensagens
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS n8n_fila_mensagens (
                    id SERIAL PRIMARY KEY,
                    id_mensagem VARCHAR(255) NOT NULL,
                    telefone VARCHAR(50) NOT NULL,
                    mensagem TEXT NOT NULL,
                    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            # Tabela de histórico de mensagens (memória de conversas)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS n8n_historico_mensagens (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(255) NOT NULL,
                    role VARCHAR(20) NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            # Índices para melhor performance
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_fila_telefone
                ON n8n_fila_mensagens(telefone)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_historico_session
                ON n8n_historico_mensagens(session_id, created_at)
            """)

    # --- Fila de Mensagens ---

    async def enqueue_message(
        self,
        message_id: str,
        phone: str,
        message: str,
        timestamp: datetime
    ):
        """Adiciona uma mensagem à fila"""
        # Remove timezone para compatibilidade com a tabela existente (timestamp without time zone)
        if timestamp.tzinfo is not None:
            timestamp = timestamp.replace(tzinfo=None)

        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO n8n_fila_mensagens (id_mensagem, telefone, mensagem, timestamp)
                VALUES ($1, $2, $3, $4)
            """, message_id, phone, message, timestamp)

    async def get_queued_messages(self, phone: str) -> list:
        """Obtém todas as mensagens na fila para um telefone"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id_mensagem, mensagem, timestamp
                FROM n8n_fila_mensagens
                WHERE telefone = $1
                ORDER BY timestamp ASC
            """, phone)
            return [dict(row) for row in rows]

    async def clear_message_queue(self, phone: str):
        """Limpa a fila de mensagens para um telefone"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM n8n_fila_mensagens
                WHERE telefone = $1
            """, phone)

    async def get_last_message_id(self, phone: str) -> Optional[str]:
        """Obtém o ID da última mensagem na fila"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id_mensagem
                FROM n8n_fila_mensagens
                WHERE telefone = $1
                ORDER BY timestamp DESC
                LIMIT 1
            """, phone)
            return row["id_mensagem"] if row else None

    # --- Histórico de Mensagens (Memória) ---

    async def add_message_to_history(
        self,
        session_id: str,
        role: str,
        content: str
    ):
        """Adiciona uma mensagem ao histórico"""
        import json
        # Usa formato JSONB compatível com a tabela existente (type: human/ai)
        msg_type = "human" if role == "user" else "ai"
        message_data = json.dumps({
            "type": msg_type,
            "content": content,
            "additional_kwargs": {},
            "response_metadata": {}
        })

        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO n8n_historico_mensagens (session_id, message)
                VALUES ($1, $2::jsonb)
            """, session_id, message_data)

    async def get_message_history(
        self,
        session_id: str,
        limit: int = None
    ) -> list:
        """Obtém o histórico de mensagens de uma sessão"""
        import json

        if limit is None:
            limit = Config.CONTEXT_WINDOW_LENGTH

        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT message, created_at
                FROM n8n_historico_mensagens
                WHERE session_id = $1
                ORDER BY created_at DESC
                LIMIT $2
            """, session_id, limit)

            # Retorna em ordem cronológica, extraindo role e content do JSONB
            result = []
            for row in reversed(rows):
                msg = row["message"]
                # Se for string, faz parse do JSON
                if isinstance(msg, str):
                    try:
                        msg = json.loads(msg)
                    except json.JSONDecodeError:
                        continue

                # Converte type (human/ai) para role (user/assistant)
                msg_type = msg.get("type", "human")
                role = "user" if msg_type == "human" else "assistant"
                result.append({
                    "role": role,
                    "content": msg.get("content", ""),
                    "created_at": row["created_at"]
                })
            return result

    async def clear_message_history(self, session_id: str):
        """Limpa o histórico de uma sessão"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM n8n_historico_mensagens
                WHERE session_id = $1
            """, session_id)


# Instância global do serviço
db_service = DatabaseService()


async def get_db_service() -> DatabaseService:
    """Retorna a instância do serviço de banco de dados conectada"""
    if db_service.pool is None:
        await db_service.connect()
        await db_service.init_tables()
    return db_service
