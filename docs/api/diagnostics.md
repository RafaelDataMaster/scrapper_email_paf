# Diagnostics - Sistema de Análise de Qualidade

O módulo `core.diagnostics` fornece ferramentas para validação, classificação e geração de relatórios sobre a qualidade da extração de dados.

## Visão Geral

**Responsabilidades:**

- Classificar extrações como sucesso ou falha
- Identificar motivos específicos de falha
- Gerar relatórios estatísticos
- Diagnosticar problemas automaticamente

**Uso principal:**

- Scripts de validação ([`validate_extraction_rules.py`](../../scripts/validate_extraction_rules.py))
- Análise de lotes de processamento
- Geração de relatórios de qualidade

---

## ExtractionDiagnostics

Classe principal com métodos estáticos para análise de qualidade.

### Métodos

#### `validar_prazo_vencimento(dt_classificacao: Optional[str], vencimento: Optional[str]) -> Tuple[bool, int]`

Valida se há no mínimo 04 dias úteis entre classificação e vencimento.

**Conformidade:** Política Interna 5.9 e POP 4.10 exigem lançamento com antecedência mínima de 04 dias úteis ao vencimento.

**Considera:**

- Feriados nacionais
- Feriados estaduais de São Paulo
- Feriados municipais de São Paulo (capital)
- Finais de semana (sábado e domingo)

**Parâmetros:**

- `dt_classificacao`: Data de classificação no formato ISO (YYYY-MM-DD)
- `vencimento`: Data de vencimento no formato ISO (YYYY-MM-DD)

**Retorna:**

Tupla `(prazo_ok, quantidade_dias_uteis)`

- `prazo_ok`: True se >= 4 dias úteis, False caso contrário
- `quantidade_dias_uteis`: Número de dias úteis calculado

**Exemplo:**

```python
from core.diagnostics import ExtractionDiagnostics

# Classificação: 03/01/2025, Vencimento: 30/01/2025
ok, dias = ExtractionDiagnostics.validar_prazo_vencimento(
    "2025-01-03", "2025-01-30"
)
print(f"Prazo OK: {ok}, Dias úteis: {dias}")  # True, 19 (considerando feriados)
```

---

#### `classificar_nfse(result: InvoiceData) -> Tuple[bool, List[str]]`

Classifica uma NFSe extraída como sucesso ou falha baseado em critérios de negócio.

**Critérios de Sucesso (Conformidade PAF):**

- ✅ Número da nota presente e não vazio
- ✅ Valor total maior que zero
- ✅ Razão Social (fornecedor_nome) preenchida
- ✅ Prazo de 04 dias úteis ao vencimento (se houver vencimento)

**Códigos de Falha:**

- `SEM_NUMERO`: Número da nota ausente ou vazio
- `VALOR_ZERO`: Valor total zero ou ausente
- `SEM_CNPJ`: CNPJ do prestador não encontrado
- `SEM_RAZAO_SOCIAL`: Fornecedor não identificado
- `PRAZO_INSUFICIENTE_Xd`: Menos de 4 dias úteis até o vencimento (X = quantidade de dias)

**Exemplo:**

```python
from core.diagnostics import ExtractionDiagnostics
from core.models import InvoiceData

# NFSe completa
nfse = InvoiceData(
    arquivo_origem="nota.pdf",
    texto_bruto="...",
    numero_nota="12345",
    valor_total=1500.00,
    cnpj_prestador="12.345.678/0001-90"
)

sucesso, motivos = ExtractionDiagnostics.classificar_nfse(nfse)
print(f"Sucesso: {sucesso}")     # True
print(f"Motivos: {motivos}")     # []

# NFSe incompleta
nfse_falha = InvoiceData(
    arquivo_origem="nota.pdf",
    texto_bruto="...",
    numero_nota="",
    valor_total=0.0
)

sucesso, motivos = ExtractionDiagnostics.classificar_nfse(nfse_falha)
print(f"Sucesso: {sucesso}")     # False
print(f"Motivos: {motivos}")     # ['SEM_NUMERO', 'VALOR_ZERO']
```

---

#### `classificar_boleto(result: BoletoData) -> Tuple[bool, List[str]]`

Classifica um boleto extraído como sucesso ou falha.

**Critérios de Sucesso (Conformidade PAF):**

- ✅ Valor do documento maior que zero
- ✅ Vencimento preenchido
- ✅ Linha digitável OU vencimento presente
- ✅ Razão Social (fornecedor_nome) preenchida
- ✅ Prazo de 04 dias úteis ao vencimento

