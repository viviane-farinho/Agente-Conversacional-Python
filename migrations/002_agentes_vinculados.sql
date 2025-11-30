-- Migração: Agentes Vinculados (Agentes Independentes que podem ser chamados por outros)
-- Data: 2025-11-30
-- Descrição: Permite que agentes funcionem independentemente OU como sub-agentes de outros

-- =============================================
-- NOVOS CAMPOS NA TABELA agentes
-- =============================================

-- Adiciona campo para indicar se o agente pode ser usado como sub-agente por outros
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'agentes' AND column_name = 'pode_ser_vinculado') THEN
        ALTER TABLE agentes ADD COLUMN pode_ser_vinculado BOOLEAN DEFAULT false;
        COMMENT ON COLUMN agentes.pode_ser_vinculado IS 'Se true, este agente pode ser vinculado/chamado por outros agentes';
    END IF;
END $$;

-- Adiciona campo para tipo/especialidade do agente (usado no roteamento)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'agentes' AND column_name = 'tipo') THEN
        ALTER TABLE agentes ADD COLUMN tipo VARCHAR(50) DEFAULT 'principal';
        COMMENT ON COLUMN agentes.tipo IS 'Tipo do agente: principal, financeiro, suporte, agendamento, etc';
    END IF;
END $$;

-- Adiciona campo para condição de ativação (palavras-chave)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'agentes' AND column_name = 'condicao_ativacao') THEN
        ALTER TABLE agentes ADD COLUMN condicao_ativacao TEXT;
        COMMENT ON COLUMN agentes.condicao_ativacao IS 'Palavras-chave que ativam este agente quando vinculado';
    END IF;
END $$;

-- Adiciona campo para ferramentas permitidas
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'agentes' AND column_name = 'ferramentas') THEN
        ALTER TABLE agentes ADD COLUMN ferramentas JSONB DEFAULT '[]';
        COMMENT ON COLUMN agentes.ferramentas IS 'Lista de ferramentas habilitadas para este agente';
    END IF;
END $$;

-- Adiciona campo para prioridade (usado no roteamento)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'agentes' AND column_name = 'prioridade') THEN
        ALTER TABLE agentes ADD COLUMN prioridade INTEGER DEFAULT 0;
        COMMENT ON COLUMN agentes.prioridade IS 'Prioridade no roteamento (maior = avaliado primeiro)';
    END IF;
END $$;

-- =============================================
-- TABELA: agentes_vinculados (Relacionamento N:N)
-- =============================================
CREATE TABLE IF NOT EXISTS agentes_vinculados (
    id SERIAL PRIMARY KEY,
    -- Agente que faz a chamada (ex: Secretária)
    agente_principal_id INTEGER NOT NULL REFERENCES agentes(id) ON DELETE CASCADE,
    -- Agente que é chamado (ex: Financeiro)
    agente_vinculado_id INTEGER NOT NULL REFERENCES agentes(id) ON DELETE CASCADE,
    -- Configurações da vinculação
    condicao_ativacao TEXT,  -- Sobrescreve a condição do agente vinculado (opcional)
    prioridade INTEGER DEFAULT 0,  -- Prioridade específica desta vinculação
    -- Comportamento
    modo_transferencia VARCHAR(20) DEFAULT 'interno',  -- 'interno' (mesmo chat) ou 'externo' (transfere conversa)
    manter_contexto BOOLEAN DEFAULT true,  -- Se deve passar o histórico da conversa
    -- Status
    ativo BOOLEAN DEFAULT true,
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    -- Constraints
    UNIQUE(agente_principal_id, agente_vinculado_id)
);

-- Comentários
COMMENT ON TABLE agentes_vinculados IS 'Relacionamento entre agentes - permite que um agente chame outro';
COMMENT ON COLUMN agentes_vinculados.modo_transferencia IS 'interno: processa no mesmo chat | externo: transfere para WhatsApp do agente';
COMMENT ON COLUMN agentes_vinculados.manter_contexto IS 'Se true, passa o histórico da conversa para o agente vinculado';

