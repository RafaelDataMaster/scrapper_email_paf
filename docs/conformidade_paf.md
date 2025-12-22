# Documentação de Conformidade PAF

**Processo:** Automação PAF - Lançamento de Títulos Financeiros  
**Versão:** v0001  
**Data de Elaboração:** 22/12/2025  
**Última Revisão:** 22/12/2025

---

## 1. Identificação do Processo

### 1.1 Objetivo

Automatizar a extração de dados de Notas Fiscais de Serviço (NFSe) e Boletos Bancários, realizando o lançamento automático dos títulos na planilha "PAF NOVO - SETORES CSC" com conformidade total às políticas de governança da Master Internet.

### 1.2 Aprovadores

- **Larissa Sbampato** - Controladoria
- **Kleiton Tavares** - Fiscal

### 1.3 Revisão

Este documento deve ser revisado anualmente ou sempre que houver alterações nas políticas internas (Política 5.9) ou nos POPs relacionados (POP 4.4 e 4.10).

---

## 2. Mapeamento: Código → Política de Governança

Esta seção mapeia cada componente técnico do sistema às diretrizes de governança corporativa da Master Internet.

### 2.1 Política Interna 5.9 - Prazo de Lançamento (04 Dias Úteis)

**Diretriz:**  
*"Todos os títulos financeiros devem ser lançados no sistema com antecedência mínima de 04 (quatro) dias úteis em relação à data de vencimento."*

**Implementação Técnica:**

<!-- markdownlint-disable MD060 -->

| Componente                | Arquivo                 | Descrição                                                                                                                                                            |
| ------------------------- | ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Calendário de SP**      | `config/feriados_sp.py` | Classe `SPBusinessCalendar` que calcula dias úteis considerando feriados nacionais, estaduais e municipais de São Paulo. Usa cache LRU (maxsize=12) para otimização. |
| **Validação de Prazo**    | `core/diagnostics.py`   | Método `validar_prazo_vencimento()` que verifica se há >= 4 dias úteis entre `dt_classificacao` e `vencimento`.                                                     |
| **Aplicação nas NFSe**    | `core/diagnostics.py`   | Método `classificar_nfse()` adiciona motivo `PRAZO_INSUFICIENTE_Xd` se validação falhar.                                                                            |
| **Aplicação nos Boletos** | `core/diagnostics.py`   | Método `classificar_boleto()` adiciona motivo `PRAZO_INSUFICIENTE_Xd` se validação falhar.                                                                          |

<!-- markdownlint-enable MD060 -->

**Mitigação de Risco:**  
Documentos que não atendam ao prazo mínimo são sinalizados automaticamente no diagnóstico, permitindo que a equipe financeira tome ação corretiva antes do vencimento.

---

### 2.2 POP 4.4 - Salvamento Hierárquico no Servidor

**Diretriz:**  
*"Todos os documentos processados devem ser salvos de forma hierárquica no servidor, permitindo rastreabilidade e auditoria."*

**Implementação Técnica:**

<!-- markdownlint-disable MD060 -->

| Componente              | Arquivo              | Descrição                                                                                           |
| ----------------------- | -------------------- | --------------------------------------------------------------------------------------------------- |
| **Estrutura de Pastas** | `config/settings.py` | Define `DIR_SAIDA`, `DIR_TEMP`, `DIR_DEBUG_OUTPUT` para organização hierárquica.                   |
| **Processor**           | `core/processor.py`  | Salva arquivos processados com metadados (`arquivo_origem`, `data_processamento`).                 |
| **Campo Link Drive**    | `core/models.py`     | Campo `link_drive` em `InvoiceData` permite rastreamento de documentos no Google Drive.            |

<!-- markdownlint-enable MD060 -->

**Mitigação de Risco:**  
Estrutura de pastas bem definida e campo de rastreabilidade garantem que qualquer documento possa ser auditado a qualquer momento.

---

### 2.3 POP 4.10 - Preenchimento da Planilha PAF

**Diretriz:**  
*"Os dados extraídos devem ser inseridos na planilha 'PAF NOVO - SETORES CSC' respeitando as 18 colunas na ordem exata definida pela equipe financeira."*

