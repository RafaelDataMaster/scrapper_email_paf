# 🎯 Exemplos Práticos - Docker NFSe Scrapper

Guia rápido com comandos copy-paste para operações comuns.

---

## 🚀 Setup Inicial (Primeira Vez)

### Windows

```powershell
# 1. Clone o repositório (se ainda não tiver)
git clone <seu-repo-url>
cd scrapper

# 2. Execute o setup automático
setup-docker.bat

# 3. Edite o .env com suas credenciais (abre no Notepad)
notepad .env

# 4. Build e teste
docker-compose build
docker-compose run --rm scrapper python scripts/test_docker_setup.py
```

### Linux/Mac

```bash
# 1. Clone o repositório
git clone <seu-repo-url>
cd scrapper

# 2. Execute o setup automático
chmod +x setup-docker.sh
./setup-docker.sh

# 3. Edite o .env
nano .env  # ou vim, code, etc.

# 4. Build e teste
docker-compose build
docker-compose run --rm scrapper python scripts/test_docker_setup.py
```

---

## 📧 Configuração do Email

### Gmail com 2FA (Recomendado)

```bash
# 1. Gere uma senha de aplicativo:
#    https://myaccount.google.com/apppasswords
#
# 2. Configure no .env:
EMAIL_HOST=imap.gmail.com
EMAIL_USER=seu_email@gmail.com
EMAIL_PASS=xxxx xxxx xxxx xxxx  # Senha de app (com espaços mesmo!)
EMAIL_FOLDER=INBOX
```

### Outlook / Office 365

```bash
EMAIL_HOST=outlook.office365.com
EMAIL_USER=seu_email@outlook.com
EMAIL_PASS=sua_senha_de_app
EMAIL_FOLDER=INBOX
```

### Outros Provedores

```bash
# Yahoo
EMAIL_HOST=imap.mail.yahoo.com

# ProtonMail (precisa do Bridge)
EMAIL_HOST=127.0.0.1
EMAIL_PORT=1143

# Servidor customizado
EMAIL_HOST=mail.suaempresa.com.br
```

---

## ▶️ Execução

### Modo 1: Execução Manual (Uma Vez)

**Use quando:** Quer processar manualmente, testar, ou debugar.

```bash
# Executa uma vez e mostra output no terminal
docker-compose run --rm scrapper

# Com logs mais verbosos
docker-compose run --rm scrapper python -u run_ingestion.py
```

**Output esperado:**

```
📂 Diretório temporário criado: /app/temp_email
🔌 Conectando a imap.gmail.com como scrapper.nsfe@gmail.com...
🔍 Buscando e-mails com assunto: 'ENC'...
📦 5 anexo(s) encontrado(s). Iniciando processamento...
  Processing: nota_fiscal_123.pdf...
  Processing: boleto_456.pdf...
✅ Processamento concluído! Relatórios salvos em data/output/
```

### Modo 2: Execução Contínua (Cron)

**Use quando:** Quer que rode automaticamente de X em X minutos.

```bash
# Inicia em background (a cada 30 minutos)
docker-compose up -d scrapper-cron

# Verifica se está rodando
docker-compose ps

# Acompanha logs em tempo real
docker-compose logs -f scrapper-cron

# Para de acompanhar: Ctrl+C (container continua rodando)
```

**Para modificar o intervalo**, edite o `docker-compose.yml`:

```yaml
# A cada 15 minutos (900 segundos)
command: sh -c "while true; do python run_ingestion.py && sleep 900; done"

# A cada 1 hora (3600 segundos)
command: sh -c "while true; do python run_ingestion.py && sleep 3600; done"

# A cada 6 horas
command: sh -c "while true; do python run_ingestion.py && sleep 21600; done"
```

Depois de editar:

```bash
docker-compose down
docker-compose up -d scrapper-cron
```

### Modo 3: Cron do Sistema (Horários Específicos)

**Use quando:** Quer executar em horários fixos (ex: 9h e 18h).

**Linux (crontab):**

```bash
# Editar crontab
crontab -e

# Adicionar (executa às 9h e 18h):
0 9,18 * * * cd /caminho/para/scrapper && docker-compose run --rm scrapper >> /var/log/scrapper.log 2>&1

# Executa de hora em hora:
0 * * * * cd /caminho/para/scrapper && docker-compose run --rm scrapper

# Executa a cada 30 minutos:
*/30 * * * * cd /caminho/para/scrapper && docker-compose run --rm scrapper
```

**Windows (Task Scheduler):**

```powershell
# Criar script run_scrapper.bat:
@echo off
cd C:\Users\rafael.ferreira\Documents\scrapper
docker-compose run --rm scrapper >> logs\scrapper.log 2>&1

# Depois:
# 1. Abra o Task Scheduler (Agendador de Tarefas)
# 2. Criar Tarefa Básica
# 3. Trigger: Diariamente às 9h e 18h
# 4. Ação: Iniciar programa → run_scrapper.bat
```

