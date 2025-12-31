# Sistema de Extração (MVP PAF)

Sistema para extração e processamento de documentos fiscais (NFSe e Boletos) a partir de PDFs.

O **MVP atual** está focado em gerar as colunas essenciais da planilha PAF:

- DATA (processamento)
- SETOR (**vazio no MVP**, será preenchida via ingestão/metadata do e-mail)
- EMPRESA
- FORNECEDOR
- NF (**vazio no MVP**, será preenchida via API da openAI)
- EMISSÃO (quando aplicável)
- VALOR
- VENCIMENTO

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Documentation](https://img.shields.io/badge/docs-MkDocs-blue.svg)](./docs/)

## To Do - Notas mentais

- [ ] **Implementar a refatoração descrito em refatora.md incluindo alteraçãos no models e process**.
- [ ] **Verificar se o projeto roda corretamente em container de docker e testar local mesmo no docker desktop do windows**.
- [ ] Lembrar de atualizar os dados do imap pro email da empresa.
- [ ] Procurar APIs da openAI para OCR e validadção dos dados no documento no caso para a coluna NF num primeiro momento.
- [ ] Quando o projeto estiver no estágio real pra primeira release ler git-futuro.md e pesquisar ferramentas/plugins/qualquer coisa que ajude a melhorar a maluquice que é os commits e tudo mais.
- [ ] Verificar cada caso a fundo dos pdfs e avaliar possíveis estratégias para os casos onde o pdf em si não esta anexado no email (link de prefeitura ou redirecionador de terceiros) [LOW_PRIORITY].

# Estudar por agora

### Nova estratégia camada Prata.

Alterar o modelo de ingestão para guardar o contexto do email em json e utilizar os dados de diferentes pdfs para validarem entre si. Criar nova coluna identificando o email de origem.

- Regra 1: Herança de Dados (Complementação)
    - Se tem DANFE e Boleto na mesma pasta:
        - O Boleto herda o numero_nota da DANFE (se não conseguiu ler).
        - A DANFE herda o vencimento do Boleto (ou da primeira parcela, como vimos no caso da Azul).
        - Ambos herdam o numero_pedido se estiver no Assunto/Corpo do e-mail.
- Regra 2: Fallback de Identificação (OCR vs Metadados)
    - Se o OCR do fornecedor falhou ou veio vazio:
        - Usar email_sender_name do metadado.
    - Se o CNPJ não foi achado no PDF:
        - Procurar CNPJ no email_body_text.
- Regra 3: Validação Cruzada (Auditoria)
    - Somar o valor de todos os Boletos da pasta.
    - Comparar com o valor_total da DANFE.
    - Novo Campo: status_conciliacao
        - "OK" (Valores batem)
        - "DIVERGENTE" (Nota de 10k, Boleto de 5k -> Alerta de parcela faltante)
        - "ORFAO" (Só veio boleto, sem nota)

### Verificar esses pdfs

    - 10-19 RBC NF20762 ETK INDUSTRIA.pdf
    - 01-28 NF 127090 AZUL (CARRIER).pdf
    - 04-09 NF128458 AZUL DISTRIBUIDORA.pdf
    - 04-18 RBC NF114906 AZUL DISTRIBUIDORA.pdf
    - 01-21 NF 43802 AZUL DISTRIBUIDORA (EXATA).pdf

## Done

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

### 1) Processar PDFs locais (colunas MVP)

Use o script de debug do MVP para ver as colunas PAF prioritárias:

```bash
python scripts/debug_pdf.py "caminho/para/arquivo.pdf"
```

Para inspecionar o texto bruto extraído:

```bash
python scripts/debug_pdf.py "caminho/para/arquivo.pdf" --full-text
```

### 2) Validar regras em lote (pasta `failed_cases_pdf/`)

Processa todos os PDFs em `failed_cases_pdf/` e gera relatórios em `data/debug_output/`:

```bash
python scripts/validate_extraction_rules.py
```

### 3) Ingestão via e-mail (gera CSVs)

Baixa anexos e processa o pipeline:

```bash
python run_ingestion.py
```

Saída em `data/output/`:

- `relatorio_nfse.csv`
- `relatorio_boletos.csv`

Obs.: o filtro de assunto está **hardcoded** em `run_ingestion.py` (variável `assunto_teste`, atualmente `"ENC"`).

## Dependências externas (OCR)

Quando o PDF não tem texto selecionável, o pipeline pode cair para OCR.
No Windows, os caminhos padrão são configurados em `config/settings.py` (`TESSERACT_CMD` e `POPPLER_PATH`).

## Estrutura do projeto (resumo)

```
config/          # settings (.env), parâmetros e caminhos
core/            # modelos (PAF), processor e diagnósticos
extractors/      # extratores por tipo (NFSe/Boleto)
strategies/      # estratégias (nativa/ocr/fallback)
ingestors/       # IMAP e utilitários de download
scripts/         # ferramentas (debug_pdf, validate_extraction_rules, etc.)
failed_cases_pdf/# PDFs para testes/validação de regras
data/
  output/        # CSVs gerados pela ingestão
  debug_output/  # relatórios de validação (sucesso/falha)
tests/           # suíte de testes
```

📖 Documentação técnica em [docs/](./docs/).
