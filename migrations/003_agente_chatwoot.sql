-- =============================================
-- Migration 003: Configurações Chatwoot por Agente
-- =============================================
-- Cada agente precisa ter suas próprias configurações do Chatwoot
-- para receber e enviar mensagens de forma independente

-- Adiciona campos de configuração do Chatwoot na tabela agentes
DO $$
BEGIN
    -- URL do Chatwoot (pode variar por agente se usar instâncias diferentes)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'agentes' AND column_name = 'chatwoot_url') THEN
        ALTER TABLE agentes ADD COLUMN chatwoot_url VARCHAR(255);
    END IF;

    -- Token de API do Chatwoot (para enviar mensagens)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'agentes' AND column_name = 'chatwoot_api_token') THEN
        ALTER TABLE agentes ADD COLUMN chatwoot_api_token TEXT;
    END IF;

    -- Webhook secret para validação (opcional, mas recomendado)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'agentes' AND column_name = 'webhook_secret') THEN
        ALTER TABLE agentes ADD COLUMN webhook_secret VARCHAR(255);
    END IF;
END $$;

-- Comentários para documentação
COMMENT ON COLUMN agentes.chatwoot_url IS 'URL base do Chatwoot (ex: https://app.chatwoot.com)';
COMMENT ON COLUMN agentes.chatwoot_api_token IS 'Token de API do Chatwoot para enviar mensagens';
COMMENT ON COLUMN agentes.chatwoot_account_id IS 'ID da conta no Chatwoot';
COMMENT ON COLUMN agentes.chatwoot_inbox_id IS 'ID da inbox (canal WhatsApp) no Chatwoot';
COMMENT ON COLUMN agentes.webhook_secret IS 'Secret para validar webhooks (opcional)';

-- =============================================
-- Instruções de configuração:
-- =============================================
-- 1. No Chatwoot, vá em Settings > Integrations > Webhooks
-- 2. Crie um webhook com a URL: https://seu-dominio.com/webhook/chatwoot/{agente_id}
-- 3. Selecione o evento: message_created
-- 4. Copie o token de API do agente bot em Settings > Agents
-- 5. Configure os campos no painel de administração do sistema