---

## 📊 Monitoramento

### Ver Logs

```bash
# Logs em tempo real (Ctrl+C para sair)
docker-compose logs -f scrapper-cron

# Últimas 50 linhas
docker-compose logs --tail=50 scrapper-cron

# Logs de um período específico
docker-compose logs --since="2025-12-18T09:00:00" scrapper-cron

# Exportar logs para arquivo
docker-compose logs --no-color scrapper-cron > logs_$(date +%Y%m%d).txt
```

### Ver Status

```bash
# Containers ativos
docker-compose ps

# Recursos (CPU, RAM, Rede)
docker stats nfse-scrapper-cron

# Informações detalhadas
docker inspect nfse-scrapper-cron
```

### Healthcheck

```bash
# Verifica se o Tesseract está OK (healthcheck automático)
docker-compose exec scrapper-cron tesseract --version

# Testa manualmente
docker-compose exec scrapper-cron python -c "
import pytesseract
from config import settings
print('Tesseract:', pytesseract.get_tesseract_version())
print('Config:', settings.TESSERACT_CMD)
"
```

---

## 🧪 Testes e Validação

### Teste Completo de Setup

```bash
docker-compose run --rm scrapper python scripts/test_docker_setup.py
```

### Validar Regras de Extração

```bash
# Valida regras com PDFs em failed_cases_pdf/
docker-compose run --rm scrapper python scripts/validate_extraction_rules.py
```

### Inspecionar PDF

```bash
docker-compose run --rm scrapper python scripts/inspect_pdf.py arquivo.pdf
```

### Validação Batch com Correlação

```bash
docker-compose run --rm scrapper python scripts/validate_extraction_rules.py --batch-mode --apply-correlation
```

### Teste de Conexão Email (Interativo)

```bash
docker-compose run --rm scrapper python -c "
from ingestors.imap import ImapIngestor
from config import settings

print('Testando conexão...')
ingestor = ImapIngestor(
    host=settings.EMAIL_HOST,
    user=settings.EMAIL_USER,
    password=settings.EMAIL_PASS,
    folder=settings.EMAIL_FOLDER
)

try:
    ingestor.connect()
    print('✅ Conexão OK!')
    print(f'Pasta: {settings.EMAIL_FOLDER}')
except Exception as e:
    print(f'❌ Erro: {e}')
"
```

---

## 🔧 Manutenção

### Atualizar Código

```bash
# 1. Baixar atualizações
git pull origin main

# 2. Parar containers
docker-compose down

# 3. Rebuild (sem cache para forçar atualização)
docker-compose build --no-cache

# 4. Subir novamente
docker-compose up -d scrapper-cron
```

### Limpar Dados Temporários

```bash
# Limpa temp_email (é limpo automaticamente a cada execução)
docker-compose run --rm scrapper rm -rf temp_email/*

# Limpa logs antigos
docker-compose run --rm scrapper find /app -name "*.log" -mtime +30 -delete
```

### Backup de Dados

```bash
# Backup manual
tar -czf backup_$(date +%Y%m%d_%H%M%S).tar.gz data/

# Script de backup automático (Linux cron)
# Adicione ao crontab:
0 2 * * * cd /path/to/scrapper && tar -czf backup_$(date +\%Y\%m\%d).tar.gz data/ && find . -name "backup_*.tar.gz" -mtime +7 -delete
```

### Reset Completo

```bash
# Para tudo
docker-compose down

# Remove volumes (⚠️ DELETA DADOS!)
docker-compose down -v

# Remove imagens
docker rmi $(docker images -q 'scrapper*')

# Rebuild do zero
docker-compose build --no-cache
docker-compose up -d scrapper-cron
```

---

## 🐚 Acesso ao Container

### Shell Interativo

```bash
# Acessa bash do container em execução
docker-compose exec scrapper-cron bash

# Dentro do container, você pode:
ls data/output/           # Ver arquivos gerados
cat data/output/relatorio_nfse.csv  # Ver conteúdo
python run_ingestion.py   # Executar manualmente
tesseract --version       # Verificar Tesseract
```

### Executar Comandos One-Off

```bash
# Lista arquivos de output
docker-compose exec scrapper-cron ls -lh data/output/

# Conta quantos PDFs foram processados
docker-compose exec scrapper-cron wc -l data/output/relatorio_nfse.csv

# Verifica espaço em disco
docker-compose exec scrapper-cron df -h

# Ver variáveis de ambiente
docker-compose exec scrapper-cron env | grep EMAIL
```

---

## 📁 Acessar Dados Gerados

### No Host (Seu PC/Servidor)

Os dados são automaticamente sincronizados via volumes:

```bash
# Windows
dir data\output\
type data\output\relatorio_nfse.csv

# Linux/Mac
ls -lh data/output/
cat data/output/relatorio_nfse.csv
```

### Copiar do Container para Host

