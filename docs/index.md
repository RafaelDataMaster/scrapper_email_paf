# Pipeline de Automação de Entradas de NFS-e

Bem-vindo à documentação oficial do projeto de automação fiscal. Este sistema foi projetado para eliminar o gargalo manual no recebimento e lançamento de Notas Fiscais de Serviço (NFS-e), garantindo integridade de dados e integração direta com o ERP Protheus.

O projeto opera sobre três pilares fundamentais: **Orquestração**, **ELT (Extract, Load, Transform)** e **Automação**.

---

## 🏗️ Arquitetura do Processo

Abaixo, o fluxo de dados desenhado para atender aos requisitos da Master:

```mermaid
graph TD
    subgraph ORCH [1. Orquestração]
        A[📧 Varredura de E-mails] -->|Identifica NF| B(Download Anexos)
    end

    subgraph ELT [2. ELT & Validação]
        B --> C{Tipo de Arquivo?}
        C -->|PDF Texto| D[Extração Nativa]
        C -->|Imagem/Scan| E[OCR Tesseract]
        D --> F[Estruturação de Dados]
        E --> F
        F --> G{Validação Cruzada}
        H[(Tabela Verdade<br>Contratos e Pedidos)] --> G
    end

    subgraph AUTO [3. Automação]
        G -->|Dados Válidos| I[🚀 Inserção no Protheus]
        G -->|Divergência| J[⚠️ Relatório de Exceção]
    end

    style ORCH fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    style ELT fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style AUTO fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
```

-----

## 🔄 1. Orquestração (Ingestão)

Responsável pela **monitoria e captura** dos documentos fiscais na entrada da empresa.

  * **Rotinas de Varredura:** Monitoramento contínuo de caixas de e-mail específicas.
  * **Filtros Inteligentes:** Identificação de e-mails contendo NFS-e (baseado em assunto, remetente e anexos).
  * **Gestão de Fontes:** Integração com a base de contratos para priorizar fornecedores cadastrados.

-----

## ⛏️ 2. ELT (Extração e Transformação)

Este é o núcleo atual do projeto (`scrapper_nfe`), responsável por transformar documentos desestruturados (PDFs variados) em dados estruturados.

### Funcionalidades

1.  **Leitura Híbrida:** Utiliza *Strategies* para alternar entre leitura nativa (rápida) e OCR (Tesseract) automaticamente.
2.  **Categorização:** Digitaliza as informações críticas (CNPJ, Valores, Datas).
3.  **Validação de Negócio (Tabela Verdade):**
      * Lê a tabela de **Contratos e Pedidos** vigentes.
      * Compara: *Dados da NF extraída* **vs** *Dados do Pedido de Compra*.
      * Garante que o valor faturado corresponde ao contratado antes do lançamento.

### Modelo de Dados Extraídos

Atualmente, o núcleo extrai e normaliza os seguintes campos:

| Campo | Descrição | Tipo |
| :--- | :--- | :--- |
| `arquivo_origem` | Nome do arquivo processado | `string` |
| `cnpj_prestador` | Identificação fiscal do fornecedor | `string` |
| `numero_nota` | Número da NFS-e (higienizado) | `string` |
| `data_emissao` | Data de competência (ISO 8601) | `date` |
| `valor_total` | Valor líquido da nota | `float` |
| `texto_bruto` | Conteúdo completo para auditoria | `text` |

-----

## 🤖 3. Automação (Ação)

A etapa final do pipeline, onde o dado validado se transforma em ação no ERP.

  * **Input de Dados:** Criação da tabela final de *input*.
  * **Integração Protheus:** Inserção automática da pré-nota ou nota classificada no sistema Protheus.
  * **Logs de Auditoria:** Registro de todas as operações para rastreabilidade fiscal.

-----

## 📂 Estrutura do Código Fonte

A organização do projeto segue princípios de *Clean Architecture* para facilitar a manutenção e escalabilidade para novos municípios.

```bash
extrator_nfse/
│
├── core/               # Kernel: Interfaces e Modelos de Dados
├── strategies/         # Motores de Leitura (PDF Nativo vs OCR)
├── extractors/         # Regras de Negócio por Município/Layout
├── config/             # Configurações de Ambiente (Tesseract, Paths)
├── main.py             # Ponto de entrada (CLI)
└── requirements.txt    # Dependências do Projeto
```

-----

*© 2025 Master. Desenvolvido para modernização do setor fiscal.*