**Implementação Técnica:**

<!-- markdownlint-disable MD060 -->

| Componente                 | Arquivo              | Descrição                                                                                                       |
| -------------------------- | -------------------- | --------------------------------------------------------------------------------------------------------------- |
| **Método to_sheets_row()** | `core/models.py`     | Converte `InvoiceData` e `BoletoData` para lista com 18 valores na ordem PAF. Converte datas ISO → DD/MM/YYYY. |
| **GoogleSheetsExporter**   | `core/exporters.py`  | Implementa inserção na planilha via API do Google Sheets com retry strategy.                                   |
| **Batch Processing**       | `core/exporters.py`  | Processa 100 linhas por vez para otimização e evita rate limits.                                               |
| **Modo Tempo Real**        | `core/exporters.py`  | Método `export_single()` para ingestão de e-mails um a um.                                                     |

<!-- markdownlint-enable MD060 -->

**Ordem das Colunas PAF (18 colunas):**

1. DATA (Processamento)
2. SETOR
3. EMPRESA
4. FORNECEDOR
5. NF
6. EMISSÃO
7. VALOR
8. Nº PEDIDO
9. VENCIMENTO
10. FORMA PAGTO
11. (vazio/índice)
12. DT CLASS
13. Nº FAT
14. TP DOC
15. TRAT PAF
16. LANC SISTEMA
17. OBSERVAÇÕES
18. OBS INTERNA

**Mitigação de Risco:**  
Ordem fixa garante que dados não sejam inseridos nas colunas erradas, evitando erros de classificação contábil.

---

### 2.4 Política de Rastreabilidade - Logging Detalhado

**Diretriz:**  
*"Todas as operações críticas devem ser registradas em logs para auditoria técnica e troubleshooting."*

**Implementação Técnica:**

<!-- markdownlint-disable MD060 -->

| Componente              | Arquivo              | Descrição                                                                              |
| ----------------------- | -------------------- | -------------------------------------------------------------------------------------- |
| **RotatingFileHandler** | `config/settings.py` | Logs com rotação (10MB, 5 backups) para evitar crescimento descontrolado.             |
| **Logs de Sucesso**     | `core/exporters.py`  | `logger.info()` registra cada documento exportado com sucesso.                         |
| **Logs de Retry**       | `core/exporters.py`  | `logger.warning()` registra tentativas de retry em caso de rate limit 429.             |
| **Formato de Log**      | `config/settings.py` | Timestamp + Nível + Mensagem para rastreabilidade temporal.                            |

<!-- markdownlint-enable MD060 -->

**Mitigação de Risco:**  
Logs detalhados permitem identificar falhas de integração com Google Sheets, problemas de extração e discrepâncias de dados.

---

## 3. Campos Obrigatórios para Sucesso de Classificação

### 3.1 NFSe (Notas Fiscais)

**Critérios de SUCESSO:**

- ✅ Número da Nota preenchido
- ✅ Valor total > 0
- ✅ Razão Social (fornecedor_nome) preenchida
- ✅ Prazo de 04 dias úteis ao vencimento (se houver vencimento)

**Motivos de Falha (gerados automaticamente):**

- `SEM_NUMERO`: Número da nota não extraído
- `VALOR_ZERO`: Valor total é zero ou não extraído
- `SEM_CNPJ`: CNPJ do prestador não extraído
- `SEM_RAZAO_SOCIAL`: Razão Social não extraída
- `PRAZO_INSUFICIENTE_Xd`: Menos de 4 dias úteis até o vencimento

### 3.2 Boletos Bancários

**Critérios de SUCESSO:**

- ✅ Valor do documento > 0
- ✅ Vencimento preenchido
- ✅ Linha digitável preenchida
- ✅ Razão Social (fornecedor_nome) preenchida
- ✅ Prazo de 04 dias úteis ao vencimento

**Motivos de Falha (gerados automaticamente):**

