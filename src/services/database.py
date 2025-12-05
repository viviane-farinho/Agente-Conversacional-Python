"""
Servico de banco de dados PostgreSQL/Supabase
Gerencia fila de mensagens e historico de conversas

Paradigma: Funcional
"""
import json
from datetime import datetime
from typing import Optional

import asyncpg

from src.config import Config


# --- Estado Global do Pool ---

_pool: Optional[asyncpg.Pool] = None


# --- Conexao ---

async def db_connect() -> asyncpg.Pool:
    """
    Conecta ao banco de dados e retorna o pool

    Returns:
        Pool de conexoes asyncpg
    """
    global _pool

    if _pool is not None:
        return _pool

    if Config.DATABASE_URL:
        _pool = await asyncpg.create_pool(Config.DATABASE_URL)
    else:
        _pool = await asyncpg.create_pool(
            host=Config.POSTGRES_HOST,
            port=int(Config.POSTGRES_PORT),
            user=Config.POSTGRES_USER,
            password=Config.POSTGRES_PASSWORD,
            database=Config.POSTGRES_DB
        )

    return _pool


async def db_get_pool() -> asyncpg.Pool:
    """
    Retorna o pool existente ou conecta

    Returns:
        Pool de conexoes asyncpg
    """
    global _pool

    if _pool is None:
        await db_connect()

    return _pool


async def db_disconnect() -> None:
    """Fecha a conexao com o banco de dados"""
    global _pool

    if _pool:
        await _pool.close()
        _pool = None


# --- Inicializacao de Tabelas ---

async def db_init_tables() -> None:
    """Cria as tabelas necessarias se nao existirem"""
    pool = await db_get_pool()

    async with pool.acquire() as conn:
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

        # Tabela de historico de mensagens (memoria de conversas)
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

        # Adiciona coluna tipo_atendimento se nao existir
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

        # Atualiza registros existentes
        await conn.execute("""
            UPDATE pipeline_conversas SET tipo_atendimento = 'agente' WHERE tipo_atendimento IS NULL
        """)

        # Indices
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

        # Tabela de agentes (multi-agent architecture)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS agentes (
                id SERIAL PRIMARY KEY,
                tipo VARCHAR(50) NOT NULL,
                nome VARCHAR(100) NOT NULL,
                descricao TEXT,
                prompt_sistema TEXT,
                ativo BOOLEAN DEFAULT true,
                configuracoes JSONB DEFAULT '{}',
                tools TEXT[] DEFAULT '{}',
                categorias_rag TEXT[] DEFAULT '{}',
                ordem INTEGER DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)

        # Migracao: Adiciona colunas novas se nao existirem
        await conn.execute("""
            DO $$
            BEGIN
                -- Coluna ordem
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'agentes' AND column_name = 'ordem') THEN
                    ALTER TABLE agentes ADD COLUMN ordem INTEGER DEFAULT 0;
                END IF;
                
                -- Coluna tools
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'agentes' AND column_name = 'tools') THEN
                    ALTER TABLE agentes ADD COLUMN tools TEXT[] DEFAULT '{}';
                END IF;

                -- Coluna categorias_rag
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'agentes' AND column_name = 'categorias_rag') THEN
                    ALTER TABLE agentes ADD COLUMN categorias_rag TEXT[] DEFAULT '{}';
                END IF;
            END $$;
        """)

        # Indice para tipo de agente
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_agentes_tipo
            ON agentes(tipo)
        """)

        # Insere agentes padrao se a tabela estiver vazia
        existing = await conn.fetchval("SELECT COUNT(*) FROM agentes")
        if existing == 0:
            await conn.execute("""
                INSERT INTO agentes (tipo, nome, descricao, prompt_sistema, ativo, ordem, tools, categorias_rag)
                VALUES
                ('supervisor', 'Supervisor', 'Agente supervisor que roteia conversas para agentes especializados',
                 'Você é o supervisor da Secretaria IA. Analise a mensagem do usuário e decida qual agente especializado deve atender: vendas (para informações sobre serviços e preços), suporte (para dúvidas gerais e reclamações), ou agendamento (para marcar, remarcar ou cancelar consultas).',
                 true, 0, '{}', '{}'),
                ('vendas', 'Vendas', 'Especialista em apresentar serviços e preços',
                 'Você é especialista em vendas. Apresente os serviços disponíveis, tire dúvidas sobre preços e benefícios. Seja persuasivo mas não insistente.',
                 true, 1, '{}', ARRAY['servicos', 'precos', 'promocoes']),
                ('suporte', 'Suporte', 'Atendimento de dúvidas e reclamações',
                 'Você é especialista em suporte. Responda dúvidas gerais, resolva problemas e encaminhe reclamações de forma empática e eficiente.',
                 true, 2, '{}', ARRAY['faq', 'procedimentos', 'politicas']),
                ('agendamento', 'Agendamento', 'Gestão de consultas e horários',
                 'Você é especialista em agendamentos. Ajude a marcar, remarcar ou cancelar consultas. Verifique disponibilidade e confirme os dados do paciente.',
                 true, 3, ARRAY['verificar_disponibilidade', 'criar_agendamento', 'cancelar_agendamento'], ARRAY['profissionais', 'horarios'])
            """)


# --- Fila de Mensagens ---

async def db_enqueue_message(
    message_id: str,
    phone: str,
    message: str,
    timestamp: datetime
) -> None:
    """
    Adiciona uma mensagem a fila

    Args:
        message_id: ID da mensagem
        phone: Telefone do remetente
        message: Conteudo da mensagem
        timestamp: Data/hora da mensagem
    """
    pool = await db_get_pool()

    # Remove timezone para compatibilidade
    if timestamp.tzinfo is not None:
        timestamp = timestamp.replace(tzinfo=None)

    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO n8n_fila_mensagens (id_mensagem, telefone, mensagem, timestamp)
            VALUES ($1, $2, $3, $4)
        """, message_id, phone, message, timestamp)


