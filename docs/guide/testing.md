# Guia de Testes Automatizados

Este documento descreve como executar e expandir a suíte de testes do projeto.

## Visão Geral

Utilizamos o framework `pytest` para testes. Os testes estão localizados na pasta `tests/` e cobrem:

1. **Estratégias de Leitura (`test_strategies.py`):** Valida se o `pdfplumber` e o fallback para OCR estão funcionando.
2. **Ingestão de E-mail (`test_ingestion.py`):** Simula a conexão IMAP e o download de anexos (usando Mocks).
3. **Batch Processing (`test_batch_processing.py`):** Testes para os novos módulos de processamento em lote (BatchProcessor, CorrelationService, EmailMetadata, BatchResult, IngestionService).

## Executando os Testes

### Rodar Todos os Testes

```bash
python -m pytest tests/ -v
```

### Rodar Apenas Testes de Batch Processing

```bash
python -m pytest tests/test_batch_processing.py -v
```

### Rodar um Teste Específico

```bash
python -m pytest tests/test_batch_processing.py::TestBatchProcessor::test_process_single_file -v
```

### Saída Esperada

Se tudo estiver correto, você verá uma saída similar a esta:

```text
========================= test session starts ==========================
collected 164 items

tests/test_strategies.py ......                                   [  3%]
tests/test_ingestion.py ...                                       [  5%]
tests/test_batch_processing.py ................................................ [ 35%]
...
========================= 164 passed in 2.34s ==========================
```

## Estrutura dos Testes

### 1. Testes de Estratégia (`test_strategies.py`)

Verifica se a lógica de extração de texto está resiliente.

- `test_extract_success`: Garante que PDFs legíveis retornam texto.
- `test_extract_fallback_empty_text`: Garante que PDFs vazios/imagens retornam string vazia (para acionar o OCR).
- `test_extract_file_error`: Garante que o sistema não trava com arquivos corrompidos.

### 2. Testes de Ingestão (`test_ingestion.py`)

Verifica a integração com e-mail sem precisar de credenciais reais.

- `test_connect`: Verifica se os parâmetros de host/user/pass são passados corretamente para o `imaplib`.
- `test_fetch_attachments_success`: Simula uma resposta do servidor IMAP contendo um PDF e verifica se o parser extrai o anexo corretamente.
- `test_save_bytes_to_disk_with_unique_name`: **Crítico.** Verifica se a lógica de salvar arquivos temporários gera nomes únicos (UUID) para evitar sobrescrita.

### 3. Testes de Batch Processing (`test_batch_processing.py`)

Testes para os módulos da v2.x:

- **TestEmailMetadata**: Criação, serialização e carregamento de metadados de e-mail.
- **TestBatchResult**: Agregação de resultados, cálculo de totais, serialização.
- **TestBatchProcessor**: Processamento de lotes com e sem metadata, modo legado.
- **TestCorrelationService**: Correlação DANFE/Boleto, herança de campos, validação cruzada.
- **TestIngestionService**: Criação de lotes, limpeza automática, integração com ingestor.

## Criando Novos Testes

Ao adicionar uma nova funcionalidade, crie testes na pasta `tests/`.

### Exemplo de Teste Simples

```python
import pytest

def test_caso_sucesso():
    resultado = minha_funcao(10)
    assert resultado == 20

def test_caso_erro():
    with pytest.raises(ValueError):
        minha_funcao(-1)
```

### Exemplo com Fixtures

```python
import pytest
from pathlib import Path

@pytest.fixture
def sample_metadata():
    return {
        "batch_id": "test_123",
        "email_subject": "Test Subject",
        "email_sender_name": "Test Sender"
    }

def test_with_fixture(sample_metadata):
    assert sample_metadata["batch_id"] == "test_123"
```

---

## Scripts Utilitários para Validação

Além dos testes unitários, o projeto conta com scripts na pasta `scripts/` para validar regras de extração com dados reais.

### 1. Validação de Regras (`scripts/validate_extraction_rules.py`)

Valida as regras de extração em PDFs reais, suportando modo legado e batch.

**Uso básico (modo legado):**

```bash
python scripts/validate_extraction_rules.py
```

**Modo batch com correlação:**

```bash
python scripts/validate_extraction_rules.py --batch-mode --apply-correlation
```

