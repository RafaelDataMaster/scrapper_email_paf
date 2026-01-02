# Guia de Uso: Processamento de Boletos

## Visão Geral

O sistema agora processa **Notas Fiscais (NFSe)** e **Boletos Bancários** automaticamente, gerando relatórios separados para cada tipo de documento.

## Dados Extraídos

### NFSe (Nota Fiscal de Serviço Eletrônica)

- CNPJ do Prestador
- Número da Nota
- Data de Emissão
- Valor Total

### Boletos Bancários

- CNPJ do Beneficiário (quem recebe)
- Valor do Documento
- Data de Vencimento
- Número do Documento
- Linha Digitável (código de barras)
- Nosso Número
- Referência à NFSe (quando disponível)

## Regra EMPRESA vs FORNECEDOR (MVP PAF)

Para reduzir ambiguidades nos boletos, usamos uma regra determinística baseada no cadastro interno:

- **EMPRESA**: se algum CNPJ do nosso cadastro (`config/empresas.py`) aparece no documento, ele define a coluna EMPRESA.
- **FORNECEDOR**: a entidade que recebe (beneficiário/cedente) ou qualquer CNPJ/nome que não seja do nosso cadastro.

Isso evita que a própria empresa (nós) apareça como fornecedor por erro de layout.

## Robustez de classificação (OCR / texto “quebrado”)

Alguns PDFs (principalmente híbridos) podem corromper palavras-chave como “Beneficiário”/“Número” e quebrar linhas no meio das palavras.
O classificador de boleto foi ajustado para ser tolerante a:

- acentos
- quebras de linha no meio de palavras
- caracteres perdidos (ex: “NÚMERO” → “NMERO”)

## Como Usar

### 1. Processamento Automático

Execute o script de ingestão normalmente:

```powershell
python run_ingestion.py
```

O sistema irá:

1. Conectar ao email e baixar anexos
2. Classificar automaticamente cada PDF (NFSe ou Boleto)
3. Extrair dados específicos de cada tipo
4. Gerar dois CSVs separados

### 2. Arquivos de Saída

Após o processamento, você encontrará:

- **`data/output/relatorio_nfse.csv`** - Todas as notas fiscais
- **`data/output/relatorio_boletos.csv`** - Todos os boletos

## Vinculando Boletos e NFSe

### Método 1: Referência Explícita

Alguns boletos incluem o número da NFSe na descrição:

```python
import pandas as pd

df_nfse = pd.read_csv('data/output/relatorio_nfse.csv')
df_boleto = pd.read_csv('data/output/relatorio_boletos.csv')

# Vincular por referência explícita no boleto
merged = pd.merge(
    df_boleto,
    df_nfse,
    left_on='referencia_nfse',
    right_on='numero_nota',
    how='left',
    suffixes=('_boleto', '_nfse')
)

print(merged[['arquivo_origem_boleto', 'numero_nota', 'valor_documento', 'valor_total']])
```

### Método 2: Número do Documento

Muitos fornecedores usam o número da NF como número do documento:

```python
# Vincular por número do documento
merged = pd.merge(
    df_boleto,
    df_nfse,
    left_on='numero_documento',
    right_on='numero_nota',
    how='left'
)
```

### Método 3: Cruzamento por Dados

Quando não há referência direta:

```python
# Normalizar valores para comparação
df_boleto['valor_normalizado'] = df_boleto['valor_documento'].round(2)
df_nfse['valor_normalizado'] = df_nfse['valor_total'].round(2)

# Buscar correspondências por CNPJ e Valor
merged = pd.merge(
    df_boleto,
    df_nfse,
    left_on=['cnpj_beneficiario', 'valor_normalizado'],
    right_on=['cnpj_prestador', 'valor_normalizado'],
    how='left'
)

# Filtrar por diferença de data (ex: boleto vence até 30 dias após emissão da NF)
merged['vencimento'] = pd.to_datetime(merged['vencimento'])
merged['data_emissao'] = pd.to_datetime(merged['data_emissao'])
merged['dias_diff'] = (merged['vencimento'] - merged['data_emissao']).dt.days

# Manter apenas vinculações plausíveis
merged = merged[(merged['dias_diff'] >= 0) & (merged['dias_diff'] <= 30)]
```

## Identificando Boletos sem NFSe Correspondente

Encontre boletos que não têm NFSe vinculada:

```python
# Boletos sem referência explícita
boletos_sem_ref = df_boleto[df_boleto['referencia_nfse'].isna()]

print(f"Total de boletos: {len(df_boleto)}")
print(f"Boletos sem referência à NF: {len(boletos_sem_ref)}")
print(f"Percentual: {len(boletos_sem_ref)/len(df_boleto)*100:.1f}%")
```

## Relatório de Cobrança

Crie um relatório consolidado de cobranças:

```python
# Agrupar por beneficiário
cobrancas = df_boleto.groupby('cnpj_beneficiario').agg({
    'valor_documento': 'sum',
    'arquivo_origem': 'count',
    'vencimento': 'min'
}).rename(columns={
    'valor_documento': 'valor_total',
    'arquivo_origem': 'qtd_boletos',
    'vencimento': 'proximo_vencimento'
})

print(cobrancas.sort_values('valor_total', ascending=False))
```

## Alertas de Vencimento

Identifique boletos próximos ao vencimento:

```python
from datetime import datetime, timedelta

df_boleto['vencimento'] = pd.to_datetime(df_boleto['vencimento'])
hoje = datetime.now()
limite = hoje + timedelta(days=7)

# Boletos vencendo nos próximos 7 dias
proximos = df_boleto[
    (df_boleto['vencimento'] >= hoje) &
    (df_boleto['vencimento'] <= limite)
]

print(f"\n⚠️ {len(proximos)} boletos vencem nos próximos 7 dias:")
print(proximos[['cnpj_beneficiario', 'valor_documento', 'vencimento', 'arquivo_origem']])
```

## Estatísticas

Obtenha estatísticas sobre os documentos processados:

```python
print("\n📊 ESTATÍSTICAS DE PROCESSAMENTO\n")
print(f"NFSe processadas: {len(df_nfse)}")
print(f"Boletos processados: {len(df_boleto)}")
print(f"\nValor total NFSe: R$ {df_nfse['valor_total'].sum():,.2f}")
print(f"Valor total Boletos: R$ {df_boleto['valor_documento'].sum():,.2f}")
print(f"\nMédia NFSe: R$ {df_nfse['valor_total'].mean():,.2f}")
print(f"Média Boletos: R$ {df_boleto['valor_documento'].mean():,.2f}")
```

## Testando o Extrator

Para testar a extração de boletos:

```powershell
# Inspecionar um boleto específico
python scripts/inspect_pdf.py boleto_exemplo.pdf

# Ver campos específicos de boleto
python scripts/inspect_pdf.py boleto.pdf --fields valor_documento vencimento cnpj_beneficiario

# Validar regras em lote
python scripts/validate_extraction_rules.py
```

Campos validados:

- ✅ Identificação correta de boletos
- ✅ Extração de todos os campos (valor, vencimento, linha digitável, etc.)
- ✅ Diferenciação entre NFSe e Boletos
