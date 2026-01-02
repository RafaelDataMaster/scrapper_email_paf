# ⚡ Referência Rápida - Docker Commands

Comandos mais usados em ordem de frequência.

---

## 🔥 Top 10 Comandos

```bash
# 1. Ver logs em tempo real
docker-compose logs -f scrapper-cron

# 2. Executar uma vez
docker-compose run --rm scrapper

# 3. Iniciar em background
docker-compose up -d scrapper-cron

# 4. Parar tudo
docker-compose down

# 5. Ver status
docker-compose ps

# 6. Acessar shell
docker-compose exec scrapper-cron bash

# 7. Rebuild
docker-compose build

# 8. Restart completo
docker-compose restart scrapper-cron

# 9. Ver últimas 50 linhas de log
docker-compose logs --tail=50 scrapper-cron

# 10. Testar configuração
docker-compose run --rm scrapper python scripts/test_docker_setup.py
```

---

## 📋 Makefile Shortcuts

```bash
make help           # Lista todos os comandos
make build          # Build da imagem
make up             # Inicia em background
make down           # Para tudo
make logs           # Ver logs
make shell          # Acessa bash
make test           # Testa setup
make restart        # Down + Build + Up
make clean          # Remove tudo
```

---

## 🚀 Workflows Comuns

### Primeira Vez

```bash
./setup-docker.sh   # ou setup-docker.bat no Windows
# Edite o .env
make build
make test
make up
```

### Dia a Dia

```bash
make logs           # Ver o que está acontecendo
make shell          # Investigar algo
make restart        # Se algo der errado
```

### Deploy/Atualização

```bash
git pull
make down
make build
make test
make up
```

### Debug

```bash
make logs           # Ver erros
make shell          # Entrar no container
make test           # Validar setup
# Investigar manualmente:
docker-compose run --rm scrapper python -c "..."
```

---

## 📊 Monitoramento

```bash
# Logs
docker-compose logs -f scrapper-cron
docker-compose logs --tail=100 scrapper-cron
docker-compose logs --since="1h" scrapper-cron

# Status
docker-compose ps
docker stats nfse-scrapper-cron
docker inspect nfse-scrapper-cron

# Healthcheck
docker-compose exec scrapper-cron tesseract --version
docker-compose exec scrapper-cron pdfinfo -v
```

---

## 🔧 Manutenção

```bash
# Atualizar
git pull && make restart

# Limpar
make clean              # Remove containers/volumes
make clean-all          # Remove tudo + imagens

# Backup
make backup-data        # Cria backup_YYYYMMDD_HHMMSS.tar.gz

# Reset completo
docker-compose down -v && docker-compose build --no-cache && docker-compose up -d
```

---

## 🐚 Container Shell

```bash
# Entrar
docker-compose exec scrapper-cron bash

# Comandos úteis dentro do container
ls data/output/
cat data/output/relatorio_nfse.csv | wc -l
python run_ingestion.py
tesseract --version
pdfinfo -v
env | grep EMAIL
df -h
top
```

---

## 🧪 Testes

```bash
# Setup completo
make test

# Scripts específicos
docker-compose run --rm scrapper python scripts/validate_extraction_rules.py
docker-compose run --rm scrapper python scripts/validate_extraction_rules.py --batch-mode --apply-correlation
docker-compose run --rm scrapper python scripts/inspect_pdf.py arquivo.pdf

# Teste de conexão email
docker-compose run --rm scrapper python -c "from ingestors.imap import ImapIngestor; from config import settings; i = ImapIngestor(settings.EMAIL_HOST, settings.EMAIL_USER, settings.EMAIL_PASS); i.connect(); print('OK')"

# Teste de extração em PDF específico
docker-compose run --rm scrapper python -c "from core.processor import BaseInvoiceProcessor; p = BaseInvoiceProcessor(); print(p.process('failed_cases_pdf/teste.pdf').__dict__)"
```

---

## 🚨 Troubleshooting One-Liners

```bash
# Container não inicia?
docker-compose up scrapper-cron  # Sem -d para ver erro

# Tesseract não encontrado?
docker-compose run --rm scrapper which tesseract

# Poppler não encontrado?
docker-compose run --rm scrapper which pdfinfo

# Email não conecta?
docker-compose run --rm scrapper python -c "from config import settings; print(settings.EMAIL_HOST, settings.EMAIL_USER)"

# Rebuild forçado
docker-compose build --no-cache

# Ver todos os erros recentes
docker-compose logs --tail=100 scrapper-cron | grep -i erro

# Espaço em disco
docker system df
docker system prune -a  # ⚠️ Remove tudo que não está em uso!
```

