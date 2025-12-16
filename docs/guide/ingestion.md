# Guia de Ingestão de E-mails

Este guia descreve como configurar e executar o pipeline de ingestão automática de Notas Fiscais via e-mail.

## Visão Geral

O módulo de ingestão conecta-se a uma conta de e-mail via protocolo IMAP, busca por mensagens contendo Notas Fiscais (filtrando por assunto), baixa os anexos PDF e os encaminha para o processador de extração.

## Configuração de Segurança (.env)

Por razões de segurança, as credenciais de e-mail **nunca** devem ser colocadas diretamente no código. Utilizamos um arquivo `.env` para gerenciar essas variáveis.

1.  Crie um arquivo chamado `.env` na raiz do projeto (você pode copiar o modelo `.env.example`).
2.  Preencha as seguintes variáveis:

```ini
# Configurações do Servidor IMAP
EMAIL_HOST=imap.gmail.com          # Ex: imap.gmail.com, outlook.office365.com
EMAIL_USER=seu.email@exemplo.com
EMAIL_PASS=sua_senha_de_app        # Use Senha de Aplicativo (App Password) se tiver 2FA ativado
EMAIL_FOLDER=INBOX                 # Pasta a ser monitorada
```

!!! warning "Atenção"
    Se você utiliza Gmail ou Outlook com autenticação de dois fatores (2FA), a sua senha de login normal **não funcionará**. Você deve gerar uma "Senha de Aplicativo" nas configurações de segurança da sua conta.

## Executando a Ingestão

Para iniciar o processo de varredura e processamento, execute o script dedicado:

```bash
python run_ingestion.py
```

### O que o script faz?

1.  **Conecta** ao servidor de e-mail usando SSL.
2.  **Busca** e-mails com o assunto "Nota Fiscal" (configurável no código).
3.  **Baixa** os anexos PDF para uma pasta temporária (`temp_email/`).
    *   *Nota:* O sistema gera nomes de arquivos únicos (UUID) para evitar que notas com nomes iguais (ex: `invoice.pdf`) se sobrescrevam.
4.  **Processa** cada arquivo baixado usando o `BaseInvoiceProcessor`.
5.  **Gera** um relatório consolidado em `data/output/relatorio_ingestao.csv`.

## Personalização

Você pode ajustar o filtro de busca editando o arquivo `run_ingestion.py`:

```python
# run_ingestion.py
assunto_teste = "Nota Fiscal"  # Altere para o assunto que seus fornecedores usam
```
