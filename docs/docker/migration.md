# 📊 Análise e Migração para Docker - NFSe Scrapper

## Resumo Executivo

O projeto foi completamente analisado e preparado para execução em Docker. Todos os arquivos necessários foram criados, incluindo tratamento especial para as dependências externas (Tesseract e Poppler).

---

## 🔍 Análise do Projeto

### Estrutura Identificada

**Tipo:** Sistema de scraping e extração de dados de PDFs via email (IMAP)

**Componentes principais:**

1. **Ingestão** (`ingestors/imap.py`) - Conexão IMAP e download de anexos
2. **Processamento** (`core/processor.py`) - Orquestração da extração
3. **Estratégias** (`strategies/`) - Native PDF, OCR, Fallback
4. **Extratores** (`extractors/`) - NFSe e Boletos especializados
5. **Configuração** (`config/settings.py`) - Centralização de settings

### Dependências Críticas

**Python (requirements.txt):**

- `pdfplumber` - Extração de PDFs vetoriais
- `pytesseract` - Interface Python para Tesseract
- `pdf2image` - Conversão PDF → Imagem
- `pandas` - Manipulação de dados
- `pillow` - Processamento de imagens
- `python-dotenv` - Variáveis de ambiente

**Binários Externos (Windows vs Linux):**

| Dependência | Windows (Dev)                                  | Linux (Docker)       |
| ----------- | ---------------------------------------------- | -------------------- |
| Tesseract   | `C:\Program Files\Tesseract-OCR\tesseract.exe` | `/usr/bin/tesseract` |
| Poppler     | `C:\Poppler\...\Library\bin`                   | `/usr/bin`           |

### Fluxo de Execução

```
Email (IMAP) → Download Anexos → Salva em temp_email/
                    ↓
         Processamento (processor.py)
                    ↓
         Estratégia de Leitura (Fallback)
         ├─ Native PDF (pdfplumber) → sucesso? → Extração
         └─ OCR (Tesseract + Poppler) → Extração
                    ↓
         Classificação (NFSe vs Boleto)
                    ↓
         Extrator Especializado
                    ↓
         CSV Output (data/output/)
```

---

## 🐳 Solução de Dockerização

### Arquivos Criados

1. ✅ **Dockerfile** - Multi-stage build otimizado
    - Base: `python:3.11-slim`
    - Instala: `tesseract-ocr`, `tesseract-ocr-por`, `poppler-utils`
    - Usuário não-root: `scrapper:1000`
    - Healthcheck para Tesseract

2. ✅ **docker-compose.yml** - Orquestração completa
    - Serviço `scrapper`: Execução única
    - Serviço `scrapper-cron`: Execução periódica (30 min)
    - Volumes para persistência de dados
    - Configuração de recursos (CPU/RAM)
    - Logs rotacionados

3. ✅ **.dockerignore** - Otimização de build
    - Exclui: `__pycache__`, dados locais, documentação, testes

4. ✅ **docker-entrypoint.sh** - Script de inicialização
    - Valida Tesseract e Poppler
    - Verifica credenciais
    - Cria estrutura de diretórios

5. ✅ **README-DOCKER.md** - Documentação completa
    - Guia de instalação
    - Comandos úteis
    - Troubleshooting
    - Exemplos de uso

6. ✅ **Makefile** - Atalhos para comandos Docker
    - `make build`, `make up`, `make logs`, etc.
    - Simplifica operações complexas

7. ✅ **setup-docker.sh / .bat** - Setup automático
    - Valida pré-requisitos
    - Cria `.env` se não existir
    - Build e teste inicial
    - Suporte Windows e Linux

8. ✅ **run_ingestion.py --status** - Validação de ambiente
    - Verifica status do sistema e checkpoints
    - Valida configurações de email
    - Mostra dados parciais pendentes

### Modificações no Código Existente

**config/settings.py** - Detecção automática de SO:

