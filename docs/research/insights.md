# Insights e Aprendizados do Projeto

Este documento serve como um "Diário de Bordo" técnico. Aqui registramos descobertas, problemas encontrados com bibliotecas específicas e a racional por trás de decisões técnicas que não são óbvias apenas olhando para o código.

---

## 1. Desafios com OCR e Tesseract

### O Problema da Instalação no Windows

Uma das maiores barreiras de entrada para este projeto foi a dependência do Tesseract OCR. Diferente de bibliotecas Python puras (`pip install`), o Tesseract é um binário externo.

* **Sintoma:** Erro `TesseractNotFoundError` ou `Path not found`.
* **Solução:** Foi necessário implementar uma configuração explícita em `config/settings.py` para apontar para o executável (`C:\Program Files\Tesseract-OCR\tesseract.exe`).
* **Lição:** Para distribuição futura (Docker ou exe), o caminho do Tesseract não pode ser *hardcoded*. Precisamos verificar variáveis de ambiente primeiro.

### Qualidade vs. Velocidade

Testes iniciais mostraram que o Tesseract é lento. Processar um PDF de 1 página leva cerca de 2 a 4 segundos.

* **Decisão:** O OCR deve ser sempre o **último recurso**. A estratégia `NativePdfStrategy` (usando `pdfplumber`) é instantânea (milissegundos). O sistema de fallback foi desenhado especificamente para priorizar velocidade e só pagar o custo de performance do OCR quando estritamente necessário (arquivos digitalizados).

---

## 2. Extração de Texto: PDFPlumber vs. PyPDF2

Durante a fase de pesquisa (Fase 1), avaliamos bibliotecas de leitura de PDF.

* **PyPDF2:** Muito popular, mas foca em manipulação de arquivos (cortar, girar, unir). A extração de texto é pobre e perde o layout (espaços em branco).
* **PDFPlumber:** Foca na extração de dados. Ele mantém a estrutura espacial (tabelas, colunas).
* **Veredito:** Escolhemos `pdfplumber`. A precisão na detecção de quebras de linha e colunas é crucial para separar "Rótulo" de "Valor" (ex: "CNPJ:" e "12.345...").

---

## 3. Modelagem de Dados e Imutabilidade

Inicialmente, usávamos dicionários Python (`dict`) para passar dados entre funções.

* **Problema:** Dicionários são frágeis. Não há garantia de que a chave `cnpj` existe, e erros de digitação (`cpnj`) passavam silenciosos até o momento de salvar o CSV.
* **Solução:** Adoção de `dataclasses` (`core.models.InvoiceData`).
* **Benefício:** Autocomplete na IDE, tipagem forte (sabemos que `valor` é `float`, não `str`) e garantia de estrutura. Se um campo for adicionado no futuro, a IDE avisa onde precisamos atualizar o código.

---

## 4. Estratégia de Regex (Expressões Regulares)

A extração de valores monetários brasileiros é traiçoeira.

* Formatos encontrados: `1.234,56`, `1234,56`, `1 234,56`.
* O ponto (`.`) pode ser separador de milhar ou decimal (em notas internacionais).
* **Decisão:** Padronizamos uma função de limpeza que remove tudo que não é dígito ou vírgula final, e então converte para float padrão Python (ponto como decimal). Isso centraliza a lógica de conversão em um único lugar, evitando bugs dispersos.

---

## 5. Ingestão de E-mails e Segurança

A implementação do módulo de ingestão trouxe desafios de arquitetura e segurança que não existiam no processamento local.

### O "Gap" Memória vs. Disco

Bibliotecas de e-mail (`imaplib`) retornam anexos como objetos de bytes na memória RAM. No entanto, bibliotecas de PDF (`pdfplumber`) e OCR (`pytesseract`) são otimizadas para ler caminhos de arquivos no disco.

* **Solução:** Implementamos um *buffer* em disco (`temp_email/`). O script baixa os bytes, materializa um arquivo temporário, processa e (opcionalmente) deleta. Isso desacopla a lógica de rede da lógica de processamento.

### Colisão de Nomes de Arquivo

Em testes reais, descobrimos que muitos fornecedores enviam arquivos com nomes genéricos como `invoice.pdf` ou `nota.pdf`.

* **Risco:** Se processarmos 10 e-mails em sequência, o arquivo `invoice.pdf` do e-mail 10 sobrescreveria o do e-mail 1 antes que pudéssemos auditá-lo.
* **Solução:** Adoção de UUIDs. Todo arquivo salvo recebe um prefixo único (ex: `a1b2c3d4_invoice.pdf`), garantindo rastreabilidade e evitando perda de dados.

