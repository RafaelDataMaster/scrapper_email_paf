# Projeto de Scraping  de notas fiscais eletrônicas

# To Do
- [ ] Conseguir o acesso ao maior número de pdfs e a tabela já catalogada dos dados pra conferir se a extração do PDF está de fato funcionando.
- [ ] Configurar o email pra fazer os testes em ambiente real de scrapping. Provavelmente usando meu pessoal. Verificar a possibilidade de um redirecionador de email pra um separado (Verificar com a Melyssa).



# Done

## 16/12/2025
- [X] Começar a estudar como realmente fazer o scrapping de diferentes tipos de email. (Talvez pedir um email alternativo pra isso).
- [X] Terminar de organizar a documentação por completo! As funções de código, ver oque eu faço com a parte de arquitetura ou se troco pra pesquisa. 

## 15/12/2025
- [X] Montar o site da documentação
- [X] Organizar a estrutura do projeto

## 11/12/2025
- [X] Debugar os pdfs pra entender cada caso. 
- [X] Extração de dados para um csv baseados em pdf's de diferentes casos


# Oque eu to focando em pesquisar por agora
- Validar a extração de dados do pdf. 
- Identificar adição de abordagem de extração de xml. 
- Configuração dos imaps e testar o scrapping em um email real.

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

## Estrutura do projeto

```
extrator_nfse/
│
├── config/                     # Configurações (settings.py + .env)
├── core/                       # Interfaces e Classes Base
├── extractors/                 # Lógica de extração específica
├── ingestors/                  # Conectores de E-mail (IMAP)
├── strategies/                 # Estratégias de Leitura (PDF/OCR)
├── docs/                       # Documentação (MkDocs)
├── nfs/                        # Pasta de entrada local
├── data/                       # Saída de dados
├── main.py                     # Script de processamento local
├── run_ingestion.py            # Script de ingestão de e-mail
└── requirements.txt            # Dependências
```

# Guia Rápido

## Instalação

1.  Clone o repositório e crie o ambiente virtual:
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # Linux/Mac
    .venv\Scripts\activate     # Windows
    ```

2.  Instale as dependências:
    ```bash
    pip install -r requirements.txt
    ```

3.  Configure a segurança:
    *   Copie `.env.example` para `.env`.
    *   Preencha suas credenciais de e-mail no `.env`.

## Como Usar

*   **Ingestão de E-mail:** `python run_ingestion.py` (Baixa e processa notas do e-mail).
*   **Processamento Local:** `python main.py` (Processa arquivos da pasta `nfs/`).
*   **Documentação:** `mkdocs serve` (Abre o site da documentação localmente).

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