-- =============================================
-- TABELA: transferencias_agente (Log de transferências)
-- =============================================
CREATE TABLE IF NOT EXISTS transferencias_agente (
    id SERIAL PRIMARY KEY,
    -- Contexto
    tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE,
    conversation_id VARCHAR(100),
    telefone VARCHAR(50),
    -- Agentes envolvidos
    agente_origem_id INTEGER REFERENCES agentes(id) ON DELETE SET NULL,
    agente_destino_id INTEGER REFERENCES agentes(id) ON DELETE SET NULL,
    -- Detalhes
    motivo TEXT,  -- Por que foi transferido
    contexto_transferido JSONB,  -- Resumo do contexto passado
    modo VARCHAR(20),  -- 'interno' ou 'externo'
    -- Status
    status VARCHAR(20) DEFAULT 'pendente',  -- pendente, aceito, concluido, falhou
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
);

COMMENT ON TABLE transferencias_agente IS 'Log de todas as transferências entre agentes';

-- =============================================
-- ÍNDICES
-- =============================================
CREATE INDEX IF NOT EXISTS idx_agentes_vinculados_principal ON agentes_vinculados(agente_principal_id);
CREATE INDEX IF NOT EXISTS idx_agentes_vinculados_vinculado ON agentes_vinculados(agente_vinculado_id);
CREATE INDEX IF NOT EXISTS idx_agentes_tipo ON agentes(tipo);
CREATE INDEX IF NOT EXISTS idx_agentes_pode_vincular ON agentes(pode_ser_vinculado) WHERE pode_ser_vinculado = true;
CREATE INDEX IF NOT EXISTS idx_transferencias_conversation ON transferencias_agente(conversation_id);
CREATE INDEX IF NOT EXISTS idx_transferencias_tenant ON transferencias_agente(tenant_id);

-- =============================================
-- VIEW: agentes_com_vinculacoes
-- =============================================
CREATE OR REPLACE VIEW agentes_com_vinculacoes AS
SELECT
    a.*,
    COALESCE(
        (SELECT json_agg(json_build_object(
            'id', av.id,
            'agente_id', av.agente_vinculado_id,
            'agente_nome', a2.nome,
            'agente_tipo', a2.tipo,
            'condicao_ativacao', COALESCE(av.condicao_ativacao, a2.condicao_ativacao),
            'prioridade', COALESCE(av.prioridade, a2.prioridade),
            'modo_transferencia', av.modo_transferencia,
            'manter_contexto', av.manter_contexto
        ) ORDER BY COALESCE(av.prioridade, a2.prioridade) DESC)
        FROM agentes_vinculados av
        JOIN agentes a2 ON av.agente_vinculado_id = a2.id
        WHERE av.agente_principal_id = a.id AND av.ativo = true AND a2.ativo = true
        ), '[]'::json
    ) as agentes_vinculados
FROM agentes a;

-- =============================================
-- FUNÇÃO: buscar_agente_vinculado_por_intencao
-- =============================================
CREATE OR REPLACE FUNCTION buscar_agente_vinculado_por_intencao(
    p_agente_principal_id INTEGER,
    p_intencao TEXT
) RETURNS TABLE (
    agente_id INTEGER,
    agente_nome VARCHAR,
    agente_tipo VARCHAR,
    system_prompt TEXT,
    ferramentas JSONB,
    modo_transferencia VARCHAR,
    manter_contexto BOOLEAN,
    prioridade INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        a.id as agente_id,
        a.nome as agente_nome,
        a.tipo as agente_tipo,
        a.system_prompt,
        a.ferramentas,
        av.modo_transferencia,
        av.manter_contexto,
        COALESCE(av.prioridade, a.prioridade) as prioridade
    FROM agentes_vinculados av
    JOIN agentes a ON av.agente_vinculado_id = a.id
    WHERE av.agente_principal_id = p_agente_principal_id
      AND av.ativo = true
      AND a.ativo = true
      AND (
          -- Verifica se a intenção corresponde à condição de ativação
          COALESCE(av.condicao_ativacao, a.condicao_ativacao) IS NULL
          OR p_intencao ILIKE '%' || ANY(string_to_array(COALESCE(av.condicao_ativacao, a.condicao_ativacao), ',')) || '%'
      )
    ORDER BY COALESCE(av.prioridade, a.prioridade) DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;
