Você é um analista de qualidade de dados fiscais. Analise o caso abaixo e identifique o problema de extração.

**Contexto do Sistema:**

- Pipeline de ETL que processa PDFs de Notas Fiscais (NFSe/NF-e) e Boletos
- Extratores baseados em regex patterns para diferentes layouts de documentos
- OCR é usado quando o PDF não tem texto nativo selecionável
- Arquitetura: E-mail → PDF → Extração Texto → Classificação → CSV

**Caso para Análise:**

```
ID: [NÚMERO_DO_CASO]
ARQUIVO: [NOME_DO_PDF]
ASSUNTO EMAIL: [ASSUNTO]

DADOS EXTRAÍDOS (CSV):
- Tipo: [NFSe/Boleto/Outros/Desconhecido]
- Valor: [R$ X,XX ou vazio]
- Vencimento: [data ou vazio]
- Fornecedor: [nome ou vazio]
- Nº Documento: [número ou vazio]

CONTEÚDO DO PDF (texto bruto extraído):
[COLE AQUI O TEXTO_EXTRAIDO ou descrição do conteúdo visual]

PROBLEMA REPORTADO:
[Descreva o que está errado: ex: "Valor aparece 0 mas PDF tem R$ 150,00",
ou "Classificado como Desconhecido mas é NFSe"]
```

**Sua Análise deve conter:**

1. **CLASSIFICAÇÃO DO ERRO** (escolha um):
    - [ ] Erro de OCR (texto ilegível/corrupção caracteres)
    - [ ] Regex falha (padrão não captura variação de layout)
    - [ ] Roteamento errado (extrator genérico impediu o específico)
    - [ ] Campo ausente (informação existe mas não foi extraída)
    - [ ] Falso positivo/negativo (classificação incorreta do documento)

2. **DIAGNÓSTICO TÉCNICO:**
    - O que deveria ter sido capturado: [ex: "Valor R$ 150,00 na seção 'Valor a Pagar'"]
    - O que aconteceu: [ex: "Regex procurava 'Valor Total:' mas documento usa 'Valor a Pagar'"]
    - Onde está o padrão no texto: [indique a linha/coluna ou trecho específico]

3. **MATRIZ DE IMPACTO:**
    - Severidade: [Alta/Média/Baixa]
    - Frequência estimada: [Único/Padrão frequente/Episódico]
    - Bloqueia processamento? [Sim/Não]

4. **RECOMENDAÇÃO INICIAL:**
    - Criar novo extrator? [Sim/Não]
    - Ajustar regex existente? [Qual arquivo]
    - Requer OCR melhorado? [Sim/Não]

Responda em formato estruturado para eu copiar e colar no segundo prompt de criação.