**Códigos de Falha:**

- `VALOR_ZERO`: Valor do documento não encontrado ou zero
- `SEM_VENCIMENTO`: Data de vencimento ausente
- `SEM_LINHA_DIGITAVEL`: Código de barras/linha digitável ausente
- `SEM_RAZAO_SOCIAL`: Fornecedor não identificado
- `PRAZO_INSUFICIENTE_Xd`: Menos de 4 dias úteis até o vencimento (X = quantidade de dias)

**Lógica:**
Um boleto é considerado válido se tem valor **E** pelo menos uma identificação (vencimento ou linha digitável).

**Exemplo:**

```python
from core.diagnostics import ExtractionDiagnostics
from core.models import BoletoData

# Boleto completo
boleto = BoletoData(
    arquivo_origem="boleto.pdf",
    texto_bruto="...",
    valor_documento=850.00,
    vencimento="2025-01-15",
    linha_digitavel="12345.67890 12345.678901..."
)

sucesso, motivos = ExtractionDiagnostics.classificar_boleto(boleto)
print(f"Sucesso: {sucesso}")     # True

# Boleto sem valor
boleto_falha = BoletoData(
    arquivo_origem="boleto.pdf",
    texto_bruto="...",
    valor_documento=0.0,
    vencimento="2025-01-15"
)

sucesso, motivos = ExtractionDiagnostics.classificar_boleto(boleto_falha)
print(f"Motivos: {motivos}")     # ['VALOR_ZERO']
```

---

#### `gerar_relatorio_texto(dados: Dict) -> str`

Gera relatório formatado em texto com estatísticas de extração.

**Parâmetros:**

```python
dados = {
    'total': 100,                      # Total de arquivos processados
    'nfse_ok': 85,                     # NFSe extraídas com sucesso
    'nfse_falha': 10,                  # NFSe com falhas
    'boleto_ok': 4,                    # Boletos extraídos com sucesso
    'boleto_falha': 1,                 # Boletos com falhas
    'erros': 0,                        # Erros críticos
    'nfse_falhas_detalhe': [...],     # Lista de dicts com detalhes
    'boleto_falhas_detalhe': [...]    # Lista de dicts com detalhes
}
```

**Retorna:**

```text
================================================================================
📊 RELATÓRIO DE QUALIDADE DA EXTRAÇÃO
================================================================================

📅 Data: 18/12/2025 11:15:32
📦 Total de arquivos: 100

--- NFSe ---
✅ Completas: 85
⚠️ Com falhas: 10
📈 Taxa de sucesso: 89.5%

--- Boletos ---
✅ Completos: 4
⚠️ Com falhas: 1
📈 Taxa de sucesso: 80.0%

❌ Erros: 0

================================================================================
🔍 FALHAS - NFSe
================================================================================

📄 arquivo_problema.pdf
   Motivo: SEM_NUMERO|VALOR_ZERO
   Número: N/A
   Valor: R$ 0,00
```

**Exemplo de uso:**

```python
from core.diagnostics import ExtractionDiagnostics

stats = {
    'total': 100,
    'nfse_ok': 85,
    'nfse_falha': 10,
    'boleto_ok': 4,
    'boleto_falha': 1,
    'erros': 0,
    'nfse_falhas_detalhe': [],
    'boleto_falhas_detalhe': []
}

relatorio = ExtractionDiagnostics.gerar_relatorio_texto(stats)
print(relatorio)
```

---

#### `salvar_relatorio(dados: Dict, caminho_arquivo: Path) -> None`

Gera relatório e salva em arquivo de texto.

**Exemplo:**

```python
from pathlib import Path
from core.diagnostics import ExtractionDiagnostics

output_path = Path("data/output/relatorio_qualidade.txt")
ExtractionDiagnostics.salvar_relatorio(stats, output_path)
```

---

#### `diagnosticar_tipo_falha(arquivo: str, texto_snippet: str, numero_nota: str, valor: float) -> str`

Tenta classificar automaticamente o tipo de falha de extração usando heurísticas.

**Lógica de Diagnóstico:**

1. **BOLETO/RECIBO**: Se nome do arquivo contém "boleto" ou "recibo"
2. **LOCAÇÃO**: Se texto contém "locação" (layout atípico)
3. **VALOR**: Se valor está zerado ou ausente
4. **NÚMERO**: Se número da nota está vazio

**Exemplo:**

