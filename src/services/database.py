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

            # Tabela de conversas (pipeline de atendimento)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS pipeline_conversas (
                    id SERIAL PRIMARY KEY,
                    telefone VARCHAR(50) NOT NULL,
                    nome_paciente VARCHAR(255),
                    etapa VARCHAR(50) NOT NULL DEFAULT 'novo_contato',
                    conversation_id VARCHAR(255),
                    ultima_mensagem TEXT,
                    ultima_atualizacao TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    agendamento_id INTEGER,
                    observacoes TEXT,
                    tipo_atendimento VARCHAR(20) DEFAULT 'agente',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)

            # Adiciona coluna tipo_atendimento se nao existir (para tabelas existentes)
            await conn.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'pipeline_conversas' AND column_name = 'tipo_atendimento'
                    ) THEN
                        ALTER TABLE pipeline_conversas ADD COLUMN tipo_atendimento VARCHAR(20) DEFAULT 'agente';
                    END IF;
                END $$;
            """)

            # Atualiza registros existentes que estao com NULL para 'agente'
            await conn.execute("""
                UPDATE pipeline_conversas SET tipo_atendimento = 'agente' WHERE tipo_atendimento IS NULL
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
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_pipeline_etapa
                ON pipeline_conversas(etapa)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_pipeline_telefone
                ON pipeline_conversas(telefone)
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
        # Aceita tanto "user"/"human" para humano quanto "assistant"/"ai" para IA
        msg_type = "human" if role in ("user", "human") else "ai"
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

    # --- Pipeline de Conversas ---

    async def pipeline_upsert_conversa(
        self,
        telefone: str,
        etapa: str = None,
        nome_paciente: str = None,
        conversation_id: str = None,
        ultima_mensagem: str = None,
        agendamento_id: int = None,
        observacoes: str = None,
        tipo_atendimento: str = None
    ) -> int:
        """Cria ou atualiza uma conversa no pipeline"""
        async with self.pool.acquire() as conn:
            # Verifica se ja existe
            existing = await conn.fetchrow("""
                SELECT id FROM pipeline_conversas WHERE telefone = $1
            """, telefone)

            if existing:
                # Atualiza
                updates = ["ultima_atualizacao = NOW()"]
                params = []
                param_num = 1

                if etapa:
                    params.append(etapa)
                    updates.append(f"etapa = ${param_num}")
                    param_num += 1
                if nome_paciente:
                    params.append(nome_paciente)
                    updates.append(f"nome_paciente = ${param_num}")
                    param_num += 1
                if conversation_id:
                    params.append(conversation_id)
                    updates.append(f"conversation_id = ${param_num}")
                    param_num += 1
                if ultima_mensagem:
                    params.append(ultima_mensagem)
                    updates.append(f"ultima_mensagem = ${param_num}")
                    param_num += 1
                if agendamento_id is not None:
                    params.append(agendamento_id)
                    updates.append(f"agendamento_id = ${param_num}")
                    param_num += 1
                if observacoes:
                    params.append(observacoes)
                    updates.append(f"observacoes = ${param_num}")
                    param_num += 1
                if tipo_atendimento:
                    params.append(tipo_atendimento)
                    updates.append(f"tipo_atendimento = ${param_num}")
                    param_num += 1

                params.append(telefone)
                query = f"UPDATE pipeline_conversas SET {', '.join(updates)} WHERE telefone = ${param_num}"
                await conn.execute(query, *params)
                return existing["id"]
            else:
                # Cria novo
                row = await conn.fetchrow("""
                    INSERT INTO pipeline_conversas
                    (telefone, etapa, nome_paciente, conversation_id, ultima_mensagem, agendamento_id, observacoes, tipo_atendimento)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    RETURNING id
                """, telefone, etapa or "novo_contato", nome_paciente, conversation_id, ultima_mensagem, agendamento_id, observacoes, tipo_atendimento or "agente")
                return row["id"]

    async def pipeline_listar_conversas(self, etapa: str = None, tenant_id: int = None) -> list:
        """Lista todas as conversas do pipeline, opcionalmente filtradas por tenant"""
        async with self.pool.acquire() as conn:
            base_query = """
                SELECT pc.*,
                       a.paciente_nome as agendamento_paciente,
                       a.data_hora as agendamento_data,
                       p.nome as profissional_nome
                FROM pipeline_conversas pc
                LEFT JOIN agendamentos a ON pc.agendamento_id = a.id
                LEFT JOIN profissionais p ON a.profissional_id = p.id
            """
            conditions = []
            params = []
            param_num = 1

            if tenant_id is not None:
                conditions.append(f"pc.tenant_id = ${param_num}")
                params.append(tenant_id)
                param_num += 1

            if etapa:
                conditions.append(f"pc.etapa = ${param_num}")
                params.append(etapa)
                param_num += 1

            if conditions:
                base_query += " WHERE " + " AND ".join(conditions)

            base_query += " ORDER BY pc.ultima_atualizacao DESC"

            rows = await conn.fetch(base_query, *params)
            return [dict(row) for row in rows]

    async def pipeline_mover_etapa(self, conversa_id: int, nova_etapa: str) -> bool:
        """Move uma conversa para outra etapa"""
        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE pipeline_conversas
                SET etapa = $1, ultima_atualizacao = NOW()
                WHERE id = $2
            """, nova_etapa, conversa_id)
            return result != "UPDATE 0"

    async def pipeline_buscar_por_telefone(self, telefone: str) -> dict:
        """Busca uma conversa pelo telefone"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT pc.*,
                       a.paciente_nome as agendamento_paciente,
                       a.data_hora as agendamento_data,
                       p.nome as profissional_nome
                FROM pipeline_conversas pc
                LEFT JOIN agendamentos a ON pc.agendamento_id = a.id
                LEFT JOIN profissionais p ON a.profissional_id = p.id
                WHERE pc.telefone = $1
            """, telefone)
            return dict(row) if row else None

    async def pipeline_deletar_conversa(self, conversa_id: int) -> bool:
        """Remove uma conversa do pipeline"""
        async with self.pool.acquire() as conn:
            # Primeiro verifica se existe
            existing = await conn.fetchrow("""
                SELECT id FROM pipeline_conversas WHERE id = $1
            """, conversa_id)
            if not existing:
                return False

            # Deleta
            await conn.execute("""
                DELETE FROM pipeline_conversas WHERE id = $1
            """, conversa_id)
            return True

    async def pipeline_stats(self, tenant_id: int = None) -> dict:
        """Retorna estatisticas do pipeline, opcionalmente filtradas por tenant"""
        async with self.pool.acquire() as conn:
            if tenant_id is not None:
                rows = await conn.fetch("""
                    SELECT etapa, COUNT(*) as total
                    FROM pipeline_conversas
                    WHERE tenant_id = $1
                    GROUP BY etapa
                """, tenant_id)
            else:
                rows = await conn.fetch("""
                    SELECT etapa, COUNT(*) as total
                    FROM pipeline_conversas
                    GROUP BY etapa
                """)
            stats = {row["etapa"]: row["total"] for row in rows}
            return stats


# Instância global do serviço
db_service = DatabaseService()


async def get_db_service() -> DatabaseService:
    """Retorna a instância do serviço de banco de dados conectada"""
    if db_service.pool is None:
        await db_service.connect()
        await db_service.init_tables()
    return db_service
