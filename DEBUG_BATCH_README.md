# Script de Debug de Batch Processing

## 📋 Descrição

O `debug_batch.py` é uma ferramenta de diagnóstico que processa uma pasta de email e mostra **exatamente** quais valores apareceriam no `relatorio_lotes.csv`, aplicando a lógica completa de pairing e fallbacks.

## 🎯 Para que serve?

Use este script quando precisar:

- ✅ Verificar se o `numero_nota` está sendo extraído corretamente
- ✅ Entender qual campo está sendo usado como fallback
- ✅ Comparar os métodos legado vs. pairing
- ✅ Diagnosticar problemas de extração de dados
- ✅ Ver todos os campos de todos os documentos de um lote
- ✅ Identificar divergências entre NF e Boleto

## 🚀 Como usar

### Sintaxe básica

```bash
python debug_batch.py <caminho_da_pasta>
```

### Exemplos

```bash
# Usando caminho relativo
python debug_batch.py temp_email/email_20260105_125518_4e51c5e2

# Usando caminho absoluto (Windows)
python debug_batch.py C:\Users\user\Documents\scrapper\temp_email\email_20260105_125519_9b0b0752

# Usando caminho absoluto (Linux/Mac)
python debug_batch.py /home/user/scrapper/temp_email/email_20260105_125519_9b0b0752
```

## 📊 O que o script mostra

O script está dividido em **8 seções**:

### 1. Informações Básicas do Lote
- Batch ID
- Total de documentos
- Total de erros
- Assunto e remetente do email

### 2. Documentos por Tipo
- Contagem de DANFEs, NFSes, Boletos e Outros

### 3. Detalhes dos Documentos
Para cada documento, mostra:
- Tipo (DANFE, NFSe, Boleto, Outro)
- Nome do arquivo
- **Todos os campos de número**: `numero_nota`, `numero_documento`, `numero_pedido`, `numero_fatura`, `referencia_nfse`
- Fornecedor, CNPJ, valores, datas

### 4. Método 1: batch_result.to_summary() [LEGADO]
- Mostra o resultado do método antigo
- Gera **UMA linha por lote**
- Usado quando não há múltiplas notas

### 5. Método 2: DocumentPairingService [NOVO]
- Mostra o resultado do método de pairing
- Gera **múltiplas linhas** quando necessário
- Faz fallback correto do `numero_nota`
- **Este é o método recomendado!**

### 6. Comparação dos Métodos
- Compara lado a lado: Legado vs. Pairing
- Identifica diferenças com ✓ ou ✗
- Campos comparados:
  - numero_nota
  - fornecedor
  - vencimento
  - valor_compra
  - valor_boleto
  - status

### 7. Análise de Fallbacks de numero_nota
Esta é a seção **mais importante**! Mostra exatamente:

- Para cada documento, qual campo de número foi encontrado
- A ordem de prioridade dos fallbacks:
  1. ✅ `numero_nota` → [USADO]
  2. ℹ️  `numero_pedido` → [ignorado]
  3. ℹ️  `numero_fatura` → [ignorado]
  4. ℹ️  `numero_documento` → [ignorado]
  5. ℹ️  `referencia_nfse` → [ignorado]

- Qual valor será usado no CSV final

### 8. Recomendações
- Lista avisos e problemas encontrados
- Sugestões de correção

## 🎨 Recursos

### Cores (quando disponível no terminal)
- 🟢 **Verde**: Status OK, campos preenchidos
- 🟡 **Amarelo**: Avisos, status CONFERIR
- 🔴 **Vermelho**: Erros, divergências, campos vazios

### Símbolos
- ✅ Campo preenchido e usado
- ❌ Campo vazio
- ℹ️  Campo preenchido mas ignorado (outro tem prioridade)
- ⚠️  Aviso ou problema
- ✓ Valores idênticos na comparação
- ✗ Valores diferentes na comparação

## 📖 Casos de Uso Comuns

### Caso 1: Verificar se REPROMAQ pegou o número correto do boleto

