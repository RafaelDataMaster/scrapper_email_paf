# Relatório de Arquitetura de Software
**Assunto:** Modernização e Escalabilidade de Sistemas de ETL para Documentos Fiscais Desestruturados

## Sumário Executivo

A engenharia de dados, no contexto fiscal brasileiro, enfrenta um desafio de heterogeneidade sem precedentes. A tarefa de processar Notas Fiscais de Serviço Eletrônicas (NFS-e) não se resume a um problema de ingestão de dados convencional, mas configura-se como um problema de **"Domínio Caótico"**, onde a variabilidade é a única constante.

O presente relatório técnico detalha a transição arquitetural de um script de extração linear para um framework orientado a objetos robusto, escalável e auditável. A análise foca na aplicação rigorosa de **Padrões de Projeto (Design Patterns)** clássicos e modernos, adaptados à linguagem Python, para resolver as dores centrais de variação de formato, instabilidade de leitura (OCR vs. Texto) e validação de regras de negócio complexas.

**Objetivo Final:** Fornecer um *blueprint* arquitetural que permita a inclusão de centenas de layouts municipais com impacto marginal zero na estabilidade do núcleo do sistema.

---

## 1. Introdução e Contextualização do Problema

### 1.1 O Cenário da NFS-e e a Falta de Padronização
Diferentemente da Nota Fiscal Eletrônica de mercadorias (NF-e, modelo 55), que possui um esquema XML nacionalmente unificado e rígido, a Nota Fiscal de Serviços (NFS-e) é de competência municipal. No Brasil, com mais de 5.570 municípios, isso resulta em uma fragmentação tecnológica massiva.

Cada prefeitura tem autonomia para contratar seu próprio provedor de solução (ex: Ginfes, Betha, ISSNet, sistemas próprios), o que gera milhares de layouts visuais distintos e formatos de exportação inconsistentes.

Para um sistema de ETL (*Extract, Transform, Load*) que visa ser "Universal", essa realidade impõe barreiras significativas. A "Dor" identificada no projeto atual — a variação de formato e o ruído de dados — não é uma anomalia, mas a natureza intrínseca do domínio. A solução atual, baseada em um pipeline linear com condicionais aninhados (`if/else`) e loops de tentativas, atinge um limite de complexidade ciclomática rapidamente.

### 1.2 Limitações da Arquitetura Linear Atual
A arquitetura vigente, descrita como um script procedural que tenta ler texto e falha para OCR, sofre de **acoplamento rígido (Tight Coupling)**. A lógica de como ler um arquivo (I/O e OCR) está entrelaçada com a lógica de o que extrair (Regras de Negócio e Regex).

As principais vulnerabilidades identificadas são:

* **Fragilidade no Fallback:** A lógica de alternância entre `pdfplumber` e `Tesseract` é *hardcoded*. Adicionar uma terceira opção (ex: uma API de IA Vision) exigiria refatorar o fluxo principal.
* **Dificuldade de Teste:** Testar a lógica de extração de valores requer instanciar todo o pipeline de leitura de PDF, tornando os testes unitários lentos e dependentes de arquivos físicos.
* **Violação do Princípio Aberto/Fechado (OCP):** Para suportar uma nova prefeitura (ex: Marília), é necessário modificar o código fonte existente, introduzindo riscos de regressão para prefeituras já estáveis (ex: Salvador).

### 1.3 Objetivos da Refatoração Arquitetural
A proposta deste relatório é decompor o problema monolítico em componentes ortogonais, utilizando Padrões de Projeto para gerenciar a complexidade. A reestruturação visa atingir:

1.  **Desacoplamento Temporal e Funcional:** Separar a leitura física do arquivo da interpretação lógica dos dados.
2.  **Extensibilidade por Plugins:** Permitir que novos layouts sejam adicionados apenas criando novos arquivos, sem alterar o núcleo do sistema (Kernel).
3.  **Resiliência a Falhas:** Implementar estratégias de fallback e validação que recuperem erros de forma graciosa.

---

## 2. Padrão Strategy: Abstração e Resiliência na Ingestão

A primeira fronteira do sistema é a conversão de um arquivo binário (PDF, Imagem) em texto processável. A solução atual utiliza uma lógica condicional simples: *"Tente A, se der erro, tente B"*. Em uma arquitetura robusta, isso é modelado através do **Strategy Pattern**.

