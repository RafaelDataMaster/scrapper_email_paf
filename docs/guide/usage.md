# Guia de Instalação e Execução

Este guia descreve como configurar o ambiente de desenvolvimento e executar o pipeline do MVP (NFSe e Boletos).

## Pré-requisitos

- **Python 3.8+** instalado.
- **Tesseract OCR** instalado e configurado no PATH (ou caminho especificado em `config/settings.py`).
- **Poppler** (para `pdf2image`) instalado.

## Instalação

1. Clone o repositório:

    ```bash
    git clone https://github.com/rafaeldatamaster/scrapper_nfe.git
    cd scrapper_nfe
    ```

2. Crie um ambiente virtual:

    ```bash
    python -m venv .venv
    source .venv/bin/activate  # Linux/Mac
    .venv\Scripts\activate     # Windows
    ```

3. Instale as dependências:

    ```bash
    pip install -r requirements.txt
    ```

## Configuração Avançada

Você pode alterar o comportamento do extrator através de variáveis de ambiente ou editando `config/settings.py`.

| Variável        | Descrição                       | Padrão (Windows)                               |
| :-------------- | :------------------------------ | :--------------------------------------------- |
| `TESSERACT_CMD` | Caminho do executável do OCR    | `C:\Program Files\Tesseract-OCR\tesseract.exe` |
| `POPPLER_PATH`  | Caminho dos binários do Poppler | `C:\Program Files\poppler-xx\bin`              |

## Execução

### 1) Ingestão via E-mail (Modo Padrão)

Este é o modo principal de operação. O script conecta ao e-mail, baixa os anexos, cria lotes e processa-os com correlação.

```bash
# Ingestão padrão com correlação
python run_ingestion.py
```

**Flags úteis:**

```bash
# Reprocessar lotes que já estão em temp_email/
python run_ingestion.py --reprocess

# Processar apenas uma pasta de lote específica
python run_ingestion.py --batch-folder temp_email/email_123

# Desabilitar a correlação automática entre documentos
python run_ingestion.py --no-correlation

# Limpar lotes antigos após a execução
python run_ingestion.py --cleanup

# Filtrar e-mails por assunto (default: "ENC")
python run_ingestion.py --subject "Nota Fiscal"
```

### 2) Debug de PDF Individual

Use `inspect_pdf.py` para analisar um único arquivo PDF e ver o que está sendo extraído. É a melhor ferramenta para começar a investigar um problema.

```bash
# Busca automática pelo nome do arquivo
python scripts/inspect_pdf.py exemplo.pdf

# Mostrar o texto bruto completo (para criar regex)
python scripts/inspect_pdf.py exemplo.pdf --raw

# Inspecionar apenas campos específicos
python scripts/inspect_pdf.py danfe.pdf --fields fornecedor_nome valor_total
```

### 3) Debug de Lote de Processamento

Use `run_ingestion.py` com a flag `--batch-folder` para processar ou reprocessar um lote específico.

```bash
# Analisar uma pasta de lote específica
python run_ingestion.py --batch-folder temp_email/email_com_problema_123

# Reprocessar lote específico
python run_ingestion.py --batch-folder temp_email/email_com_problema_123 --reprocess
```

### 4) Validação em Massa

O script `validate_extraction_rules.py` processa todos os PDFs de teste e gera CSVs de sucesso e falha, o que é ótimo para verificar regressões após uma mudança.

```bash
# Validar em modo lote (recomendado)
python scripts/validate_extraction_rules.py --batch-mode --apply-correlation
```

### Saídas

Os CSVs de debug/saída ficam em:

- `data/output/` (relatórios finais)
- `data/debug_output/` (sucesso/falha com texto bruto reduzido e colunas auxiliares)

## Solução de Problemas Comuns

- **Erro `TesseractNotFoundError`**: Verifique se o Tesseract está instalado e se o caminho em `config/settings.py` está correto.
- **Erro `Poppler not found`**: Certifique-se de que o Poppler está instalado e adicionado ao PATH do sistema.