```bash
python debug_batch.py temp_email/email_20260105_125518_4e51c5e2
```

Procure na **Seção 7** para ver se `numero_documento: S06633-1` foi usado.

### Caso 2: Verificar se EMC pegou o número da fatura

```bash
python debug_batch.py temp_email/email_20260105_125519_9b0b0752
```

Procure na **Seção 7** para ver se `numero_documento: 50446` foi usado.

### Caso 3: Diagnosticar numero_nota vazio

Se o `numero_nota` está vazio no CSV, rode o script e veja na **Seção 7**:

1. Se algum documento tem algum campo de número
2. Se não tem, o extrator pode estar falhando
3. Se tem mas não está sendo usado, pode ser um bug no fallback

### Caso 4: Comparar métodos legado vs. pairing

Veja a **Seção 6** para identificar diferenças. Se houver divergência:
- ✓ Métodos idênticos = tudo OK
- ✗ Métodos diferentes = pode haver um problema

## 🔧 Troubleshooting

### Erro: "Pasta não encontrada"

```
❌ ERRO: Pasta não encontrada: temp_email/email_xyz
```

**Solução**: Verifique se o caminho está correto e se a pasta existe.

### Erro: "ImportError"

```
ModuleNotFoundError: No module named 'core'
```

**Solução**: Execute o script a partir da pasta raiz do projeto (`scrapper/`).

### numero_nota está vazio mesmo após correções

**Passos para diagnosticar**:

1. Verifique a **Seção 7** do debug
2. Se nenhum documento tem campo de número:
   - O extrator pode não estar reconhecendo o documento
   - Verifique se o extrator especializado está ativo
3. Se algum documento tem campo de número mas não é usado:
   - Pode ser um bug no fallback
   - Reporte o problema com o output do debug

## 📝 Exemplo de Output

```
================================================================================
  DEBUG DE BATCH - Processamento de Documentos
================================================================================

📁 Pasta: C:\Users\user\Documents\scrapper\temp_email\email_20260105_125518_4e51c5e2

⏳ Processando lote...

--------------------------------------------------------------------------------
  7. ANÁLISE DE FALLBACKS DE numero_nota
--------------------------------------------------------------------------------

  🔍 Rastreamento de onde veio o numero_nota:

  Documento #1 (OtherDocumentData):
    ❌ numero_nota: (vazio)
    ❌ numero_pedido: (vazio)
    ❌ numero_fatura: (vazio)
    ❌ numero_documento: (vazio)
    ❌ referencia_nfse: (vazio)
    ⚠️  Nenhum campo de número encontrado!

  Documento #2 (BoletoData):
    ❌ numero_nota: (vazio)
    ❌ numero_pedido: (vazio)
    ❌ numero_fatura: (vazio)
    ✅ numero_documento: S06633-1 [USADO]
    ❌ referencia_nfse: (vazio)

  ────────────────────────────────────────────────────────────────────────────
  📊 Resultado no CSV (numero_nota):
    ✅ S06633-1
```

## 🛠️ Manutenção

### Adicionar novos campos no debug

Edite a função `analyze_document()` em `debug_batch.py`:

```python
info = {
    "index": index,
    "tipo": doc_type,
    # ... campos existentes ...
    "novo_campo": getattr(doc, "novo_campo", None),  # Adicione aqui
}
```

### Adicionar nova seção

Adicione no final da função `debug_batch()`:

```python
print_section("9. NOVA SEÇÃO")
# Sua lógica aqui
```

## 📚 Referências

- **Correções de Fallback**: Ver commits relacionados a `batch_result.py` e `document_pairing.py`
- **Padrões de Regex**: Ver `boleto.py` linha 643-684
- **Lógica de Pairing**: Ver `document_pairing.py` linha 158-215

## 🤝 Contribuindo

Se encontrar bugs ou tiver sugestões:
1. Execute o script e capture o output completo
2. Identifique a seção problemática
3. Reporte com detalhes do caso de uso

---

**Última atualização**: 2026-01-07
**Autor**: Sistema de Processamento de Documentos