### 2.1 Conceito e Justificativa
O Padrão Strategy define uma família de algoritmos, encapsula cada um deles e os torna intercambiáveis. No contexto deste extrator, o "algoritmo" é o mecanismo de extração de texto bruto.

A aplicação deste padrão permite que o sistema principal (o Contexto) desconheça se o texto foi obtido através de parsing de vetores PDF, OCR local ou uma API em nuvem. O contrato é simples: `Entra Arquivo -> Sai Texto`.

### 2.2 Implementação da Interface de Estratégia
Em Python, a definição do contrato é feita através de Classes Base Abstratas (ABCs).

```python
from abc import ABC, abstractmethod

class TextExtractionStrategy(ABC):
    """
    Interface abstrata para estratégias de extração de texto.
    Garante que qualquer mecanismo de leitura (OCR, Nativo, Cloud)
    siga o mesmo contrato de interação.
    """
    
    @abstractmethod
    def extract(self, file_path: str, **kwargs) -> str:
        """
        Extrai o texto bruto de um arquivo especificado.
        Returns: str: O texto extraído bruto.
        Raises: ExtractionError: Se houver falha irrecuperável.
        """
        pass
```

### 2.3 Estratégias Concretas e Detalhes Técnicos

#### 2.3.1 NativeTextStrategy (Alta Performance)

Esta estratégia é a preferencial. Ferramentas como `pdfplumber` acessam a camada de conteúdo do PDF e extraem os caracteres diretamente.

  * **Vantagens:** Velocidade extrema (milissegundos), precisão de 100% nos caracteres e retenção de metadados espaciais.
  * **Desafios:** PDFs com "texto sujo" (*mojibake*) onde a codificação de fontes está corrompida.

#### 2.3.2 TesseractOCRStrategy (Alta Compatibilidade)

Quando o arquivo é uma imagem (raster), o OCR é mandatório. Esta estratégia encapsula a complexidade do `pytesseract` e do motor Tesseract 4.0+.

  * **Pipeline Interno:**
    1.  **Rasterização:** Converter PDF para imagem (`pdf2image`) em alta resolução (300 DPI).
    2.  **Pré-processamento:** Aplicar binarização e remoção de ruído (*salt-and-pepper*).
    3.  **Execução do OCR:** Chamar o motor com parâmetros configurados (ex: `--psm 6`).

### 2.4 O Padrão Composite para Fallback Robusto

Para resolver a "Tentativa A -\> Tentativa B" sem `if/else`, utilizamos uma variação do padrão Composite/Chain aplicada às estratégias. Criamos uma `FallbackStrategy` que contém uma lista de outras estratégias e itera sobre elas até obter sucesso.

| Característica | Abordagem Atual (Procedural) | Abordagem Proposta (Strategy + Composite) |
| :--- | :--- | :--- |
| **Fluxo de Controle** | `if native_success: ... else: do_ocr()` | `pipeline.extract(file)` (Polimorfismo) |
| **Extensibilidade** | Edição de código fonte arriscada | Adição de nova classe na lista de configuração |
| **Tratamento de Erro** | Disperso e repetitivo | Centralizado na classe Composite |
| **Testabilidade** | Difícil isolar o OCR | Mocking trivial da interface |

### 2.5 Insights de Segunda Ordem: O Custo do "Hybrid Fallback"

A literatura sugere que a distinção entre "PDF Texto" e "PDF Imagem" nem sempre é binária. Existem PDFs híbridos (texto sobre imagem) ou PDFs onde o texto existe mas é "lixo".

Uma implementação avançada da `FallbackStrategy` deve implementar uma **Heurística de Qualidade**. Se a estratégia nativa retornar texto, mas este texto tiver 40% de caracteres não imprimíveis, a estratégia deve considerar isso uma "falha lógica" e acionar o OCR automaticamente.

-----

## 3\. Chain of Responsibility: O Pipeline de Mineração e Limpeza

Uma vez que o texto bruto foi obtido, o desafio se desloca para a extração de dados estruturados (Mineração). O padrão **Chain of Responsibility (CoR)** transforma loops cegos em uma corrente de especialistas.

