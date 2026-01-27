# Documentação de Debugging e Diagnóstico

Esta seção contém documentação e referências para debugging, diagnóstico e solução de problemas no sistema de extração de documentos fiscais.

## Visão Geral

O sistema conta com uma suite completa de scripts organizados na pasta `scripts/` para auxiliar em todas as fases de debugging, desde problemas pontuais até análise sistêmica.

## Documentos Disponíveis

| Documento                                                                  | Descrição                                                              |
| -------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| **[scripts_quick_reference.md](scripts_quick_reference.md)**               | Referência rápida de todos os scripts de debug com comandos essenciais |
| **[../development/debugging_guide.md](../development/debugging_guide.md)** | Guia completo de debugging com workflows detalhados                    |

## Script Principal de Ingestão

O **`run_ingestion.py`** é o script principal de orquestração do sistema:

```bash
# Ingestão unificada completa (COM e SEM anexos)
python run_ingestion.py

# Apenas e-mails COM anexos
python run_ingestion.py --only-attachments

# Reprocessar lotes existentes
python run_ingestion.py --reprocess

# Reprocessar lotes que deram timeout
python run_ingestion.py --reprocess-timeouts

# Processar pasta específica
python run_ingestion.py --batch-folder temp_email/email_123

# Ver status do checkpoint
python run_ingestion.py --status

# Exportar dados parciais
python run_ingestion.py --export-partial

# Limpar lotes antigos (>48h)
python run_ingestion.py --cleanup
```

## Categorias de Scripts

Os scripts estão organizados em quatro categorias principais:

### 📊 Análise de Dados e Relatórios

Scripts para análise de lotes problemáticos, geração de relatórios e identificação de padrões.

- `simple_list.py` - Lista simples de lotes problemáticos (outros > 0 e valor = 0)
- `list_problematic.py` - Versão mais completa com classificação de tipos de problemas
- `check_problematic_pdfs.py` - Analisa PDFs de casos problemáticos onde "outros" têm valor zero
- `generate_report.py` - Converte relatório pyright JSON para markdown formatado

### 🔍 Diagnóstico e Debug Específico

Scripts para diagnóstico de problemas individuais, análise de texto e qualidade OCR.

- `inspect_pdf.py` - Inspeção rápida de PDFs (busca automática em `failed_cases_pdf/` e `temp_email/`)
- `diagnose_inbox_patterns.py` - Analisa padrões de e-mail na caixa de entrada
- `repro_extraction_failure.py` - Reproduz falhas de extração para análise

### 🧪 Testes e Validação

Scripts para teste de extratores, validação de regras e detecção de documentos.

- `test_extractor_routing.py` - Testa qual extrator seria usado para um PDF específico
- `validate_extraction_rules.py` - Valida regras de extração contra casos conhecidos (substitui scripts de diagnóstico específicos)
- `test_admin_detection.py` - Testa padrões de detecção de documentos administrativos

### 🔧 Utilitários e Operações

Scripts para exportação, ingestão, consolidação e outras operações.

- `export_to_sheets.py` - Exporta dados para Google Sheets
- `ingest_emails_no_attachment.py` - Ingestão de e-mails sem anexos para criação de avisos
- `consolidate_batches.py` - Consolida resultados de múltiplos batches
- `clean_dev.py` - Limpeza de arquivos temporários de desenvolvimento
- `_init_env.py` - Configuração de paths para importação de módulos
- `example_batch_processing.py` - Exemplo de processamento de lote completo

## Fluxos de Trabalho Comuns

### Para um PDF que não extrai campos corretamente:

1. `python scripts/inspect_pdf.py arquivo.pdf --raw`
2. Analise o texto bruto e ajuste regex no extrator correspondente
3. `python scripts/validate_extraction_rules.py --batch-mode` para validar

### Para múltiplos lotes com problemas no CSV final:

1. `python scripts/simple_list.py` para visão rápida
2. `python scripts/list_problematic.py` para análise detalhada
3. `python scripts/check_problematic_pdfs.py` para análise dos PDFs
4. `python run_ingestion.py --reprocess` para reprocessar lotes problemáticos

