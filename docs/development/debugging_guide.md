# Guia de Debug para Extração de PDFs e Lotes

Este guia apresenta o workflow e as ferramentas recomendadas para debugar problemas de extração, desde um único PDF até a lógica de correlação em lotes.

## Estrutura de Scripts de Debug

O projeto conta com uma estrutura organizada de scripts na pasta `scripts/`, categorizados por finalidade:

### 📊 **Análise de Dados e Relatórios**

- `analyze_admin_nfse.py` - Analisa casos de NFSEs classificadas como administrativas com valor zero
- `analyze_all_batches.py` - Processa todos os batches em `temp_email` e gera relatório comparativo
- `analyze_emails_no_attachment.py` - Analisa e-mails sem anexos para identificar padrões úteis
- `simple_list.py` - Lista simples de lotes problemáticos (outros > 0 e valor = 0)
- `list_problematic.py` - Versão mais completa com classificação de tipos de problemas
- `generate_report.py` - Converte relatório pyright JSON para markdown formatado

### 🔍 **Diagnóstico e Debug Específico**

- `inspect_pdf.py` - Inspeção rápida de PDFs para debug (mais prático)
- `diagnose_inbox_patterns.py` - Analisa padrões de e-mail na caixa de entrada para otimização
- `repro_extraction_failure.py` - Reproduz falhas de extração para análise

### 🧪 **Testes e Validação**

- `test_admin_detection.py` - Testa padrões de detecção de documentos administrativos
- `test_extractor_routing.py` - Testa qual extrator seria usado para um PDF específico
- `validate_extraction_rules.py` - Valida regras de extração contra casos conhecidos (substitui scripts de diagnóstico específicos)

### 🔧 **Utilitários e Operações**

- `export_to_sheets.py` - Exporta dados para Google Sheets
- `ingest_emails_no_attachment.py` - Ingestão de e-mails sem anexos para criação de avisos
- `consolidate_batches.py` - Consolida resultados de múltiplos batches
- `clean_dev.py` - Limpeza de arquivos temporários de desenvolvimento
- `_init_env.py` - Configuração de paths para importação de módulos
- `example_batch_processing.py` - Exemplo de processamento de lote completo

## Workflow de Debug Recomendado

### 1. **Problema com um PDF Individual**

**Use: `inspect_pdf.py` (primeira escolha) ou `debug_pdf_text.py`**

```bash
# Para debug rápido e prático
python scripts/inspect_pdf.py exemplo.pdf

# Para análise detalhada do texto extraído
python scripts/inspect_pdf.py exemplo.pdf --raw

# Para inspecionar campos específicos
python scripts/inspect_pdf.py nota_fiscal.pdf --fields fornecedor_nome valor_total vencimento

# Para teste de roteamento de extrator
python scripts/test_extractor_routing.py caminho/do/pdf.pdf
```

**Análise:**

- Verifique se o `[tipo]` detectado está correto
- Confirme se o `[extrator]` selecionado é apropriado
- Revise os campos extraídos vs. esperados
- Use `--raw` para ver o texto completo e ajustar regex

### 2. **Problema com Lotes (resultados no CSV)**

**Use: `list_problematic.py`, `simple_list.py` ou `check_problematic_pdfs.py`**

```bash
# Para lista completa de lotes problemáticos
python scripts/list_problematic.py

# Para versão simplificada
python scripts/simple_list.py

# Para análise detalhada dos PDFs problemáticos
python scripts/check_problematic_pdfs.py
```

**Análise:**

- Verifique se "outros > 0 e valor = 0" indica NFSEs/DANFEs mal classificadas
- Analise padrões de assuntos de e-mail
- Identifique fornecedores problemáticos recorrentes

### 3. **Problema de OCR ou Qualidade de Texto**

**Use: `inspect_pdf.py --raw` e `validate_extraction_rules.py`**

```bash
# Para debug específico de texto de PDF
python scripts/inspect_pdf.py arquivo.pdf --raw

# Para validar após ajustar regex
python scripts/validate_extraction_rules.py --batch-mode
```

**Análise:**

- Identifique caracteres problemáticos ('Ê' substituindo espaços)
- Normalize texto nos extratores (ex: `text.replace('Ê', ' ')`)
- Valide regras após modificações

### 4. **Problema de Ingestão ou Configuração**

**Use: `run_ingestion.py --status` e `diagnose_inbox_patterns.py`**

```bash
# Ver status do checkpoint e dados parciais
python run_ingestion.py --status

# Para diagnóstico de padrões de inbox
python scripts/diagnose_inbox_patterns.py --limit 100

# Exportar dados parciais se necessário
python run_ingestion.py --export-partial
```

## Scripts Chave para Casos Comuns

### Para debug rápido de um PDF suspeito:

```bash
python scripts/inspect_pdf.py arquivo_problematico.pdf --raw
```

### Para identificar lotes com problemas de classificação:

```bash
python scripts/simple_list.py
```

### Para verificar status do sistema e lotes pendentes:

```bash
python run_ingestion.py --status
```

### Para validar regras de extração após modificações:

```bash
python scripts/validate_extraction_rules.py --batch-mode
```

### Para testar detecção de documentos administrativos:

