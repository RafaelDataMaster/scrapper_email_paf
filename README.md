# Projeto de Scraping de notas fiscais eletrônicas


# To Do
- [ ] Conseguir o acesso ao maior número de pdfs e a tabela de verdades já catalogada dos dados pra conferir se a extração do PDF está de fato funcionando.
- [ ] Verificar cada caso a fundo dos pdfs e avaliar possíveis estratégias para os casos onde o pdf em si não esta anexado no email (link de prefeitura ou redirecionador de terceiros).
- [ ] Verificar se o projeto roda corretamente em container de docker e testar local mesmo no docker desktop do windows.
- [ ] Quando o projeto estiver no estágio real pra primeira release ler git-futuro.md e pesquisar ferramentas/plugins/qualquer coisa que ajude a melhorar a maluquice que é os commits e tudo mais.
- [ ] Estudar o vídeo do rapaz explicando que o git push é praticamente um ssh pro servidor do github e entender como fazer isso pra um notebook local de forma eficiente.




# Done

## 19/12/2025 - Dia 6
- [X] **Refatoração SOLID completa (production-ready):**
  - Implementados 4 princípios SOLID: LSP, OCP, SRP, DIP
  - Criado módulo `core/exporters.py` com classes separadas (FileSystemManager, AttachmentDownloader, DataExporter)
  - Adicionada classe base `DocumentData` com `doc_type` para extensibilidade (OCP)
  - Implementada injeção de dependências no `BaseInvoiceProcessor` e `run_ingestion.py` (DIP)
  - Padronizado tratamento de erros nas estratégias (LSP)
  - Criado esqueleto de `GoogleSheetsExporter` para futura integração
  - **43/43 testes passando** (14 novos testes SOLID + 23 existentes + 6 estratégias)
  - Documentação completa: `solid_refactoring_report.md` e `solid_usage_guide.md`
  - Projeto agora permite adicionar novos tipos de documento sem modificar código existente
- [X] Validação completa dos 10 boletos extraídos (100% de taxa de sucesso)
- [X] Corrigidos 3 casos críticos de extração:
  - `numero_documento` capturando data em vez do valor correto (layout tabular)
  - `nosso_numero` em layouts multi-linha (label e valor separados por \n)
  - `nosso_numero` quando label está como imagem (fallback genérico)
- [X] Implementados padrões regex robustos com `re.DOTALL` e diferenciação de formatos
- [X] Documentação atualizada: `refactoring_history.md` (Fase 3 e 4 completas) e `extractors.md`
- [X] Criado guia completo de debug de PDFs em `docs/development/debugging_guide.md`
- [X] Criado script avançado de debug `scripts/debug_pdf.py` com:
  - Output colorido, análise de campos, comparação de PDFs
  - Biblioteca de padrões pré-testados, suporte a padrões customizados
  - Detecção automática de quando `re.DOTALL` é necessário

## 18/12/2025 
- [X] Conversar direito com a Melyssa, ou mesmo direto com o Paulo ou o Gustavo a respeito do redirecionamento de emails. Avaliar possíveis soluções e planejar como realmente as NFSE vai estar e em qual email.
- [X] Criado configuração do projeto pra rodar em container.
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

## 17/12/2025
- [x] Configurar o email para testes em ambiente real de scraping
- [x] **Nota**: Email `scrapper.nfse@gmail.com` configurado com autenticação em `rafael.ferreira@soumaster.com.br` e Google Authenticator

## 16/12/2025
- [x] Estudar scraping de diferentes tipos de email
- [x] Terminar de organizar a documentação por completo

## 15/12/2025
- [x] Montar site da documentação (MkDocs)
- [x] Organizar estrutura do projeto

## 11/12/2025
- [x] Debugar PDFs para entender cada caso
- [x] Extração de dados para CSV baseados em PDFs de diferentes casos


# Oque eu to focando em pesquisar por agora
- Validar a extração de dados do pdf. 
- Identificar adição de abordagem de extração de xml. 
- Configuração dos imaps e testar o scrapping em um email real.

# Dificuldades até o momento
Boa parte dos erros foram relacionados ao Regex, estudar mais a fundo e procurar fazer testes com casos mais complexos para ir adicionando mais palavras ao dicionário de Regex.
Durante o planejamento do projeto avaliar a necessidade de separar uma fila de processamentos de pdfs que são imagens do OCR e tesseract por conta do alto tempo de execução, pra um caso já esta demorando 30 segundos na versão atual do código.

# Informações gerais do projeto e requisitos

## Tipos de Documentos Suportados

O sistema processa automaticamente dois tipos de documentos:

### 1. NFSe (Nota Fiscal de Serviço Eletrônica)
**Dados extraídos:**
- `arquivo_origem` - Nome do arquivo PDF
- `cnpj_prestador` - CNPJ do prestador de serviço
- `numero_nota` - Número da nota fiscal
- `data_emissao` - Data de emissão (YYYY-MM-DD)
- `valor_total` - Valor total da nota
- `texto_bruto` - Snippet do texto extraído

