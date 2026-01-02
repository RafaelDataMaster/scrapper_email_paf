# Quick Start: Processamento de Boletos

## Teste Rápido

### 1. Inspecionar um Boleto

```powershell
# Busca automática pelo nome do arquivo
python scripts/inspect_pdf.py boleto_exemplo.pdf

# Ver campos específicos de boleto
python scripts/inspect_pdf.py boleto.pdf --fields valor_documento vencimento cnpj_beneficiario linha_digitavel

# Ver texto bruto (para debug de regex)
python scripts/inspect_pdf.py boleto.pdf --raw
```

**Saída esperada:**

- ✅ Tipo detectado: BOLETO
- ✅ Campos extraídos: valor, vencimento, CNPJ, linha digitável, etc.

### 2. Validar Regras de Extração

```powershell
# Modo legado (PDFs soltos)
python scripts/validate_extraction_rules.py

# Modo batch (lotes com metadata.json)
python scripts/validate_extraction_rules.py --batch-mode --apply-correlation
```

### 3. Executar Processamento Completo

```powershell
python run_ingestion.py
```

**O que acontece:**

1. Conecta ao email configurado
2. Baixa anexos PDF e cria lotes (pastas com `metadata.json`)
3. Classifica automaticamente (NFSe, DANFE ou Boleto)
4. Extrai dados específicos
5. Correlaciona documentos do mesmo lote (DANFE ↔ Boleto)
6. Gera CSVs separados por tipo

**Arquivos gerados:**

- `data/output/relatorio_nfse.csv`
- `data/output/relatorio_boletos.csv`
- `data/output/relatorio_danfe.csv`

## Consultar os CSVs

### Python

```python
import pandas as pd

# Carregar dados
df_nfse = pd.read_csv('data/output/relatorio_nfse.csv')
df_boleto = pd.read_csv('data/output/relatorio_boletos.csv')

# Ver primeiras linhas
print(df_nfse.head())
print(df_boleto.head())

# Estatísticas
print(f"Total NFSe: {len(df_nfse)}")
print(f"Total Boletos: {len(df_boleto)}")
print(f"Soma NFSe: R$ {df_nfse['valor_total'].sum():,.2f}")
print(f"Soma Boletos: R$ {df_boleto['valor_documento'].sum():,.2f}")
```

### Excel

Abra os arquivos diretamente no Excel:

- `data/output/relatorio_nfse.csv`
- `data/output/relatorio_boletos.csv`

## Correlação Automática (v2.x)

A partir da v2.x, boletos e notas do mesmo e-mail são correlacionados automaticamente:

```python
from core.batch_processor import process_email_batch
from core.correlation_service import correlate_batch
from core.metadata import EmailMetadata
from pathlib import Path

# Processar lote
batch_folder = Path("temp_email/email_123")
result = process_email_batch(batch_folder)
metadata = EmailMetadata.load(batch_folder)

# Correlacionar
correlation = correlate_batch(result, metadata)

print(f"Status: {correlation.status}")  # OK, DIVERGENTE ou ORFAO
print(f"Valor Total Lote: R$ {correlation.valor_total_lote:.2f}")

# Documentos enriquecidos (com campos herdados)
for doc in correlation.enriched_documents:
    print(f"{doc.arquivo_origem}: {doc.status_conciliacao}")
```

## Vinculação Manual (v1.x - Legado)

### Método 1: Por Referência Explícita

```python
import pandas as pd

df_nfse = pd.read_csv('data/output/relatorio_nfse.csv')
df_boleto = pd.read_csv('data/output/relatorio_boletos.csv')

# Vincular
merged = pd.merge(
    df_boleto,
    df_nfse,
    left_on='referencia_nfse',
    right_on='numero_nota',
    how='left'
)

# Salvar resultado
merged.to_csv('data/output/boletos_vinculados.csv', index=False)
```

### Método 2: Por Número do Documento

```python
merged = pd.merge(
    df_boleto,
    df_nfse,
    left_on='numero_documento',
    right_on='numero_nota',
    how='left'
)
```

### Método 3: Por CNPJ + Valor

```python
# Normalizar valores
df_boleto['valor_norm'] = df_boleto['valor_documento'].round(2)
df_nfse['valor_norm'] = df_nfse['valor_total'].round(2)

# Vincular
merged = pd.merge(
    df_boleto,
    df_nfse,
    left_on=['cnpj_beneficiario', 'valor_norm'],
    right_on=['cnpj_prestador', 'valor_norm'],
    how='left'
)
```

## Filtros Úteis

### Boletos Vencendo Esta Semana

```python
from datetime import datetime, timedelta

df_boleto['vencimento'] = pd.to_datetime(df_boleto['vencimento'])
hoje = datetime.now()
limite = hoje + timedelta(days=7)

proximos = df_boleto[
    (df_boleto['vencimento'] >= hoje) &
    (df_boleto['vencimento'] <= limite)
]

print(proximos[['cnpj_beneficiario', 'valor_documento', 'vencimento']])
```

### Boletos Sem NFSe Vinculada

```python
# Boletos sem referência
sem_ref = df_boleto[df_boleto['referencia_nfse'].isna()]

print(f"Boletos sem referência: {len(sem_ref)}")
print(sem_ref[['arquivo_origem', 'cnpj_beneficiario', 'valor_documento']])
```

### NFSe de um Fornecedor Específico

```python
cnpj_busca = "12.345.678/0001-90"

nfse_fornecedor = df_nfse[df_nfse['cnpj_prestador'] == cnpj_busca]
print(f"NFSe do CNPJ {cnpj_busca}: {len(nfse_fornecedor)}")
print(f"Valor total: R$ {nfse_fornecedor['valor_total'].sum():,.2f}")
```

## Troubleshooting

### Problema: CSV vazio ou sem dados

**Solução:**

1. Verifique se há PDFs na pasta de entrada
2. Confirme que o email está configurado corretamente
3. Inspecione um PDF: `python scripts/inspect_pdf.py arquivo.pdf`

### Problema: Boletos sendo identificados como NFSe

**Solução:**

O `BoletoExtractor` verifica automaticamente. Se houver problema:

1. Inspecione o PDF: `python scripts/inspect_pdf.py boleto.pdf`
2. Verifique o tipo detectado no output
3. Ajuste os thresholds em `extractors/boleto.py` se necessário

### Problema: Dados não sendo extraídos corretamente

**Solução:**

1. Inspecione o PDF com texto bruto: `python scripts/inspect_pdf.py arquivo.pdf --raw`
2. Verifique o arquivo em `data/debug_output/`
3. Ajuste as regex em `BoletoExtractor._extract_*()` conforme necessário

### Problema: Correlação não funcionando

**Solução:**

1. Verifique se os documentos estão na mesma pasta de lote
2. Confirme que existe `metadata.json` na pasta
3. Rode com correlação explícita:

```bash
python scripts/validate_extraction_rules.py --batch-mode --apply-correlation
```

## Próximos Passos

1. **Adicione novos extratores** - Ver [Como Estender](extending.md)
2. **Customize os campos** - Edite `core/models.py`
3. **Integre com sistemas** - Importe os CSVs no seu ERP/sistema financeiro
4. **Migre para batch** - Ver [Migração Batch](../MIGRATION_BATCH_PROCESSING.md)

## Links Úteis

- [Documentação Completa de Boletos](boletos.md)
- [Como Estender o Sistema](extending.md)
- [Guia de Debug](../development/debugging_guide.md)
- [Migração Batch Processing](../MIGRATION_BATCH_PROCESSING.md)
