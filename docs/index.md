# Pipeline de Automação de Entradas de NFS-e

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)
![Status](https://img.shields.io/badge/status-active-success)
![Documentation](https://img.shields.io/badge/docs-mkdocs-material)

Bem-vindo à documentação oficial do projeto de automação fiscal. Este sistema foi projetado para eliminar o gargalo manual no recebimento e lançamento de Notas Fiscais de Serviço (NFS-e), garantindo integridade de dados e integração direta com o ERP.

O projeto opera sobre três pilares fundamentais: **Ingestão (E-mail)**, **Processamento (OCR/PDF)** e **Integração**.

---

## 🚀 Quick Start

Comece a processar notas em menos de 5 minutos.

<div class="grid cards" markdown>

-   :material-email-fast: **Ingestão Automática**
    
    Configure o `.env` e baixe notas direto do Gmail/Outlook.
    [Guia de Ingestão](guide/ingestion.md)

-   :material-file-document-outline: **Processamento Local**
    
    Tem uma pasta cheia de PDFs? Processe tudo de uma vez.
    [Guia de Uso](guide/usage.md)

-   :material-test-tube: **Testes & Qualidade**
    
    Garanta que nada quebrou antes de subir para produção.
    [Guia de Testes](guide/testing.md)

-   :material-api: **Referência da API**
    
    Detalhes técnicos das classes e métodos internos.
    [API Reference](api.md)

</div>

---

## 🏗️ Arquitetura do Processo

O fluxo de dados foi desenhado para ser resiliente e escalável:

```mermaid
graph TD
    subgraph INGEST ["1. Ingestão (ImapIngestor)"]
        A["📧 E-mail Server"] -->|IMAP/SSL| B("run_ingestion.py")
        B -->|Bytes| C{"Buffer em Disco"}
        C -->|UUID| D["Arquivos Temporários"]
    end

    subgraph CORE ["2. Processamento (InvoiceProcessor)"]
        D --> E{"É Texto?"}
        E -->|Sim| F["NativePdfStrategy"]
        E -->|Não| G["TesseractOcrStrategy"]
        F --> H["Extração Regex"]
        G --> H
        H --> I["InvoiceData Model"]
    end

    subgraph OUTPUT ["3. Saída"]
        I --> J["CSV Consolidado"]
        I --> K["Integração ERP (Futuro)"]
    end

    style INGEST fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    style CORE fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style OUTPUT fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
```

-----

## 🔄 1. Ingestão Segura

Responsável pela **monitoria e captura** dos documentos fiscais.

*   **Protocolo IMAP:** Conexão persistente e segura (SSL) com provedores modernos (Gmail, Office 365).
*   **Segurança:** Credenciais gerenciadas via variáveis de ambiente (`.env`), suportando *App Passwords* para contornar 2FA.
*   **Resiliência:** Tratamento de colisão de nomes de arquivos usando UUIDs.

-----

## ⛏️ 2. Extração Inteligente

O núcleo do projeto (`scrapper_nfe`) transforma documentos desestruturados em dados.

### Funcionalidades Chave

1.  **Estratégia Híbrida (Fallback):**
    *   Tenta leitura nativa (`pdfplumber`) primeiro: **~0.1s/arquivo**.
    *   Falha graciosamente para OCR (`Tesseract`) se necessário: **~3.0s/arquivo**.
2.  **Normalização:** Converte valores monetários (`R$ 1.234,56`) e datas para formatos padrão de banco de dados (`float`, `ISO 8601`).

### Modelo de Dados

| Campo | Descrição | Tipo |
| :--- | :--- | :--- |
| `arquivo_origem` | Nome do arquivo processado | `string` |
| `cnpj_prestador` | Identificação fiscal do fornecedor | `string` |
| `numero_nota` | Número da NFS-e (higienizado) | `string` |
| `data_emissao` | Data de competência (ISO 8601) | `date` |
| `valor_total` | Valor líquido da nota | `float` |

-----

## 📂 Estrutura do Projeto

Organização seguindo princípios de *Clean Architecture*.

```bash
extrator_nfse/
│
├── config/             # Settings e carregamento de .env
├── core/               # Interfaces, Models e Exceptions
├── extractors/         # Regras de Regex (GenericExtractor)
├── ingestors/          # Conectores de E-mail (ImapIngestor)
├── strategies/         # Motores de Leitura (Native vs OCR)
├── tests/              # Testes Unitários e de Integração
├── docs/               # Documentação MkDocs
├── main.py             # CLI para processamento local
└── run_ingestion.py    # CLI para ingestão de e-mail
```