**Saída:** `data/output/relatorio_nfse.csv`

### 2. Boletos Bancários
**Dados extraídos:**
- `arquivo_origem` - Nome do arquivo PDF
- `cnpj_beneficiario` - CNPJ do beneficiário (quem recebe)
- `valor_documento` - Valor nominal do boleto
- `vencimento` - Data de vencimento (YYYY-MM-DD)
- `numero_documento` - Número do documento/fatura
- `linha_digitavel` - Código de barras do boleto
- `nosso_numero` - Identificação interna do banco
- `referencia_nfse` - Número da NFSe (se mencionado no boleto)
- `texto_bruto` - Snippet do texto extraído

**Saída:** `data/output/relatorio_boletos.csv`

### Vinculação de Boletos e NFSe

O sistema pode vincular boletos às suas notas fiscais através de:
1. **Referência explícita** - Campo `referencia_nfse` no boleto
2. **Número do documento** - Muitos fornecedores usam o nº da NF
3. **Cruzamento de dados** - CNPJ + Valor + Data aproximada

Consulte [docs/guide/boletos.md](docs/guide/boletos.md) para exemplos detalhados.

## Estrutura do projeto

```
scrapper/
│
├── config/                     # Configurações (settings.py + .env)
├── core/                       # Módulos centrais
│   ├── processor.py            # Orquestrador principal
│   ├── models.py               # InvoiceData, BoletoData
│   ├── extractors.py           # Classe base para extratores
│   ├── diagnostics.py          # Sistema de análise de qualidade ✨ NOVO
│   ├── interfaces.py           # Contratos e interfaces
│   └── exceptions.py           # Exceções customizadas
│
├── extractors/                 # Extratores especializados
│   ├── generic.py              # NFSe genéricas (regex)
│   └── boleto.py               # Boletos bancários
│
├── strategies/                 # Estratégias de extração de texto
│   ├── native.py               # PDFPlumber (rápido)
│   ├── ocr.py                  # Tesseract OCR
│   └── fallback.py             # Fallback automático
│
├── ingestors/                  # Conectores de entrada
│   └── imap.py                 # Ingestão via e-mail IMAP
│
├── scripts/                    # Scripts utilitários
│   ├── _init_env.py            # Path resolution centralizado ✨ NOVO
│   ├── validate_extraction_rules.py  # Validação de regras (renomeado)
│   ├── diagnose_failures.py    # Análise de falhas (refatorado)
│   ├── analyze_boletos.py      # Análise estatística de boletos
│   ├── move_failed_files.py    # Move PDFs com falha
│   └── test_boleto_extractor.py # Teste do extrator de boletos
│
├── tests/                      # Testes unitários ✨ NOVO
│   └── test_extractors.py      # 23 testes (GenericExtractor, BoletoExtractor)
│
├── docs/                       # Documentação MkDocs ✨ REORGANIZADA
│   ├── index.md                # Home
│   ├── api/                    # Referência técnica (5 páginas)
│   │   ├── overview.md         # Visão geral + diagrama
│   │   ├── core.md             # Módulos centrais
│   │   ├── extractors.md       # Extratores
│   │   ├── strategies.md       # Estratégias
│   │   └── diagnostics.md      # Sistema de qualidade
│   ├── guide/                  # Guias de uso
│   ├── research/               # Arquitetura e pesquisa
│   └── development/            # Histórico de desenvolvimento
│
├── data/                       # Dados
│   ├── debug_output/           # CSVs de validação (sucesso/falha)
│   └── output/                 # Relatórios finais (NFSe + Boletos)
│
├── nfs/                        # PDFs para análise manual
├── temp_email/                 # Buffer temporário de downloads
├── failed_cases_pdf/           # Casos de teste para validação
│
├── main.py                     # Script de processamento local
├── run_ingestion.py            # Script de ingestão de e-mail
├── mkdocs.yml                  # Configuração da documentação
└── requirements.txt            # Dependências Python
```

# Guia Rápido

## Instalação

1.  Clone o repositório e crie o ambiente virtual:
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # Linux/Mac
    .venv\Scripts\activate     # Windows
    ```

2.  Instale as dependências:
    ```bash
    pip install -r requirements.txt
    ```

3.  Configure a segurança:
    *   Copie `.env.example` para `.env`.
    *   Preencha suas credenciais de e-mail no `.env`.

## Como Usar

*   **Ingestão de E-mail:** `python run_ingestion.py` (Baixa e processa notas do e-mail).
*   **Processamento Local:** `python main.py` (Processa arquivos da pasta `nfs/`).
*   **Documentação:** `mkdocs serve` (Abre o site da documentação localmente).

## 1. Automação de Entradas de NFe

### ORQUESTRAÇÃO
- Programar rotinas de varredura do email e integrar com fonte de contratos
- ELT

### Requisitos
- [ ] Ler e-mails com NF
- [ ] Categorizar e digitalizar informações
- [ ] Ler tabela verdade de Contratos e Pedidos
- [ ] Comparar informações de NF de entrada e informações da tabela
- [ ] Criar tabela de input de dados