### Segurança de Credenciais (12-Factor App)

Inicialmente, para testes rápidos, as senhas estavam no código.

* **Ação:** Migração imediata para variáveis de ambiente (`.env`) usando `python-dotenv`.
* **Insight:** Além de segurança, isso facilita a troca de ambientes (Dev vs. Prod) sem alterar uma linha de código. O uso de "Senhas de Aplicativo" (App Passwords) provou-se essencial para contornar o 2FA de provedores modernos como Gmail.

---

## 6. Desafios de Extração e Padrões de Falha (Fase de Testes)

Durante a validação com dados reais (Dez/2025), identificamos três categorias principais de falhas na extração de dados, mesmo quando o arquivo é baixado corretamente.

### Falsos Positivos (Boletos e Recibos)

Muitos e-mails contêm anexos que são PDFs válidos, mas não são Notas Fiscais de Serviço (NFSe).

* **Sintoma:** O extrator roda, não encontra campos de NF (Número, CNPJ Prestador) e retorna valores vazios ou nulos.
* **Exemplos:** `Boleto Locaweb.pdf`, `Comprovante de Entrega.pdf`.
* **Solução Proposta:** Implementar uma etapa de **Classificação de Documento** antes da extração. Se o texto contiver palavras-chave fortes como "Boleto", "Recibo de Entrega" ou "Fatura", o arquivo deve ser ignorado ou marcado com uma flag `tipo_documento="OUTROS"`, evitando poluir o dataset de notas fiscais.

### Variação de Layout (Regex Específica Necessária)

O extrator genérico (`GenericExtractor`) funciona bem para layouts padrão (ABRASF), mas falha em prefeituras com layouts proprietários.

* **Caso 1 (Vila Velha):** O campo "Número da Nota" aparece rotulado como `Número Cód`, o que foge da regex padrão `Número da Nota`.
* **Caso 2 (Repromaq/Outros):** O valor monetário às vezes não é capturado porque o OCR ou o layout insere caracteres estranhos ou quebras de linha inesperadas entre o símbolo `R$` e o número.
* **Solução Proposta:** Criação de **Extratores Específicos** (Strategy Pattern).
  * Criar `VilaVelhaExtractor` que herda de `BaseExtractor` mas sobrescreve as regexes problemáticas.
  * O `Processor` deve iterar sobre uma lista de extratores (`[VilaVelhaExtractor, GenericExtractor]`) e usar o primeiro que validar com sucesso (`can_handle()`).

### Documentos Auxiliares de Locação

Alguns documentos são híbridos (Recibos de Locação) que juridicamente funcionam como comprovante, mas não têm a estrutura de uma NFSe.

* **Insight:** Tentar forçar a extração de "Número de Nota" nesses documentos é um erro conceitual. Eles devem ser tratados como uma categoria à parte ou ignorados se o escopo for estritamente NFSe.

---

## 7. Boletos: FORNECEDOR vazio (falso positivo) e texto corrompido

Durante a validação com boletos reais (Dez/2025) apareceu um padrão onde o processamento mostrava **EMPRESA correta**, mas **FORNECEDOR vazio**, mesmo quando o texto bruto continha claramente “MAIS CONSULTORIA… <CNPJ>”.

### Causas-raiz

1) **Heurística permissiva demais para “nome nosso”**

- Existia um pós-processamento para limpar `fornecedor_nome` quando ele parecesse ser “uma empresa nossa”.
- A heurística anterior marcava como “nosso” se o nome contivesse um token do cadastro que podia ser genérico.
- Resultado: nomes de fornecedor como “... SERVICOS LTDA” eram apagados por falso positivo.

2) **Classificação de boleto frágil com OCR/híbrido**

- PDFs híbridos podem corromper palavras-chave (“NÚMERO” → “NMERO”, “BENEFICIÁRIO” → variações) e quebrar palavras no meio.
- Se a classificação falha, o `GenericExtractor` pode ser escolhido e deixar campos de boleto incompletos.

### Solução implementada

- `is_nome_nosso()` ficou mais conservador: só considera códigos curtos/distintivos e ignora stopwords comuns para reduzir falso positivo.
- `BoletoExtractor.can_handle()` ficou mais resiliente a texto corrompido (normalização + detecção com stems) e passou a retornar booleano de forma consistente.

### Lição

- Para definir “empresa nossa”, priorize **CNPJ do cadastro** (determinístico) e seja conservador em heurísticas por nome.
- Quando um campo “sumiu”, use `scripts/debug_pdf.py --full-text` para confirmar como o PDF está quebrando palavras e se o extrator correto está sendo selecionado.