```python
import platform
is_linux = platform.system() == 'Linux'

if is_linux:
    TESSERACT_CMD = os.getenv('TESSERACT_CMD', '/usr/bin/tesseract')
    POPPLER_PATH = os.getenv('POPPLER_PATH', '/usr/bin')
else:
    TESSERACT_CMD = os.getenv('TESSERACT_CMD', r'C:\Program Files\...')
    POPPLER_PATH = os.getenv('POPPLER_PATH', r'C:\Poppler\...')
```

**Benefício:** Mesmo código funciona em Windows (dev) e Linux (prod)

---

## 🚀 Como Usar

### Setup Inicial (Primeira Vez)

**Windows:**

```bash
setup-docker.bat
```

**Linux/Mac:**

```bash
chmod +x setup-docker.sh
./setup-docker.sh
```

### Execução Manual (Uma Vez)

```bash
docker-compose run --rm scrapper
```

### Execução Automática (Cron - A cada 30 min)

```bash
docker-compose up -d scrapper-cron
docker-compose logs -f scrapper-cron
```

### Comandos Úteis

```bash
# Com Makefile (mais fácil)
make build          # Build da imagem
make up             # Inicia em background
make logs           # Ver logs
make shell          # Acessar bash do container
make test           # Testar configuração
make restart        # Rebuild + restart

# Sem Makefile
docker-compose build
docker-compose up -d scrapper-cron
docker-compose logs -f scrapper-cron
docker-compose exec scrapper-cron bash
```

---

## 🔧 Dependências Externas - Resolução

### Problema

O projeto depende de binários externos (Tesseract e Poppler) que:

- No Windows: Precisam ser instalados manualmente e configurados via paths
- No Docker: Precisam estar disponíveis no container Linux

### Solução Implementada

**1. Instalação no Dockerfile:**

```dockerfile
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-por \  # Idioma português!
    poppler-utils \
    libpoppler-dev
```

**2. Configuração Automática:**

O `settings.py` detecta o SO automaticamente:

- **Linux (Docker):** Usa `/usr/bin/tesseract` e `/usr/bin`
- **Windows (Dev):** Usa os paths do Windows

**3. Override Manual (se necessário):**

Via `.env`:

```env
TESSERACT_CMD=/usr/bin/tesseract
POPPLER_PATH=/usr/bin
```

Via `docker-compose.yml`:

```yaml
environment:
    - TESSERACT_CMD=/usr/bin/tesseract
    - POPPLER_PATH=/usr/bin
```

### Validação

Execute o teste para confirmar que tudo está instalado:

```bash
# Verificar status do sistema
docker-compose run --rm scrapper python run_ingestion.py --status

# Validar regras de extração
docker-compose run --rm scrapper python scripts/validate_extraction_rules.py --batch-mode
```

Output esperado:

```
📊 STATUS DA INGESTÃO
   Status: READY
   E-mails processados: 0
   Lotes criados: 0
   ...
✅ Validação concluída - X sucessos, Y falhas
```

---

## 📁 Estrutura de Volumes

```
Host (seu PC/servidor)          Container (Docker)
┌─────────────────────────┐    ┌────────────────────────┐
│ ./data/output/          │ ←→ │ /app/data/output/      │
│ ./data/debug_output/    │ ←→ │ /app/data/debug_output/│
│ ./failed_cases_pdf/     │ ←→ │ /app/failed_cases_pdf/ │
│ [volume] temp_email     │ ←→ │ /app/temp_email/       │
└─────────────────────────┘    └────────────────────────┘
```

**Benefícios:**

- Dados persistem mesmo se o container for destruído
- Acesso fácil aos CSVs gerados
- Debug de PDFs problemáticos

---

## 🔐 Segurança

✅ Container roda com usuário não-root (`scrapper:1000`)
✅ Credenciais via `.env` (nunca commitadas)
✅ `.dockerignore` evita vazar dados sensíveis na imagem
✅ Volumes isolados do host
✅ Resource limits (CPU/RAM) configurados

---

## ⚡ Performance

### Otimizações Implementadas