---

## 📁 Arquivos e Diretórios

```bash
# Dados gerados (no host)
ls -lh data/output/
cat data/output/relatorio_nfse.csv
cat data/output/relatorio_boletos.csv

# Copiar arquivo para testar
cp ~/Downloads/meu_pdf.pdf failed_cases_pdf/
make run-once

# Backup
tar -czf backup.tar.gz data/
```

---

## 🎛️ Configuração

```bash
# Ver configurações atuais
cat .env

# Validar .env
make env-check

# Editar (Linux/Mac)
nano .env

# Editar (Windows)
notepad .env

# Recarregar após mudar .env
make restart
```

---

## 📈 Performance

```bash
# Ver uso de recursos
docker stats nfse-scrapper-cron

# Aumentar recursos (editar docker-compose.yml)
nano docker-compose.yml  # Seção deploy.resources

# Ver logs de performance
docker-compose logs scrapper-cron | grep "Processing:"
```

---

## 🔄 Múltiplos Ambientes

```bash
# Desenvolvimento
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up

# Produção
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Teste
docker-compose -f docker-compose.test.yml run --rm scrapper-test
```

---

## 🌐 Rede e Portas

```bash
# Ver redes
docker network ls
docker network inspect scrapper_scrapper-network

# Conectar outro container na mesma rede
docker run --network scrapper_scrapper-network ...
```

---

## 💾 Volumes

```bash
# Listar volumes
docker volume ls

# Inspecionar volume
docker volume inspect scrapper_temp_email

# Remover volumes órfãos
docker volume prune

# Backup de volume
docker run --rm -v scrapper_temp_email:/data -v $(pwd):/backup alpine tar czf /backup/temp_email_backup.tar.gz /data
```

---

## 🔍 Inspeção

```bash
# Ver configuração completa do container
docker inspect nfse-scrapper-cron

# Ver apenas IPs
docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' nfse-scrapper-cron

# Ver variáveis de ambiente
docker inspect -f '{{.Config.Env}}' nfse-scrapper-cron

# Ver volumes montados
docker inspect -f '{{.Mounts}}' nfse-scrapper-cron
```

---

## 📝 Logs Avançados

```bash
# Logs desde determinada data/hora
docker-compose logs --since="2025-12-18T09:00:00" scrapper-cron

# Logs até determinada data/hora
docker-compose logs --until="2025-12-18T18:00:00" scrapper-cron

# Logs com timestamp
docker-compose logs -t scrapper-cron

# Logs sem cores (para exportar)
docker-compose logs --no-color scrapper-cron > logs.txt

# Logs de todos os serviços
docker-compose logs -f
```

---

## 🎯 One-Shot Commands

```bash
# Executar comando Python arbitrário
docker-compose run --rm scrapper python -c "print('Hello from Docker')"

# Ver versão do Python
docker-compose run --rm scrapper python --version

# Listar pacotes instalados
docker-compose run --rm scrapper pip list

# Ver estrutura de diretórios
docker-compose run --rm scrapper tree /app  # se tree estiver instalado
docker-compose run --rm scrapper find /app -type d -maxdepth 3

# Ver uso de disco
docker-compose run --rm scrapper du -sh /app/*
```

---

## 🛡️ Segurança

```bash
# Ver como usuário que está rodando
docker-compose exec scrapper-cron whoami
docker-compose exec scrapper-cron id

# Ver permissões de arquivos
docker-compose exec scrapper-cron ls -la data/

# Scan de vulnerabilidades (se tiver Docker Scout)
docker scout cves scrapper_scrapper
```

---

## 📚 Ajuda

```bash
# Help do Docker
docker --help
docker-compose --help

# Help de comando específico
docker run --help
docker-compose up --help

# Makefile help
make help

# Ver todas as variáveis de ambiente disponíveis
docker-compose config
```

---

## 🔗 Links Rápidos

- [Dockerfile](Dockerfile)
- [docker-compose.yml](docker-compose.yml)
- [Makefile](Makefile)
- [README-DOCKER.md](README-DOCKER.md)
- [DOCKER-EXAMPLES.md](DOCKER-EXAMPLES.md)
- [DOCKER-MIGRATION.md](DOCKER-MIGRATION.md)

---

**💡 Dica:** Adicione este arquivo aos seus favoritos do navegador para acesso rápido!

**Última atualização:** 18/12/2025