### 3.1 O Problema da Extração Sequencial

Em um loop simples de Regex, a lógica de "parada" é binária. Não há espaço para "Refinamento". Além disso, tratar "distratores" (ex: confundir número do RPS com número da Nota) exige condicionais complexas.

### 3.2 Estrutura do Handler de Extração

```python
class ExtractionHandler(ABC):
    def __init__(self, next_handler: Optional['ExtractionHandler'] = None):
        self._next_handler = next_handler

    def handle(self, context: ExtractionContext) -> Optional:
        # Tenta processar. Se tiver sucesso, retorna o resultado.
        result = self._extract(context)
        if result and result.is_valid():
            return result
        
        # Se não, delega para o próximo.
        if self._next_handler:
            return self._next_handler.handle(context)
        
        return None 

    @abstractmethod
    def _extract(self, context) -> Optional:
        pass
```

### 3.3 Tipologia de Handlers para NFS-e

Propomos uma cadeia estratificada para cada campo crítico:

1.  **AnchorBasedHandler (Alta Precisão):** Procura por âncoras rígidas (Ex: "Número da Nota:" seguido de dígitos).
2.  **SpatialHandler (Contextual):** Se houver coordenadas X/Y, busca o número no canto superior direito (posição padrão), ignorando o resto.
3.  **PatternFallbackHandler (Baixa Precisão):** Regex genérica como último recurso.

### 3.4 Higienização Integrada (Decorator)

Um `SanitizingHandler` pode ser colocado no início da cadeia para remover ruídos conhecidos (como "RPS 1234") antes que os extratores tentem ler o texto.

### 3.5 Comparativo: Loop vs. Chain of Responsibility

| Critério | Loop de Regex (Atual) | Chain of Responsibility (Proposto) |
| :--- | :--- | :--- |
| **Complexidade Lógica** | Alta (Regex complexas tentam fazer tudo) | Baixa (Cada handler faz uma coisa simples) |
| **Manutenibilidade** | Adicionar regex nova requer cuidado com a ordem | Handlers são plugáveis e reordenáveis |
| **Contexto** | Regex não vê contexto (apenas string) | Handlers podem acessar metadados (posição, página) |
| **Depuração** | Difícil saber qual regex "pegou" errado | Logs indicam exatamente qual Handler processou |

-----

## 4\. Factory Pattern e Registry: Gerenciamento de Municípios

Criar uma classe para cada uma das 5.570 prefeituras é inevitável, mas gerenciar a instanciação é o gargalo. O **Factory Pattern**, potencializado por um **Registry Dinâmico**, é a solução.

### 4.1 O Problema da Descoberta (Discovery)

Frequentemente, o nome do arquivo não é confiável. O sistema precisa identificar o layout baseando-se no conteúdo (*Content-Based Dispatching*).

### 4.2 O Padrão Registry com Decoradores

Em vez de modificar a Factory a cada nova prefeitura, utilizamos a metaprogramação do Python para auto-registro.

```python
EXTRACTOR_REGISTRY = []

def register_extractor(cls):
    """Decorador para auto-registrar extratores."""
    EXTRACTOR_REGISTRY.append(cls)
    return cls

@register_extractor
class SaoPauloExtractor(BaseExtractor):
    @staticmethod
    def can_handle(text: str) -> bool:
        return "PREFEITURA DO MUNICÍPIO DE SÃO PAULO" in text.upper()
```

### 4.3 A Factory Inteligente

A `InvoiceExtractorFactory` itera sobre o `EXTRACTOR_REGISTRY`, chamando `can_handle()`. O primeiro que responder `True` é instanciado. Isso permite uma arquitetura de **Plugins**: novos layouts são adicionados apenas criando o arquivo, sem tocar no núcleo do sistema.

-----

## 5\. Template Method: A Orquestração

Enquanto Strategy e Factory lidam com as partes móveis, o **Template Method** define a estrutura fixa do processo.

### 5.1 A Classe Base AbstractInvoiceProcessor

