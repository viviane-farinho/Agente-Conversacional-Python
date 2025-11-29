"""
Serviço de Multi-tenant
Gerencia tenants, agentes e sub-agentes
"""
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
import json

from src.services.database import get_db_service


@dataclass
class SubAgente:
    """Representa um sub-agente especializado"""
    id: int
    agente_id: int
    nome: str
    tipo: str
    descricao: Optional[str] = None
    system_prompt: Optional[str] = None
    ferramentas: List[str] = field(default_factory=list)
    condicao_ativacao: Optional[str] = None
    prioridade: int = 0
    ativo: bool = True


@dataclass
class Agente:
    """Representa um agente de atendimento"""
    id: int
    tenant_id: int
    nome: str
    descricao: Optional[str] = None
    chatwoot_account_id: Optional[str] = None
    chatwoot_inbox_id: Optional[str] = None
    system_prompt: Optional[str] = None
    modelo_llm: str = "google/gemini-2.0-flash-001"
    temperatura: float = 0.7
    max_tokens: int = 4096
    info_empresa: Dict[str, Any] = field(default_factory=dict)
    ativo: bool = True
    sub_agentes: List[SubAgente] = field(default_factory=list)


@dataclass
class Tenant:
    """Representa um tenant (empresa/clínica)"""
    id: int
    nome: str
    slug: str
    email: Optional[str] = None
    telefone: Optional[str] = None
    endereco: Optional[str] = None
    logo_url: Optional[str] = None
    plano: str = "basico"
    ativo: bool = True
    chatwoot_url: Optional[str] = None
    chatwoot_api_token: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    agentes: List[Agente] = field(default_factory=list)