async def db_get_queued_messages(phone: str) -> list:
    """
    Obtem todas as mensagens na fila para um telefone

    Args:
        phone: Telefone do remetente

    Returns:
        Lista de mensagens na fila
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id_mensagem, mensagem, timestamp
            FROM n8n_fila_mensagens
            WHERE telefone = $1
            ORDER BY timestamp ASC
        """, phone)
        return [dict(row) for row in rows]


async def db_clear_message_queue(phone: str) -> None:
    """
    Limpa a fila de mensagens para um telefone

    Args:
        phone: Telefone do remetente
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        await conn.execute("""
            DELETE FROM n8n_fila_mensagens
            WHERE telefone = $1
        """, phone)


async def db_get_last_message_id(phone: str) -> Optional[str]:
    """
    Obtem o ID da ultima mensagem na fila

    Args:
        phone: Telefone do remetente

    Returns:
        ID da ultima mensagem ou None
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT id_mensagem
            FROM n8n_fila_mensagens
            WHERE telefone = $1
            ORDER BY timestamp DESC
            LIMIT 1
        """, phone)
        return row["id_mensagem"] if row else None


# --- Historico de Mensagens (Memoria) ---

async def db_add_message_to_history(
    session_id: str,
    role: str,
    content: str
) -> None:
    """
    Adiciona uma mensagem ao historico

    Args:
        session_id: ID da sessao (telefone)
        role: Papel (user/human ou assistant/ai)
        content: Conteudo da mensagem
    """
    pool = await db_get_pool()

    # Formato JSONB compativel com a tabela existente
    msg_type = "human" if role in ("user", "human") else "ai"
    message_data = json.dumps({
        "type": msg_type,
        "content": content,
        "additional_kwargs": {},
        "response_metadata": {}
    })

    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO n8n_historico_mensagens (session_id, message)
            VALUES ($1, $2::jsonb)
        """, session_id, message_data)


