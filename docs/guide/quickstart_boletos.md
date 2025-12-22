# Quick Start: Processamento de Boletos

## Teste Rápido

### 1. Testar o Extrator de Boletos

```powershell
python scripts/test_boleto_extractor.py
```

**Saída esperada:**

- ✅ BoletoExtractor reconheceu o boleto
- ✅ BoletoExtractor corretamente rejeitou a NFSe
- ✅ GenericExtractor reconheceu a NFSe

### 2. Executar Processamento Completo

```powershell
python run_ingestion.py
```

**O que acontece:**

1. Conecta ao email configurado
2. Baixa anexos PDF
3. Classifica automaticamente (NFSe ou Boleto)
4. Extrai dados específicos
5. Gera dois CSVs separados

**Arquivos gerados:**

- `data/output/relatorio_nfse.csv`
- `data/output/relatorio_boletos.csv`

### 3. Analisar Resultados

```powershell
python scripts/analyze_boletos.py
```

**O script mostra:**

- 📊 Estatísticas gerais (totais, médias)
- 🔗 Análise de vinculação (3 métodos)
- ⚠️ Alertas de vencimento
- 👥 Top fornecedores

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

## Vinculação Manual

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
3. Execute o teste: `python scripts/test_boleto_extractor.py`

### Problema: Boletos sendo identificados como NFSe

**Solução:**

O `BoletoExtractor` verifica automaticamente. Se houver problema:

1. Verifique o score de palavras-chave em [extractors/boleto.py](extractors/boleto.py#L27)
2. Ajuste os thresholds se necessário

### Problema: Dados não sendo extraídos corretamente

**Solução:**

1. Verifique o arquivo em `data/debug_output/`
2. Ajuste as regex em `BoletoExtractor._extract_*()` conforme necessário
3. Teste com: `python scripts/test_boleto_extractor.py`

## Próximos Passos

1. **Adicione novos extratores** - Ver [docs/guide/extending.md](docs/guide/extending.md)
2. **Customize os campos** - Edite [core/models.py](core/models.py)
3. **Automatize alertas** - Use `analyze_boletos.py` como base
4. **Integre com sistemas** - Importe os CSVs no seu ERP/sistema financeiro

## Links Úteis

- [Documentação Completa de Boletos](docs/guide/boletos.md)
- [Como Estender o Sistema](docs/guide/extending.md)
- [Arquitetura do Sistema](docs/research/architecture_pdf_extraction.md)
