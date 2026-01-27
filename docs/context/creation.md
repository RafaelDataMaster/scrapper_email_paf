
Você é um engenheiro de software especialista em parsers de documentos fiscais. 
Crie um extrator Python baseado no diagnóstico anterior.

**Estrutura Base do Projeto:**
- Local: `extractors/[nome_do_extrator].py`
- Herda de: classe base com métodos `can_handle()` e `extract()`
- Deve seguir o padrão dos extratores existentes (50+ casos no projeto)

**Input do Diagnóstico Anterior:**
```
TIPO DOCUMENTO: [NFSe/Boleto/NF-e/Administrativo]
PADRÃO IDENTIFICADO: [ex: "Notas de prestador específico X", "Boletos do Banco Y"]
CAMPOS PROBLEMÁTICOS: [Valor/Vencimento/Fornecedor/Número]
TRECHOS DE TEXTO DE REFERÊNCIA:
[COLE AQUI os 3-5 trechos-chave do PDF que precisam ser parseados]
VARIAÇÕES ESPERADAS: [ex: "pode vir com pontos ou vírgulas", "data em formato americano"]
```

**Código a Gerar:**

1. **Cabeçalho do Arquivo:**
   - Docstring explicando para qual layout/documento serve
   - Imports necessários (re, typing, etc)

2. **Classe do Extrator:**
   ```python
   class NomeDoExtrator(BaseExtractor):
       def can_handle(self, text: str, filename: str = "") -> bool:
           # Lógica para identificar se este é o extrator correto
           # Use padrões únicos (CNPJ emitente, termos específicos, etc)
           pass
       
       def extract(self, text: str, filename: str = "") -> DocumentData:
           # Extração dos campos usando regex
           # Tratamento de variações (com/sem máscara, formatos de data)
           pass
   ```

3. **Patterns de Regex:**
   - Forneça as expressões regulares específicas comentadas
   - Inclua grupos nomeados `(?P<valor>...)`
   - Trate variações (ex: `R\$[\s]*` para aceitar espaços)

4. **Normalização:**
   - Limpeza de texto (remover espaços duplos, normalizar acentos?)
   - Conversão de tipos (string → float para valores, string → date)

5. **Fallbacks:**
   - Se campo obrigatório falhar, tentar alternativa?
   - Se regex principal falhar, qual o plano B?

6. **Testes de Validação:**
   - Liste 3-5 casos de teste (input → output esperado)
   - Indique casos edge (bordo) que devem ser rejeitados

**Regras de Negócio:**
- Valores monetários: sempre retornar float (ex: 150.00)
- Datas: preferir objeto datetime ou string padronizada
- CNPJ: manter apenas números ou formato XX.XXX.XXX/XXXX-XX (consistente)
- Se o documento tem código de barras (boleto), extrair também
- Campos vazios devem retornar None, não string vazia ""

Entregue o código completo e pronto para copiar para o arquivo `.py`.