**Flags disponíveis:**

| Flag                      | Descrição                          |
| :------------------------ | :--------------------------------- |
| `--batch-mode`            | Processa lotes com metadata.json   |
| `--apply-correlation`     | Aplica correlação entre documentos |
| `--revalidar-processados` | Reprocessa arquivos já validados   |
| `--validar-prazo`         | Valida vencimentos (obrigatório)   |
| `--exigir-nf`             | Exige número da nota               |
| `--input-dir <path>`      | Diretório customizado              |

**Saída:** Gera CSVs em `data/debug_output/` separados por tipo (danfe, boleto, nfse, outros).

### 2. Inspeção de PDFs (`scripts/inspect_pdf.py`)

Permite inspecionar rapidamente um PDF e ver os campos extraídos.

```bash
# Busca automática pelo nome do arquivo
python scripts/inspect_pdf.py exemplo.pdf

# Caminho completo
python scripts/inspect_pdf.py failed_cases_pdf/pasta/boleto.pdf

# Mostrar apenas campos específicos
python scripts/inspect_pdf.py danfe.pdf --fields fornecedor valor vencimento

# Mostrar texto bruto completo
python scripts/inspect_pdf.py nota.pdf --raw
```

**Funcionalidades:**

- Busca recursiva em `failed_cases_pdf/` e `temp_email/`
- Mostra campos relevantes baseado no tipo do documento
- Suporta filtro de campos específicos
- Exibe texto bruto (truncado ou completo)

### 3. Exemplos de Batch Processing (`scripts/example_batch_processing.py`)

Demonstra como usar os novos módulos de batch processing.

```bash
# Criar lote de teste
python scripts/example_batch_processing.py --create-test-batch

# Processar lote existente
python scripts/example_batch_processing.py --process temp_email/email_123
```

### 4. Teste de Setup Docker (`scripts/test_docker_setup.py`)

Verifica se os pré-requisitos (Tesseract, Poppler, etc.) estão instalados.

```bash
python scripts/test_docker_setup.py
```

---

## Workflow de Validação Recomendado

### 1. Após Mudanças no Código

```bash
# Rodar todos os testes
python -m pytest tests/ -v

# Se todos passarem, validar com PDFs reais
python scripts/validate_extraction_rules.py --batch-mode
```

### 2. Debug de PDF Problemático

```bash
# 1. Inspecionar o PDF
python scripts/inspect_pdf.py arquivo_problematico.pdf

# 2. Ver texto bruto para criar regex
python scripts/inspect_pdf.py arquivo_problematico.pdf --raw

# 3. Após ajustar o código, rodar testes
python -m pytest tests/ -v

# 4. Validar em lote
python scripts/validate_extraction_rules.py
```

### 3. Validação Completa (CI/CD)

```bash
# Testes unitários
python -m pytest tests/ -v --tb=short

# Validação de regras
python scripts/validate_extraction_rules.py --batch-mode --apply-correlation
```

---

## Cobertura de Testes

Para gerar relatório de cobertura:

```bash
# Instalar pytest-cov
pip install pytest-cov

# Rodar com cobertura
python -m pytest tests/ --cov=core --cov=extractors --cov=services --cov-report=html

# Abrir relatório
open htmlcov/index.html  # macOS
start htmlcov/index.html  # Windows
```

---

## Resumo dos Comandos

| Ação                    | Comando                                                    |
| :---------------------- | :--------------------------------------------------------- |
| Rodar todos os testes   | `python -m pytest tests/ -v`                               |
| Rodar testes de batch   | `python -m pytest tests/test_batch_processing.py -v`       |
| Validar regras (legado) | `python scripts/validate_extraction_rules.py`              |
| Validar regras (batch)  | `python scripts/validate_extraction_rules.py --batch-mode` |
| Inspecionar PDF         | `python scripts/inspect_pdf.py arquivo.pdf`                |
| Testar setup            | `python scripts/test_docker_setup.py`                      |

## Próximos Passos

- [Guia de Debug](../development/debugging_guide.md) - Técnicas avançadas de debug
- [Guia de Uso](usage.md) - Processar PDFs locais
- [Migração Batch](../MIGRATION_BATCH_PROCESSING.md) - Migrar para v2.x
