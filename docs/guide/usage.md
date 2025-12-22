# Guia de Instalação e Execução

Este guia descreve como configurar o ambiente de desenvolvimento e executar o extrator de NFS-e.

## Pré-requisitos

* **Python 3.8+** instalado.
* **Tesseract OCR** instalado e configurado no PATH (ou caminho especificado em `config/settings.py`).
* **Poppler** (para `pdf2image`) instalado.

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

| Variável | Descrição | Padrão (Windows) |
| :--- | :--- | :--- |
| `TESSERACT_CMD` | Caminho do executável do OCR | `C:\Program Files\Tesseract-OCR\tesseract.exe` |
| `POPPLER_PATH` | Caminho dos binários do Poppler | `C:\Program Files\poppler-xx\bin` |

## Execução

Para processar os arquivos na pasta `nfs/`:

```bash
python main.py
```

O script irá:

1. Ler todos os PDFs na pasta `nfs/`.
2. Extrair os dados (CNPJ, Valor, Data, Número).
3. Gerar um arquivo `carga_notas_fiscais.csv` na raiz do projeto.

### Exemplo de Resultado

Após processar os PDFs, o arquivo `carga_notas_fiscais.csv` será gerado com o seguinte formato:

| arquivo_origem | cnpj_prestador | data_emissao | numero_nota | valor_total |
| :--- | :--- | :--- | :--- | :--- |
| nota_sp_01.pdf | 12.345.678/0001-90 | 2023-10-15 | 98765 | 1500.00 |
| nota_rj_scan.pdf | 98.765.432/0001-10 | 2023-10-16 | 452 | 350.50 |

## Solução de Problemas Comuns

* **Erro `TesseractNotFoundError`**: Verifique se o Tesseract está instalado e se o caminho em `config/settings.py` está correto.
* **Erro `Poppler not found`**: Certifique-se de que o Poppler está instalado e adicionado ao PATH do sistema.