```python
class AbstractInvoiceProcessor(ABC):
    def process(self, file_path: str):
        # Passo 1: Leitura (Strategy)
        raw_text = self.read_file(file_path)
        
        # Passo 2: Limpeza (Hook)
        clean_text = self.sanitize(raw_text)
        
        # Passo 3: Extração (Abstract/Factory)
        data_model = self.extract_data(clean_text)
        
        # Passo 4: Validação (Specification)
        if self.validate(data_model):
            self.save(data_model)
        else:
            self.handle_error(data_model)
```

### 5.2 Hooks vs. Métodos Abstratos

  * **Métodos Abstratos (`extract_data`):** Obrigam as subclasses a implementar a lógica específica.
  * **Hooks (`sanitize`):** Métodos com implementação padrão vazia na classe base, mas que podem ser sobrescritos se uma prefeitura específica precisar de limpeza extra.

-----

## 6\. Specification Pattern: Validação de Negócio

A validação fiscal é condicional e complexa. Codificar isso em `if` aninhados cria código espaguete. O **Specification Pattern** encapsula regras de negócio em classes reutilizáveis.

### 6.1 Desacoplando Regras

```python
class IssValidRule(BusinessRule):
    def is_satisfied_by(self, invoice) -> bool:
        if invoice.aliquota > 0:
            return invoice.valor_iss > 0
        return True
```

### 6.2 Composição Booleana

Permite compor regras complexas: `RegraFinal = RegraData() AND (RegraCNPJ() OR RegraCPF())`. Isso permite definir regras de validação de forma declarativa.

-----

## 7\. Robustez, Escalabilidade e Idiomas Pythonicos

### 7.1 Concorrência e Paralelismo

Devido ao GIL do Python, threads não são eficazes para OCR (CPU-bound). A arquitetura deve utilizar `multiprocessing` ou filas (Celery). Como o pipeline é *Stateless*, o paralelismo é trivial.

### 7.2 Gestão de Memória com Geradores

Ao processar milhares de PDFs, o pipeline deve operar com **Generators** (`yield`), carregando um arquivo por vez na memória e descartando imagens pesadas imediatamente após o uso.

### 7.3 Data Quality e Pydantic

O método `extract_data` deve retornar uma instância de `InvoiceModel` (Pydantic). Isso garante *Schema Validation* e *Fail Fast* se os tipos de dados estiverem incorretos.

-----

## 8\. Estudo de Caso Simulado

### Caso A: Salvador (Layout Padrão, PDF Texto)

  * **Factory:** Detecta "Salvador". Instancia `SalvadorProcessor`.
  * **Strategy:** `FallbackStrategy` tenta `NativeText`. Sucesso rápido (\< 0.5s).
  * **CoR:** Handlers simples baseados em Regex posicional.

### Caso B: Marília (Layout Antigo, Scan ruidoso)

  * **Factory:** Detecta padrão visual de Marília. Instancia `MariliaProcessor`.
  * **Strategy:** `NativeText` falha. Aciona `TesseractOCRStrategy`.
  * **Template:** O hook `sanitize` remove bordas escuras da imagem.
  * **CoR:** Usa `FuzzyMatchingHandler` pois o OCR trocou "NOTA" por "N0TA".
  * **Resultado:** Processamento em \~3.0s, dados recuperados com sucesso.

-----

## 9\. Conclusão e Roadmap

A transição para esta arquitetura orientada a padrões é um imperativo de engenharia para viabilizar a escala.

  * **Strategy** resolve a instabilidade de entrada.
  * **Chain of Responsibility** resolve a complexidade de extração.
  * **Factory/Registry** resolve a expansão geográfica.
  * **Template Method** garante a governança do processo.

### Roadmap Sugerido

1.  **Fase 1 (Fundação):** Implementar `TextExtractionStrategy` e o fallback.
2.  **Fase 2 (Estrutura):** Criar `AbstractInvoiceProcessor` e migrar a lógica atual.
3.  **Fase 3 (Expansão):** Implementar o Registry e separar lógicas de cidades.
4.  **Fase 4 (Refinamento):** Substituir loops de Regex por Chains of Responsibility.

-----

## 10\. Referências Técnicas Integradas

Este relatório baseou-se em práticas consolidadas de:

  * Padrões GoF em Python.
  * OCR e Processamento de Imagem.
  * Pipeline de Dados e ETL.
  * Python Idioms e Metaprogramação.