- `VALOR_ZERO`: Valor do documento é zero ou não extraído
- `SEM_VENCIMENTO`: Data de vencimento não extraída
- `SEM_LINHA_DIGITAVEL`: Linha digitável não extraída
- `SEM_RAZAO_SOCIAL`: Razão Social não extraída
- `PRAZO_INSUFICIENTE_Xd`: Menos de 4 dias úteis até o vencimento

---

## 4. Normalização de Dados Bancários

**Objetivo:** Garantir formato consistente para futura integração com arquivos CNAB e APIs bancárias.

### 4.1 Formato de Agência

- **Padrão:** `1234-5` (número-dígito verificador)
- **Implementação:** `extractors/boleto.py` → `_extract_agencia()`
- **Normalização:** Remove espaços e pontos, mantém hífen antes do dígito

### 4.2 Formato de Conta Corrente

- **Padrão:** `123456-7` (número-dígito verificador)
- **Implementação:** `extractors/boleto.py` → `_extract_conta_corrente()`
- **Normalização:** Remove espaços e pontos, mantém hífen antes do dígito

### 4.3 Identificação de Banco

- **Estratégia:** Mapeia código bancário (3 primeiros dígitos da linha digitável) para nome oficial
- **Implementação:** `config/bancos.py` → dicionário `NOMES_BANCOS` (Top 20 bancos)
- **Fallback:** Se código não estiver mapeado, retorna `BANCO_XXX` (onde XXX é o código)

---

## 5. Retry Strategy - Google Sheets API

**Problema:** API do Google Sheets possui limite de 300 requisições por minuto. Em processamentos em lote, o sistema pode atingir este limite.

**Solução Implementada:**

| Parâmetro                   | Valor                              | Justificativa                                                  |
| --------------------------- | ---------------------------------- | -------------------------------------------------------------- |
| **Máximo de Tentativas**    | 5                                  | Suficiente para recuperar de rate limits temporários           |
| **Backoff Exponencial**     | 2s, 4s, 8s, 10s (máx)              | Reduz carga na API gradualmente                                |
| **Tipo de Erro**            | `APIError`                         | Apenas erros da API (não erros de rede local)                  |
| **Logging**                 | WARNING                            | Cada retry é registrado para troubleshooting                   |

**Implementação:** `core/exporters.py` → decorador `@retry` da biblioteca `tenacity`

---

## 6. Status de Lançamento no ERP

### 6.1 Campo LANC SISTEMA

**Valores Possíveis:**

- `PENDENTE` (default): Título foi extraído mas ainda não foi lançado no Protheus Ambiente 06
- `LANÇADO`: Título foi confirmado no ERP (preenchimento manual pela equipe financeira)

**Fluxo:**

1. Sistema preenche automaticamente como `PENDENTE`
2. Equipe financeira valida dados na planilha PAF
3. Após lançamento no Protheus, equipe altera manualmente para `LANÇADO`
4. Campo permite filtrar rapidamente títulos que ainda precisam de ação

---

## 7. Histórico de Alterações

<!-- markdownlint-disable MD060 -->

| Data       | Versão | Autor                 | Descrição                                     |
| ---------- | ------ | --------------------- | --------------------------------------------- |
| 22/12/2025 | v0001  | Sistema Automação PAF | Criação inicial do documento de conformidade |

<!-- markdownlint-enable MD060 -->

---

## 8. Observações Finais

### 8.1 Campos Secundários (Fase 2)

Os seguintes campos estão definidos no modelo de dados mas não são extraídos na Fase 1:

- `cfop` (Código Fiscal de Operações)
- `cst` (Código de Situação Tributária)
- `ncm` (Nomenclatura Comum do Mercosul)
- `natureza_operacao`

**Justificativa:** Foco inicial em campos obrigatórios para PAF. Campos secundários serão implementados após validação do MVP.

### 8.2 Feriados Municipais Dinâmicos

O sistema calcula automaticamente feriados móveis (Corpus Christi, Carnaval) usando a biblioteca `dateutil.easter`, eliminando necessidade de manutenção anual manual.

### 8.3 Integração Futura

O design modular permite futuras integrações:

- API do Protheus para lançamento automático
- Arquivos CNAB para pagamento de boletos
- Dashboards de BI para análise de impostos

---

Documento Controlado - Versão Digital Prevalece
