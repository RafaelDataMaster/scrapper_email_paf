# Guia de Extensão

O sistema foi projetado com uma arquitetura de plugins para facilitar a adição de novos layouts de documentos (prefeituras, bancos, etc.) sem a necessidade de modificar o núcleo do processador.

Este guia cobre:

1. Como adicionar novos extratores de NFS-e
2. Como trabalhar com boletos
3. Como integrar com o batch processing (v2.x)

## Visão Geral

Cada prefeitura ou layout de nota fiscal é tratado por uma classe "Extratora" específica. O sistema utiliza um mecanismo de **Registro (Registry)** para descobrir automaticamente quais extratores estão disponíveis.

Para adicionar suporte a uma nova cidade, você precisa apenas criar um novo arquivo Python na pasta `extractors/` e implementar uma classe que herde de `BaseExtractor`.

## Passo a Passo

### 1. Crie o Arquivo do Extrator

Crie um novo arquivo em `extractors/`, por exemplo: `extractors/curitiba.py`.

### 2. Implemente a Classe

Use o modelo abaixo como base. É fundamental decorar a classe com `@register_extractor` para que ela seja reconhecida pelo sistema.

```python
import re
from typing import Dict, Any
from core.extractors import BaseExtractor, register_extractor

@register_extractor
class CuritibaExtractor(BaseExtractor):
    """
    Extrator para Notas Fiscais de Serviço de Curitiba - PR.
    """

    @classmethod
    def can_handle(cls, text: str) -> bool:
        """
        Retorna True se este extrator deve ser usado para o texto fornecido.
        Geralmente busca por palavras-chave no cabeçalho.
        """
        return "PREFEITURA MUNICIPAL DE CURITIBA" in text.upper()

    def extract(self, text: str) -> Dict[str, Any]:
        """
        Extrai os dados específicos do layout.
        """
        data = {}

        # Exemplo de extração de Número da Nota
        # Procura por "Número da Nota: 12345"
        match_numero = re.search(r'Número da Nota:\s*(\d+)', text)
        data['numero_nota'] = match_numero.group(1) if match_numero else None

        # Exemplo de extração de Valor
        # Procura por "Valor Total: R$ 1.234,56"
        match_valor = re.search(r'Valor Total:\s*R\$\s?([\d.,]+)', text)
        if match_valor:
            valor_str = match_valor.group(1).replace('.', '').replace(',', '.')
            data['valor_total'] = float(valor_str)
        else:
            data['valor_total'] = 0.0

        # Adicione outros campos conforme necessário (CNPJ, Data, etc.)

        return data
```

### 3. Teste o Novo Extrator

Basta colocar um PDF correspondente na pasta `nfs/` e rodar o `main.py`. O sistema irá:

1. Ler o texto do PDF.
2. Percorrer todos os extratores registrados.
3. Chamar `CuritibaExtractor.can_handle(texto)`.
4. Se retornar `True`, usará sua classe para extrair os dados.

## Dicas para Expressões Regulares (Regex)

