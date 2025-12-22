# Sistema de Extração Inteligente de Documentos Fiscais

Sistema automatizado para extração e processamento de **NFSe** e **Boletos Bancários** a partir de PDFs recebidos por e-mail. Utiliza estratégias de extração adaptativas (PDFPlumber + OCR) e segue princípios SOLID para garantir manutenibilidade e extensibilidade.

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-43%20passing-brightgreen.svg)](./tests/)
[![Documentation](https://img.shields.io/badge/docs-MkDocs-blue.svg)](./docs/)

## 🎯 Características Principais

- **Extração Dual**: Processa NFSe e Boletos automaticamente
- **Estratégias Adaptativas**: Fallback automático para OCR quando necessário
- **Ingestão IMAP**: Baixa anexos diretamente do e-mail
- **Arquitetura SOLID**: 4 princípios implementados (SRP, OCP, LSP, DIP)
- **43 Testes Passando**: Cobertura completa de extratores e estratégias
- **Vinculação Inteligente**: Associa boletos às suas NFSe automaticamente
- **Sistema de Qualidade**: Análise de taxa de sucesso e diagnóstico de falhas

## 📦 Instalação Rápida

```bash
# Clone e configure o ambiente
git clone <repository-url>
cd scrapper
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Instale dependências
pip install -r requirements.txt

# Configure credenciais (copie .env.example para .env)
cp .env.example .env
# Edite .env com suas credenciais IMAP
```

## 🚀 Uso Básico

### Processar PDFs Locais

```bash
python main.py
```

### Ingestão via E-mail

```bash
python run_ingestion.py
```

### Executar Testes

```bash
pytest tests/ -v
```

## 📊 Dados Extraídos

### NFSe

- CNPJ Prestador, Número da Nota, Data de Emissão, Valor Total

### Boletos

- CNPJ Beneficiário, Valor, Vencimento, Linha Digitável, Nosso Número, Referência NFSe

📖 Consulte a [documentação completa](./docs/) para detalhes.

## 🐳 Docker

```bash
# Build e execução
docker-compose up --build

# Ou use o Makefile
make docker-build
make docker-run
```

## To Do - Notas mentais

- [ ] Concertar/adicionar a logica de extração das NSFE pra funcionar com os casos falhos.
- [ ] Estudar os relatórios do PAF e refatorar as variáveis necessárias que eles pedem!
- [ ] Conseguir o acesso ao maior número de pdfs e a tabela de verdades já catalogada dos dados pra conferir se a extração do PDF está de fato funcionando.
- [ ] Verificar cada caso a fundo dos pdfs e avaliar possíveis estratégias para os casos onde o pdf em si não esta anexado no email (link de prefeitura ou redirecionador de terceiros).
- [ ] Verificar se o projeto roda corretamente em container de docker e testar local mesmo no docker desktop do windows.
- [ ] Quando o projeto estiver no estágio real pra primeira release ler git-futuro.md e pesquisar ferramentas/plugins/qualquer coisa que ajude a melhorar a maluquice que é os commits e tudo mais.

## To Do - Adequação aos Requisitos do PAF

### 🎯 Dados Prioritários para Extração

#### 📑 Identificação do Documento

- [X] **Número da NF/TF** - Já extraído para NFSe (`numero_nota`) e Boletos (`numero_documento`)
- [ ] **Série da NF** - Adicionar extração (não implementado)
- [ ] **Tipo de documento** - Implementar classificação: fatura/boleto/taxa/imposto
- [X] **Data de emissão** - Já extraído (`data_emissao`)

#### 💰 Dados Bancários e Pagamento

- [ ] **Forma de pagamento** - Adicionar detecção (PIX/Boleto/Depósito/Transferência)
- [ ] **Valor total** - Já extraído (`valor_total` e `valor_documento`)
- [X] **Data de vencimento** - Já extraído para boletos (`vencimento`), adicionar para NFSe
- [ ] **Dados bancários do beneficiário** - Extrair banco, agência, conta (se presente no documento)

#### 🏢 Classificação Contábil

- [ ] **Centro de custo** - Não presente em PDF (origem: área solicitante)
- [ ] **Classe de valor** - Não presente em PDF (origem: área solicitante)
- [ ] **Natureza da operação** - Extrair se mencionada no PDF
- [ ] **Conta contábil** - Não presente em PDF (classificação interna)

#### 📊 Impostos e Tributos (Prioridade Alta)

- [ ] **Base de cálculo ICMS** - Adicionar extração
- [ ] **Valor ICMS** - Adicionar extração
- [ ] **ISS (Imposto sobre Serviço)** - Adicionar extração para NFSe
- [ ] **PIS/COFINS** - Adicionar extração se aplicável
- [ ] **Retenções federais** - IR, INSS, CSLL (se houver)

#### 🔗 Rastreabilidade e Integração

- [ ] **Número do Pedido de Compra (PC)** - Adicionar extração (pode estar em campo de referência)
- [ ] **CNPJ do fornecedor** - Já extraído (`cnpj_prestador`, `cnpj_beneficiario`)
- [ ] **Razão Social do fornecedor** - Adicionar extração
- [ ] **Link do documento** - Implementar campo para URL da pasta no Drive
- [ ] **Histórico/Justificativa** - Campo manual (não extraível de PDF)

#### ⚙️ Validações Fiscais (TES/CFOP/CST)

- [ ] **CFOP (Código Fiscal)** - Adicionar extração se presente na NFSe
- [ ] **CST (Código de Situação Tributária)** - Adicionar extração
- [ ] **TES (Tipo Entrada/Saída)** - Não presente em PDF (classificação interna via planilha TES BASE SA)
- [ ] **NCM (Nomenclatura Comum do Mercosul)** - Adicionar extração se aplicável

### 🔧 Refatorações Técnicas Necessárias

#### 1. Modelo de Dados

- [ ] Criar classe `FiscalData` com campos adicionais:

  ```python
  @dataclass
  class FiscalData(DocumentData):
      serie_nf: Optional[str]
      tipo_documento: str  # fatura/boleto/taxa/imposto
      forma_pagamento: Optional[str]
      base_calculo_icms: Optional[Decimal]
      valor_icms: Optional[Decimal]
      valor_iss: Optional[Decimal]
      cfop: Optional[str]
      cst: Optional[str]
      numero_pedido_compra: Optional[str]
      razao_social_fornecedor: Optional[str]
      link_drive: Optional[str]
  ```

## Done

### 19/12/2025 - Dia 6

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

### 18/12/2025

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

### 17/12/2025

- [x] Configurar o email para testes em ambiente real de scraping
- [x] **Nota**: Email `scrapper.nfse@gmail.com` configurado com autenticação em `rafael.ferreira@soumaster.com.br` e Google Authenticator

### 16/12/2025

- [x] Estudar scraping de diferentes tipos de email
- [x] Terminar de organizar a documentação por completo

### 15/12/2025

- [x] Montar site da documentação (MkDocs)
- [x] Organizar estrutura do projeto

### 11/12/2025

- [x] Debugar PDFs para entender cada caso
- [x] Extração de dados para CSV baseados em PDFs de diferentes casos

## 🔍 Foco Atual de Desenvolvimento

- ✅ Validação de extração com 100% de taxa de sucesso em boletos
- 🔄 Extração de XML (próxima iteração)
- ✅ IMAP configurado e testado em ambiente real
- 🔄 Otimização de fila de processamento OCR

## 📈 Métricas de Qualidade

- **Taxa de Sucesso Boletos**: 100% (10/10 validados)
- **Taxa de Sucesso NFSe**: ~85% (em monitoramento)
- **Cobertura de Testes**: 43 testes unitários
- **Tempo de Processamento**:
  - Extração Nativa: ~2s/documento
  - Extração OCR: ~30s/documento

## ⚠️ Desafios e Soluções

### Regex Complexo

- **Problema**: Variações de layout entre municípios
- **Solução**: Biblioteca de padrões testados + `re.DOTALL` para layouts multi-linha
- **Ferramenta**: `scripts/debug_pdf.py` para validação rápida

### Performance OCR

- **Problema**: PDFs com imagem demoram ~30s
- **Planejamento**: Fila assíncrona para processamento paralelo (próxima fase)

### Vinculação NFSe-Boleto

- **Solução**: 3 estratégias (referência explícita, nº documento, cruzamento de dados)
- **Taxa de Sucesso**: ~90% de vinculação automática

## 📋 Arquitetura e Tecnologias

### Stack Tecnológico

- **Python 3.8+** - Linguagem principal
- **PDFPlumber** - Extração nativa de texto
- **Tesseract OCR** - Fallback para PDFs com imagem
- **IMAPClient** - Ingestão de e-mails
- **Pandas** - Manipulação de dados e exportação CSV
- **pytest** - Framework de testes
- **MkDocs** - Documentação técnica

### Princípios SOLID Implementados

- **SRP** - Separação de responsabilidades (FileSystemManager, AttachmentDownloader, DataExporter)
- **OCP** - Extensível sem modificação (classe base DocumentData)
- **LSP** - Estratégias intercambiáveis com comportamento consistente
- **DIP** - Injeção de dependências no processador principal
