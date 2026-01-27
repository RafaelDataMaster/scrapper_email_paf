# Guia de Ingestão de E-mails

Este guia explica como configurar e usar o sistema de ingestão automática de e-mails para baixar Notas Fiscais, DANFEs e Boletos diretamente do seu servidor de e-mail.

## 📋 Visão Geral

O sistema de ingestão conecta-se ao seu servidor de e-mail (IMAP) via `IngestionService`, baixa anexos PDF/XML de e-mails que contêm documentos fiscais e os organiza em "lotes" (pastas individuais por e-mail) com metadata completa.

**Funcionalidades:**

- Conexão IMAP com provedores modernos (Gmail, Office 365, Outlook)
- Download automático de anexos PDF/XML
- Organização por lotes (uma pasta por e-mail)
- Metadata contextual (assunto, remetente, data, corpo)
- Filtros inteligentes por assunto e tipo de anexo
- Limpeza automática de lotes antigos

## 🚀 Configuração Rápida

### 1. Configurar credenciais de e-mail

Crie um arquivo `.env` na raiz do projeto baseado no `.env.example`:

```bash
# Copiar template
cp .env.example .env

# Editar com suas credenciais
# Use "App Password" para contas com 2FA ativado
```

Exemplo de `.env`:

```env
# Configurações IMAP
EMAIL_HOST=imap.gmail.com
EMAIL_USER=seu.email@gmail.com
EMAIL_PASS=sua_senha_de_aplicativo  # NÃO use sua senha normal!
EMAIL_FOLDER=INBOX
EMAIL_SSL=True
EMAIL_PORT=993

# Configurações do sistema
INGESTION_TEMP_DIR=temp_email
INGESTION_MAX_AGE_HOURS=48
```

### 2. Executar ingestão

```bash
# Modo automático (processa novos e-mails)
python run_ingestion.py

# Modo manual (processa lotes específicos)
python run_ingestion.py --folder temp_email/email_20250101_abc123

# Com filtro de assunto
python run_ingestion.py --subject "Nota Fiscal"

# Limpar lotes antigos
python run_ingestion.py --cleanup
```

## 🔧 Configuração Detalhada

### Provedores de E-mail Suportados

| Provedor               | Configuração IMAP       | Porta SSL | Observações                          |
| ---------------------- | ----------------------- | --------- | ------------------------------------ |
| **Gmail**              | `imap.gmail.com`        | 993       | Requer "App Password" se 2FA ativado |
| **Outlook/Office 365** | `outlook.office365.com` | 993       | Funciona com autenticação normal     |
| **Yahoo**              | `imap.mail.yahoo.com`   | 993       | Pode requerer configuração especial  |
| **iCloud**             | `imap.mail.me.com`      | 993       | Requer senha de aplicativo           |

### Criar "App Password" no Gmail

Para contas com autenticação de dois fatores (2FA) no Google:

1. Acesse https://myaccount.google.com/security
2. Em "Signing in to Google", clique em "App passwords"
3. Selecione "Mail" como app e "Other" como dispositivo
4. Digite um nome (ex: "Scrapper PAF")
5. Use a senha gerada de 16 caracteres no `.env`

### Configurações Avançadas

No arquivo `config/settings.py`:

```python
# Diretório para armazenar lotes
DIR_TEMP = Path("temp_email")

# Idade máxima dos lotes (horas)
MAX_BATCH_AGE_HOURS = 48

# Filtros padrão de assunto
DEFAULT_SUBJECT_FILTERS = [
    "Nota Fiscal",
    "DANFE",
    "Boleto",
    "Fatura",
    "NFSe",
    "NFS-e",
    "Pagamento"
]

# Tipos de arquivo aceitos
VALID_ATTACHMENT_EXTENSIONS = [".pdf", ".xml", ".PDF", ".XML"]
```

## 📁 Estrutura de Pastas

Quando um e-mail é processado, é criada uma pasta com estrutura:

```
temp_email/
└── email_20251231_142030_abc123/      # Timestamp + hash único
    ├── metadata.json                  # Informações do e-mail
    ├── 01_DANFE_12345.pdf            # Anexos numerados
    ├── 02_boleto.pdf
    ├── 03_nota_fiscal.xml            # XMLs têm prioridade
    └── ignored/                      # Arquivos ignorados
        └── logo.png
```

### Arquivo `metadata.json`

Contém contexto completo do e-mail para enriquecimento dos dados:

```json
{
    "email_id": "ABC123",
    "subject": "NF 12345 - FORNECEDOR XYZ LTDA",
    "sender": "financeiro@fornecedor.com",
    "sender_name": "Fornecedor XYZ",
    "date": "2025-01-15 10:30:00",
    "body": "Prezados,\n\nSegue em anexo Nota Fiscal 12345...",
    "attachments_count": 2,
    "batch_id": "email_20251231_142030_abc123",
    "processed_at": "2025-01-15 11:00:00"
}
```

## 🔄 Fluxo de Processamento

### 1. Conexão IMAP

- Estabelece conexão segura (SSL) com servidor
- Autentica com credenciais do `.env`
- Seleciona pasta configurada (default: `INBOX`)

### 2. Busca de E-mails

- Filtra por assunto (padrão: contém "Nota Fiscal")
- Ordena por data (mais recentes primeiro)
- Limita a 50 e-mails por execução (configurável)

### 3. Download de Anexos

- Identifica anexos PDF/XML válidos
- Ignora imagens, documentos Office, etc.
- Numera sequencialmente (01*, 02*, etc.)
- Preserva XML como prioridade se houver

### 4. Criação de Lote

