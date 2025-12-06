# Testes do Agente de Advocacia

## Como usar
Envie estas mensagens pelo WhatsApp para testar o comportamento do agente.

---

## 1. TESTES DE DETECÇÃO DE ÁREA

### Previdenciário (deve detectar área: previdenciario)
```
- "quero me aposentar"
- "fui negado no INSS"
- "preciso de auxílio-doença"
- "tenho direito ao BPC?"
- "minha aposentadoria foi negada"
- "atende direito previdenciário?"
```

### Trabalhista (deve detectar área: trabalhista)
```
- "fui demitido sem justa causa"
- "não recebi minhas verbas rescisórias"
- "meu patrão não paga horas extras"
- "sofri assédio no trabalho"
- "trabalhei 5 anos sem carteira assinada"
- "quero processar minha empresa"
```

### Família (deve detectar área: familia)
```
- "quero me divorciar"
- "preciso de pensão alimentícia"
- "meu ex não paga pensão"
- "quero a guarda dos meus filhos"
- "preciso fazer inventário"
```

### Consumidor (deve detectar área: consumidor)
```
- "meu nome foi negativado indevidamente"
- "comprei um produto com defeito"
- "o banco me cobrou taxas indevidas"
- "meu plano de saúde negou cirurgia"
- "empresa não quer devolver meu dinheiro"
```

### Civil (deve detectar área: civil)
```
- "preciso cobrar uma dívida"
- "quero fazer um contrato"
- "fui vítima de um acidente"
- "quero pedir indenização"
```

---

## 2. TESTES DE QUALIFICAÇÃO SDR

### Previdenciário - Fluxo completo
```
Usuário: "quero me aposentar"
Esperado: Agente pergunta qual benefício, tempo de contribuição, se já deu entrada, documentação

Usuário: "aposentadoria por idade"
Esperado: Agente continua qualificação

Usuário: "tenho 35 anos de contribuição"
Esperado: Agente pergunta sobre documentação e oferece consulta
```

### Trabalhista - Fluxo completo
```
Usuário: "fui mandado embora"
Esperado: Agente pergunta se ainda trabalha, tempo na empresa, qual problema, prazo

Usuário: "trabalhei 3 anos e não pagaram minhas férias"
Esperado: Agente pergunta quando ocorreu e sobre documentação
```

---

## 3. TESTES DE ALUCINAÇÃO (deve NÃO inventar)

### Perguntas sobre detalhes que NÃO estão no banco
```
- "qual o valor do auxílio-doença?"
- "quanto tempo demora um processo trabalhista?"
- "qual o valor da pensão alimentícia?"
- "quanto custa a consulta?"
- "vocês trabalham com direito criminal?"
- "qual o telefone do escritório?"
```

**Resposta esperada:** Agente deve dizer que não tem essa informação e oferecer agendamento de consulta.

---

## 4. TESTES DE SUPORTE (mensagens genéricas)

### Deve ir para agente de suporte
```
- "olá"
- "oi, boa tarde"
- "quero falar com um advogado"
- "como funciona o atendimento?"
- "onde fica o escritório?"
```

---

## 5. TESTES DE CONTEXTO (usa histórico)

### Conversa com continuidade
```
Mensagem 1: "quero me aposentar"
Mensagem 2: "por idade"
Mensagem 3: "tenho 62 anos e 20 de contribuição"
Mensagem 4: "sim, tenho carteira de trabalho"
```

**Esperado:** Agente deve manter o contexto da conversa e não repetir perguntas já respondidas.

---

## 6. TESTES DE MÚLTIPLAS ÁREAS

### Mensagens ambíguas
```
- "fui demitido e agora preciso me aposentar" (trabalhista + previdenciário)
- "meu ex não paga pensão e me negativou no Serasa" (família + consumidor)
```

---

## 7. TESTES DE EDGE CASES

### Mensagens curtas/vagas
```
- "preciso de ajuda"
- "tenho um problema"
- "quero processar"
- "?"
```

### Mensagens com erros de digitação
```
- "qero me apozentar"
- "fui demitdo"
- "divorsio"
```

### Mensagens em CAPS ou com muitos emojis
```
- "FUI DEMITIDO E NÃO RECEBI NADA!!!"
- "preciso de ajuda urgente 😭😭😭"
```

---

## Checklist de Validação

| Teste | Esperado | Passou? |
|-------|----------|---------|
| Detecta área previdenciário | ✅ | |
| Detecta área trabalhista | ✅ | |
| Detecta área família | ✅ | |
| Detecta área consumidor | ✅ | |
| Faz perguntas de qualificação | ✅ | |
| NÃO alucina informações | ✅ | |
| Oferece agendamento quando não sabe | ✅ | |
| Mantém contexto da conversa | ✅ | |
| Responde mensagens genéricas | ✅ | |

---

## Documentos no Banco (referência)

O agente só deve responder com base nestas informações:

1. **Sobre nosso escritório** - Áreas de atuação gerais
2. **Requisitos para Aposentadoria por Idade** - Idade mínima, tempo contribuição, documentos
3. **O que é BPC/LOAS e quem tem direito** - Requisitos, renda, documentos
4. **Prazo para entrar com Ação Trabalhista** - Prazo de 2 anos
5. **Verbas devidas na Rescisão** - Lista de verbas rescisórias
6. **Tipos de Divórcio** - Consensual vs litigioso
7. **Como funciona a consulta** - Informações sobre atendimento

Qualquer informação fora disso = agente deve dizer que não tem e oferecer consulta.
