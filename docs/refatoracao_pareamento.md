# Refatoração: Extração de Links e Pareamento Flexível

## Visão Geral

Esta refatoração resolve o problema de **linhas divergentes** no `relatorio_lotes.csv`, onde e-mails com NF via link (sem anexo PDF) geravam pareamentos incorretos.

## Problema Original

### Sintoma
O relatório de lotes gerava linhas separadas para o mesmo pagamento:
- Linha 1: Nota Fiscal com `valor_compra = R$ 0,00`
- Linha 2: Boleto com `valor_boleto = R$ 1.500,00`

### Causa Raiz
1. **Extratores limitados a PDF**: O sistema só extraía dados de anexos PDF/XML
2. **NF enviada como link**: E-mails da Omie, prefeituras e outros remetentes enviam boleto em PDF, mas a NF é apenas um link no corpo do e-mail
3. **Pareamento rígido**: A lógica de pareamento separava documentos quando `valor_nota != valor_boleto`

## Solução Implementada

### Fase 1: Novo Extrator de Corpo de E-mail

**Arquivo:** `extractors/email_body_extractor.py`

Novo módulo que extrai dados do corpo do e-mail (HTML/texto plano):

```python
from extractors.email_body_extractor import EmailBodyExtractor

extractor = EmailBodyExtractor()
result = extractor.extract(body_text=body, subject=subject)

# Resultado:
# - valor_total: float (maior valor encontrado)
# - vencimento: str (YYYY-MM-DD)
# - numero_nota: str
# - link_nfe: str (URL da NF-e)
# - codigo_verificacao: str
# - fornecedor_nome: str
# - confianca: float (0.0 a 1.0)
```

#### Padrões Suportados

**Valores monetários:**
- `R$ 1.234,56`
- `Valor: R$ 500,00`
- `Total a pagar: R$ 999,99`
- `TOTAL A PAGAR: R$ 2.000,00`

**Datas de vencimento:**
- `Vencimento: 29/12/2025`
- `Venc.: 15/01`
- `- 29/12 Seg` (formato Omie)

**Números de nota:**
- `NFS-e nº 3406`
- `NF-e 12345`
- `Fatura 50446`

**Links de NF-e:**
- `https://click.omie.com.br/...`
- `https://nfe.prefeitura.sp.gov.br/...`
- `https://notacarioca.rio.gov.br/...`

### Fase 2: Pareamento Flexível por Lote

**Arquivo:** `core/document_pairing.py`

Nova lógica de pareamento com fallback para e-mails sem NF anexada:

#### Novos Status de Pareamento

| Status | Descrição |
|--------|-----------|
| `OK` | Valores conferem dentro da tolerância |
| `DIVERGENTE` | Valores diferentes, pareados por número |
| `CONFERIR` | Sem boleto para comparação |
| `PAREADO_FORCADO` | **NOVO** - Nota sem valor pareada com boleto por lote |

#### Lógica de Pareamento Forçado

```
SE existe 1 nota com valor = 0
E existe 1 boleto com valor > 0
E ambos estão no mesmo batch_id (mesmo e-mail)
ENTÃO força o pareamento
```

**Código:**
```python
def _try_forced_pairing(self, notas, boletos, batch):
    # Condição: exatamente 1 nota e 1 boleto
    if len(notas) != 1 or len(boletos) != 1:
        return None

    numero_nota, valor_nf, doc_nota = notas[0]
    numero_bol, valor_boleto, doc_boleto = boletos[0]

    # Só força quando nota tem valor ZERO
    if valor_nf > 0:
        return None  # Deixa pareamento normal decidir

    # Cria par forçado
    return [DocumentPair(
        status="PAREADO_FORCADO",
        pareamento_forcado=True,
        valor_nf=0.0,
        valor_boleto=valor_boleto,
        ...
    )]
```

### Fase 3: Integração no Pipeline

**Arquivo:** `core/batch_processor.py`

O `BatchProcessor` agora:
1. Processa XMLs e PDFs normalmente
2. **NOVO**: Se não encontrou NF com valor, extrai dados do corpo do e-mail
3. Cria `InvoiceData` sintético com dados extraídos
4. Aplica correlação e pareamento

```python
def process_batch(self, folder_path, apply_correlation=True):
    # ... processamento normal ...

    # NOVO: Extrai dados do corpo do e-mail se não há NF anexada
    if metadata and not self._has_nota_with_valor(final_docs):
        email_body_doc = self._extract_from_email_body(metadata, batch_id)
        if email_body_doc:
            result.add_document(email_body_doc)
```

### Fase 4: Métodos de Extração em EmailMetadata

**Arquivo:** `core/metadata.py`

Novos métodos para extração via metadata:

```python
# Extrai apenas valor
valor = metadata.extract_valor_from_body()  # -> float

# Extrai vencimento
venc = metadata.extract_vencimento_from_body()  # -> str (YYYY-MM-DD)

# Extrai todos os dados
dados = metadata.extract_all_from_body()  # -> dict
```

## Resultado Esperado

### Antes
```csv
batch_id;status_conciliacao;valor_compra;valor_boleto
email_001;CONFERIR;0,0;0,0
email_001_bol;DIVERGENTE;0,0;1500,00
```

### Depois
```csv
batch_id;status_conciliacao;valor_compra;valor_boleto
email_001;PAREADO_FORCADO;0,0;1500,00
```

## Testes

**Arquivo:** `tests/test_email_body_extractor.py`

31 testes cobrindo:
- Extração de valores monetários
- Extração de datas de vencimento
- Extração de números de nota
- Extração de links de NF-e
- Pareamento forçado por lote
- Integração com EmailMetadata

```bash
# Executar testes
python -m pytest tests/test_email_body_extractor.py -v
```

## Arquivos Modificados/Criados

| Arquivo | Ação | Descrição |
|---------|------|-----------|
| `extractors/email_body_extractor.py` | CRIADO | Extrator de dados do corpo de e-mail |
| `extractors/__init__.py` | MODIFICADO | Registro do novo extrator |
| `core/document_pairing.py` | MODIFICADO | Pareamento flexível por lote |
| `core/metadata.py` | MODIFICADO | Novos métodos de extração |
| `core/batch_processor.py` | MODIFICADO | Integração do extrator de body |
| `tests/test_email_body_extractor.py` | CRIADO | Testes unitários |
| `docs/refatoracao_pareamento.md` | CRIADO | Esta documentação |

## Compatibilidade

- ✅ Não altera lógica de filtros (`filters.py`)
- ✅ Mantém comportamento existente para e-mails com NF anexada
- ✅ Todos os testes existentes continuam passando
- ✅ Princípios SOLID mantidos

## Uso

Nenhuma alteração necessária no fluxo de uso. O sistema automaticamente:
1. Tenta extrair dados do corpo quando não há NF anexada
2. Aplica pareamento forçado quando apropriado
3. Marca status correto no relatório

## Limitações Conhecidas

1. **Extração de fornecedor**: Funciona bem para formatos comuns, mas pode falhar em assuntos não-padronizados
2. **Valores múltiplos**: Usa o maior valor encontrado como `valor_total`
3. **Vencimentos parciais**: Assume ano atual para datas DD/MM sem ano
