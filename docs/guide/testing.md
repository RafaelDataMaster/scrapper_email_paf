# Guia de Testes Automatizados

Este guia descreve como validar e testar o sistema de extração de documentos fiscais, garantindo que as regras de extração funcionem corretamente e que modificações não causem regressões.

## Visão Geral

O sistema inclui várias ferramentas de teste e validação:

1. **Validação de regras de extração** - Testa todos os extratores contra PDFs de referência
2. **Testes de integração** - Valida o fluxo completo de processamento
3. **Testes de performance** - Mede tempo de extração e uso de recursos
4. **Monitoramento de qualidade** - Analisa taxa de sucesso em dados reais

## Validação de Regras de Extração

A ferramenta principal para validação é o script `validate_extraction_rules.py`.

### Testes Básicos

```bash
# Validar regras básicas (failed_cases_pdf/)
python scripts/validate_extraction_rules.py

# Modo batch (lotes com metadata.json)
python scripts/validate_extraction_rules.py --batch-mode

# Validação completa com correlação
python scripts/validate_extraction_rules.py --batch-mode --apply-correlation

# Gerar relatório detalhado
python scripts/validate_extraction_rules.py --report
```

### Outputs Gerados

O script cria CSVs detalhados em `data/debug_output/`:

| Arquivo                      | Descrição                        |
| ---------------------------- | -------------------------------- |
| `boletos_sucesso_debug.csv`  | Boletos processados com sucesso  |
| `boletos_falha_debug.csv`    | Boletos que falharam na extração |
| `danfes_sucesso_debug.csv`   | DANFEs processados com sucesso   |
| `danfes_falha_debug.csv`     | DANFEs que falharam na extração  |
| `nfses_sucesso_debug.csv`    | NFSEs processadas com sucesso    |
| `nfses_falha_debug.csv`      | NFSEs que falharam na extração   |
| `outros_sucesso_debug.csv`   | Documentos "outros" processados  |
| `extractors_performance.csv` | Tempo de execução por extrator   |

### Interpretando os Resultados

1. **Taxa de sucesso**: `sucesso / (sucesso + falha)`
2. **Campos problemáticos**: Campos frequentemente vazios ou incorretos
3. **Extratores lentos**: Extratores com tempo médio de execução alto
4. **Padrões de falha**: PDFs com problemas semelhantes (OCR, layout, etc.)

## Testes de Extratores

### Testar um Extrator Específico

```bash
# Testar o extrator de boletos
python scripts/test_extractor_routing.py data/test/boletos/exemplo.pdf

# Testar com texto OCR
python scripts/test_extractor_routing.py --texto caminho/do/pdf.pdf

# Testar múltiplos PDFs
find data/test/boletos -name "*.pdf" | xargs -I {} python scripts/test_extractor_routing.py {}
```

### Criar Novos Casos de Teste

1. **Colete PDFs representativos** em `data/test/<tipo>/`
2. **Execute validação**: `python scripts/validate_extraction_rules.py`
3. **Analise falhas**: Revise `data/debug_output/*_falha_debug.csv`
4. **Ajuste extratores**: Modifique regex ou lógica de extração
5. **Revalide**: Execute novamente para garantir correção

## Testes de Processamento em Lote

### Debug de Lotes Completos

```bash
# Analisar um lote específico
python run_ingestion.py --batch-folder temp_email/email_20260105_125518_4e51c5e2

# Identificar lotes problemáticos
python scripts/list_problematic.py

# Lista simples de problemas
python scripts/simple_list.py
```

### Validação de Correlação

A correlação entre DANFE e Boleto pode ser testada com:

```python
from core.correlation_service import CorrelationService

service = CorrelationService()
result = service.correlate(batch_documents, email_metadata)

print(f"Status: {result.status}")
print(f"Divergência: {result.divergencia}")
print(f"Documentos correlacionados: {len(result.enriched_documents)}")
```

## Testes de Performance

### Benchmark de Extratores

```bash
# Medir tempo de extração
python scripts/validate_extraction_rules.py --benchmark

# Limitar tempo máximo por PDF
python scripts/validate_extraction_rules.py --timeout 10

# Testar com diferentes estratégias de OCR
python scripts/validate_extraction_rules.py --strategy ocr
python scripts/validate_extraction_rules.py --strategy native
```

### Métricas de Performance

| Métrica                    | Alvo          | Como Medir                   |
| -------------------------- | ------------- | ---------------------------- |
| Tempo médio de extração    | < 5s por PDF  | `extractors_performance.csv` |
| Taxa de sucesso            | > 95%         | CSVs de sucesso/falha        |
| Uso de memória             | < 500MB       | Monitorar durante execução   |
| Tempo de correlacionamento | < 1s por lote | Logs do `CorrelationService` |

## Testes de Integração

### Pipeline Completo

