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

### 1) Processar e-mails (ingestão)

Executa o pipeline completo (baixa anexos, classifica documento, extrai dados e gera CSVs/debug):

```bash
python run_ingestion.py
```

### 2) Inspecionar um PDF

Mostra os campos extraídos diretamente no terminal:

```bash
python scripts/inspect_pdf.py "caminho/para/arquivo.pdf"
```

O script busca automaticamente em `failed_cases_pdf/` e `temp_email/`, então você pode passar só o nome:

```bash
python scripts/inspect_pdf.py exemplo.pdf
```

Para ver o texto bruto completo (útil para criar regex):

```bash
python scripts/inspect_pdf.py exemplo.pdf --raw
```

Para ver apenas campos específicos:

```bash
python scripts/inspect_pdf.py exemplo.pdf --fields fornecedor valor vencimento
```

### 3) Validar regras / gerar CSVs de debug

Executa a validação e escreve outputs em `data/debug_output/`:

```bash
python scripts/validate_extraction_rules.py
```

### Saídas

Os CSVs de debug/saída ficam em:

- `data/output/` (relatórios finais)
- `data/debug_output/` (sucesso/falha com texto bruto reduzido e colunas auxiliares)

## Solução de Problemas Comuns

- **Erro `TesseractNotFoundError`**: Verifique se o Tesseract está instalado e se o caminho em `config/settings.py` está correto.
- **Erro `Poppler not found`**: Certifique-se de que o Poppler está instalado e adicionado ao PATH do sistema.
