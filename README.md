# Secretária IA - WhatsApp para Clínicas Médicas

Sistema de atendimento automatizado via WhatsApp para clínicas médicas, construído com **LangChain**, **LangGraph** e **Python**.

## Funcionalidades

- **Agendamento de consultas** - Criar, remarcar e cancelar consultas
- **Integração com Google Calendar** - Gerenciamento de agenda dos profissionais
- **Suporte a áudio** - Transcrição (Whisper) e síntese de voz (ElevenLabs)
- **Memória de conversas** - Histórico persistido no PostgreSQL
- **Fila de mensagens** - Tratamento de mensagens encavaladas
- **Envio de arquivos** - Integração com Google Drive
- **Alertas via Telegram** - Notificações para a equipe
- **Escalação para humanos** - Transferência automática quando necessário

## Arquitetura

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    WhatsApp     │────▶│    Chatwoot     │────▶│    FastAPI      │
│   (Usuário)     │     │   (Webhook)     │     │   (Servidor)    │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
                        ┌────────────────────────────────────────────┐
                        │              LangGraph Agent               │
                        │  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
                        │  │ Memória  │  │  Tools   │  │   LLM    │ │
                        │  │ Postgres │  │ Calendar │  │  Gemini  │ │
                        │  └──────────┘  │  Drive   │  └──────────┘ │
                        │                │ Telegram │                │
                        │                └──────────┘                │
                        └────────────────────────────────────────────┘
```

## Estrutura do Projeto

```
.
├── main.py                 # Servidor FastAPI principal
├── requirements.txt        # Dependências Python
├── .env.example           # Exemplo de variáveis de ambiente
├── credentials.json       # Credenciais Google (não versionado)
└── src/
    ├── config.py          # Configurações e variáveis de ambiente
    ├── agent/
    │   ├── graph.py       # Grafo LangGraph do agente
    │   ├── tools.py       # Ferramentas do agente
    │   └── prompts.py     # Prompts do sistema
    └── services/
        ├── chatwoot.py    # Integração com Chatwoot
        ├── database.py    # PostgreSQL/Supabase
        ├── google_calendar.py  # Google Calendar API
        ├── google_drive.py     # Google Drive API
        ├── telegram.py    # Notificações Telegram
        └── audio.py       # Whisper e ElevenLabs
```

## Pré-requisitos

1. **Python 3.10+**
2. **Chatwoot** com integração WhatsApp (Baileys)
3. **PostgreSQL/Supabase** para persistência
4. **Conta Google Cloud** com Calendar e Drive APIs habilitadas
5. **Chave OpenAI** (para Whisper)
6. **Chave Google AI** (para Gemini)
7. **Conta ElevenLabs** (para síntese de voz)
8. **Bot Telegram** (para alertas)

## Instalação

### 1. Clone o repositório

```bash
git clone <url-do-repositorio>
cd secretaria-ia
```

### 2. Crie e ative o ambiente virtual

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate     # Windows
```

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```

### 4. Configure as variáveis de ambiente

```bash
cp .env.example .env
# Edite o arquivo .env com suas credenciais
```

### 5. Configure as credenciais do Google

1. Acesse o [Google Cloud Console](https://console.cloud.google.com)
2. Crie um projeto ou selecione um existente
3. Habilite as APIs: Calendar e Drive
4. Crie credenciais OAuth 2.0
5. Baixe o `credentials.json` e coloque na raiz do projeto

### 6. Configure o banco de dados

Execute o SQL no Supabase para criar as tabelas:

```sql
CREATE TABLE IF NOT EXISTS n8n_fila_mensagens (
    id SERIAL PRIMARY KEY,
    id_mensagem VARCHAR(255) NOT NULL,
    telefone VARCHAR(50) NOT NULL,
    mensagem TEXT NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS n8n_historico_mensagens (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fila_telefone ON n8n_fila_mensagens(telefone);
CREATE INDEX IF NOT EXISTS idx_historico_session ON n8n_historico_mensagens(session_id, created_at);
```

### 7. Configure o Chatwoot

1. Crie um webhook apontando para `http://seu-servidor:8000/webhook/chatwoot`
2. Selecione o evento "Mensagem criada"

## Execução

### Desenvolvimento

```bash
python main.py
```

ou com hot reload:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Produção

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

## Ferramentas do Agente

| Ferramenta | Descrição |
|------------|-----------|
| `criar_evento` | Cria uma consulta no Google Calendar |
| `buscar_evento` | Busca um evento específico por ID |
| `buscar_todos_os_eventos` | Lista eventos em um período |
| `atualizar_evento` | Atualiza um evento existente |
| `deletar_evento` | Cancela uma consulta |
| `listar_arquivos` | Lista arquivos do Google Drive |
| `baixar_e_enviar_arquivo` | Envia arquivo para o paciente |
| `reagir_mensagem` | Reage com emoji à mensagem |
| `escalar_humano` | Transfere para atendente humano |
| `enviar_alerta_de_cancelamento` | Notifica via Telegram |
| `refletir` | Permite raciocínio complexo |

## Personalização

### Alterar informações da clínica

Edite o arquivo `src/config.py`:

```python
CLINIC_INFO = {
    "name": "Sua Clínica",
    "address": "Seu endereço",
    # ...
}

PROFESSIONALS = [
    {
        "name": "Dr. Nome",
        "role": "Médico",
        "specialty": "Especialidade",
        "calendar_id": "id@group.calendar.google.com"
    },
    # ...
]
```

### Alterar modelo de IA

No arquivo `src/agent/graph.py`, você pode trocar o modelo:

```python
# Para usar OpenAI GPT-4
agent = SecretaryAgent(model_provider="openai")

# Para usar Google Gemini (padrão)
agent = SecretaryAgent(model_provider="google")
```

## Endpoints da API

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/` | GET | Verificação de saúde |
| `/health` | GET | Status do serviço |
| `/webhook/chatwoot` | POST | Webhook do Chatwoot |

## Diferenças do N8N Original

Este projeto replica a funcionalidade do fluxo N8N em Python puro:

| N8N | Python |
|-----|--------|
| Nodes visuais | Código modular |
| MCP Server | Ferramentas LangChain |
| Expressions | Python nativo |
| Workflow triggers | FastAPI webhooks |
| Postgres node | asyncpg |
| HTTP Request node | httpx |

## Troubleshooting

### Erro de autenticação Google

```
FileNotFoundError: credentials.json
```

Baixe o arquivo de credenciais do Google Cloud Console.

### Erro de conexão com banco

```
asyncpg.exceptions.ConnectionError
```

Verifique as credenciais do PostgreSQL no `.env`.

### Webhook não recebe mensagens

1. Verifique se o webhook está configurado no Chatwoot
2. Confirme que a URL está acessível externamente
3. Use ngrok para testes locais: `ngrok http 8000`

## Contribuição

1. Fork o projeto
2. Crie uma branch: `git checkout -b feature/nova-feature`
3. Commit: `git commit -m 'Adiciona nova feature'`
4. Push: `git push origin feature/nova-feature`
5. Abra um Pull Request

## Licença

Este projeto está sob a licença MIT.