- Gera pasta única com timestamp
- Salva `metadata.json`
- Organiza anexos numerados

### 5. Processamento

- `BatchProcessor` extrai dados dos documentos
- `CorrelationService` vincula DANFEs e Boletos
- Resultados são consolidados no CSV

## 📊 Filtros e Configurações

### Filtros por Assunto

```python
# No arquivo .env ou config/settings.py
SUBJECT_FILTERS=Nota Fiscal,DANFE,Boleto,Fatura,NFSe

# No comando
python run_ingestion.py --subject "DANFE"
```

### Ignorar Remetentes

```python
# Em config/settings.py
IGNORED_SENDERS = [
    "noreply@",
    "newsletter@",
    "marketing@",
    "no-reply@"
]
```

### Limite de E-mails

```bash
# Processar apenas 10 e-mails
python run_ingestion.py --limit 10

# Processar todos (sem limite)
python run_ingestion.py --all
```

## 🧪 Testando a Configuração

### Script de Validação

```bash
# Verificar status e configuração
python run_ingestion.py --status

# Verificar estrutura de pastas (simulação)
echo "Verificando estrutura..."
python -c "from config.settings import DIR_TEMP, DIR_SAIDA; print(f'Temp: {DIR_TEMP}'); print(f'Saída: {DIR_SAIDA}')"
```

### Modo Debug

```bash
# Ver logs detalhados
python run_ingestion.py --verbose

# Manter e-mails não lidos
python run_ingestion.py --no-mark-read

# Não baixar anexos (apenas simular)
python run_ingestion.py --dry-run
```

## 🚨 Solução de Problemas

### Problema: "Authentication failed"

**Solução:**

1. Verifique se a senha está correta
2. Para Gmail com 2FA, use "App Password"
3. Certifique-se de permitir "apps menos seguros" se necessário

### Problema: "Connection timeout"

**Solução:**

1. Verifique firewall/antivírus
2. Confirme porta SSL (993)
3. Teste conectividade: `telnet imap.gmail.com 993`

### Problema: "No emails found"

**Solução:**

1. Verifique filtro de assunto
2. Confirme se há e-mails não lidos
3. Teste com `--subject ""` (sem filtro)

### Problema: "Anexos não baixados"

**Solução:**

1. Verifique extensões (só .pdf e .xml)
2. Confirme tamanho do anexo
3. Verifique permissões de escrita

## 🔄 Integração com Processamento

Após a ingestão, os lotes são processados automaticamente:

```python
from services.ingestion_service import IngestionService

# Criar serviço (usa config do .env)
service = IngestionService()

# 1. Baixar e-mails e criar lotes
folders = service.ingest_emails(subject_filter="Nota Fiscal")

# 2. Processar cada lote
for folder in folders:
    result = service.process_batch(folder)

    print(f"Lote: {folder.name}")
    print(f"Status: {result.status}")
    print(f"Documentos: {len(result.documents)}")
```

## 🧹 Limpeza Automática

Lotes antigos são removidos automaticamente:

```bash
# Remover lotes com mais de 48 horas (padrão)
python run_ingestion.py --cleanup

# Especificar idade máxima
python run_ingestion.py --cleanup --max-age 24

# Ver o que será removido (dry run)
python run_ingestion.py --cleanup --dry-run
```

## 📈 Monitoramento

### Logs do Sistema

Os logs são salvos em `logs/ingestion.log`:

```
2025-01-15 10:30:00 - INFO - Conectando a imap.gmail.com:993
2025-01-15 10:30:02 - INFO - Autenticado: seu.email@gmail.com
2025-01-15 10:30:05 - INFO - Encontrados 5 e-mails com anexos
2025-01-15 10:30:10 - INFO - Criado lote: email_20250115_103010_abc123
2025-01-15 10:30:15 - INFO - Processamento concluído: 5 lotes criados
```

### Métricas

```bash
# Ver lotes problemáticos
python scripts/simple_list.py

# Ver análise detalhada de problemas
python scripts/list_problematic.py

# Analisar padrões de e-mail
python scripts/diagnose_inbox_patterns.py

# Validar regras de extração
python scripts/validate_extraction_rules.py --batch-mode
```

## 🔗 Integração com Outros Sistemas

### Google Sheets

```bash
# Exportar resultados para planilha
python scripts/export_to_sheets.py
```

### Webhooks (Futuro)

```python
# Exemplo de webhook para notificações
webhook_url = "https://api.seusistema.com/notifications"
payload = {
    "event": "ingestion_completed",
    "batch_count": len(folders),
    "timestamp": datetime.now().isoformat()
}
```

## 🆕 Recursos da v0.2.x+

### Batch Processing

- Processamento por lote (uma pasta por e-mail)
- Metadata contextual para enriquecimento
- Correlação automática DANFE↔Boleto

### Google Sheets Export

- Exportação automática para duas abas
- Cálculo de situação (À vencer, Vencido, Pago)
- Alertas de vencimento

### Diagnóstico Avançado

- Scripts de debug especializados
- Análise de padrões de e-mail
- Validação de regras de extração

## 📚 Próximos Passos

- [Guia de Uso](usage.md) - Processar PDFs locais
- [Quick Start Boletos](quickstart_boletos.md) - Extrair boletos rapidamente
- [Exportação Google Sheets](google_sheets_export.md) - Enviar dados para planilha
- [Migração Batch](../development/MIGRATION_BATCH_PROCESSING.md) - Migrar do v0.1.x para v0.2.x
- [API Reference](../api/overview.md) - Documentação técnica

---

**Última atualização:** 2025-01-21  
**Versão:** v0.3.x (Google Sheets Export)