```bash
# Pipeline completo (ingestão + processamento + exportação)
python run_ingestion.py --test-mode

# Testar apenas extração (sem enviar e-mails)
python run_ingestion.py --dry-run

# Validar exportação para Google Sheets
python scripts/export_to_sheets.py --dry-run
```

### Testes com Dados Reais

1. **Prepare dados de teste** em `temp_email/test_batch/`
2. **Execute processamento**: `python run_ingestion.py --batch-folder temp_email/test_batch`
3. **Verifique resultados**: `data/output/relatorio_lotes.csv`
4. **Compare com esperado**: Valide campos críticos (valor, vencimento, fornecedor)

## Monitoramento Contínuo

### Scripts de Análise Periódica

```bash
# Identificar padrões de falha
python scripts/check_problematic_pdfs.py

# Monitorar qualidade de OCR
python scripts/inspect_pdf.py arquivo.pdf --raw
python scripts/validate_extraction_rules.py --batch-mode

# Analisar padrões de e-mail
python scripts/diagnose_inbox_patterns.py --limit 100
```

### Métricas de Qualidade

| Métrica                      | Como Calcular                              | Frequência   |
| ---------------------------- | ------------------------------------------ | ------------ |
| Taxa de extração completa    | `campos_preenchidos / campos_totais`       | Diária       |
| Taxa de correlação           | `lotes_correlacionados / lotes_totais`     | Por execução |
| Tempo médio de processamento | `soma_tempos / lotes_processados`          | Semanal      |
| Taxa de falsos positivos     | `outros_mal_classificados / outros_totais` | Mensal       |

## Testes após Modificações

### Checklist de Validação

Antes de considerar uma modificação como concluída:

1. [ ] **Testes unitários** passam: `pytest tests/test_extractors.py`
2. [ ] **Validação de regras** sem regressões: `python scripts/validate_extraction_rules.py --batch-mode`
3. [ ] **Performance** dentro dos limites: Verificar `extractors_performance.csv`
4. [ ] **Integração** funciona: `python run_ingestion.py --test-mode`
5. [ ] **Documentação** atualizada: Atualizar docstrings e guias relevantes

### Fluxo de Trabalho para Novos Extratores

1. **Criar extrator** em `extractors/nome_do_extrator.py`
2. **Adicionar testes** em `tests/test_extractors.py`
3. **Validar com PDFs reais** em `data/test/nome_do_extrator/`
4. **Executar validação completa**: `python scripts/validate_extraction_rules.py`
5. **Monitorar em produção**: Analisar logs e métricas após deploy

## Solução de Problemas Comuns

### Problema: Validação falha em muitos PDFs

**Possíveis causas:**

- Regex muito específica
- Problemas de OCR
- Layout de PDF incomum

**Solução:**

1. Use `python scripts/inspect_pdf.py arquivo.pdf --raw` para ver texto
2. Ajuste regex no extrator correspondente
3. Teste com `python scripts/test_extractor_routing.py`

### Problema: Performance ruim

**Solução:**

1. Identifique extratores lentos: `extractors_performance.csv`
2. Considere cache de texto extraído
3. Avalie uso de OCR apenas quando necessário

### Problema: Correlação incorreta

**Solução:**

1. Use `python run_ingestion.py --batch-folder <pasta>` para analisar lote específico
2. Verifique `metadata.json` para contexto
3. Ajuste regras no `CorrelationService`

## Integração com CI/CD

### Exemplo de Pipeline

```yaml
# .github/workflows/validate.yml
name: Validate Extraction Rules

on:
    push:
        branches: [main]
    pull_request:
        branches: [main]

jobs:
    validate:
        runs-on: ubuntu-latest

        steps:
            - uses: actions/checkout@v3

            - name: Set up Python
              uses: actions/setup-python@v4
              with:
                  python-version: "3.10"

            - name: Install dependencies
              run: |
                  pip install -r requirements.txt

            - name: Run validation
              run: |
                  python scripts/validate_extraction_rules.py --batch-mode

            - name: Check for regressions
              run: |
                  # Verificar taxa de sucesso no relatório
                  python scripts/generate_report.py
```

### Baseline de Performance

Mantenha um arquivo `data/baseline/performance_baseline.json` com:

```json
{
    "extraction_success_rate": 0.95,
    "average_extraction_time": 3.5,
    "correlation_success_rate": 0.98,
    "test_cases_count": 150
}
```

## Referências

- [Guia de Debug](../development/debugging_guide.md) - Técnicas avançadas de debug
- [Guia de Uso](usage.md) - Processar PDFs locais
- [Migração Batch](../development/MIGRATION_BATCH_PROCESSING.md) - Migrar para v0.2.x
- [Como Estender](extending.md) - Criar novos extratores
- [API Reference](../api/overview.md) - Documentação técnica completa

---

**Última atualização:** 2025-01-21  
**Versão:** v0.3.x (Google Sheets Export)