class TenantService:
    """Serviço para gerenciamento de multi-tenant"""

    # Cache de agentes por chatwoot_account_id
    _agent_cache: Dict[str, Agente] = {}

    async def run_migrations(self):
        """Executa as migrações do banco de dados"""
        import os
        db = await get_db_service()

        migrations_dir = os.path.join(os.path.dirname(__file__), "..", "..", "migrations")
        migration_file = os.path.join(migrations_dir, "001_multi_tenant.sql")

        if os.path.exists(migration_file):
            with open(migration_file, "r") as f:
                sql = f.read()

            async with db.pool.acquire() as conn:
                # Executa a migração
                await conn.execute(sql)
            print("[TenantService] Migrações executadas com sucesso")
        else:
            print(f"[TenantService] Arquivo de migração não encontrado: {migration_file}")

    # =============================================
    # TENANT CRUD
    # =============================================

    async def criar_tenant(
        self,
        nome: str,
        slug: str,
        email: str = None,
        telefone: str = None,
        endereco: str = None,
        plano: str = "basico",
        chatwoot_url: str = None,
        chatwoot_api_token: str = None,
        telegram_bot_token: str = None,
        telegram_chat_id: str = None
    ) -> Tenant:
        """Cria um novo tenant"""
        db = await get_db_service()
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO tenants (nome, slug, email, telefone, endereco, plano,
                    chatwoot_url, chatwoot_api_token, telegram_bot_token, telegram_chat_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING *
            """, nome, slug, email, telefone, endereco, plano,
                chatwoot_url, chatwoot_api_token, telegram_bot_token, telegram_chat_id)

            return self._row_to_tenant(row)

    async def buscar_tenant(self, tenant_id: int) -> Optional[Tenant]:
        """Busca um tenant por ID"""
        db = await get_db_service()
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM tenants WHERE id = $1", tenant_id)
            if row:
                tenant = self._row_to_tenant(row)
                tenant.agentes = await self.listar_agentes(tenant_id)
                return tenant
        return None

    async def buscar_tenant_por_slug(self, slug: str) -> Optional[Tenant]:
        """Busca um tenant pelo slug"""
        db = await get_db_service()
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM tenants WHERE slug = $1", slug)
            if row:
                tenant = self._row_to_tenant(row)
                tenant.agentes = await self.listar_agentes(tenant.id)
                return tenant
        return None

    async def listar_tenants(self, apenas_ativos: bool = True) -> List[Tenant]:
        """Lista todos os tenants"""
        db = await get_db_service()
        async with db.pool.acquire() as conn:
            if apenas_ativos:
                rows = await conn.fetch("SELECT * FROM tenants WHERE ativo = true ORDER BY nome")
            else:
                rows = await conn.fetch("SELECT * FROM tenants ORDER BY nome")

            return [self._row_to_tenant(row) for row in rows]

    async def atualizar_tenant(self, tenant_id: int, **kwargs) -> Optional[Tenant]:
        """Atualiza um tenant"""
        db = await get_db_service()
        async with db.pool.acquire() as conn:
            # Constrói a query dinamicamente
            updates = []
            params = []
            i = 1
            for key, value in kwargs.items():
                if value is not None:
                    updates.append(f"{key} = ${i}")
                    params.append(value)
                    i += 1

            if not updates:
                return await self.buscar_tenant(tenant_id)

            params.append(tenant_id)
            query = f"UPDATE tenants SET {', '.join(updates)} WHERE id = ${i} RETURNING *"
            row = await conn.fetchrow(query, *params)

            if row:
                return self._row_to_tenant(row)
        return None

    async def deletar_tenant(self, tenant_id: int) -> bool:
        """Deleta um tenant (e todos seus dados relacionados)"""
        db = await get_db_service()
        async with db.pool.acquire() as conn:
            result = await conn.execute("DELETE FROM tenants WHERE id = $1", tenant_id)
            return result != "DELETE 0"

    # =============================================
    # AGENTE CRUD
    # =============================================

    async def criar_agente(
        self,
        tenant_id: int,
        nome: str,
        descricao: str = None,
        chatwoot_account_id: str = None,
        chatwoot_inbox_id: str = None,
        system_prompt: str = None,
        modelo_llm: str = "google/gemini-2.0-flash-001",
        temperatura: float = 0.7,
        max_tokens: int = 4096,
        info_empresa: Dict = None
    ) -> Agente:
        """Cria um novo agente"""
        db = await get_db_service()
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO agentes (tenant_id, nome, descricao, chatwoot_account_id,
                    chatwoot_inbox_id, system_prompt, modelo_llm, temperatura, max_tokens, info_empresa)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING *
            """, tenant_id, nome, descricao, chatwoot_account_id, chatwoot_inbox_id,
                system_prompt, modelo_llm, temperatura, max_tokens,
                json.dumps(info_empresa or {}))

            # Limpa cache
            self._agent_cache.clear()

            return self._row_to_agente(row)

    async def buscar_agente(self, agente_id: int) -> Optional[Agente]:
        """Busca um agente por ID"""
        db = await get_db_service()
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM agentes WHERE id = $1", agente_id)
            if row:
                agente = self._row_to_agente(row)
                agente.sub_agentes = await self.listar_sub_agentes(agente_id)
                return agente
        return None

    async def buscar_agente_por_chatwoot(
        self,
        account_id: str,
        inbox_id: str = None
    ) -> Optional[Agente]:
        """Busca agente pelo account_id do Chatwoot (usado no webhook)"""
        # Verifica cache primeiro
        cache_key = f"{account_id}:{inbox_id or ''}"
        if cache_key in self._agent_cache:
            return self._agent_cache[cache_key]

        db = await get_db_service()
        async with db.pool.acquire() as conn:
            if inbox_id:
                row = await conn.fetchrow("""
                    SELECT * FROM agentes
                    WHERE chatwoot_account_id = $1 AND chatwoot_inbox_id = $2 AND ativo = true
                """, account_id, inbox_id)
            else:
                row = await conn.fetchrow("""
                    SELECT * FROM agentes
                    WHERE chatwoot_account_id = $1 AND ativo = true
                    LIMIT 1
                """, account_id)

            if row:
                agente = self._row_to_agente(row)
                agente.sub_agentes = await self.listar_sub_agentes(agente.id)
                self._agent_cache[cache_key] = agente
                return agente
        return None

    async def listar_agentes(self, tenant_id: int, apenas_ativos: bool = True) -> List[Agente]:
        """Lista agentes de um tenant"""
        db = await get_db_service()
        async with db.pool.acquire() as conn:
            if apenas_ativos:
                rows = await conn.fetch("""
                    SELECT * FROM agentes WHERE tenant_id = $1 AND ativo = true ORDER BY nome
                """, tenant_id)
            else:
                rows = await conn.fetch("""
                    SELECT * FROM agentes WHERE tenant_id = $1 ORDER BY nome
                """, tenant_id)

            return [self._row_to_agente(row) for row in rows]

    async def atualizar_agente(self, agente_id: int, **kwargs) -> Optional[Agente]:
        """Atualiza um agente"""
        db = await get_db_service()
        async with db.pool.acquire() as conn:
            updates = []
            params = []
            i = 1
            for key, value in kwargs.items():
                if value is not None:
                    if key == "info_empresa":
                        value = json.dumps(value)
                    updates.append(f"{key} = ${i}")
                    params.append(value)
                    i += 1

            if not updates:
                return await self.buscar_agente(agente_id)

            params.append(agente_id)
            query = f"UPDATE agentes SET {', '.join(updates)} WHERE id = ${i} RETURNING *"
            row = await conn.fetchrow(query, *params)

            # Limpa cache
            self._agent_cache.clear()

            if row:
                return self._row_to_agente(row)
        return None

    async def deletar_agente(self, agente_id: int) -> bool:
        """Deleta um agente"""
        db = await get_db_service()
        async with db.pool.acquire() as conn:
            result = await conn.execute("DELETE FROM agentes WHERE id = $1", agente_id)
            self._agent_cache.clear()
            return result != "DELETE 0"

    # =============================================
    # SUB-AGENTE CRUD
    # =============================================

    async def criar_sub_agente(
        self,
        agente_id: int,
        nome: str,
        tipo: str,
        descricao: str = None,
        system_prompt: str = None,
        ferramentas: List[str] = None,
        condicao_ativacao: str = None,
        prioridade: int = 0
    ) -> SubAgente:
        """Cria um novo sub-agente"""
        db = await get_db_service()
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO sub_agentes (agente_id, nome, tipo, descricao, system_prompt,
                    ferramentas, condicao_ativacao, prioridade)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING *
            """, agente_id, nome, tipo, descricao, system_prompt,
                json.dumps(ferramentas or []), condicao_ativacao, prioridade)

            self._agent_cache.clear()
            return self._row_to_sub_agente(row)

    async def listar_sub_agentes(self, agente_id: int, apenas_ativos: bool = True) -> List[SubAgente]:
        """Lista sub-agentes de um agente"""
        db = await get_db_service()
        async with db.pool.acquire() as conn:
            if apenas_ativos:
                rows = await conn.fetch("""
                    SELECT * FROM sub_agentes
                    WHERE agente_id = $1 AND ativo = true
                    ORDER BY prioridade DESC, nome
                """, agente_id)
            else:
                rows = await conn.fetch("""
                    SELECT * FROM sub_agentes WHERE agente_id = $1 ORDER BY prioridade DESC, nome
                """, agente_id)

            return [self._row_to_sub_agente(row) for row in rows]

    async def atualizar_sub_agente(self, sub_agente_id: int, **kwargs) -> Optional[SubAgente]:
        """Atualiza um sub-agente"""
        db = await get_db_service()
        async with db.pool.acquire() as conn:
            updates = []
            params = []
            i = 1
            for key, value in kwargs.items():
                if value is not None:
                    if key == "ferramentas":
                        value = json.dumps(value)
                    updates.append(f"{key} = ${i}")
                    params.append(value)
                    i += 1

            if not updates:
                return None

            params.append(sub_agente_id)
            query = f"UPDATE sub_agentes SET {', '.join(updates)} WHERE id = ${i} RETURNING *"
            row = await conn.fetchrow(query, *params)

            self._agent_cache.clear()
            if row:
                return self._row_to_sub_agente(row)
        return None

    async def deletar_sub_agente(self, sub_agente_id: int) -> bool:
        """Deleta um sub-agente"""
        db = await get_db_service()
        async with db.pool.acquire() as conn:
            result = await conn.execute("DELETE FROM sub_agentes WHERE id = $1", sub_agente_id)
            self._agent_cache.clear()
            return result != "DELETE 0"

    # =============================================
    # RAG DOCUMENTOS
    # =============================================

    async def criar_documento_rag(
        self,
        agente_id: int,
        titulo: str,
        conteudo: str,
        categoria: str = None,
        tags: List[str] = None,
        fonte: str = None
    ) -> Dict:
        """Cria um documento RAG para um agente"""
        db = await get_db_service()
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO rag_documentos (agente_id, titulo, conteudo, categoria, tags, fonte)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id, titulo, categoria, created_at
            """, agente_id, titulo, conteudo, categoria, json.dumps(tags or []), fonte)

            return dict(row)

    async def listar_documentos_rag(self, agente_id: int, categoria: str = None) -> List[Dict]:
        """Lista documentos RAG de um agente"""
        db = await get_db_service()
        async with db.pool.acquire() as conn:
            if categoria:
                rows = await conn.fetch("""
                    SELECT id, titulo, categoria, tags, fonte, created_at
                    FROM rag_documentos
                    WHERE agente_id = $1 AND categoria = $2 AND ativo = true
                    ORDER BY titulo
                """, agente_id, categoria)
            else:
                rows = await conn.fetch("""
                    SELECT id, titulo, categoria, tags, fonte, created_at
                    FROM rag_documentos
                    WHERE agente_id = $1 AND ativo = true
                    ORDER BY categoria, titulo
                """, agente_id)

            return [dict(row) for row in rows]

    async def buscar_documentos_rag(
        self,
        agente_id: int,
        query: str,
        limite: int = 5,
        categoria: str = None
    ) -> List[Dict]:
        """Busca documentos RAG por texto (busca simples por LIKE)"""
        db = await get_db_service()
        async with db.pool.acquire() as conn:
            search_pattern = f"%{query}%"
            if categoria:
                rows = await conn.fetch("""
                    SELECT id, titulo, conteudo, categoria
                    FROM rag_documentos
                    WHERE agente_id = $1
                      AND categoria = $2
                      AND ativo = true
                      AND (titulo ILIKE $3 OR conteudo ILIKE $3)
                    LIMIT $4
                """, agente_id, categoria, search_pattern, limite)
            else:
                rows = await conn.fetch("""
                    SELECT id, titulo, conteudo, categoria
                    FROM rag_documentos
                    WHERE agente_id = $1
                      AND ativo = true
                      AND (titulo ILIKE $2 OR conteudo ILIKE $2)
                    LIMIT $3
                """, agente_id, search_pattern, limite)

            return [dict(row) for row in rows]

    # =============================================
    # HELPERS
    # =============================================

    def _row_to_tenant(self, row) -> Tenant:
        """Converte uma row do banco para Tenant"""
        return Tenant(
            id=row["id"],
            nome=row["nome"],
            slug=row["slug"],
            email=row.get("email"),
            telefone=row.get("telefone"),
            endereco=row.get("endereco"),
            logo_url=row.get("logo_url"),
            plano=row.get("plano", "basico"),
            ativo=row.get("ativo", True),
            chatwoot_url=row.get("chatwoot_url"),
            chatwoot_api_token=row.get("chatwoot_api_token"),
            telegram_bot_token=row.get("telegram_bot_token"),
            telegram_chat_id=row.get("telegram_chat_id")
        )

    def _row_to_agente(self, row) -> Agente:
        """Converte uma row do banco para Agente"""
        info_empresa = row.get("info_empresa") or {}
        if isinstance(info_empresa, str):
            info_empresa = json.loads(info_empresa)

        return Agente(
            id=row["id"],
            tenant_id=row["tenant_id"],
            nome=row["nome"],
            descricao=row.get("descricao"),
            chatwoot_account_id=row.get("chatwoot_account_id"),
            chatwoot_inbox_id=row.get("chatwoot_inbox_id"),
            system_prompt=row.get("system_prompt"),
            modelo_llm=row.get("modelo_llm", "google/gemini-2.0-flash-001"),
            temperatura=row.get("temperatura", 0.7),
            max_tokens=row.get("max_tokens", 4096),
            info_empresa=info_empresa,
            ativo=row.get("ativo", True)
        )

    def _row_to_sub_agente(self, row) -> SubAgente:
        """Converte uma row do banco para SubAgente"""
        ferramentas = row.get("ferramentas") or []
        if isinstance(ferramentas, str):
            ferramentas = json.loads(ferramentas)

        return SubAgente(
            id=row["id"],
            agente_id=row["agente_id"],
            nome=row["nome"],
            tipo=row["tipo"],
            descricao=row.get("descricao"),
            system_prompt=row.get("system_prompt"),
            ferramentas=ferramentas,
            condicao_ativacao=row.get("condicao_ativacao"),
            prioridade=row.get("prioridade", 0),
            ativo=row.get("ativo", True)
        )


# Instância global
tenant_service = TenantService()


async def get_tenant_service() -> TenantService:
    """Retorna a instância do serviço de tenant"""
    return tenant_service
