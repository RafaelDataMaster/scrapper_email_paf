# Script de Debug de Batch Processing

## ⚠️ Script Removido

O script `debug_batch.py` foi **removido** do projeto. Sua funcionalidade foi migrada para o script principal `run_ingestion.py`.

## 🔄 Alternativa Atual

Use o `run_ingestion.py` com a flag `--batch-folder` para processar ou reprocessar um lote específico:

```bash
# Processar um lote específico
python run_ingestion.py --batch-folder temp_email/email_20260105_125518_4e51c5e2

# Reprocessar um lote específico
python run_ingestion.py --batch-folder temp_email/email_20260105_125518_4e51c5e2 --reprocess

# Ver status do processamento
python run_ingestion.py --status

# Exportar resultados parciais
python run_ingestion.py --export-partial
```

## 🎯 Outras Ferramentas de Debug

Para análise detalhada de lotes, use os scripts disponíveis:

| Script                         | Propósito                              |
| ------------------------------ | -------------------------------------- |
| `inspect_pdf.py`               | Inspeção rápida de PDFs individuais    |
| `list_problematic.py`          | Lista detalhada de lotes problemáticos |
| `simple_list.py`               | Visão rápida de lotes com problemas    |
| `check_problematic_pdfs.py`    | Análise de PDFs problemáticos          |
| `validate_extraction_rules.py` | Validação completa das regras          |

## 📋 Exemplos de Uso

### Inspecionar um PDF específico:

```bash
python scripts/inspect_pdf.py temp_email/email_xxx/arquivo.pdf --raw
```

### Listar lotes problemáticos:

```bash
python scripts/simple_list.py
```

### Validar regras em modo batch:

```bash
python scripts/validate_extraction_rules.py --batch-mode --apply-correlation
```

## 📚 Referências

- [Guia de Debug](../development/debugging_guide.md) - Técnicas avançadas de debug
- [Referência Rápida de Scripts](../debug/scripts_quick_reference.md) - Comandos essenciais
- [Guia de Uso](../guide/usage.md) - Processar PDFs locais

---

**Nota**: Esta documentação é mantida para referência histórica. Use as ferramentas atuais mencionadas acima.

**Última atualização**: 2026-01-27