async def db_get_message_history(
    session_id: str,
    limit: int = None
) -> list:
    """
    Obtem o historico de mensagens de uma sessao

    Args:
        session_id: ID da sessao (telefone)
        limit: Numero maximo de mensagens

    Returns:
        Lista de mensagens do historico
    """
    pool = await db_get_pool()

    if limit is None:
        limit = Config.CONTEXT_WINDOW_LENGTH

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT message, created_at
            FROM n8n_historico_mensagens
            WHERE session_id = $1
            ORDER BY created_at DESC
            LIMIT $2
        """, session_id, limit)

        # Retorna em ordem cronologica
        result = []
        for row in reversed(rows):
            msg = row["message"]

            # Se for string, faz parse do JSON
            if isinstance(msg, str):
                try:
                    msg = json.loads(msg)
                except json.JSONDecodeError:
                    continue

            # Converte type para role
            msg_type = msg.get("type", "human")
            role = "user" if msg_type == "human" else "assistant"
            result.append({
                "role": role,
                "content": msg.get("content", ""),
                "created_at": row["created_at"]
            })

        return result


async def db_clear_message_history(session_id: str) -> None:
    """
    Limpa o historico de uma sessao

    Args:
        session_id: ID da sessao (telefone)
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        await conn.execute("""
            DELETE FROM n8n_historico_mensagens
            WHERE session_id = $1
        """, session_id)


# --- Pipeline de Conversas ---

async def db_pipeline_upsert_conversa(
    telefone: str,
    etapa: str = None,
    nome_paciente: str = None,
    conversation_id: str = None,
    ultima_mensagem: str = None,
    agendamento_id: int = None,
    observacoes: str = None,
    tipo_atendimento: str = None
) -> int:
    """
    Cria ou atualiza uma conversa no pipeline

    Args:
        telefone: Telefone do paciente
        etapa: Etapa atual do pipeline
        nome_paciente: Nome do paciente
        conversation_id: ID da conversa no Chatwoot
        ultima_mensagem: Ultima mensagem recebida
        agendamento_id: ID do agendamento relacionado
        observacoes: Observacoes adicionais
        tipo_atendimento: Tipo (agente, humano, manual)

    Returns:
        ID da conversa
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
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


async def db_pipeline_listar_conversas(etapa: str = None) -> list:
    """
    Lista todas as conversas do pipeline

    Args:
        etapa: Filtrar por etapa especifica

    Returns:
        Lista de conversas
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        if etapa:
            rows = await conn.fetch("""
                SELECT pc.*,
                       a.paciente_nome as agendamento_paciente,
                       a.data_hora as agendamento_data,
                       p.nome as profissional_nome
                FROM pipeline_conversas pc
                LEFT JOIN agendamentos a ON pc.agendamento_id = a.id
                LEFT JOIN profissionais p ON a.profissional_id = p.id
                WHERE pc.etapa = $1
                ORDER BY pc.ultima_atualizacao DESC
            """, etapa)
        else:
            rows = await conn.fetch("""
                SELECT pc.*,
                       a.paciente_nome as agendamento_paciente,
                       a.data_hora as agendamento_data,
                       p.nome as profissional_nome
                FROM pipeline_conversas pc
                LEFT JOIN agendamentos a ON pc.agendamento_id = a.id
                LEFT JOIN profissionais p ON a.profissional_id = p.id
                ORDER BY pc.ultima_atualizacao DESC
            """)
        return [dict(row) for row in rows]


async def db_pipeline_mover_etapa(conversa_id: int, nova_etapa: str) -> bool:
    """
    Move uma conversa para outra etapa

    Args:
        conversa_id: ID da conversa
        nova_etapa: Nova etapa

    Returns:
        True se moveu com sucesso
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        result = await conn.execute("""
            UPDATE pipeline_conversas
            SET etapa = $1, ultima_atualizacao = NOW()
            WHERE id = $2
        """, nova_etapa, conversa_id)
        return result != "UPDATE 0"


async def db_pipeline_buscar_por_telefone(telefone: str) -> Optional[dict]:
    """
    Busca uma conversa pelo telefone

    Args:
        telefone: Telefone do paciente

    Returns:
        Dados da conversa ou None
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
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