```python
from core.diagnostics import ExtractionDiagnostics

# Caso 1: Boleto classificado como NFSe
diag = ExtractionDiagnostics.diagnosticar_tipo_falha(
    arquivo="boleto_123.pdf",
    texto_snippet="BANCO BRADESCO...",
    numero_nota="",
    valor=0.0
)
print(diag)  # "BOLETO/RECIBO (Ignorar se não for NF)."

# Caso 2: Problema de regex no valor
diag = ExtractionDiagnostics.diagnosticar_tipo_falha(
    arquivo="nota_456.pdf",
    texto_snippet="PREFEITURA MUNICIPAL...",
    numero_nota="12345",
    valor=0.0
)
print(diag)  # "Regex de VALOR falhou."

# Caso 3: Documento de locação (layout atípico)
diag = ExtractionDiagnostics.diagnosticar_tipo_falha(
    arquivo="doc.pdf",
    texto_snippet="ATESTAMOS A LOCAÇÃO QUE...",
    numero_nota="",
    valor=0.0
)
print(diag)  # "LOCAÇÃO (Layout atípico)."
```

---

## Uso em Scripts

### Script de Validação

O módulo é usado em [`scripts/validate_extraction_rules.py`](../../scripts/validate_extraction_rules.py):

```python
from core.diagnostics import ExtractionDiagnostics
from core.models import InvoiceData, BoletoData

# Processar arquivo
result = processor.process("arquivo.pdf")

# Classificar resultado
if isinstance(result, InvoiceData):
    sucesso, motivos = ExtractionDiagnostics.classificar_nfse(result)
    if not sucesso:
        print(f"⚠️ NFSe INCOMPLETA: {' | '.join(motivos)}")

elif isinstance(result, BoletoData):
    sucesso, motivos = ExtractionDiagnostics.classificar_boleto(result)
    if not sucesso:
        print(f"⚠️ BOLETO INCOMPLETO: {' | '.join(motivos)}")
```

## Modelo de Dados: DiagnosticReport

Dataclass para estruturar resultados de análise.

```python
@dataclass
class DiagnosticReport:
    total_arquivos: int
    nfse_sucesso: int
    nfse_falhas: int
    boleto_sucesso: int
    boleto_falhas: int
    taxa_sucesso_nfse: float
    taxa_sucesso_boleto: float
    falhas_detalhadas: List[Dict]
```

**Uso:**

```python
from core.diagnostics import DiagnosticReport

report = DiagnosticReport(
    total_arquivos=100,
    nfse_sucesso=85,
    nfse_falhas=10,
    boleto_sucesso=4,
    boleto_falhas=1,
    taxa_sucesso_nfse=89.5,
    taxa_sucesso_boleto=80.0,
    falhas_detalhadas=[]
)
```

---

## Integração com Testes

Os métodos de diagnóstico são testados em [`tests/test_extractors.py`](../../tests/test_extractors.py):

```python
import unittest
from core.diagnostics import ExtractionDiagnostics
from core.models import InvoiceData

class TestDiagnostics(unittest.TestCase):
    def test_classificar_nfse_sucesso(self):
        nfse = InvoiceData(
            arquivo_origem="test.pdf",
            texto_bruto="",
            numero_nota="12345",
            valor_total=100.0
        )
        sucesso, motivos = ExtractionDiagnostics.classificar_nfse(nfse)
        self.assertTrue(sucesso)
        self.assertEqual(motivos, [])

    def test_classificar_nfse_falha(self):
        nfse = InvoiceData(
            arquivo_origem="test.pdf",
            texto_bruto="",
            numero_nota="",
            valor_total=0.0
        )
        sucesso, motivos = ExtractionDiagnostics.classificar_nfse(nfse)
        self.assertFalse(sucesso)
        self.assertIn('SEM_NUMERO', motivos)
        self.assertIn('VALOR_ZERO', motivos)
```

---

## API Reference

::: core.diagnostics.ExtractionDiagnostics
options:
show_root_heading: true
show_source: false
members: - classificar_nfse - classificar_boleto - gerar_relatorio_texto - salvar_relatorio - diagnosticar_tipo_falha

::: core.diagnostics.DiagnosticReport
options:
show_root_heading: true
members_order: source

---

## Ver Também

- [Core](core.md) - Modelos de dados (InvoiceData, BoletoData)
- [Extractors](extractors.md) - Lógica de extração
- [Guia de Testes](../guide/testing.md) - Como validar extrações
- [Histórico de Refatorações](../development/refactoring_history.md) - Criação do módulo
