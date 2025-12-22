# Core - Módulos Centrais

Os módulos `core` contêm a lógica fundamental do sistema de processamento de documentos.

## Visão Geral

O pacote `core` é responsável por:

- **Orquestração**: Coordenação do pipeline completo de extração
- **Modelos de Dados**: Estruturas padronizadas (InvoiceData, BoletoData)
- **Interfaces**: Contratos para extensibilidade (Strategy Pattern)
- **Diagnósticos**: Sistema de análise de qualidade
- **Exceções**: Tratamento de erros customizado

## Módulos

### BaseInvoiceProcessor

Orquestrador principal que coordena todo o pipeline de processamento.

**Responsabilidades:**

- Receber PDF de entrada
- Selecionar estratégia de extração de texto apropriada
- Identificar tipo de documento (NFSe vs Boleto)
- Rotear para extrator especializado
- Retornar modelo de dados estruturado

::: core.processor.BaseInvoiceProcessor
    options:
      show_root_heading: true
      show_source: false
      members:
        - process

---

### Modelos de Dados

Estruturas de dados imutáveis usando `@dataclass`.

#### InvoiceData

Modelo para Notas Fiscais de Serviço Eletrônica (NFSe).

**Campos:**

- `arquivo_origem` (str): Nome do arquivo PDF original
- `texto_bruto` (str): Primeiros 500 caracteres do texto limpo (útil para debug/auditoria)
  - **Implementação:** Remove espaços/quebras primeiro, depois pega 500 chars
  - **Formato:** `' '.join(raw_text.split())[:500]`
- `cnpj_prestador` (Optional[str]): CNPJ do prestador formatado
- `fornecedor_nome` (Optional[str]): Razão Social do prestador (coluna FORNECEDOR na planilha PAF)
- `numero_nota` (Optional[str]): Número da nota fiscal
- `data_emissao` (Optional[str]): Data no formato ISO (YYYY-MM-DD)
- `valor_total` (float): Valor total da nota
- `vencimento` (Optional[str]): Data de vencimento no formato ISO (YYYY-MM-DD)
- `dt_classificacao` (Optional[str]): Data de classificação no formato ISO (YYYY-MM-DD)
- `forma_pagamento` (Optional[str]): Forma de pagamento (PIX, TED, BOLETO)
- `tipo_doc_paf` (str): Tipo de documento para PAF (default: "NF")
- `trat_paf` (Optional[str]): Responsável pela classificação (coluna TRAT PAF)
- `lanc_sistema` (str): Status de lançamento no ERP (default: "PENDENTE")

::: core.models.InvoiceData
    options:
      show_root_heading: true
      members_order: source

#### BoletoData

Modelo para Boletos Bancários.

**Campos:**

- `arquivo_origem` (str): Nome do arquivo PDF original
- `texto_bruto` (str): Primeiros 500 caracteres do texto limpo
  - **Implementação:** Remove espaços/quebras primeiro, depois pega 500 chars
  - **Formato:** `' '.join(raw_text.split())[:500]`
  - **Uso:** Debug, auditoria, treino de ML futuro
- `cnpj_beneficiario` (Optional[str]): CNPJ do beneficiário
- `fornecedor_nome` (Optional[str]): Razão Social do beneficiário (coluna FORNECEDOR na planilha PAF)
- `valor_documento` (float): Valor nominal do boleto
- `vencimento` (Optional[str]): Data de vencimento (YYYY-MM-DD)
  - **Fallback:** Busca primeira data DD/MM/YYYY mesmo sem label "Vencimento:"
- `dt_classificacao` (Optional[str]): Data de classificação no formato ISO (YYYY-MM-DD)
- `numero_documento` (Optional[str]): Número do documento
  - **Suporta:** Formato ano.número (ex: 2025.122) e 8 variações de padrão
- `linha_digitavel` (Optional[str]): Código de barras
- `nosso_numero` (Optional[str]): Identificação do banco
- `referencia_nfse` (Optional[str]): NFSe vinculada (se encontrado)
- `forma_pagamento` (Optional[str]): Forma de pagamento (default: "BOLETO")
- `tipo_doc_paf` (str): Tipo de documento para PAF (default: "BOLETO")
- `trat_paf` (Optional[str]): Responsável pela classificação
- `lanc_sistema` (str): Status de lançamento no ERP (default: "PENDENTE")

::: core.models.BoletoData
    options:
      show_root_heading: true
      members_order: source

---

### BaseExtractor

Classe abstrata base para todos os extratores de dados.

**Padrão de Design:** Template Method

**Métodos Abstratos:**

- `can_handle(text: str) -> bool`: Verifica se o extrator pode processar o documento
- `extract(text: str) -> Dict[str, Any]`: Extrai dados estruturados do texto

::: core.extractors.BaseExtractor
    options:
      show_root_heading: true
      show_source: false

---

### Interfaces

Contratos para implementação de componentes extensíveis.

#### TextExtractionStrategy

Interface para estratégias de extração de texto de PDFs.

**Implementações:**

- `NativePdfStrategy` - Usa PDFPlumber
- `TesseractOcrStrategy` - Usa OCR
- `SmartExtractionStrategy` - Fallback automático

::: core.interfaces.TextExtractionStrategy
    options:
      show_root_heading: true

#### EmailIngestorStrategy

Interface para conectores de entrada de dados.

**Implementações:**

- `ImapIngestor` - Servidor IMAP/Email

::: core.interfaces.EmailIngestorStrategy
    options:
      show_root_heading: true

---

### Exceções Customizadas

Hierarquia de exceções para tratamento de erros específicos do domínio.

::: core.exceptions
    options:
      show_root_heading: true

---

## Fluxo de Dados

```mermaid
sequenceDiagram
    participant Client
    participant Processor as BaseInvoiceProcessor
    participant Strategy as TextExtractionStrategy
    participant Extractor as BaseExtractor
    participant Model as InvoiceData/BoletoData
    
    Client->>Processor: process(pdf_path)
    Processor->>Strategy: extract_text(pdf)
    Strategy-->>Processor: texto_bruto
    Processor->>Extractor: can_handle(texto)
    Extractor-->>Processor: True/False
    Processor->>Extractor: extract(texto)
    Extractor-->>Processor: dict
    Processor->>Model: create(dict)
    Model-->>Client: InvoiceData/BoletoData
```

## Exemplo de Uso

```python
from core.processor import BaseInvoiceProcessor
from core.models import InvoiceData, BoletoData

# Criar processador
processor = BaseInvoiceProcessor()

# Processar documento
result = processor.process("path/to/document.pdf")

# Verificar tipo
if isinstance(result, InvoiceData):
    print(f"NFSe #{result.numero_nota}: R$ {result.valor_total}")
elif isinstance(result, BoletoData):
    print(f"Boleto: R$ {result.valor_documento} - Venc: {result.vencimento}")
```

## Ver Também

- [Extractors](extractors.md) - Implementações de extratores
- [Strategies](strategies.md) - Estratégias de extração de texto
- [Diagnostics](diagnostics.md) - Sistema de análise de qualidade
