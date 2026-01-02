# Sistema de Extração de Documentos Fiscais (v2.x)

Sistema para extração e processamento de documentos fiscais (DANFE, NFSe e Boletos) a partir de PDFs, com suporte a **processamento em lote** e **correlação automática** entre documentos.

## Colunas Extraídas (PAF)

- DATA (processamento)
- SETOR (via metadata do e-mail)
- EMPRESA
- FORNECEDOR
- NF (número da nota)
- EMISSÃO
- VALOR
- VENCIMENTO

## Novidades da v2.x

- ✅ **Batch Processing**: Processa e-mails como lotes (pasta com `metadata.json`)
- ✅ **Correlação DANFE/Boleto**: Vincula automaticamente boletos às suas notas
- ✅ **Herança de campos**: Boleto herda `numero_nota` da DANFE, DANFE herda `vencimento` do Boleto
- ✅ **Status de conciliação**: OK, DIVERGENTE ou ORFAO

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Documentation](https://img.shields.io/badge/docs-MkDocs-blue.svg)](./docs/)

## To Do - Notas mentais

- [ ] **Verificar se o projeto roda corretamente em container de docker e testar local mesmo no docker desktop do windows**.
- [ ] Lembrar de atualizar os dados do imap pro email da empresa.
- [ ] Procurar APIs da openAI para OCR e validadção dos dados no documento no caso para a coluna NF num primeiro momento.
- [ ] Quando o projeto estiver no estágio real pra primeira release ler git-futuro.md e pesquisar ferramentas/plugins/qualquer coisa que ajude a melhorar a maluquice que é os commits e tudo mais.
- [ ] Verificar cada caso a fundo dos pdfs e avaliar possíveis estratégias para os casos onde o pdf em si não esta anexado no email (link de prefeitura ou redirecionador de terceiros) [LOW_PRIORITY].
- [ ] Implementar exportador para Google Sheets (esqueleto já existe).

# Estudar por agora

### Comandos de terminal uteis

Procurar pdfs com nome de empresas específicas ao identificar casos falhos nos debugs do validate

```bash
Get-ChildItem -Path .\failed_cases_pdf\ -Recurse -Filter "*MOTO*" -Name
```

### ✅ Camada Prata Implementada (v2.x)

A estratégia de correlação foi implementada nos seguintes módulos:

- `core/metadata.py` - EmailMetadata (contexto do e-mail)
- `core/batch_processor.py` - BatchProcessor (processa lotes)
- `core/batch_result.py` - BatchResult (resultado de lote)
- `core/correlation_service.py` - CorrelationService (correlação)

**Regras implementadas:**

- ✅ Regra 1: Herança de Dados (Boleto ↔ DANFE)
- ✅ Regra 2: Fallback de Identificação (OCR → Metadados)
- ✅ Regra 3: Validação Cruzada (status_conciliacao: OK/DIVERGENTE/ORFAO)

### Verificar esses pdfs

## Done

### 02/01/2026

- [x] **Implementar a refatoração descrito em refatora.md incluindo alteraçãos no models e process** ✅ (v2.x - Batch Processing)
- [x] **Batch Processing v2.x**: Módulos `BatchProcessor`, `CorrelationService`, `EmailMetadata`, `BatchResult`, `IngestionService`
- [x] **Correlação DANFE/Boleto**: Herança automática de campos entre documentos do mesmo lote
- [x] **Novo script `inspect_pdf.py`**: Inspeção rápida com busca automática em `failed_cases_pdf/` e `temp_email/`
- [x] **164 testes unitários**: Cobertura completa incluindo novos módulos de batch
- [x] **Documentação atualizada**: Guias de debug, testing, extending e migration atualizados para v2.x
- [x] **Limpeza de scripts**: Removidos scripts obsoletos (`debug_pdf.py`, `diagnose_failures.py`, `analyze_boletos.py`, etc.)

### 30/12/2025

- [x] Correção na análise de linhas digitaveis, priorizando o uso do extractor de boleto.

### 29/12/2025

- [x] Separação de amostras de pdfs para validação de extração de dados.
- [x] Criação do primeiro extrator específico.
- [x] Adicionado a flag de reavaliação no script de validação de extração.

### 26/12/2025 - Dia 10

- [x] **Fazer a limpeza e catalogação dos pdfs na pasta de C:Dados**

### 24/12/2025 - Dia 9

- [x] **Concertar/adicionar a logica de extração das NSFE, DANFES, etc, pra funcionar com os casos falhos.**
    - Suporte completo a múltiplos tipos além de NFSe: **DANFE** e **OUTROS** (faturas/demonstrativos)
    - Roteamento por extrator via `can_handle()` (plugins) para evitar DANFE/OUTROS caindo como NFSe
    - Novos extratores especializados: `DanfeExtractor` e `OutrosExtractor`
    - Novos modelos de dados: `DanfeData` e `OtherDocumentData` (padronizando `DocumentData`)
    - Relatórios/CSVs de validação separados e debug por tipo (incluindo `danfe_sucesso_debug.csv` e `outros_sucesso_debug.csv`)
    - Renomeação do fallback de NFSe: `GenericExtractor` → `NfseGenericExtractor` (módulo legado removido)
    - Correção do script de validação no Windows: stdout/stderr em UTF-8 (evita `UnicodeEncodeError`)
    - OUTROS/Locaweb: preenchimento de `empresa` via fallback por domínio/e-mail quando não existe CNPJ nosso no texto
    - OUTROS/Locação: correção de extração de valor quando aparece como “Total a Pagar no Mês … 2.855,00” (sem “R$”) + teste unitário

### 23/12/2025 - Dia 8

- [x] Focar em um primeiro momento a extração das seguintes colunas [(Data inicio/recebimento do pedido),(setor que fez o pedido aparentemente pode deixar pra la mas se tiver bom),EMPRESA(nós),FORNECEDOR(eles),NF,EMISSÃO,VALOR,VENCIMENTO,]
- [x] Boletos: FORNECEDOR robusto (não captura linha digitável e não fica vazio por falso positivo de "empresa nossa")
- [x] Classificação de boleto mais resiliente a OCR/quebras (keywords corrompidas)

### 22/12/2025 - Dia 7

- [x] Alinhamento dos modelos de extração com o requisitado pra um primeiro momento com PAF
- [x] Refatoração do script de debug_pdf pra ficar condizente com o MVP

### 19/12/2025 - Dia 6

- [x] **Refatoração SOLID completa (production-ready):**
    - Implementados 4 princípios SOLID: LSP, OCP, SRP, DIP
    - Criado módulo `core/exporters.py` com classes separadas (FileSystemManager, AttachmentDownloader, DataExporter)
    - Adicionada classe base `DocumentData` com `doc_type` para extensibilidade (OCP)
    - Implementada injeção de dependências no `BaseInvoiceProcessor` e `run_ingestion.py` (DIP)
    - Padronizado tratamento de erros nas estratégias (LSP)
    - Criado esqueleto de `GoogleSheetsExporter` para futura integração
    - **43/43 testes passando** (14 novos testes SOLID + 23 existentes + 6 estratégias)
    - Documentação completa: `solid_refactoring_report.md` e `solid_usage_guide.md`
    - Projeto agora permite adicionar novos tipos de documento sem modificar código existente
- [x] Validação completa dos 10 boletos extraídos (100% de taxa de sucesso)
- [x] Corrigidos 3 casos críticos de extração:
    - `numero_documento` capturando data em vez do valor correto (layout tabular)
    - `nosso_numero` em layouts multi-linha (label e valor separados por \n)
    - `nosso_numero` quando label está como imagem (fallback genérico)
- [x] Implementados padrões regex robustos com `re.DOTALL` e diferenciação de formatos
- [x] Documentação atualizada: `refactoring_history.md` (Fase 3 e 4 completas) e `extractors.md`
- [x] Criado guia completo de debug de PDFs em `docs/development/debugging_guide.md`
- [x] Criado script avançado de debug `scripts/debug_pdf.py` com:
    - Output colorido, análise de campos, comparação de PDFs
    - Biblioteca de padrões pré-testados, suporte a padrões customizados
    - Detecção automática de quando `re.DOTALL` é necessário

### 18/12/2025 - Dia 5

- [x] Conversar direito com a Melyssa, ou mesmo direto com o Paulo ou o Gustavo a respeito do redirecionamento de emails. Avaliar possíveis soluções e planejar como realmente as NFSE vai estar e em qual email.
- [x] Criado configuração do projeto pra rodar em container.
- [x] Criado módulo centralizado `core/diagnostics.py` para análise de qualidade
- [x] Criado `scripts/_init_env.py` para path resolution centralizado
- [x] Renomeado `test_rules_extractors.py` → `validate_extraction_rules.py` (clareza semântica)
- [x] Removidos comentários redundantes no código (mantendo docstrings importantes)
- [x] Implementado suporte completo para processamento de **Boletos Bancários**
- [x] Sistema identifica e separa automaticamente NFSe de Boletos
- [x] Extração de dados específicos de boletos (linha digitável, vencimento, CNPJ beneficiário, etc.)
- [x] Geração de relatórios separados: `relatorio_nfse.csv` e `relatorio_boletos.csv`
- [x] Criado extrator especializado `BoletoExtractor` com detecção inteligente
- [x] Implementada lógica de vinculação entre boletos e NFSe (por referência, número documento, ou cruzamento de dados)
- [x] Adicionada documentação completa em `docs/guide/boletos.md` e `docs/guide/quickstart_boletos.md`
- [x] Criados scripts de teste e análise (`test_boleto_extractor.py`, `analyze_boletos.py`)

### 17/12/2025 - Dia 4

- [x] Configurar o email para testes em ambiente real de scraping
- [x] **Nota**: Email `scrapper.nfse@gmail.com` configurado com autenticação em `rafael.ferreira@soumaster.com.br` e Google Authenticator

### 16/12/2025 - Dia 3

- [x] Estudar scraping de diferentes tipos de email
- [x] Terminar de organizar a documentação por completo

### 15/12/2025 - Dia 2

- [x] Montar site da documentação (MkDocs)
- [x] Organizar estrutura do projeto

### 11/12/2025 - Dia 1

- [x] Debugar PDFs para entender cada caso
- [x] Extração de dados para CSV baseados em PDFs de diferentes casos

## Instalação

```bash
python -m venv .venv

# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1

# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
```

## Configuração (.env)

Copie o modelo e preencha com suas credenciais IMAP:

```bash
copy .env.example .env  # Windows
# ou
cp .env.example .env    # Linux/macOS
```

Variáveis (ver [.env.example](.env.example)):

- `EMAIL_HOST`
- `EMAIL_USER`
- `EMAIL_PASS`
- `EMAIL_FOLDER`

## Uso (MVP)

### 1) Inspecionar um PDF

Use o script de inspeção para ver os campos extraídos:

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

### 2) Validar regras em lote

**Modo legado** (PDFs soltos em `failed_cases_pdf/`):

```bash
python scripts/validate_extraction_rules.py
```

**Modo batch** (lotes com `metadata.json` em `temp_email/`):

```bash
python scripts/validate_extraction_rules.py --batch-mode --apply-correlation
```

### 3) Ingestão via e-mail (gera CSVs)

Baixa anexos, cria lotes e processa com correlação:

```bash
python run_ingestion.py
```

**Flags disponíveis:**

```bash
python run_ingestion.py --reprocess           # Reprocessa lotes existentes
python run_ingestion.py --batch-folder <path> # Processa pasta específica
python run_ingestion.py --subject "NF-e"      # Filtro de assunto customizado
python run_ingestion.py --no-correlation      # Sem correlação (modo legado)
python run_ingestion.py --cleanup             # Remove lotes antigos
```

Saída em `data/output/`:

- `relatorio_nfse.csv`
- `relatorio_boletos.csv`
- `relatorio_danfe.csv`

## Dependências externas (OCR)

Quando o PDF não tem texto selecionável, o pipeline pode cair para OCR.
No Windows, os caminhos padrão são configurados em `config/settings.py` (`TESSERACT_CMD` e `POPPLER_PATH`).

## Estrutura do projeto (resumo)

```
config/          # settings (.env), parâmetros e caminhos
core/            # modelos, processor, batch_processor, correlation_service
  metadata.py    # EmailMetadata (contexto do e-mail)
  batch_processor.py  # Processador de lotes
  batch_result.py     # Resultado de lote
  correlation_service.py  # Correlação DANFE/Boleto
services/        # Serviços de alto nível
  ingestion_service.py  # Ingestão com lotes
extractors/      # extratores por tipo (NFSe/Boleto/DANFE)
strategies/      # estratégias (nativa/ocr/fallback)
ingestors/       # IMAP e utilitários de download
scripts/         # ferramentas utilitárias
  inspect_pdf.py           # Inspeção rápida de PDFs
  validate_extraction_rules.py  # Validação de regras
  example_batch_processing.py   # Exemplos de batch
  test_docker_setup.py     # Teste de setup
temp_email/      # Pastas de lotes (batch folders)
failed_cases_pdf/# PDFs para testes/validação de regras
data/
  output/        # CSVs gerados pela ingestão
  debug_output/  # relatórios de validação (sucesso/falha)
tests/           # suíte de testes (164 testes)
```

📖 Documentação técnica em [docs/](./docs/).