1. **Multi-stage build** - Imagem final menor
2. **Cache de layers** - Build incremental mais rápido
3. **Logs rotacionados** - Previne disco cheio
4. **Resource limits** - Previne consumir todos os recursos do servidor

### Configuração de Recursos

Edite em `docker-compose.yml`:

```yaml
deploy:
    resources:
        limits:
            cpus: "2.0" # Máximo de CPUs
            memory: 2G # Máximo de RAM
        reservations:
            cpus: "0.5" # Garantido
            memory: 512M
```

**Recomendações:**

- **Leve** (poucos PDFs): 1 CPU, 1GB RAM
- **Médio** (100-500 PDFs/dia): 2 CPUs, 2GB RAM
- **Pesado** (1000+ PDFs/dia): 4 CPUs, 4GB RAM

---

## 🐛 Troubleshooting

### Erro: "Tesseract not found"

```bash
# Verifique se está instalado
docker-compose run --rm scrapper which tesseract

# Se não, rebuild:
docker-compose build --no-cache
```

### Erro: "Unable to get page count (Poppler)"

```bash
# Verifique pdfinfo
docker-compose run --rm scrapper which pdfinfo

# Teste manualmente
docker-compose run --rm scrapper pdfinfo --version
```

### Container não conecta ao email

```bash
# Verifique se o .env está correto
cat .env

# Teste as variáveis dentro do container
docker-compose run --rm scrapper python -c "from config import settings; print(settings.EMAIL_HOST, settings.EMAIL_USER)"
```

### OCR muito lento

**Causa:** PDFs escaneados são processados via OCR, que é lento.

**Solução:**

1. Aumente recursos do container (mais CPUs)
2. Processe em lote menor
3. Use GPU (requer Tesseract com suporte CUDA)

---

## 📈 Próximos Passos Recomendados

### Curto Prazo

1. ✅ Teste local com `docker-compose run --rm scrapper`
2. ✅ Valide extração de NFSe e Boletos
3. ✅ Configure cron com `docker-compose up -d scrapper-cron`
4. ✅ Monitore logs por 24h

### Médio Prazo

1. [ ] Deploy em servidor de produção (VPS, AWS, Azure)
2. [ ] Configure backup automático de `data/output/`
3. [ ] Integre com sistema de monitoramento (Grafana, Prometheus)
4. [ ] Implemente alertas (email/Slack quando falhar)

### Longo Prazo

1. [ ] Migre para Kubernetes (se escalar muito)
2. [ ] Adicione fila de processamento (RabbitMQ, Redis)
3. [ ] Implemente retry automático para falhas
4. [ ] Dashboard web para visualizar extrações

---

## 📚 Referências e Links Úteis

- **Docker Desktop:** https://www.docker.com/products/docker-desktop/
- **Docker Compose:** https://docs.docker.com/compose/
- **Tesseract OCR:** https://github.com/tesseract-ocr/tesseract
- **Poppler:** https://poppler.freedesktop.org/
- **Documentação do Projeto:** [README-DOCKER.md](README-DOCKER.md)

---

## 💬 Suporte

**Desenvolvedor:** rafael.ferreira@soumaster.com.br

**Repositório:** c:\Users\rafael.ferreira\Documents\scrapper

**Data da Migração:** 18/12/2025

---

## ✅ Checklist de Validação

Antes de fazer deploy em produção, valide:

- [ ] Docker e Docker Compose instalados
- [ ] Arquivo `.env` configurado com credenciais corretas
- [ ] Teste local executado com sucesso (`make test`)
- [ ] Logs não mostram erros de Tesseract/Poppler
- [ ] CSVs sendo gerados em `data/output/`
- [ ] Emails sendo processados corretamente
- [ ] Container reinicia automaticamente em caso de falha
- [ ] Backup configurado para `data/output/`
- [ ] Monitoramento de recursos (CPU/RAM/Disco)
- [ ] Documentação lida e compreendida

---

**🎉 Projeto totalmente dockerizado e pronto para produção!**
