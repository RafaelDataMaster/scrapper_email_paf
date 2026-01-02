# 🐳 Guia de Dockerização - NFSe Scrapper

Este guia explica como executar o projeto de scraping de NFSe e Boletos usando Docker, incluindo as dependências externas (Tesseract e Poppler).

## 📋 Pré-requisitos

- Docker Engine 20.10+
- Docker Compose 2.0+
- Arquivo `.env` configurado com credenciais de email

## 🚀 Quick Start

### 1. Clone o repositório e entre na pasta

```bash
cd scrapper
```

### 2. Configure as variáveis de ambiente

Copie o arquivo de exemplo e edite com suas credenciais:

```bash
cp .env.example .env
```

Edite o arquivo `.env`:

```env
EMAIL_HOST=imap.gmail.com
EMAIL_USER=seu_email@gmail.com
EMAIL_PASS=sua_senha_de_aplicativo
EMAIL_FOLDER=INBOX
```

**⚠️ IMPORTANTE:**

- Para Gmail, use uma [senha de aplicativo](https://myaccount.google.com/apppasswords), não sua senha normal!
- As variáveis `TESSERACT_CMD` e `POPPLER_PATH` são automaticamente configuradas no container Linux

### 3. Build da imagem

```bash
docker-compose build
```

### 4. Execute o scrapper

#### Execução única (manual)

```bash
docker-compose run --rm scrapper
```

#### Execução contínua (a cada 30 minutos)

```bash
docker-compose up -d scrapper-cron
```

Para ver os logs:

```bash
docker-compose logs -f scrapper-cron
```

## 📁 Estrutura de Volumes

O Docker monta volumes para persistir dados entre execuções:

```
./data/output/          → Relatórios CSV gerados (nfse.csv, boletos.csv)
./data/debug_output/    → Relatórios de debug e qualidade
./failed_cases_pdf/     → PDFs de teste (somente leitura)
```

Todos os arquivos gerados ficam disponíveis no seu sistema de arquivos local.

## 🔧 Dependências Externas no Container

### Tesseract OCR

**No Windows (desenvolvimento):**

```
C:\Program Files\Tesseract-OCR\tesseract.exe
```

**No Docker (produção):**

```
/usr/bin/tesseract
```

Instalado via `apt-get install tesseract-ocr tesseract-ocr-por` no Dockerfile.

### Poppler (pdf2image)

**No Windows (desenvolvimento):**

```
C:\Poppler\...\Library\bin
```

**No Docker (produção):**

```
/usr/bin (pdfinfo, pdftocairo, etc.)
```

Instalado via `apt-get install poppler-utils libpoppler-dev` no Dockerfile.

## 📊 Comandos Úteis

### Build e inicialização

```bash
# Build da imagem
docker-compose build

# Executa uma vez e remove o container
docker-compose run --rm scrapper

# Inicia em modo daemon (background)
docker-compose up -d scrapper-cron
```

### Monitoramento

```bash
# Ver logs em tempo real
docker-compose logs -f scrapper-cron

# Status dos containers
docker-compose ps

# Inspecionar recursos
docker stats nfse-scrapper-cron
```

### Debugging

```bash
# Acessar shell do container
docker-compose exec scrapper-cron bash

# Testar Tesseract manualmente
docker-compose exec scrapper-cron tesseract --version

# Testar Python
docker-compose exec scrapper-cron python -c "import pytesseract; print(pytesseract.get_tesseract_version())"
```

### Manutenção

```bash
# Parar containers
docker-compose down

# Parar e remover volumes
docker-compose down -v

# Limpar cache de build
docker-compose build --no-cache

# Rebuild completo
docker-compose down -v && docker-compose build --no-cache && docker-compose up -d
```

## 🧪 Testando a Configuração

Execute este comando para validar se tudo está funcionando:

```bash
docker-compose run --rm scrapper python -c "
import pytesseract
from pdf2image import convert_from_path
from config import settings

print('✅ Tesseract:', pytesseract.get_tesseract_version())
print('✅ Config OK:', settings.TESSERACT_CMD)
"
```

## 🔐 Segurança

- O container roda com usuário não-root (`scrapper:1000`)
- Senhas nunca vão para a imagem (apenas via `.env`)
- Volumes são isolados do sistema
- Logs rotacionados automaticamente (max 10MB x 3 arquivos)

## 🎯 Executando Scripts Específicos

### Validar regras de extração

```bash
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

## ⚙️ Ajustes de Performance

Edite `docker-compose.yml` para ajustar recursos:

```yaml
deploy:
    resources:
        limits:
            cpus: "4.0" # Aumentar para processar mais PDFs
            memory: 4G # Aumentar se tiver muitos PDFs grandes
        reservations:
            cpus: "1.0"
            memory: 1G
```

## 🐛 Troubleshooting

### Erro: "Tesseract not found"

**Solução:** Verifique se a build incluiu o Tesseract:

```bash
docker-compose run --rm scrapper which tesseract
```

### Erro: "Unable to get page count (Poppler)"

**Solução:** Verifique se o Poppler está instalado:

```bash
docker-compose run --rm scrapper which pdfinfo
```

### PDFs não estão sendo processados

**Solução:** Verifique os logs:

```bash
docker-compose logs scrapper-cron | grep -i erro
```

### Container não consegue conectar ao email

**Solução:** Verifique:

1. Se o `.env` está no diretório correto
2. Se as credenciais estão corretas
3. Se o Gmail tem autenticação de 2 fatores ativa (precisa de senha de app)

```bash
docker-compose run --rm scrapper python -c "from config import settings; print(settings.EMAIL_HOST, settings.EMAIL_USER)"
```

## 📚 Diferenças Windows vs Docker

| Componente | Windows (Dev)                                  | Docker (Prod)                 |
| ---------- | ---------------------------------------------- | ----------------------------- |
| Tesseract  | `C:\Program Files\Tesseract-OCR\tesseract.exe` | `/usr/bin/tesseract`          |
| Poppler    | `C:\Poppler\...\Library\bin`                   | `/usr/bin` (pdfinfo, etc.)    |
| Python     | Instalação local                               | Python 3.11 slim no container |
| Paths      | Barras invertidas `\`                          | Barras normais `/`            |

**As configurações são ajustadas automaticamente!** O `settings.py` usa `os.getenv()` que lê do `.env` ou do Dockerfile.

## 🚢 Deploy em Produção

### Opção 1: Docker Compose (servidor único)

```bash
# No servidor
git clone <repo>
cd scrapper
cp .env.example .env
# Edite o .env com credenciais de produção
docker-compose up -d scrapper-cron
```

### Opção 2: Docker Swarm (múltiplos nós)

```bash
docker stack deploy -c docker-compose.yml nfse-stack
```

### Opção 3: Kubernetes

Converta o `docker-compose.yml` para manifests K8s:

```bash
kompose convert -f docker-compose.yml
kubectl apply -f .
```

## 📝 Logs e Monitoramento

Os logs são salvos em formato JSON e rotacionados automaticamente:

```bash
# Tail logs
docker-compose logs -f --tail=100 scrapper-cron

# Exportar logs
docker-compose logs --no-color scrapper-cron > logs_$(date +%Y%m%d).txt
```

## 🔄 Atualizações

Para atualizar o código e rebuildar:

```bash
git pull
docker-compose down
docker-compose build --no-cache
docker-compose up -d scrapper-cron
```

## 💡 Dicas Avançadas

### Executar em horários específicos (cron real)

Crie um arquivo `crontab` no host:

```cron
# Executar todo dia às 9h e 18h
0 9,18 * * * cd /path/to/scrapper && docker-compose run --rm scrapper >> /var/log/scrapper.log 2>&1
```

### Integração com CI/CD

Exemplo de GitHub Actions:

```yaml
name: Build and Push Docker Image

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
            - name: Push to registry
              run: docker-compose push
```

---

**📧 Suporte:** rafael.ferreira@soumaster.com.br
