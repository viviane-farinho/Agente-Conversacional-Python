#!/bin/bash

# ============================================
# Script de inicialização - Secretária IA
# ============================================

echo "🚀 Iniciando Secretária IA..."
echo ""

# Ativa o ambiente virtual
source venv/bin/activate

# Verifica se as dependências estão instaladas
if ! python -c "import fastapi" 2>/dev/null; then
    echo "📦 Instalando dependências..."
    pip install -r requirements.txt
fi

# Inicia o servidor
echo "✅ Servidor iniciando em http://localhost:8000"
echo ""
echo "📋 Endpoints:"
echo "   - Health: http://localhost:8000/health"
echo "   - Webhook: http://localhost:8000/webhook/chatwoot"
echo ""
echo "⏳ Para expor na internet, abra outro terminal e execute:"
echo "   ./ngrok.sh"
echo ""
echo "----------------------------------------"

python main.py
