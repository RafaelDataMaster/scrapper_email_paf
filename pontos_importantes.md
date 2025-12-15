# Insights de Segunda Ordem: O Custo do "Hybrid Fallback"

A literatura sugere que a distinção entre "PDF Texto" e "PDF Imagem" nem sempre é binária. Existem PDFs híbridos (texto sobre imagem) ou PDFs onde o texto existe mas é "lixo" (encoding incorreto). Uma implementação avançada da FallbackStrategy não deve apenas checar se o texto é vazio. Ela deve implementar uma Heurística de Qualidade. Se a estratégia nativa retornar texto, mas este texto tiver 40% de caracteres não imprimíveis, a estratégia deve considerar isso uma "falha lógica" e acionar o OCR, mesmo que tecnicamente a extração tenha ocorrido. Esse nível de robustez é impossível de manter em scripts lineares simples.

# Roadmap Sugerido
- Fase 1 (Fundação): Implementar TextExtractionStrategy e o fallback. Isso estanca os erros de leitura imediata.

- Fase 2 (Estrutura): Criar AbstractInvoiceProcessor (Template Method) e migrar a lógica atual para dentro dele.

- Fase 3 (Expansão): Implementar o Registry e começar a separar as lógicas de Salvador e SP em arquivos distintos.

- Fase 4 (Refinamento): Substituir os loops de Regex por Chains of Responsibility progressivamente. 

# Referências Técnicas Integradas
A elaboração deste relatório baseou-se em práticas consolidadas de engenharia de software e documentação técnica de bibliotecas Python.

Padrões GoF em Python

OCR e Processamento de Imagem.   

Pipeline de Dados e ETL.   

Validação e Qualidade de Dados.   

Python Idioms e Metaprogramação.