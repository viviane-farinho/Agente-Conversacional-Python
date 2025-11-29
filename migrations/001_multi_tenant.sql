-- Migração: Multi-tenant + Multi-agente
-- Data: 2025-11-29

-- =============================================
-- TABELA: tenants (Empresas/Clínicas)
-- =============================================
CREATE TABLE IF NOT EXISTS tenants (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    -- Configurações gerais
    email VARCHAR(255),
    telefone VARCHAR(50),
    endereco TEXT,
    logo_url TEXT,
    -- Plano e status
    plano VARCHAR(50) DEFAULT 'basico',  -- basico, profissional, enterprise
    ativo BOOLEAN DEFAULT true,
    -- Configurações de integração (herdadas pelos agentes)
    chatwoot_url VARCHAR(255),
    chatwoot_api_token TEXT,
    telegram_bot_token TEXT,
    telegram_chat_id VARCHAR(100),
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =============================================
-- TABELA: agentes (Agentes de cada tenant)
-- =============================================
CREATE TABLE IF NOT EXISTS agentes (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    nome VARCHAR(255) NOT NULL,
    descricao TEXT,
    -- Identificação no Chatwoot
    chatwoot_account_id VARCHAR(50),
    chatwoot_inbox_id VARCHAR(50),
    -- Configurações do agente
    system_prompt TEXT,
    modelo_llm VARCHAR(100) DEFAULT 'google/gemini-2.0-flash-001',  -- modelo do OpenRouter
    temperatura FLOAT DEFAULT 0.7,
    max_tokens INTEGER DEFAULT 4096,
    -- Informações da empresa (usadas no prompt)
    info_empresa JSONB DEFAULT '{}',  -- nome, endereco, telefone, horarios, etc
    -- Status
    ativo BOOLEAN DEFAULT true,
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =============================================
-- TABELA: sub_agentes (Sub-agentes especializados)
-- =============================================
CREATE TABLE IF NOT EXISTS sub_agentes (
    id SERIAL PRIMARY KEY,
    agente_id INTEGER NOT NULL REFERENCES agentes(id) ON DELETE CASCADE,
    nome VARCHAR(100) NOT NULL,
    tipo VARCHAR(50) NOT NULL,  -- router, agendamento, informacao, cobranca, etc
    descricao TEXT,
    -- Configurações específicas
    system_prompt TEXT,
    ferramentas JSONB DEFAULT '[]',  -- lista de ferramentas habilitadas
    condicao_ativacao TEXT,  -- palavras-chave ou condições para ativar este sub-agente
    prioridade INTEGER DEFAULT 0,  -- ordem de avaliação (maior = primeiro)
    -- Status
    ativo BOOLEAN DEFAULT true,
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =============================================
-- TABELA: rag_documentos (Documentos RAG por agente)
-- =============================================
CREATE TABLE IF NOT EXISTS rag_documentos (
    id SERIAL PRIMARY KEY,
    agente_id INTEGER NOT NULL REFERENCES agentes(id) ON DELETE CASCADE,
    titulo VARCHAR(255) NOT NULL,
    conteudo TEXT NOT NULL,
    categoria VARCHAR(100),
    tags JSONB DEFAULT '[]',
    -- Embedding para busca semântica
    embedding vector(1536),  -- OpenAI ada-002 ou similar
    -- Metadados
    fonte VARCHAR(255),  -- origem do documento
    ativo BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =============================================
-- Migrar tabelas existentes para multi-tenant
-- =============================================

-- Adiciona tenant_id e agente_id nas tabelas existentes (se não existirem)

-- profissionais
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'profissionais' AND column_name = 'tenant_id') THEN
        ALTER TABLE profissionais ADD COLUMN tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'profissionais' AND column_name = 'agente_id') THEN
        ALTER TABLE profissionais ADD COLUMN agente_id INTEGER REFERENCES agentes(id) ON DELETE CASCADE;
    END IF;
END $$;

-- agendamentos
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'agendamentos' AND column_name = 'tenant_id') THEN
        ALTER TABLE agendamentos ADD COLUMN tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'agendamentos' AND column_name = 'agente_id') THEN
        ALTER TABLE agendamentos ADD COLUMN agente_id INTEGER REFERENCES agentes(id) ON DELETE CASCADE;
    END IF;
END $$;

-- pipeline_conversas
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'pipeline_conversas' AND column_name = 'tenant_id') THEN
        ALTER TABLE pipeline_conversas ADD COLUMN tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'pipeline_conversas' AND column_name = 'agente_id') THEN
        ALTER TABLE pipeline_conversas ADD COLUMN agente_id INTEGER REFERENCES agentes(id) ON DELETE CASCADE;
    END IF;
