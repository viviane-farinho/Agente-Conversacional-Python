"""
Servico de Agenda
Gerencia agendamentos no banco de dados

Paradigma: Funcional
"""
from datetime import datetime, date, time, timedelta
from typing import Optional, List

import asyncpg

from src.config import Config
from src.services.database import db_get_pool


# --- Inicializacao ---

async def agenda_init_tables() -> None:
    """Cria as tabelas necessarias para a agenda"""
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        # Tabela de profissionais
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS profissionais (
                id SERIAL PRIMARY KEY,
                nome VARCHAR(255) NOT NULL,
                especialidade VARCHAR(100),
                cargo VARCHAR(100),
                ativo BOOLEAN DEFAULT true,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)

        # Tabela de agendamentos
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS agendamentos (
                id SERIAL PRIMARY KEY,
                profissional_id INTEGER REFERENCES profissionais(id),
                paciente_nome VARCHAR(255) NOT NULL,
                paciente_telefone VARCHAR(50),
                paciente_nascimento DATE,
                data_hora TIMESTAMP WITH TIME ZONE NOT NULL,
                duracao_minutos INTEGER DEFAULT 30,
                status VARCHAR(50) DEFAULT 'agendado',
                confirmado BOOLEAN DEFAULT false,
                observacoes TEXT,
                conversation_id VARCHAR(100),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)

        # Indices
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_agendamentos_data
            ON agendamentos(data_hora)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_agendamentos_profissional
            ON agendamentos(profissional_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_agendamentos_telefone
            ON agendamentos(paciente_telefone)
        """)

        # Tabela de prompts
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS prompts_config (
                id SERIAL PRIMARY KEY,
                nome VARCHAR(100) UNIQUE NOT NULL,
                conteudo TEXT NOT NULL,
                descricao TEXT,
                ativo BOOLEAN DEFAULT true,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)

        # Tabela de configuracoes do sistema
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS system_config (
                id SERIAL PRIMARY KEY,
                key VARCHAR(100) UNIQUE NOT NULL,
                value TEXT NOT NULL,
                type VARCHAR(20) DEFAULT 'string',
                description TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)

        # Migration: Ensure 'type' and 'description' columns exist (for existing databases)
        try:
            await conn.execute("ALTER TABLE system_config ADD COLUMN IF NOT EXISTS type VARCHAR(20) DEFAULT 'string'")
            await conn.execute("ALTER TABLE system_config ADD COLUMN IF NOT EXISTS description TEXT")
            # Fix: Convert value column to TEXT if it was created as JSON/JSONB
            await conn.execute("ALTER TABLE system_config ALTER COLUMN value TYPE TEXT")
        except Exception as e:
            print(f"Migration warning: {e}")

        # Migration: adiciona coluna business_type na tabela profissionais
        try:
            await conn.execute("ALTER TABLE profissionais ADD COLUMN IF NOT EXISTS business_type VARCHAR(50) DEFAULT 'clinica'")
        except Exception as e:
            print(f"Migration profissionais warning: {e}")


# --- Profissionais ---

async def agenda_criar_profissional(
    nome: str,
    especialidade: str = None,
    cargo: str = None,
    business_type: str = "clinica"
) -> int:
    """
    Cria um novo profissional

    Args:
        nome: Nome do profissional
        especialidade: Especialidade
        cargo: Cargo
        business_type: Tipo de negócio (clinica, infoprodutor, etc)

    Returns:
        ID do profissional criado
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        result = await conn.fetchrow("""
            INSERT INTO profissionais (nome, especialidade, cargo, business_type)
            VALUES ($1, $2, $3, $4)
            RETURNING id
        """, nome, especialidade, cargo, business_type)
        return result["id"]


async def agenda_listar_profissionais(apenas_ativos: bool = True, business_type: str = None) -> List[dict]:
    """
    Lista todos os profissionais

    Args:
        apenas_ativos: Se True, lista apenas ativos
        business_type: Filtrar por tipo de negócio (clinica, infoprodutor, etc)

    Returns:
        Lista de profissionais
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        query = """
            SELECT id, nome, especialidade, cargo, business_type, ativo, created_at
            FROM profissionais
            WHERE 1=1
        """
        params = []
        param_count = 0

        if apenas_ativos:
            query += " AND ativo = true"

        if business_type:
            param_count += 1
            query += f" AND business_type = ${param_count}"
            params.append(business_type)

        query += " ORDER BY nome"

        rows = await conn.fetch(query, *params)
        return [dict(row) for row in rows]


async def agenda_atualizar_profissional(
    profissional_id: int,
    nome: str = None,
    especialidade: str = None,
    cargo: str = None,
    ativo: bool = None
) -> bool:
    """
    Atualiza um profissional

    Args:
        profissional_id: ID do profissional
        nome: Novo nome
        especialidade: Nova especialidade
        cargo: Novo cargo
        ativo: Status ativo

    Returns:
        True se atualizou com sucesso
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        current = await conn.fetchrow(
            "SELECT * FROM profissionais WHERE id = $1",
            profissional_id
        )
        if not current:
            return False

        await conn.execute("""
            UPDATE profissionais
            SET nome = $1, especialidade = $2, cargo = $3, ativo = $4, updated_at = NOW()
            WHERE id = $5
        """,
            nome or current["nome"],
            especialidade if especialidade is not None else current["especialidade"],
            cargo if cargo is not None else current["cargo"],
            ativo if ativo is not None else current["ativo"],
            profissional_id
        )
        return True


async def agenda_deletar_profissional(profissional_id: int) -> bool:
    """
    Desativa um profissional (soft delete)

    Args:
        profissional_id: ID do profissional

    Returns:
        True se desativou com sucesso
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        result = await conn.execute("""
            UPDATE profissionais SET ativo = false, updated_at = NOW()
            WHERE id = $1
        """, profissional_id)
        return "UPDATE 1" in result


# --- Agendamentos ---

async def agenda_verificar_conflito(
    profissional_id: int,
    data_hora: datetime,
    duracao_minutos: int = 30,
    excluir_id: int = None
) -> Optional[dict]:
    """
    Verifica se ha conflito de horario

    Args:
        profissional_id: ID do profissional
        data_hora: Data e hora do agendamento
        duracao_minutos: Duracao em minutos
        excluir_id: ID de agendamento para excluir da verificacao

    Returns:
        Dados do conflito ou None
    """
    pool = await db_get_pool()
    fim = data_hora + timedelta(minutes=duracao_minutos)

    async with pool.acquire() as conn:
        query = """
            SELECT id, paciente_nome, data_hora, duracao_minutos
            FROM agendamentos
            WHERE profissional_id = $1
            AND status != 'cancelado'
            AND (
                (data_hora <= $2 AND data_hora + (duracao_minutos || ' minutes')::interval > $2)
                OR (data_hora < $3 AND data_hora + (duracao_minutos || ' minutes')::interval >= $3)
                OR (data_hora >= $2 AND data_hora + (duracao_minutos || ' minutes')::interval <= $3)
            )
        """
        params = [profissional_id, data_hora, fim]

        if excluir_id:
            query += " AND id != $4"
            params.append(excluir_id)

        row = await conn.fetchrow(query, *params)
        return dict(row) if row else None


async def agenda_criar_agendamento(
    profissional_id: int,
    paciente_nome: str,
    data_hora: datetime,
    paciente_telefone: str = None,
    paciente_nascimento: date = None,
    duracao_minutos: int = 30,
    observacoes: str = None,
    conversation_id: str = None
) -> dict:
    """
    Cria um novo agendamento

    Args:
        profissional_id: ID do profissional
        paciente_nome: Nome do paciente
        data_hora: Data e hora do agendamento
        paciente_telefone: Telefone do paciente
        paciente_nascimento: Data de nascimento
        duracao_minutos: Duracao em minutos
        observacoes: Observacoes
        conversation_id: ID da conversa no Chatwoot

    Returns:
        Dicionario com ID ou erro
    """
    # Verifica conflitos
    conflito = await agenda_verificar_conflito(
        profissional_id, data_hora, duracao_minutos
    )
    if conflito:
        return {"error": "Horario ja ocupado", "conflito": conflito}

    pool = await db_get_pool()

    async with pool.acquire() as conn:
        result = await conn.fetchrow("""
            INSERT INTO agendamentos
            (profissional_id, paciente_nome, paciente_telefone, paciente_nascimento,
             data_hora, duracao_minutos, observacoes, conversation_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
        """,
            profissional_id, paciente_nome, paciente_telefone, paciente_nascimento,
            data_hora, duracao_minutos, observacoes, conversation_id
        )
        return {"id": result["id"], "message": "Agendamento criado com sucesso"}


async def agenda_buscar_agendamento(agendamento_id: int) -> Optional[dict]:
    """
    Busca um agendamento pelo ID

    Args:
        agendamento_id: ID do agendamento

    Returns:
        Dados do agendamento ou None
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT a.*, p.nome as profissional_nome, p.especialidade
            FROM agendamentos a
            JOIN profissionais p ON a.profissional_id = p.id
            WHERE a.id = $1
        """, agendamento_id)
        return dict(row) if row else None


async def agenda_buscar_por_telefone(
    telefone: str,
    apenas_futuros: bool = True
) -> List[dict]:
    """
    Busca agendamentos pelo telefone do paciente

    Args:
        telefone: Telefone do paciente
        apenas_futuros: Se True, busca apenas futuros

    Returns:
        Lista de agendamentos
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        if apenas_futuros:
            rows = await conn.fetch("""
                SELECT a.*, p.nome as profissional_nome, p.especialidade
                FROM agendamentos a
                JOIN profissionais p ON a.profissional_id = p.id
                WHERE a.paciente_telefone = $1
                AND a.data_hora >= NOW()
                AND a.status != 'cancelado'
                ORDER BY a.data_hora
            """, telefone)
        else:
            rows = await conn.fetch("""
                SELECT a.*, p.nome as profissional_nome, p.especialidade
                FROM agendamentos a
                JOIN profissionais p ON a.profissional_id = p.id
                WHERE a.paciente_telefone = $1
                ORDER BY a.data_hora DESC
            """, telefone)
        return [dict(row) for row in rows]


async def agenda_listar_agendamentos(
    profissional_id: int = None,
    data_inicio: datetime = None,
    data_fim: datetime = None,
    status: str = None
) -> List[dict]:
    """
    Lista agendamentos com filtros

    Args:
        profissional_id: Filtrar por profissional
        data_inicio: Data inicial
        data_fim: Data final
        status: Filtrar por status

    Returns:
        Lista de agendamentos
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        query = """
            SELECT a.*, p.nome as profissional_nome, p.especialidade
            FROM agendamentos a
            JOIN profissionais p ON a.profissional_id = p.id
            WHERE 1=1
        """
        params = []
        param_count = 0

        if profissional_id:
            param_count += 1
            query += f" AND a.profissional_id = ${param_count}"
            params.append(profissional_id)

        if data_inicio:
            param_count += 1
            query += f" AND a.data_hora >= ${param_count}"
            params.append(data_inicio)

        if data_fim:
            param_count += 1
            query += f" AND a.data_hora <= ${param_count}"
            params.append(data_fim)

        if status:
            param_count += 1
            query += f" AND a.status = ${param_count}"
            params.append(status)

        query += " ORDER BY a.data_hora"

        rows = await conn.fetch(query, *params)
        return [dict(row) for row in rows]


async def agenda_atualizar_agendamento(
    agendamento_id: int,
    data_hora: datetime = None,
    duracao_minutos: int = None,
    status: str = None,
    confirmado: bool = None,
    observacoes: str = None
) -> dict:
    """
    Atualiza um agendamento

    Args:
        agendamento_id: ID do agendamento
        data_hora: Nova data/hora
        duracao_minutos: Nova duracao
        status: Novo status
        confirmado: Status de confirmacao
        observacoes: Novas observacoes

    Returns:
        Dicionario com mensagem ou erro
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        current = await conn.fetchrow(
            "SELECT * FROM agendamentos WHERE id = $1",
            agendamento_id
        )
        if not current:
            return {"error": "Agendamento nao encontrado"}

        # Verifica conflito se mudou horario
        if data_hora and data_hora != current["data_hora"]:
            conflito = await agenda_verificar_conflito(
                current["profissional_id"],
                data_hora,
                duracao_minutos or current["duracao_minutos"],
                excluir_id=agendamento_id
            )
            if conflito:
                return {"error": "Horario ja ocupado", "conflito": conflito}

        await conn.execute("""
            UPDATE agendamentos
            SET data_hora = $1, duracao_minutos = $2, status = $3,
                confirmado = $4, observacoes = $5, updated_at = NOW()
            WHERE id = $6
        """,
            data_hora or current["data_hora"],
            duracao_minutos or current["duracao_minutos"],
            status or current["status"],
            confirmado if confirmado is not None else current["confirmado"],
            observacoes if observacoes is not None else current["observacoes"],
            agendamento_id
        )
        return {"message": "Agendamento atualizado com sucesso"}


async def agenda_cancelar_agendamento(agendamento_id: int) -> bool:
    """
    Cancela um agendamento

    Args:
        agendamento_id: ID do agendamento

    Returns:
        True se cancelou com sucesso
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        result = await conn.execute("""
            UPDATE agendamentos
            SET status = 'cancelado', updated_at = NOW()
            WHERE id = $1
        """, agendamento_id)
        return "UPDATE 1" in result


async def agenda_confirmar_agendamento(agendamento_id: int) -> bool:
    """
    Confirma um agendamento

    Args:
        agendamento_id: ID do agendamento

    Returns:
        True se confirmou com sucesso
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        result = await conn.execute("""
            UPDATE agendamentos
            SET confirmado = true, status = 'confirmado', updated_at = NOW()
            WHERE id = $1
        """, agendamento_id)
        return "UPDATE 1" in result


async def agenda_buscar_horarios_disponiveis(
    profissional_id: int,
    data: date,
    hora_inicio: time = time(8, 0),
    hora_fim: time = time(18, 0),
    duracao_minutos: int = 30
) -> List[str]:
    """
    Retorna horarios disponiveis para agendamento

    Args:
        profissional_id: ID do profissional
        data: Data para buscar
        hora_inicio: Hora de inicio do expediente
        hora_fim: Hora de fim do expediente
        duracao_minutos: Duracao de cada slot

    Returns:
        Lista de horarios disponiveis (formato HH:MM)
    """
    # Busca agendamentos do dia
    inicio = datetime.combine(data, hora_inicio)
    fim = datetime.combine(data, hora_fim)

    agendamentos = await agenda_listar_agendamentos(
        profissional_id=profissional_id,
        data_inicio=inicio,
        data_fim=fim
    )

    # Gera todos os slots
    slots = []
    current = inicio
    while current < fim:
        slots.append(current)
        current += timedelta(minutes=duracao_minutos)

    # Remove slots ocupados
    ocupados = set()
    for ag in agendamentos:
        if ag["status"] != "cancelado":
            ag_inicio = ag["data_hora"]
            ag_fim = ag_inicio + timedelta(minutes=ag["duracao_minutos"])
            for slot in slots:
                slot_fim = slot + timedelta(minutes=duracao_minutos)
                if not (slot_fim <= ag_inicio or slot >= ag_fim):
                    ocupados.add(slot)

    disponiveis = [s.strftime("%H:%M") for s in slots if s not in ocupados]
    return disponiveis


# --- Prompts ---

async def agenda_salvar_prompt(
    nome: str,
    conteudo: str,
    descricao: str = None
) -> int:
    """
    Salva ou atualiza um prompt

    Args:
        nome: Nome do prompt
        conteudo: Conteudo do prompt
        descricao: Descricao

    Returns:
        ID do prompt
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        result = await conn.fetchrow("""
            INSERT INTO prompts_config (nome, conteudo, descricao)
            VALUES ($1, $2, $3)
            ON CONFLICT (nome) DO UPDATE
            SET conteudo = $2, descricao = $3, updated_at = NOW()
            RETURNING id
        """, nome, conteudo, descricao)
        return result["id"]


async def agenda_obter_prompt(nome: str) -> Optional[dict]:
    """
    Obtem um prompt pelo nome

    Args:
        nome: Nome do prompt

    Returns:
        Dados do prompt ou None
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT * FROM prompts_config WHERE nome = $1
        """, nome)
        return dict(row) if row else None


async def agenda_listar_prompts() -> List[dict]:
    """
    Lista todos os prompts

    Returns:
        Lista de prompts
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM prompts_config ORDER BY nome
        """)
        return [dict(row) for row in rows]


async def agenda_deletar_prompt(nome: str) -> bool:
    """
    Remove um prompt

    Args:
        nome: Nome do prompt

    Returns:
        True se removeu com sucesso
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        result = await conn.execute("""
            DELETE FROM prompts_config WHERE nome = $1
        """, nome)
        return "DELETE 1" in result


# --- Configuracoes do Sistema ---

# Configuracoes padrao
DEFAULT_CONFIGS = {
    "message_buffer_seconds": {
        "value": "10",
        "type": "integer",
        "description": "Tempo de espera (em segundos) para agrupar mensagens encavaladas"
    },
    "context_window_length": {
        "value": "50",
        "type": "integer",
        "description": "Numero maximo de mensagens no historico de contexto"
    }
}


async def config_obter(chave: str, default: str = None) -> Optional[str]:
    """
    Obtem uma configuracao pelo nome

    Args:
        chave: Nome da configuracao
        default: Valor padrao se nao existir

    Returns:
        Valor da configuracao ou default
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT value FROM system_config WHERE key = $1
        """, chave)

        if row:
            return row["value"]

        # Retorna default da lista de defaults ou o parametro
        if chave in DEFAULT_CONFIGS:
            return DEFAULT_CONFIGS[chave]["value"]
        return default


async def config_obter_int(chave: str, default: int = 0) -> int:
    """
    Obtem uma configuracao como inteiro

    Args:
        chave: Nome da configuracao
        default: Valor padrao se nao existir

    Returns:
        Valor da configuracao como int
    """
    valor = await config_obter(chave)
    if valor is None:
        return default
    try:
        return int(valor)
    except ValueError:
        return default


async def config_salvar(
    chave: str,
    valor: str,
    tipo: str = "string",
    descricao: str = None
) -> int:
    """
    Salva ou atualiza uma configuracao

    Args:
        chave: Nome da configuracao
        valor: Valor da configuracao
        tipo: Tipo (string, integer, boolean, float)
        descricao: Descricao da configuracao

    Returns:
        ID da configuracao
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        result = await conn.fetchrow("""
            INSERT INTO system_config (key, value, type, description)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (key) DO UPDATE
            SET value = $2, type = $3, description = COALESCE($4, system_config.description), updated_at = NOW()
            RETURNING id
        """, chave, valor, tipo, descricao)
        return result["id"]


async def config_listar() -> List[dict]:
    """
    Lista todas as configuracoes

    Returns:
        Lista de configuracoes
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, key as chave, value as valor, type as tipo, description as descricao, created_at, updated_at
            FROM system_config ORDER BY key
        """)
        configs = [dict(row) for row in rows]

        # Adiciona defaults que nao estao no banco
        chaves_existentes = {c["chave"] for c in configs}
        for chave, dados in DEFAULT_CONFIGS.items():
            if chave not in chaves_existentes:
                configs.append({
                    "id": None,
                    "chave": chave,
                    "valor": dados["value"],
                    "tipo": dados["type"],
                    "descricao": dados["description"],
                    "is_default": True
                })

        return sorted(configs, key=lambda x: x["chave"])


async def config_deletar(chave: str) -> bool:
    """
    Remove uma configuracao (volta para o default)

    Args:
        chave: Nome da configuracao

    Returns:
        True se removeu com sucesso
    """
    pool = await db_get_pool()

    async with pool.acquire() as conn:
        result = await conn.execute("""
            DELETE FROM system_config WHERE key = $1
        """, chave)
        return "DELETE 1" in result


# --- Compatibilidade (para transicao gradual) ---

class AgendaService:
    """Classe de compatibilidade - usar funcoes diretamente"""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self, pool: asyncpg.Pool):
        self.pool = pool

    async def init_tables(self):
        await agenda_init_tables()

    # Profissionais
    async def criar_profissional(self, nome: str, especialidade: str = None, cargo: str = None, business_type: str = "clinica") -> int:
        return await agenda_criar_profissional(nome, especialidade, cargo, business_type)

    async def listar_profissionais(self, apenas_ativos: bool = True, business_type: str = None) -> List[dict]:
        return await agenda_listar_profissionais(apenas_ativos, business_type)

    async def atualizar_profissional(self, profissional_id: int, nome: str = None, especialidade: str = None, cargo: str = None, ativo: bool = None) -> bool:
        return await agenda_atualizar_profissional(profissional_id, nome, especialidade, cargo, ativo)

    async def deletar_profissional(self, profissional_id: int) -> bool:
        return await agenda_deletar_profissional(profissional_id)

    # Agendamentos
    async def criar_agendamento(self, profissional_id: int, paciente_nome: str, data_hora: datetime, paciente_telefone: str = None, paciente_nascimento: date = None, duracao_minutos: int = 30, observacoes: str = None, conversation_id: str = None) -> dict:
        return await agenda_criar_agendamento(profissional_id, paciente_nome, data_hora, paciente_telefone, paciente_nascimento, duracao_minutos, observacoes, conversation_id)

    async def verificar_conflito(self, profissional_id: int, data_hora: datetime, duracao_minutos: int = 30, excluir_id: int = None) -> dict:
        return await agenda_verificar_conflito(profissional_id, data_hora, duracao_minutos, excluir_id)

    async def buscar_agendamento(self, agendamento_id: int) -> dict:
        return await agenda_buscar_agendamento(agendamento_id)

    async def buscar_agendamentos_por_telefone(self, telefone: str, apenas_futuros: bool = True) -> List[dict]:
        return await agenda_buscar_por_telefone(telefone, apenas_futuros)

    async def listar_agendamentos(self, profissional_id: int = None, data_inicio: datetime = None, data_fim: datetime = None, status: str = None) -> List[dict]:
        return await agenda_listar_agendamentos(profissional_id, data_inicio, data_fim, status)

    async def atualizar_agendamento(self, agendamento_id: int, data_hora: datetime = None, duracao_minutos: int = None, status: str = None, confirmado: bool = None, observacoes: str = None) -> dict:
        return await agenda_atualizar_agendamento(agendamento_id, data_hora, duracao_minutos, status, confirmado, observacoes)

    async def cancelar_agendamento(self, agendamento_id: int) -> bool:
        return await agenda_cancelar_agendamento(agendamento_id)

    async def confirmar_agendamento(self, agendamento_id: int) -> bool:
        return await agenda_confirmar_agendamento(agendamento_id)

    async def buscar_horarios_disponiveis(self, profissional_id: int, data: date, hora_inicio: time = time(8, 0), hora_fim: time = time(18, 0), duracao_minutos: int = 30) -> List[str]:
        return await agenda_buscar_horarios_disponiveis(profissional_id, data, hora_inicio, hora_fim, duracao_minutos)

    # Prompts
    async def salvar_prompt(self, nome: str, conteudo: str, descricao: str = None) -> int:
        return await agenda_salvar_prompt(nome, conteudo, descricao)

    async def obter_prompt(self, nome: str) -> dict:
        return await agenda_obter_prompt(nome)

    async def listar_prompts(self) -> List[dict]:
        return await agenda_listar_prompts()

    async def deletar_prompt(self, nome: str) -> bool:
        return await agenda_deletar_prompt(nome)

    # Configuracoes do Sistema
    async def config_obter(self, chave: str, default: str = None) -> str:
        return await config_obter(chave, default)

    async def config_obter_int(self, chave: str, default: int = 0) -> int:
        return await config_obter_int(chave, default)

    async def config_salvar(self, chave: str, valor: str, tipo: str = "string", descricao: str = None) -> int:
        return await config_salvar(chave, valor, tipo, descricao)

    async def config_listar(self) -> List[dict]:
        return await config_listar()

    async def config_deletar(self, chave: str) -> bool:
        return await config_deletar(chave)


# Instancia global para compatibilidade
agenda_service = AgendaService()


async def get_agenda_service(pool: asyncpg.Pool) -> AgendaService:
    """Retorna o servico de agenda conectado"""
    if agenda_service.pool is None:
        await agenda_service.connect(pool)
        await agenda_service.init_tables()
    return agenda_service
