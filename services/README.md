# Serviços de Ingestão de E-mails

Este diretório contém os serviços responsáveis pela ingestão e processamento de e-mails com documentos fiscais.

## Arquitetura

```
services/
├── email_ingestion_orchestrator.py  # Orquestrador principal (novo)
├── ingestion_service.py              # Serviço base de ingestão
└── README.md                          # Esta documentação
```

## EmailIngestionOrchestrator

O `EmailIngestionOrchestrator` é o serviço principal para ingestão de e-mails. Ele orquestra todo o fluxo de processamento, incluindo:

### Features

- **Ingestão Unificada**: Processa e-mails COM e SEM anexos em uma única execução
- **Checkpointing**: Salva progresso automaticamente para resume após interrupções
- **Tratamento de Interrupções**: Captura Ctrl+C e salva estado antes de encerrar
- **Timeout por Lote**: Previne travamentos em PDFs problemáticos
- **Filtro Inteligente**: Aplica regras de blacklist/whitelist para evitar falsos positivos

### Uso Básico

```python
from services.email_ingestion_orchestrator import (
    EmailIngestionOrchestrator,
    create_orchestrator_from_config,
)

# Criar orquestrador a partir das configurações (.env)
orchestrator = create_orchestrator_from_config(
    batch_timeout_seconds=300,  # 5 minutos por lote
)

# Executar ingestão
result = orchestrator.run(
    subject_filter="ENC",              # Filtro de assunto IMAP
    process_with_attachments=True,      # Processar PDFs/XMLs
    process_without_attachments=True,   # Processar links/códigos
    apply_correlation=True,             # Correlacionar DANFE ↔ Boleto
    resume=True,                        # Continuar de onde parou
)

# Resultado
print(result.summary())
# Output: Ingestão COMPLETED: 50 emails escaneados, 30 com anexos, 15 sem anexos, 5 filtrados...

# Acessar resultados
for batch in result.batch_results:
    print(f"Lote {batch.batch_id}: {batch.total_documents} documentos")

for aviso in result.avisos:
    print(f"Link: {aviso.link_nfe}, Código: {aviso.codigo_verificacao}")
```

### Checkpointing

O orquestrador salva automaticamente um checkpoint em `temp_email/_checkpoint.json` após cada e-mail processado.

```python
# Verificar se há trabalho pendente
if orchestrator.has_pending_work():
    print("Há ingestão incompleta. Execute run() para continuar.")

# Forçar nova ingestão (ignorar checkpoint)
orchestrator.clear_checkpoint()
result = orchestrator.run(resume=False)

# Verificar status
status = orchestrator.get_status()
print(f"Status: {status['status']}")
print(f"Processados: {status['total_processed']}")
```

### Estrutura do Checkpoint

```json
{
  "status": "IN_PROGRESS",
  "started_at": "2025-01-15T10:00:00",
  "last_updated": "2025-01-15T10:30:00",
  "processed_email_ids": ["email_001", "email_002"],
  "created_batches": ["temp_email/email_001"],
  "created_avisos": [{"email_id": "...", "link_nfe": "..."}],
  "total_processed": 2,
  "total_errors": 0,
  "subject_filter": "ENC"
}
```

### Tratamento de Timeouts

Lotes que excedem o timeout são registrados em `temp_email/_timeouts.json` para reprocessamento posterior:

```bash
# Reprocessar apenas lotes que deram timeout
python run_ingestion.py --reprocess-timeouts
```

## IngestionService

O `IngestionService` é o serviço base que gerencia a conexão com o servidor de e-mail e organiza anexos em pastas de lote.

### Responsabilidades

1. Conectar ao servidor via IMAP
2. Baixar anexos PDF/XML
3. Criar estrutura de pastas por e-mail
4. Gerar `metadata.json` com contexto
5. Aplicar filtro de arquivos irrelevantes

### Uso

```python
from services.ingestion_service import IngestionService
from ingestors.imap import ImapIngestor

ingestor = ImapIngestor(
    host="imap.gmail.com",
    user="usuario@gmail.com",
    password="app-password",
    folder="INBOX"
)

service = IngestionService(
    ingestor=ingestor,
    temp_dir=Path("temp_email")
)

# Ingerir e-mails COM anexos
batch_folders = service.ingest_emails(subject_filter="ENC")

# Ingerir e-mails SEM anexos (links e códigos)
avisos = service.ingest_emails_without_attachments(
    subject_filter="Nota Fiscal",
    apply_filter=True
)
```

## Linha de Comando

O arquivo `run_ingestion.py` na raiz do projeto fornece uma interface de linha de comando completa:

```bash
# Ingestão unificada (padrão)
python run_ingestion.py

# Apenas e-mails COM anexos
python run_ingestion.py --only-attachments

# Apenas e-mails SEM anexos
python run_ingestion.py --only-links

# Ignorar checkpoint e iniciar do zero
python run_ingestion.py --fresh

# Ver status do checkpoint
python run_ingestion.py --status

# Reprocessar lotes existentes
python run_ingestion.py --reprocess

# Customizar filtro e timeout
python run_ingestion.py --subject "Nota Fiscal" --timeout 600
```

## Fluxo de Dados

```
┌─────────────────┐
│  Servidor IMAP  │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│        EmailIngestionOrchestrator           │
│  ┌─────────────────┐  ┌──────────────────┐  │
│  │ COM Anexos      │  │ SEM Anexos       │  │
│  │ → BatchResult[] │  │ → EmailAviso[]   │  │
│  └────────┬────────┘  └────────┬─────────┘  │
│           │                    │            │
│           ▼                    ▼            │
│  ┌─────────────────────────────────────┐   │
│  │         Checkpoint JSON              │   │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│              Exportação CSV                  │
│  • relatorio_lotes.csv                       │
│  • relatorio_avisos_links.csv                │
│  • relatorio_consolidado.csv                 │
└─────────────────────────────────────────────┘
```

## Configuração

Variáveis de ambiente necessárias (`.env`):

```env
EMAIL_HOST=imap.gmail.com
EMAIL_USER=seu-email@gmail.com
EMAIL_PASS=sua-app-password
EMAIL_FOLDER=INBOX
```

## Testes

```bash
# Executar testes do orquestrador
python -m pytest tests/test_ingestion_orchestrator.py -v
```