```bash
# Se por algum motivo não estiver usando volumes:
docker cp nfse-scrapper-cron:/app/data/output/relatorio_nfse.csv ./local_copy.csv
```

### Copiar do Host para Container

```bash
# Para testar um PDF específico:
docker cp meu_pdf_teste.pdf nfse-scrapper-cron:/app/failed_cases_pdf/
docker-compose exec scrapper-cron python scripts/validate_extraction_rules.py
```

---

## 🚨 Troubleshooting Rápido

### Container não inicia

```bash
# Ver logs de erro
docker-compose logs scrapper-cron

# Rebuild forçado
docker-compose build --no-cache
docker-compose up scrapper-cron  # Sem -d para ver output
```

### Erro "Tesseract not found"

```bash
# Verifica instalação
docker-compose run --rm scrapper which tesseract
docker-compose run --rm scrapper tesseract --version

# Se não aparecer, rebuild:
docker-compose build --no-cache
```

### Erro "Unable to get page count"

```bash
# Verifica Poppler
docker-compose run --rm scrapper which pdfinfo
docker-compose run --rm scrapper pdfinfo -v

# Se não aparecer, rebuild:
docker-compose build --no-cache
```

### Email não conecta

```bash
# Verifica credenciais
cat .env | grep EMAIL

# Testa dentro do container
docker-compose run --rm scrapper python -c "from config import settings; print(settings.EMAIL_HOST, settings.EMAIL_USER, settings.EMAIL_PASS[:4]+'***')"

# Testa conexão
docker-compose run --rm scrapper python -c "
from ingestors.imap import ImapIngestor
from config import settings
i = ImapIngestor(settings.EMAIL_HOST, settings.EMAIL_USER, settings.EMAIL_PASS)
i.connect()
print('OK!')
"
```

### PDFs não sendo extraídos

```bash
# Ativa modo debug
docker-compose run --rm scrapper python -c "
from core.processor import BaseInvoiceProcessor
processor = BaseInvoiceProcessor()
result = processor.process('failed_cases_pdf/seu_pdf.pdf')
print(result.__dict__)
"

# Testa extração manual
docker-compose run --rm scrapper python scripts/validate_extraction_rules.py
```

---

## 📈 Otimização de Performance

### Aumentar Recursos

Edite `docker-compose.yml`:

```yaml
deploy:
    resources:
        limits:
            cpus: "4.0" # Era 2.0, agora 4.0
            memory: 4G # Era 2G, agora 4G
```

Depois:

```bash
docker-compose down
docker-compose up -d scrapper-cron
```

### Paralelização (Para MUITOS Emails)

Modifique `run_ingestion.py` para processar em paralelo:

```python
from concurrent.futures import ThreadPoolExecutor

# ...
with ThreadPoolExecutor(max_workers=4) as executor:
    results = list(executor.map(processor.process, file_paths))
```

Ou rode múltiplas instâncias:

```bash
# docker-compose.yml - adicione:
scrapper-cron-2:
  <<: *scrapper-cron  # Referência
  container_name: nfse-scrapper-cron-2

scrapper-cron-3:
  <<: *scrapper-cron
  container_name: nfse-scrapper-cron-3
```

---

## 🎓 Dicas Avançadas

### Integração com CI/CD (GitHub Actions)

Crie `.github/workflows/docker.yml`:

```yaml
name: Build and Push Docker

on:
    push:
        branches: [main]

jobs:
    build:
        runs-on: ubuntu-latest
        steps:
            - uses: actions/checkout@v3

            - name: Build image
              run: docker-compose build

            - name: Run tests
              run: docker-compose run --rm scrapper python scripts/test_docker_setup.py

            - name: Push to Docker Hub
              run: |
                  echo "${{ secrets.DOCKER_PASSWORD }}" | docker login -u "${{ secrets.DOCKER_USERNAME }}" --password-stdin
                  docker-compose push
```

### Monitoramento com Prometheus

Adicione ao `docker-compose.yml`:

```yaml
prometheus:
    image: prom/prometheus
    volumes:
        - ./prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
        - "9090:9090"

grafana:
    image: grafana/grafana
    ports:
        - "3000:3000"
```

### Alertas por Email/Slack

Instale `requests`:

```bash
# Adicione ao requirements.txt
requests

# No run_ingestion.py, adicione:
import requests

def notify_slack(message):
    webhook_url = os.getenv('SLACK_WEBHOOK')
    if webhook_url:
        requests.post(webhook_url, json={"text": message})

# Use:
notify_slack(f"✅ Processados {len(anexos)} anexos com sucesso!")
```

---

## 🆘 Ajuda

**Documentação Completa:** [README-DOCKER.md](README-DOCKER.md)

**Análise do Projeto:** [DOCKER-MIGRATION.md](DOCKER-MIGRATION.md)

**Issues Comuns:** Veja seção Troubleshooting no README-DOCKER.md

**Suporte:** rafael.ferreira@soumaster.com.br

---

**Última atualização:** 18/12/2025