async def db_pipeline_deletar_conversa(conversa_id: int) -> bool:
    """
    Remove uma conversa do pipeline

    Args:
        conversa_id: ID da conversa

    Returns:
        True se removeu com sucesso
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        existing = await conn.fetchrow("""
            SELECT id FROM pipeline_conversas WHERE id = $1
        """, conversa_id)

        if not existing:
            return False

        await conn.execute("""
            DELETE FROM pipeline_conversas WHERE id = $1
        """, conversa_id)
        return True


async def db_pipeline_stats() -> dict:
    """
    Retorna estatisticas do pipeline

    Returns:
        Dicionario com contagem por etapa
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT etapa, COUNT(*) as total
            FROM pipeline_conversas
            GROUP BY etapa
        """)
        return {row["etapa"]: row["total"] for row in rows}


# --- Agentes (Multi-Agent Architecture) ---

async def db_agentes_listar(apenas_ativos: bool = False) -> list:
    """
    Lista todos os agentes

    Args:
        apenas_ativos: Se True, retorna apenas agentes ativos

    Returns:
        Lista de agentes
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        if apenas_ativos:
            rows = await conn.fetch("""
                SELECT * FROM agentes WHERE ativo = true ORDER BY ordem, id
            """)
        else:
            rows = await conn.fetch("""
                SELECT * FROM agentes ORDER BY ordem, id
            """)
        return [dict(row) for row in rows]


async def db_agentes_buscar(agente_id: int) -> Optional[dict]:
    """
    Busca um agente pelo ID

    Args:
        agente_id: ID do agente

    Returns:
        Dados do agente ou None
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT * FROM agentes WHERE id = $1
        """, agente_id)
        return dict(row) if row else None


async def db_agentes_buscar_por_tipo(tipo: str) -> Optional[dict]:
    """
    Busca um agente pelo tipo

    Args:
        tipo: Tipo do agente (supervisor, vendas, suporte, agendamento)

    Returns:
        Dados do agente ou None
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT * FROM agentes WHERE tipo = $1 AND ativo = true
        """, tipo)
        return dict(row) if row else None


async def db_agentes_criar(
    tipo: str,
    nome: str,
    descricao: str = None,
    prompt_sistema: str = None,
    ativo: bool = True,
    configuracoes: dict = None,
    tools: list = None,
    categorias_rag: list = None,
    ordem: int = 0
) -> int:
    """
    Cria um novo agente

    Args:
        tipo: Tipo do agente
        nome: Nome do agente
        descricao: Descricao do agente
        prompt_sistema: Prompt do sistema para o agente
        ativo: Se o agente esta ativo
        configuracoes: Configuracoes JSON do agente
        tools: Lista de tools disponiveis para o agente
        categorias_rag: Categorias do RAG que o agente pode consultar
        ordem: Ordem de exibicao

    Returns:
        ID do agente criado
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO agentes (tipo, nome, descricao, prompt_sistema, ativo, configuracoes, tools, categorias_rag, ordem)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id
        """, tipo, nome, descricao, prompt_sistema, ativo,
            json.dumps(configuracoes or {}), tools or [], categorias_rag or [], ordem)
        return row["id"]


async def db_agentes_atualizar(
    agente_id: int,
    nome: str = None,
    descricao: str = None,
    prompt_sistema: str = None,
    ativo: bool = None,
    configuracoes: dict = None,
    tools: list = None,
    categorias_rag: list = None,
    ordem: int = None
) -> bool:
    """
    Atualiza um agente existente

    Args:
        agente_id: ID do agente
        nome: Nome do agente
        descricao: Descricao do agente
        prompt_sistema: Prompt do sistema
        ativo: Se o agente esta ativo
        configuracoes: Configuracoes JSON
        tools: Lista de tools
        categorias_rag: Categorias do RAG
        ordem: Ordem de exibicao

    Returns:
        True se atualizou com sucesso
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        # Verifica se existe
        existing = await conn.fetchrow("SELECT id FROM agentes WHERE id = $1", agente_id)
        if not existing:
            return False

        # Monta query dinamica
        updates = ["updated_at = NOW()"]
        params = []
        param_num = 1

        if nome is not None:
            params.append(nome)
            updates.append(f"nome = ${param_num}")
            param_num += 1
        if descricao is not None:
            params.append(descricao)
            updates.append(f"descricao = ${param_num}")
            param_num += 1
        if prompt_sistema is not None:
            params.append(prompt_sistema)
            updates.append(f"prompt_sistema = ${param_num}")
            param_num += 1
        if ativo is not None:
            params.append(ativo)
            updates.append(f"ativo = ${param_num}")
            param_num += 1
        if configuracoes is not None:
            params.append(json.dumps(configuracoes))
            updates.append(f"configuracoes = ${param_num}")
            param_num += 1
        if tools is not None:
            params.append(tools)
            updates.append(f"tools = ${param_num}")
            param_num += 1
        if categorias_rag is not None:
            params.append(categorias_rag)
            updates.append(f"categorias_rag = ${param_num}")
            param_num += 1
        if ordem is not None:
            params.append(ordem)
            updates.append(f"ordem = ${param_num}")
            param_num += 1

        params.append(agente_id)
        query = f"UPDATE agentes SET {', '.join(updates)} WHERE id = ${param_num}"
        await conn.execute(query, *params)
        return True


async def db_agentes_deletar(agente_id: int) -> bool:
    """
    Remove um agente

    Args:
        agente_id: ID do agente

    Returns:
        True se removeu com sucesso
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT id FROM agentes WHERE id = $1", agente_id)
        if not existing:
            return False

        await conn.execute("DELETE FROM agentes WHERE id = $1", agente_id)
        return True


