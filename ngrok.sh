#!/bin/bash

# ============================================
# Script para expor o servidor com Ngrok
# ============================================

echo "🌐 Expondo servidor para a internet..."
echo ""

# Verifica se o ngrok está instalado
if ! command -v ngrok &> /dev/null; then
    echo "❌ Ngrok não está instalado!"
    echo ""
    echo "Instale com:"
    echo "  Mac:     brew install ngrok"
    echo "  Linux:   snap install ngrok"
    echo "  Windows: choco install ngrok"
    echo ""
    echo "Ou baixe em: https://ngrok.com/download"
    exit 1
fi

echo "✅ Ngrok encontrado!"
echo ""
echo "🔗 Após iniciar, copie a URL https://xxx.ngrok-free.app"
echo "   e configure no Chatwoot em:"
echo "   Configurações > Integrações > Webhooks"
echo ""
echo "   URL do webhook: https://xxx.ngrok-free.app/webhook/chatwoot"
echo "   Evento: message_created"
echo ""
echo "----------------------------------------"
echo ""

ngrok http 8000
