# Como Adicionar uma Nova Prefeitura (Extensão)

O sistema foi projetado com uma arquitetura de plugins para facilitar a adição de novos layouts de prefeituras sem a necessidade de modificar o núcleo do processador.

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

* Use `(?i)` no início da regex para ignorar maiúsculas/minúsculas.
* Use `\s*` para lidar com espaços variáveis entre o rótulo e o valor.
* Teste suas regex em sites como [regex101.com](https://regex101.com/).

## Prioridade de Execução

O sistema verifica os extratores na ordem em que são importados. O `GenericExtractor` é geralmente o último recurso. Se você tiver conflitos (duas cidades com cabeçalhos muito parecidos), torne sua verificação no `can_handle` mais específica.

---

## Trabalhando com Boletos

O sistema agora identifica e processa **boletos bancários** automaticamente, separando-os de notas fiscais. Para cada boleto, extraímos:

### Campos Extraídos de Boletos

* **CNPJ do Beneficiário**: Quem está recebendo o pagamento
* **Valor do Documento**: Valor nominal do boleto
* **Data de Vencimento**: Quando deve ser pago (formato YYYY-MM-DD)
* **Número do Documento**: ID da fatura/documento
* **Linha Digitável**: Código de barras do boleto
* **Nosso Número**: Identificação interna do banco
* **Referência NFSe**: Número da nota fiscal (se mencionado no boleto)

### Vinculando Boletos a NFSe

Você pode cruzar os dados dos boletos com as notas fiscais usando:

1. **Campo `referencia_nfse`**: Alguns boletos incluem explicitamente "Ref. NF 12345"
2. **Campo `numero_documento`**: Muitos fornecedores usam o número da NF como número do documento
3. **Cruzamento por dados**: Compare CNPJ + Valor + Data aproximada entre os dois CSVs

### Arquivos de Saída

O sistema gera dois CSVs separados:
* `relatorio_nfse.csv`: Contém todas as notas fiscais processadas
* `relatorio_boletos.csv`: Contém todos os boletos identificados

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
