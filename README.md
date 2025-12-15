# Projeto de Scraping  de notas fiscais eletrônicas

# To Do
- [ ] Organizar uma estrutura pro projeto.
- [ ] Estudar os emails e planejar a extração e definição de casos.

# Done
## 11/12/2025
- [X] Debugar os pdfs pra entender cada caso. 
- [X] Extração de dados para um csv baseados em pdf's de diferentes casos

# Oque eu to focando em pesquisar por agora
Padrões de projeto para tornar o código mais legivel e de fácil manutenabilidade e escalabilidade. Transformar em uma base sólida para ELT.

# Dificuldades até o momento
Boa parte dos erros foram relacionados ao Regex, estudar mais a fundo e procurar fazer testes com casos mais complexos para ir adicionando mais palavras ao dicionário de Regex.
Durante o planejamento do projeto avaliar a necessidade de separar uma fila de processamentos de pdfs que são imagens do OCR e tesseract por conta do alto tempo de execução, pra um caso já esta demorando 30 segundos na versão atual do código.

# Informações gerais do projeto e requisitos

## Dados extraídos
- 'arquivo_origem'
- 'cnpj_prestador'
- 'numero_nota'
- 'data_emissao'
- 'valor_total'
- 'texto_bruto'

## Estrutura do projeto (feita na data 15/12/2025)

```
extrator_nfse/
│
├── core/                       # O "Kernel" do sistema (Interfaces e Classes Base)
│   ├── __init__.py
│   ├── interfaces.py           # Onde fica a classe abstrata TextExtractionStrategy
│   ├── exceptions.py           # Erros personalizados (ex: ExtractionError)
│   └── models.py               # (Futuro) Classes de dados (Pydantic)
│
├── strategies/                 # Implementações concretas de LEITURA (Fase 1)
│   ├── __init__.py
│   ├── native.py               # Leitura rápida (pdfplumber)
│   ├── ocr.py                  # Leitura lenta (Tesseract)
│   └── fallback.py             # A estratégia composta (Tenta Nativo -> Se falhar -> OCR)
│
├── extractors/                 # (Fase 2/3) Lógica de extração por cidade
│   └── __init__.py             # Aqui ficarão os Processors e Handlers
│
├── config/                     # Configurações globais
│   ├── __init__.py
│   └── settings.py             # Caminhos do Tesseract, Poppler, etc.
│
├── tests/                      # Testes automatizados
│   ├── __init__.py
│   └── test_strategies.py      # Testar se o fallback está funcionando
│
├── main.py                     # Ponto de entrada (CLI ou Script)
├── requirements.txt            # Dependências
└── README.md
```

## 1. Automação de Entradas de NFe

### ORQUESTRAÇÃO
- Programar rotinas de varredura do email e integrar com fonte de contratos
- ELT

### Requisitos
- [ ] Ler e-mails com NF
- [ ] Categorizar e digitalizar informações
- [ ] Ler tabela verdade de Contratos e Pedidos
- [ ] Comparar informações de NF de entrada e informações da tabela
- [ ] Criar tabela de input de dados