### Para problemas de qualidade de texto (OCR):

1. `python scripts/inspect_pdf.py arquivo.pdf --raw` para análise do texto extraído
2. Considere normalizar texto nos extratores (ex: `text.replace('Ê', ' ')`)
3. Use `python scripts/validate_extraction_rules.py` para validar correções

### Para reprocessar após interrupção:

1. `python run_ingestion.py --status` para ver estado atual
2. `python run_ingestion.py` resume automaticamente do checkpoint
3. Ou `python run_ingestion.py --export-partial` para exportar dados salvos

## Dicas Importantes

1. **Sempre comece com `run_ingestion.py --status`** - Verifique se há dados parciais pendentes
2. **Use `inspect_pdf.py` para debug de PDFs** - Busca automaticamente em `failed_cases_pdf/` e `temp_email/`
3. **Use `simple_list.py` para visão geral** - Rápido e direto, mostra batch IDs problemáticos
4. **Valide após cada modificação** - Execute `validate_extraction_rules.py` após modificar extratores
5. **Analise padrões recorrentes** - Use `diagnose_inbox_patterns.py` para identificar e-mails úteis

## Monitoramento Contínuo

Para manter a saúde do sistema:

```bash
# Validação completa das regras
python scripts/validate_extraction_rules.py --batch-mode

# Análise de padrões de inbox (ajustar filtros)
python scripts/diagnose_inbox_patterns.py --all --resume

# Limpeza de desenvolvimento
python scripts/clean_dev.py

# Geração de relatórios
python scripts/generate_report.py
```

## Scripts Removidos (Funcionalidade Migrada)

Os seguintes scripts foram removidos por terem funcionalidades cobertas por outros scripts:

| Script Removido                   | Substituído Por                                         |
| --------------------------------- | ------------------------------------------------------- |
| `analyze_admin_nfse.py`           | `check_problematic_pdfs.py`                             |
| `analyze_all_batches.py`          | `list_problematic.py` + `simple_list.py`                |
| `analyze_emails_no_attachment.py` | `diagnose_inbox_patterns.py`                            |
| `debug_pdf_text.py`               | `inspect_pdf.py --raw`                                  |
| `debug_batch.py`                  | `run_ingestion.py --batch-folder`                       |
| `diagnose_failures.py`            | `validate_extraction_rules.py`                          |
| `diagnose_ocr_issue.py`           | `validate_extraction_rules.py` + `inspect_pdf.py --raw` |
| `diagnose_import_issues.py`       | Validação automática no `run_ingestion.py`              |
| `demo_pairing.py`                 | Documentação em `run_ingestion.py` e exemplos           |
| `repro_extraction_failure.py`     | `validate_extraction_rules.py` com casos de teste       |

## Contribuindo com Novos Scripts

Ao criar novos scripts de debug, siga estas diretrizes:

1. **Nome descritivo**: Use nomes que indiquem claramente a função (ex: `check_problematic_pdfs.py`)
2. **Documentação completa**: Inclua docstring com exemplos de uso no topo do arquivo
3. **Argumentos de linha de comando**: Use `argparse` para opções flexíveis
4. **Output estruturado**: Produza resultados fáceis de ler e processar
5. **Tratamento de erros**: Capture e relata erros de forma útil para debugging

## Estrutura de Diretórios

```
scrapper/
├── scripts/                    # Todos os scripts de debug
├── data/
│   ├── output/                # Relatórios (relatorio_lotes.csv, etc.)
│   ├── debug_output/          # Outputs de scripts de debug
│   └── cache/                 # Cache de processamento
├── temp_email/                # Lotes de e-mail processados
├── failed_cases_pdf/          # PDFs de falha para análise
└── tests/                     # Testes unitários
```

---

**Última atualização**: 2026-01-27  
**Localização**: `scrapper/scripts/` e `scrapper/docs/debug/`
