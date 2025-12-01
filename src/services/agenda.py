"""
Serviço de Agenda
Gerencia agendamentos no banco de dados (substitui Google Calendar)
"""
from datetime import datetime, date, time, timedelta
from typing import Optional, List
import json
import asyncpg

from src.config import Config


class AgendaService:
    """Serviço para gerenciamento de agenda no banco de dados"""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self, pool: asyncpg.Pool):
        """Usa o pool de conexões existente"""
        self.pool = pool

    async def init_tables(self):
        """Cria as tabelas necessárias para a agenda"""
        async with self.pool.acquire() as conn:
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

            # Índices
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

            # Tabela de configuração de prompts
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

    # --- Profissionais ---

    async def criar_profissional(
        self,
        nome: str,
        especialidade: str = None,
        cargo: str = None,
        tenant_id: int = None
    ) -> int:
        """Cria um novo profissional"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow("""
                INSERT INTO profissionais (nome, especialidade, cargo, tenant_id)
                VALUES ($1, $2, $3, $4)
                RETURNING id
            """, nome, especialidade, cargo, tenant_id)
            return result["id"]

    async def listar_profissionais(
        self,
        apenas_ativos: bool = True,
        tenant_id: int = None,
        apenas_admin: bool = False
    ) -> List[dict]:
        """
        Lista profissionais filtrados por tenant

        Args:
            apenas_ativos: Se True, retorna apenas profissionais ativos
            tenant_id: ID do tenant para filtrar (profissionais do tenant específico)
            apenas_admin: Se True, retorna apenas profissionais do admin (tenant_id IS NULL)
        """
        async with self.pool.acquire() as conn:
            conditions = []
            params = []
            param_num = 1

            if apenas_ativos:
                conditions.append("ativo = true")

            # Filtro por tenant_id
            if apenas_admin:
                # Profissionais do admin (sem tenant)
                conditions.append("tenant_id IS NULL")
            elif tenant_id is not None:
                # Profissionais de um tenant específico
                conditions.append(f"tenant_id = ${param_num}")
                params.append(tenant_id)
                param_num += 1

            query = """
                SELECT id, nome, especialidade, cargo, ativo, created_at, tenant_id
                FROM profissionais
            """
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY nome"

            if params:
                rows = await conn.fetch(query, *params)
            else:
                rows = await conn.fetch(query)
            return [dict(row) for row in rows]

    async def atualizar_profissional(
        self,
        prof_id: int,
        nome: str = None,
        especialidade: str = None,
        cargo: str = None,
        ativo: bool = None,
        tenant_id: int = None,
        apenas_admin: bool = False
    ) -> bool:
        """
        Atualiza um profissional

        Args:
            prof_id: ID do profissional
            nome, especialidade, cargo, ativo: campos a atualizar
            tenant_id: Se especificado, verifica se o profissional pertence ao tenant
            apenas_admin: Se True, só atualiza profissionais do admin (tenant_id IS NULL)
        """
        async with self.pool.acquire() as conn:
            # Verifica se o profissional existe e pertence ao contexto correto
            if apenas_admin:
                current = await conn.fetchrow(
                    "SELECT * FROM profissionais WHERE id = $1 AND tenant_id IS NULL",
                    prof_id
                )
            elif tenant_id is not None:
                current = await conn.fetchrow(
                    "SELECT * FROM profissionais WHERE id = $1 AND tenant_id = $2",
                    prof_id, tenant_id
                )
            else:
                current = await conn.fetchrow(
                    "SELECT * FROM profissionais WHERE id = $1",
                    prof_id
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
                prof_id
            )
            return True

    async def deletar_profissional(self, profissional_id: int, apenas_admin: bool = False) -> bool:
        """Desativa um profissional do admin (soft delete)"""
        async with self.pool.acquire() as conn:
            if apenas_admin:
                result = await conn.execute("""
                    UPDATE profissionais SET ativo = false, updated_at = NOW()
                    WHERE id = $1 AND tenant_id IS NULL
                """, profissional_id)
            else:
                result = await conn.execute("""
                    UPDATE profissionais SET ativo = false, updated_at = NOW()
                    WHERE id = $1
                """, profissional_id)
            return "UPDATE 1" in result

    async def desativar_profissional(self, profissional_id: int, tenant_id: int = None) -> bool:
        """Desativa um profissional (soft delete) verificando tenant"""
        async with self.pool.acquire() as conn:
            if tenant_id is not None:
                # Verifica se pertence ao tenant
                existing = await conn.fetchrow(
                    "SELECT id FROM profissionais WHERE id = $1 AND tenant_id = $2",
                    profissional_id, tenant_id
                )
                if not existing:
                    return False
            result = await conn.execute("""
                UPDATE profissionais SET ativo = false, updated_at = NOW()
                WHERE id = $1
            """, profissional_id)
            return "UPDATE 1" in result

    # --- Agendamentos ---

    async def criar_agendamento(
        self,
        profissional_id: int,
        paciente_nome: str,
        data_hora: datetime,
        paciente_telefone: str = None,
        paciente_nascimento: date = None,
        duracao_minutos: int = 30,
        observacoes: str = None,
        conversation_id: str = None
    ) -> dict:
        """Cria um novo agendamento"""
        # Verifica conflitos
        conflito = await self.verificar_conflito(
            profissional_id, data_hora, duracao_minutos
        )
        if conflito:
            return {"error": "Horário já ocupado", "conflito": conflito}

        async with self.pool.acquire() as conn:
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

    async def verificar_conflito(
        self,
        profissional_id: int,
        data_hora: datetime,
        duracao_minutos: int = 30,
        excluir_id: int = None
    ) -> dict:
        """Verifica se há conflito de horário"""
        fim = data_hora + timedelta(minutes=duracao_minutos)

        async with self.pool.acquire() as conn:
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
            if row:
                return dict(row)
            return None

    async def buscar_agendamento(self, agendamento_id: int) -> dict:
        """Busca um agendamento pelo ID"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT a.*, p.nome as profissional_nome, p.especialidade
                FROM agendamentos a
                JOIN profissionais p ON a.profissional_id = p.id
                WHERE a.id = $1
            """, agendamento_id)
            return dict(row) if row else None

    async def buscar_agendamentos_por_telefone(
        self,
        telefone: str,
        apenas_futuros: bool = True
    ) -> List[dict]:
        """Busca agendamentos pelo telefone do paciente"""
        async with self.pool.acquire() as conn:
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

    async def listar_agendamentos(
        self,
        profissional_id: int = None,
        data_inicio: datetime = None,
        data_fim: datetime = None,
        status: str = None,
        tenant_id: int = None
    ) -> List[dict]:
        """Lista agendamentos com filtros, opcionalmente por tenant"""
        async with self.pool.acquire() as conn:
            query = """
                SELECT a.*, p.nome as profissional_nome, p.especialidade
                FROM agendamentos a
                JOIN profissionais p ON a.profissional_id = p.id
                WHERE 1=1
            """
            params = []
            param_count = 0

            if tenant_id is not None:
                param_count += 1
                query += f" AND a.tenant_id = ${param_count}"
                params.append(tenant_id)

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

    async def atualizar_agendamento(
        self,
        agendamento_id: int,
        data_hora: datetime = None,
        duracao_minutos: int = None,
        status: str = None,
        confirmado: bool = None,
        observacoes: str = None
    ) -> dict:
        """Atualiza um agendamento"""
        async with self.pool.acquire() as conn:
            current = await conn.fetchrow(
                "SELECT * FROM agendamentos WHERE id = $1",
                agendamento_id
            )
            if not current:
                return {"error": "Agendamento não encontrado"}

            # Verifica conflito se mudou horário
            if data_hora and data_hora != current["data_hora"]:
                conflito = await self.verificar_conflito(
                    current["profissional_id"],
                    data_hora,
                    duracao_minutos or current["duracao_minutos"],
                    excluir_id=agendamento_id
                )
                if conflito:
                    return {"error": "Horário já ocupado", "conflito": conflito}

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

    async def cancelar_agendamento(self, agendamento_id: int) -> bool:
        """Cancela um agendamento"""
        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE agendamentos
                SET status = 'cancelado', updated_at = NOW()
                WHERE id = $1
            """, agendamento_id)
            return "UPDATE 1" in result

    async def confirmar_agendamento(self, agendamento_id: int) -> bool:
        """Confirma um agendamento"""
        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                UPDATE agendamentos
                SET confirmado = true, status = 'confirmado', updated_at = NOW()
                WHERE id = $1
            """, agendamento_id)
            return "UPDATE 1" in result

    async def buscar_horarios_disponiveis(
        self,
        profissional_id: int,
        data: date,
        hora_inicio: time = time(8, 0),
        hora_fim: time = time(18, 0),
        duracao_minutos: int = 30,
        tenant_id: int = None
    ) -> List[str]:
        """Retorna horários disponíveis para agendamento"""
        # Busca agendamentos do dia
        inicio = datetime.combine(data, hora_inicio)
        fim = datetime.combine(data, hora_fim)

        agendamentos = await self.listar_agendamentos(
            profissional_id=profissional_id,
            data_inicio=inicio,
            data_fim=fim,
            tenant_id=tenant_id
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

    async def salvar_prompt(
        self,
        nome: str,
        conteudo: str,
        descricao: str = None
    ) -> int:
        """Salva ou atualiza um prompt"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow("""
                INSERT INTO prompts_config (nome, conteudo, descricao)
                VALUES ($1, $2, $3)
                ON CONFLICT (nome) DO UPDATE
                SET conteudo = $2, descricao = $3, updated_at = NOW()
                RETURNING id
            """, nome, conteudo, descricao)
            return result["id"]

    async def obter_prompt(self, nome: str) -> dict:
        """Obtém um prompt pelo nome"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM prompts_config WHERE nome = $1
            """, nome)
            return dict(row) if row else None

    async def listar_prompts(self) -> List[dict]:
        """Lista todos os prompts"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM prompts_config ORDER BY nome
            """)
            return [dict(row) for row in rows]

    async def deletar_prompt(self, nome: str) -> bool:
        """Remove um prompt"""
        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM prompts_config WHERE nome = $1
            """, nome)
            return "DELETE 1" in result


# Instância global
agenda_service = AgendaService()


async def get_agenda_service(pool: asyncpg.Pool) -> AgendaService:
    """Retorna o serviço de agenda conectado"""
    if agenda_service.pool is None:
        await agenda_service.connect(pool)
        await agenda_service.init_tables()
    return agenda_service
