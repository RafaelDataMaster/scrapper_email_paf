# Documentação de Análise de Problemas

Esta seção contém documentos de análise detalhada de problemas específicos identificados no sistema de extração de documentos fiscais. Estes documentos são gerados a partir de investigações aprofundadas de casos de falha, padrões recorrentes e problemas sistêmicos.

## Finalidade

Os documentos nesta pasta servem como:

1. **Registro de investigações**: Análise detalhada da causa raiz de problemas
2. **Base para melhorias**: Fundamentação para ajustes em extratores e regras
3. **Referência técnica**: Documentação de padrões problemáticos identificados
4. **Histórico de decisões**: Registro de como problemas foram resolvidos

## Documentos Disponíveis

| Documento                                  | Data    | Descrição                                                                                                                                                                                                                   |
| ------------------------------------------ | ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **[analise-falhas.md](analise-falhas.md)** | 2025-01 | Análise de como o script `export_to_sheets.py` determina os valores enviados para a planilha Google Sheets. Inclui discussão sobre lógica de prioridade (valor_boleto vs valor_compra) e tratamento de documentos "outros". |

## Como São Gerados

Estes documentos são criados quando:

1. **Problemas recorrentes são identificados** através de scripts como `check_problematic_pdfs.py` ou `list_problematic.py`
2. **Análises de causa raiz** são necessárias para entender falhas sistêmicas
3. **Decisões de design** precisam ser documentadas para referência futura
4. **Padrões de problemas** emergem que requerem documentação técnica

## Relação com Scripts de Análise

Os documentos nesta pasta frequentemente complementam os scripts de análise disponíveis em `scripts/`:

| Script de Análise              | Documento Relacionado                    | Finalidade                                            |
| ------------------------------ | ---------------------------------------- | ----------------------------------------------------- |
| `check_problematic_pdfs.py`    | (Futuro) `analise-pdfs-problematicos.md` | Análise detalhada de PDFs que falham consistentemente |
| `validate_extraction_rules.py` | (Futuro) `analise-regras-extracao.md`    | Validação de regras e performance dos extratores      |
| `diagnose_inbox_patterns.py`   | (Futuro) `analise-padroes-email.md`      | Padrões de e-mail identificados como úteis/inúteis    |

## Estrutura Recomendada para Novos Documentos

Ao criar novos documentos de análise, considere incluir:

1. **Contexto**: O que motivou a análise
2. **Metodologia**: Como a análise foi conduzida
3. **Dados analisados**: Quais dados/lotes foram examinados
4. **Resultados**: O que foi descoberto
5. **Recomendações**: Ações sugeridas com base na análise
6. **Próximos passos**: O que fazer em seguida

## Usos Comuns

### Para desenvolvedores:

- Entender problemas históricos do sistema
- Evitar repetir soluções que já foram tentadas
- Compreender a lógica por trás de decisões técnicas

### Para análise de dados:

- Identificar padrões de falha recorrentes
- Priorizar melhorias no sistema
- Medir impacto de correções implementadas

### Para documentação:

- Manter registro de decisões técnicas
- Documentar trade-offs e considerações
- Preservar conhecimento institucional

## Contribuindo

Para adicionar novos documentos de análise:

1. Execute os scripts relevantes para identificar padrões (`check_problematic_pdfs.py`, `list_problematic.py`, etc.)
2. Documente as descobertas em um novo arquivo Markdown
3. Use dados concretos (exemplos de lotes, estatísticas, trechos de código)
4. Inclua recomendações acionáveis
5. Atualize esta tabela de documentos

## Exemplo de Tópicos Futuros para Análise

1. **Análise de falsos positivos em documentos administrativos**
2. **Impacto de diferentes qualidades de OCR na extração**
3. **Padrões de fornecedores problemáticos recorrentes**
4. **Análise de performance dos diferentes extratores**
5. **Correlação entre tipo de documento e taxa de sucesso**

---

**Última atualização**: 2025-01-21  
**Localização**: `scrapper/docs/analysis/`  
**Relacionado**: [Documentação de Debug](../debug/README.md), [Guia de Debugging](../development/debugging_guide.md)