```bash
python scripts/test_admin_detection.py
```

## Estrutura de Diretórios para Debug

```
scrapper/
├── scripts/                    # Scripts de debug e utilidades
├── data/
│   ├── output/                # Relatórios gerados (CSV, JSON, MD)
│   │   ├── relatorio_lotes.csv
│   │   ├── pyright_report.json
│   │   └── pyright_report.md
│   ├── debug_output/          # Outputs de scripts de debug
│   └── cache/                 # Cache de processamento
├── temp_email/                # Lotes de e-mail processados
└── failed_cases_pdf/          # PDFs de casos de falha para análise
```

## Técnicas Avançadas de Debug

### 1. Extrair Texto Bruto com `repr()`

```python
import pdfplumber

with pdfplumber.open('caminho/do/arquivo.pdf') as pdf:
    page = pdf.pages[0]
    text = page.extract_text()
    print(repr(text))  # Mostra caracteres ocultos como \n, \t, espaços
```

### 2. Testar Regex Interativamente

```python
import re

# Testar padrão com texto problemático
text = "TOTALÊAÊPAGAR:ÊR$Ê29.250,00"  # Problema do caractere 'Ê'

# Padrão que falha
pattern1 = r'TOTAL A PAGAR.*?R\$\s*([\d.,]+)'
match1 = re.search(pattern1, text)
print(f"Match 1: {match1}")  # None

# Padrão corrigido para 'Ê'
pattern2 = r'TOTALÊAÊPAGAR.*?R\$\s*([\d.,]+)'
match2 = re.search(pattern2, text)
print(f"Match 2: {match2.group(1) if match2 else 'None'}")  # 29.250,00

# Normalizar texto primeiro
normalized = text.replace('Ê', ' ')
pattern3 = r'TOTAL A PAGAR.*?R\$\s*([\d.,]+)'
match3 = re.search(pattern3, normalized, re.IGNORECASE)
print(f"Match 3: {match3.group(1) if match3 else 'None'}")  # 29.250,00
```

### 3. Analisar CSV de Resultados com pandas

```python
import pandas as pd

# Carregar relatório de lotes
df = pd.read_csv('data/output/relatorio_lotes.csv', sep=';')

# Filtrar lotes problemáticos
problematicos = df[(df['outros'] > 0) & (df['valor_compra'] == 0)]
print(f"Lotes problemáticos: {len(problematicos)}")

# Analisar padrões de assunto
assuntos = problematicos['email_subject'].value_counts().head(10)
print("\nTop 10 assuntos problemáticos:")
print(assuntos)
```

## Referência Rápida por Tipo de Problema

| Problema                              | Script Primário                | Scripts Secundários              | Comando Exemplo                                            |
| ------------------------------------- | ------------------------------ | -------------------------------- | ---------------------------------------------------------- |
| **PDF não extrai campos**             | `inspect_pdf.py`               | `test_extractor_routing.py`      | `python scripts/inspect_pdf.py arquivo.pdf --raw`          |
| **Lote com status DIVERGENTE**        | `list_problematic.py`          | `check_problematic_pdfs.py`      | `python scripts/list_problematic.py`                       |
| **NFSE classificada como "outros"**   | `check_problematic_pdfs.py`    | `list_problematic.py`            | `python scripts/check_problematic_pdfs.py`                 |
| **Problema de caractere 'Ê' no OCR**  | `inspect_pdf.py --raw`         | `validate_extraction_rules.py`   | `python scripts/inspect_pdf.py arquivo.pdf --raw`          |
| **Erro de importação/ingestão**       | `run_ingestion.py --status`    | `validate_extraction_rules.py`   | `python run_ingestion.py --status`                         |
| **Validação após modificar extrator** | `validate_extraction_rules.py` | `test_extractor_routing.py`      | `python scripts/validate_extraction_rules.py --batch-mode` |
| **E-mails sem anexo úteis**           | `diagnose_inbox_patterns.py`   | `ingest_emails_no_attachment.py` | `python scripts/diagnose_inbox_patterns.py --limit 50`     |
| **Exportação para Google Sheets**     | `export_to_sheets.py`          | -                                | `python scripts/export_to_sheets.py`                       |

## Dicas de Produtividade

1. **Sempre comece com `inspect_pdf.py`** para problemas de extração individual
2. **Use `simple_list.py`** para visão rápida de lotes problemáticos
3. **Execute `validate_extraction_rules.py`** após modificar qualquer extrator
4. **Use `inspect_pdf.py --raw`** para problemas de qualidade de texto OCR, seguido de `validate_extraction_rules.py` para validar correções
5. **Analise padrões com `diagnose_inbox_patterns.py`** para otimizar filtros de ingestão

## Monitoramento Contínuo

Para monitorar a saúde do sistema:

```bash
# Validar todas as regras periodicamente
python scripts/validate_extraction_rules.py --batch-mode

# Analisar padrões de inbox para ajustar filtros
python scripts/diagnose_inbox_patterns.py --all --resume

# Gerar relatórios
python scripts/generate_report.py
```

Os scripts estão organizados para suportar debug desde problemas pontuais até análise sistêmica, sempre com foco em identificar a causa raiz e fornecer recomendações acionáveis.