async def db_agentes_toggle_ativo(agente_id: int) -> Optional[bool]:
    """
    Alterna o status ativo de um agente

    Args:
        agente_id: ID do agente

    Returns:
        Novo status ou None se nao encontrou
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            UPDATE agentes SET ativo = NOT ativo, updated_at = NOW()
            WHERE id = $1
            RETURNING ativo
        """, agente_id)
        return row["ativo"] if row else None


# --- Compatibilidade (para transicao gradual) ---

class DatabaseService:
    """Classe de compatibilidade - usar funcoes diretamente"""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        self.pool = await db_connect()

    async def disconnect(self):
        await db_disconnect()

    async def init_tables(self):
        await db_init_tables()

    async def enqueue_message(self, message_id: str, phone: str, message: str, timestamp: datetime):
        await db_enqueue_message(message_id, phone, message, timestamp)

    async def get_queued_messages(self, phone: str) -> list:
        return await db_get_queued_messages(phone)

    async def clear_message_queue(self, phone: str):
        await db_clear_message_queue(phone)

    async def get_last_message_id(self, phone: str) -> Optional[str]:
        return await db_get_last_message_id(phone)

    async def add_message_to_history(self, session_id: str, role: str, content: str):
        await db_add_message_to_history(session_id, role, content)

    async def get_message_history(self, session_id: str, limit: int = None) -> list:
        return await db_get_message_history(session_id, limit)

    async def clear_message_history(self, session_id: str):
        await db_clear_message_history(session_id)

    async def pipeline_upsert_conversa(self, telefone: str, etapa: str = None, nome_paciente: str = None,
                                       conversation_id: str = None, ultima_mensagem: str = None,
                                       agendamento_id: int = None, observacoes: str = None,
                                       tipo_atendimento: str = None) -> int:
        return await db_pipeline_upsert_conversa(telefone, etapa, nome_paciente, conversation_id,
                                                  ultima_mensagem, agendamento_id, observacoes, tipo_atendimento)

    async def pipeline_listar_conversas(self, etapa: str = None) -> list:
        return await db_pipeline_listar_conversas(etapa)

    async def pipeline_mover_etapa(self, conversa_id: int, nova_etapa: str) -> bool:
        return await db_pipeline_mover_etapa(conversa_id, nova_etapa)

    async def pipeline_buscar_por_telefone(self, telefone: str) -> dict:
        return await db_pipeline_buscar_por_telefone(telefone)

    async def pipeline_deletar_conversa(self, conversa_id: int) -> bool:
        return await db_pipeline_deletar_conversa(conversa_id)

    async def pipeline_stats(self) -> dict:
        return await db_pipeline_stats()


# Instancia global para compatibilidade
db_service = DatabaseService()


async def get_db_service() -> DatabaseService:
    """Retorna a instancia do servico de banco de dados conectada"""
    if db_service.pool is None:
        await db_service.connect()
        await db_service.init_tables()
    return db_service
