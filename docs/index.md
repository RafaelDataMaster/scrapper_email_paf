# Pipeline de Automação de Entradas Fiscais

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)
![Status](https://img.shields.io/badge/status-active-success)
![Documentation](https://img.shields.io/badge/docs-mkdocs-material)

Bem-vindo à documentação oficial do projeto de automação fiscal. Este sistema foi projetado para eliminar o gargalo manual no recebimento e lançamento de Notas Fiscais, DANFEs e Boletos, garantindo integridade de dados e integração direta com o ERP.

O projeto opera sobre **quatro camadas fundamentais**: **Ingestão (Bronze)**, **Processamento**, **Correlação (Prata)** e **Saída (Ouro)**.

---

## 🚀 Quick Start

Comece a processar documentos em menos de 5 minutos.

<div class="grid cards" markdown>

- :material-email-fast: **Ingestão Automática (Lotes)**

    Configure o `.env` e baixe notas direto do Gmail/Outlook em lotes organizados.
    [Guia de Ingestão](guide/ingestion.md)

- :material-file-document-outline: **Processamento Local**

    Tem uma pasta cheia de PDFs? Processe tudo de uma vez com correlação automática.
    [Guia de Uso](guide/usage.md)

- :material-link-variant: **Correlação DANFE + Boleto**

    Vincule automaticamente boletos às suas notas fiscais correspondentes.
    [Migração Batch](MIGRATION_BATCH_PROCESSING.md)

- :material-api: **Referência da API**

    Detalhes técnicos das classes e métodos internos.
    [API Reference](api/overview.md)

</div>

---

## 🏗️ Arquitetura do Processo (v2.x - Batch Processing)

O fluxo de dados foi redesenhado para processar **lotes de documentos por e-mail**, permitindo correlação entre DANFE e Boleto:

```mermaid
graph LR
    subgraph "1. Camada de Ingestão (Bronze)"
        Email["Servidor de E-mail (IMAP)"] -->|Baixa Anexos| Ingestor["Ingestion Service"]
        Ingestor -->|"Cria Pasta do Lote"| Folder["Pasta: email_id_123"]

        Ingestor -->|Salva| Meta["metadata.json"]
        Ingestor -->|Salva| XML["00_nota_original.xml (Prioridade)"]
        Ingestor -->|Salva| PDF1["01_danfe.pdf"]
        Ingestor -->|Salva| PDF2["02_boleto.pdf"]

        style Meta fill:#f9f,stroke:#333,stroke-width:2px
        style XML fill:#fc9,stroke:#333,stroke-width:2px
        style Folder fill:#eee,stroke:#333,stroke-dasharray: 5 5
    end

    subgraph "2. Camada de Processamento (Process)"
        Folder -->|"Lê Lote"| Processor["Batch Processor"]

        Processor -->|"Detecta Tipo"| Router{"Router de Extratores"}

        Router -->|"É XML?"| ParserXML["XML Parser"]
        Router -->|"É Nota (PDF)?"| ExtDanfe["DanfeExtractor"]
        Router -->|"É Boleto?"| ExtBoleto["BoletoExtractor"]
        Router -->|"É Misto?"| ExtHibrido["HybridSplitter"]
        Router -->|"É Fatura/Outros?"| ExtOutros["OutrosExtractor"]

        ParserXML -->|Gera| DataXML["DanfeData (100% Preciso)"]
        ExtDanfe -->|Gera| RawDanfe["DanfeData (OCR)"]
        ExtBoleto -->|Gera| RawBoleto["BoletoData"]
        ExtHibrido -->|Gera| RawMisto["Lista de Docs"]
        ExtOutros -->|Gera| RawOutros["OtherDocumentData"]
    end

    subgraph "3. Camada de Inteligência (Prata)"
        DataXML & RawDanfe & RawBoleto & RawMisto & RawOutros --> Correlator["Correlation Service"]
        Meta -->|"Fornece Contexto (Assunto/Remetente)"| Correlator

        Correlator -->|"Regra 1: Link"| Match["Vincular Boleto à Nota"]
        Correlator -->|"Regra 2: Enrich"| Enrich["Preencher Vencimento/Parcelas"]
        Correlator -->|"Regra 3: Audit"| Validate["Validar Totais do Lote"]

        Match & Enrich & Validate --> FinalData["Lista Unificada de Documentos"]
    end

    subgraph "4. Camada de Saída (Ouro)"
        FinalData --> Exporter["Google Sheets Exporter"]
        Exporter -->|"Linha 1"| SheetRow1["NF (com Venc do Boleto)"]
        Exporter -->|"Linha 2"| SheetRow2["Fatura Energia/Locação"]
        Exporter -->|"Linha 3"| SheetRow3["Boleto Avulso (com Alerta)"]
    end

    style Correlator fill:#ff9,stroke:#333,stroke-width:4px
    style DataXML fill:#cfc,stroke:#333,stroke-width:2px
```

---

## 🔄 1. Ingestão em Lotes (Bronze)

Responsável pela **monitoria, captura e organização** dos documentos fiscais.

- **Protocolo IMAP:** Conexão persistente e segura (SSL) com provedores modernos (Gmail, Office 365).
- **Organização por Lote:** Cada e-mail gera uma pasta única com `metadata.json` contendo contexto (assunto, remetente, corpo).
- **Segurança:** Credenciais gerenciadas via variáveis de ambiente (`.env`), suportando _App Passwords_ para contornar 2FA.
- **Limpeza Automática:** Sidecar Docker remove lotes processados após 48 horas.

---

## ⛏️ 2. Extração Inteligente (Processamento)

O núcleo do projeto transforma documentos desestruturados em dados estruturados.

### Funcionalidades Chave

1. **Estratégia Híbrida (Fallback):**
    - Tenta leitura nativa (`pdfplumber`) primeiro: **~0.1s/arquivo**.
    - Falha graciosamente para OCR (`Tesseract`) se necessário: **~3.0s/arquivo**.
2. **Detecção de Tipo:** Router automático identifica DANFE, Boleto, NFSe, Fatura ou documento misto.
3. **Prioridade XML:** Se houver XML da NF-e no lote, dados são extraídos com 100% de precisão.

---

## 🔗 3. Correlação (Prata)

O `CorrelationService` é o diferencial da v2.x:

| Regra         | Descrição                                                                         |
| :------------ | :-------------------------------------------------------------------------------- |
| **Herança**   | Boleto herda `numero_nota` da DANFE; DANFE herda `vencimento` do Boleto           |
| **Fallback**  | Se `fornecedor_nome` está vazio, usa `email_sender_name` do metadata              |
| **Validação** | Compara soma dos boletos vs valor da DANFE → Status `OK`, `DIVERGENTE` ou `ORFAO` |

---

## 📤 4. Saída (Ouro)

Dados enriquecidos e validados prontos para integração:

- **CSV Consolidado** em `data/output/`
- **Debug CSVs** em `data/debug_output/` (separados por tipo: danfe, boleto, nfse, outros)
- **Google Sheets** (futuro) com atualização em tempo real

---

## 📂 Estrutura do Projeto

Organização seguindo princípios de _Clean Architecture_ e SOLID:

```bash
scrapper/
│
├── config/                     # Settings e carregamento de .env
├── core/                       # Lógica central do negócio
│   ├── processor.py            # Orquestrador principal
│   ├── models.py               # Modelos de dados (InvoiceData, BoletoData, DanfeData)
│   ├── extractors.py           # Classe base e registry de extratores
│   ├── metadata.py             # 🆕 EmailMetadata (contexto do e-mail)
│   ├── batch_processor.py      # 🆕 BatchProcessor (processa lotes)
│   ├── batch_result.py         # 🆕 BatchResult (resultado de lote)
│   ├── correlation_service.py  # 🆕 CorrelationService (vinculação)
│   ├── diagnostics.py          # Sistema de análise de qualidade
│   ├── interfaces.py           # Interfaces e contratos
│   └── exceptions.py           # Exceções customizadas
│
├── services/                   # 🆕 Serviços de alto nível
│   └── ingestion_service.py    # Serviço de ingestão com lotes
│
├── extractors/                 # Extratores especializados
│   ├── generic.py              # Extração de NFSe genéricas
│   ├── boleto.py               # Extração de boletos bancários
│   └── danfe.py                # Extração de DANFE
│
├── strategies/                 # Estratégias de extração de texto
│   ├── native.py               # PDFPlumber (rápido, nativo)
│   ├── ocr.py                  # Tesseract OCR (documentos escaneados)
│   └── fallback.py             # Combinação automática (fallback chain)
│
├── ingestors/                  # Conectores de entrada
│   └── imap.py                 # Ingestão via e-mail IMAP
│
├── data/                       # Dados (Entrada/Saída)
│   ├── debug_output/           # Saída dos testes de regras (CSV de debug)
│   └── output/                 # Relatórios finais de ingestão
│
├── temp_email/                 # 🆕 Pastas de lotes (batch folders)
│   └── email_20251231_abc123/  # Exemplo de lote
│       ├── metadata.json       # Contexto do e-mail
│       ├── 01_danfe.pdf        # Anexos numerados
│       └── 02_boleto.pdf
│
├── docs/                       # Documentação MkDocs
├── scripts/                    # Scripts utilitários e de diagnóstico
│   ├── validate_extraction_rules.py  # Valida regras (legacy + batch mode)
│   ├── example_batch_processing.py   # 🆕 Exemplos de batch processing
│   ├── inspect_pdf.py                # 🆕 Inspeção rápida de PDFs (busca automática)
│   └── test_docker_setup.py          # Testa setup Docker/Tesseract
│
├── tests/                      # Testes Unitários e de Integração
├── run_ingestion.py            # CLI para ingestão de e-mail (atualizado v2.x)
└── docker-compose.yml          # Inclui sidecar de limpeza
```

---

## 🆕 Novidades da v2.x (Batch Processing)

| Feature                         | v1.x   | v2.x       |
| ------------------------------- | ------ | ---------- |
| Processar arquivo individual    | ✅     | ✅         |
| Processar pasta de arquivos     | ✅     | ✅         |
| **Processar lote com metadata** | ❌     | ✅         |
| **Correlação DANFE/Boleto**     | ❌     | ✅         |
| **Contexto do e-mail**          | ❌     | ✅         |
| **Limpeza automática**          | Manual | Automática |
| **Status de conciliação**       | ❌     | ✅         |

Para migrar do v1.x para v2.x, consulte o [Guia de Migração](MIGRATION_BATCH_PROCESSING.md).

---

## 🎯 Modelo de Dados

### Campos Base (todos os documentos)

| Campo                  | Descrição                  | Tipo     |
| :--------------------- | :------------------------- | :------- |
| `arquivo_origem`       | Nome do arquivo processado | `string` |
| `batch_id`             | 🆕 ID do lote de origem    | `string` |
| `source_email_subject` | 🆕 Assunto do e-mail       | `string` |
| `source_email_sender`  | 🆕 Remetente do e-mail     | `string` |
| `status_conciliacao`   | 🆕 OK, DIVERGENTE ou ORFAO | `string` |

### Campos de Nota Fiscal

| Campo            | Descrição                                | Tipo     |
| :--------------- | :--------------------------------------- | :------- |
| `cnpj_prestador` | Identificação fiscal do fornecedor       | `string` |
| `numero_nota`    | Número da NFS-e/DANFE                    | `string` |
| `data_emissao`   | Data de competência (ISO 8601)           | `date`   |
| `valor_total`    | Valor líquido da nota                    | `float`  |
| `vencimento`     | 🆕 Herdado do boleto (se correlacionado) | `date`   |

### Campos de Boleto

| Campo               | Descrição                 | Tipo     |
| :------------------ | :------------------------ | :------- |
| `cnpj_beneficiario` | CNPJ do beneficiário      | `string` |
| `valor_documento`   | Valor nominal do boleto   | `float`  |
| `vencimento`        | Data de vencimento        | `date`   |
| `linha_digitavel`   | Código de barras          | `string` |
| `referencia_nfse`   | 🆕 Número da NF vinculada | `string` |

---

## 🔗 Links Rápidos

- [📧 Guia de Ingestão](guide/ingestion.md) - Configurar e-mail e processar lotes
- [🔄 Migração Batch](MIGRATION_BATCH_PROCESSING.md) - Migrar do v1.x para v2.x
- [🧪 Guia de Testes](guide/testing.md) - Validar regras de extração
- [📊 API Reference](api/overview.md) - Documentação técnica completa
- [🏗️ Arquitetura PDF](research/architecture_pdf_extraction.md) - Detalhes de extração
- [📈 Histórico de Refatorações](development/refactoring_history.md) - Changelog técnico