- Use `(?i)` no início da regex para ignorar maiúsculas/minúsculas.
- Use `\s*` para lidar com espaços variáveis entre o rótulo e o valor.
- Teste suas regex em sites como [regex101.com](https://regex101.com/).

## Prioridade de Execução

O sistema verifica os extratores na ordem em que são importados. O `NfseGenericExtractor` é geralmente o último recurso para NFS-e. Se você tiver conflitos (duas cidades com cabeçalhos muito parecidos), torne sua verificação no `can_handle` mais específica.

---

## Integração com Batch Processing (v2.x)

A partir da v2.x, os extratores são chamados pelo `BatchProcessor` que fornece contexto adicional do e-mail. Isso permite correlação automática entre DANFE e Boleto.

### Acessando Contexto do Lote

Quando seu extrator é chamado dentro de um lote, você pode acessar metadados do e-mail:

```python
from core.batch_processor import process_email_batch
from core.metadata import EmailMetadata

# Processar um lote
result = process_email_batch("temp_email/email_123")

# Cada documento tem contexto do lote
for doc in result.all_documents:
    print(f"Batch ID: {doc.batch_id}")
    print(f"Email Subject: {doc.source_email_subject}")
    print(f"Email Sender: {doc.source_email_sender}")
```

### Usando Fallbacks do Metadata

Se seu extrator não conseguir extrair certos campos, o `CorrelationService` pode preencher com dados do e-mail:

```python
from core.correlation_service import correlate_batch

# Após processar o lote
correlation = correlate_batch(batch_result, metadata)

# Campos preenchidos automaticamente:
# - fornecedor_nome <- email_sender_name (se vazio)
# - cnpj <- extraído do email_body_text (se vazio)
# - vencimento <- herdado do boleto (para DANFE)
# - numero_nota <- herdado da DANFE (para boleto)
```

### Campos Disponíveis no Metadata

O arquivo `metadata.json` de cada lote contém:

| Campo                  | Descrição           | Uso Típico                |
| :--------------------- | :------------------ | :------------------------ |
| `batch_id`             | ID único do lote    | Rastreabilidade           |
| `email_subject`        | Assunto do e-mail   | Extrair número de pedido  |
| `email_sender_name`    | Nome do remetente   | Fallback para fornecedor  |
| `email_sender_address` | E-mail do remetente | Identificação             |
| `email_body_text`      | Corpo do e-mail     | Extrair CNPJ, referências |
| `received_date`        | Data de recebimento | Auditoria                 |
| `attachments`          | Lista de anexos     | Debug                     |

---

## Trabalhando com Boletos

O sistema agora identifica e processa **boletos bancários** automaticamente, separando-os de notas fiscais. Para cada boleto, extraímos:

### Campos Extraídos de Boletos

- **CNPJ do Beneficiário**: Quem está recebendo o pagamento
- **Valor do Documento**: Valor nominal do boleto
- **Data de Vencimento**: Quando deve ser pago (formato YYYY-MM-DD)
- **Número do Documento**: ID da fatura/documento
- **Linha Digitável**: Código de barras do boleto
- **Nosso Número**: Identificação interna do banco
- **Referência NFSe**: Número da nota fiscal (se mencionado no boleto)

### Vinculando Boletos a NFSe

#### Modo Automático (v2.x - Batch Processing)

A partir da v2.x, a correlação é automática quando DANFE e Boleto estão no mesmo lote:

```python
from core.batch_processor import process_email_batch
from core.correlation_service import correlate_batch
from core.metadata import EmailMetadata

# Processar lote com correlação
result = process_email_batch("temp_email/email_123")
metadata = EmailMetadata.load(Path("temp_email/email_123"))
correlation = correlate_batch(result, metadata)

# Verificar status
print(f"Status: {correlation.status}")  # OK, DIVERGENTE, ORFAO
print(f"Vencimento herdado: {correlation.vencimento_herdado}")
print(f"Número NF herdado: {correlation.numero_nota_herdado}")
```

#### Modo Manual (v1.x - Legado)

Você pode cruzar os dados dos boletos com as notas fiscais usando:

1. **Campo `referencia_nfse`**: Alguns boletos incluem explicitamente "Ref. NF 12345"
2. **Campo `numero_documento`**: Muitos fornecedores usam o número da NF como número do documento
3. **Cruzamento por dados**: Compare CNPJ + Valor + Data aproximada entre os dois CSVs

### Arquivos de Saída

O sistema gera dois CSVs separados:

- `relatorio_nfse.csv`: Contém todas as notas fiscais processadas
- `relatorio_boletos.csv`: Contém todos os boletos identificados

### Exemplo de Cruzamento com Pandas

```python
import pandas as pd

# Carregar os dois relatórios
df_nfse = pd.read_csv('data/output/relatorio_nfse.csv')
df_boleto = pd.read_csv('data/output/relatorio_boletos.csv')

# Vincular por referência explícita
merged = pd.merge(
    df_boleto,
    df_nfse,
    left_on='referencia_nfse',
    right_on='numero_nota',
    how='left'
)

# Ou vincular por número do documento
merged2 = pd.merge(
    df_boleto,
    df_nfse,
    left_on='numero_documento',
    right_on='numero_nota',
    how='left'
)
```

---

## Testando Seus Extratores

### Com o Script de Inspeção

Use `inspect_pdf.py` para ver rapidamente os campos extraídos:

```bash
# Ver todos os campos extraídos
python scripts/inspect_pdf.py seu_pdf_de_teste.pdf

# Ver campos específicos
python scripts/inspect_pdf.py seu_pdf_de_teste.pdf --fields numero_nota valor_total cnpj

# Ver texto bruto (para criar regex)
python scripts/inspect_pdf.py seu_pdf_de_teste.pdf --raw
```

### Com Validação em Lote

Valide seu extrator com múltiplos PDFs:

```bash
# Modo legado (PDFs soltos)
python scripts/validate_extraction_rules.py

# Modo batch (com correlação)
python scripts/validate_extraction_rules.py --batch-mode --apply-correlation
```

---

## Próximos Passos

- [Guia de Debug](../development/debugging_guide.md) - Técnicas avançadas de debug de PDFs
- [Migração Batch](../MIGRATION_BATCH_PROCESSING.md) - Detalhes da migração v1.x → v2.x
- [API Reference](../api/overview.md) - Documentação técnica completa