END $$;

-- n8n_historico_mensagens
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'n8n_historico_mensagens' AND column_name = 'tenant_id') THEN
        ALTER TABLE n8n_historico_mensagens ADD COLUMN tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'n8n_historico_mensagens' AND column_name = 'agente_id') THEN
        ALTER TABLE n8n_historico_mensagens ADD COLUMN agente_id INTEGER REFERENCES agentes(id) ON DELETE CASCADE;
    END IF;
END $$;

-- =============================================
-- ÍNDICES para performance
-- =============================================
CREATE INDEX IF NOT EXISTS idx_agentes_tenant ON agentes(tenant_id);
CREATE INDEX IF NOT EXISTS idx_agentes_chatwoot ON agentes(chatwoot_account_id, chatwoot_inbox_id);
CREATE INDEX IF NOT EXISTS idx_sub_agentes_agente ON sub_agentes(agente_id);
CREATE INDEX IF NOT EXISTS idx_rag_docs_agente ON rag_documentos(agente_id);
CREATE INDEX IF NOT EXISTS idx_rag_docs_categoria ON rag_documentos(agente_id, categoria);

-- Índices nas tabelas migradas
CREATE INDEX IF NOT EXISTS idx_profissionais_tenant ON profissionais(tenant_id);
CREATE INDEX IF NOT EXISTS idx_agendamentos_tenant ON agendamentos(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_tenant ON pipeline_conversas(tenant_id);
CREATE INDEX IF NOT EXISTS idx_historico_tenant ON n8n_historico_mensagens(tenant_id);

-- =============================================
-- TRIGGER para atualizar updated_at
-- =============================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_tenants_updated_at') THEN
        CREATE TRIGGER update_tenants_updated_at BEFORE UPDATE ON tenants
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_agentes_updated_at') THEN
        CREATE TRIGGER update_agentes_updated_at BEFORE UPDATE ON agentes
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_rag_docs_updated_at') THEN
        CREATE TRIGGER update_rag_docs_updated_at BEFORE UPDATE ON rag_documentos
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- =============================================
-- DADOS INICIAIS: Tenant e Agente padrão
-- =============================================
-- Cria tenant padrão se não existir (para migrar dados existentes)
INSERT INTO tenants (nome, slug, plano)
SELECT 'Clínica Padrão', 'clinica-padrao', 'basico'
WHERE NOT EXISTS (SELECT 1 FROM tenants WHERE slug = 'clinica-padrao');

-- Cria agente padrão para o tenant
INSERT INTO agentes (tenant_id, nome, descricao, modelo_llm)
SELECT
    (SELECT id FROM tenants WHERE slug = 'clinica-padrao'),
    'Secretária IA',
    'Agente principal de atendimento',
    'google/gemini-2.0-flash-001'
WHERE NOT EXISTS (
    SELECT 1 FROM agentes WHERE tenant_id = (SELECT id FROM tenants WHERE slug = 'clinica-padrao')
);

-- Atualiza registros existentes sem tenant_id para usar o tenant padrão
UPDATE profissionais SET tenant_id = (SELECT id FROM tenants WHERE slug = 'clinica-padrao') WHERE tenant_id IS NULL;
UPDATE agendamentos SET tenant_id = (SELECT id FROM tenants WHERE slug = 'clinica-padrao') WHERE tenant_id IS NULL;
UPDATE pipeline_conversas SET tenant_id = (SELECT id FROM tenants WHERE slug = 'clinica-padrao') WHERE tenant_id IS NULL;
UPDATE n8n_historico_mensagens SET tenant_id = (SELECT id FROM tenants WHERE slug = 'clinica-padrao') WHERE tenant_id IS NULL;

-- Atualiza agente_id também
UPDATE profissionais SET agente_id = (SELECT id FROM agentes WHERE tenant_id = (SELECT id FROM tenants WHERE slug = 'clinica-padrao') LIMIT 1) WHERE agente_id IS NULL;
UPDATE agendamentos SET agente_id = (SELECT id FROM agentes WHERE tenant_id = (SELECT id FROM tenants WHERE slug = 'clinica-padrao') LIMIT 1) WHERE agente_id IS NULL;
UPDATE pipeline_conversas SET agente_id = (SELECT id FROM agentes WHERE tenant_id = (SELECT id FROM tenants WHERE slug = 'clinica-padrao') LIMIT 1) WHERE agente_id IS NULL;
UPDATE n8n_historico_mensagens SET agente_id = (SELECT id FROM agentes WHERE tenant_id = (SELECT id FROM tenants WHERE slug = 'clinica-padrao') LIMIT 1) WHERE agente_id IS NULL;
