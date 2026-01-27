# Makefile para facilitar operações Docker
.PHONY: help build up down logs shell test clean restart

# Variáveis
COMPOSE = docker-compose
SERVICE = scrapper
SERVICE_CRON = scrapper-cron

help: ## Mostra esta ajuda
	@echo "Comandos disponíveis:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

build: ## Build da imagem Docker
	$(COMPOSE) build

up: ## Inicia o container em modo daemon
	$(COMPOSE) up -d $(SERVICE_CRON)

down: ## Para todos os containers
	$(COMPOSE) down

restart: down build up ## Rebuild e restart completo

logs: ## Mostra logs em tempo real
	$(COMPOSE) logs -f $(SERVICE_CRON)

logs-all: ## Mostra todos os logs (sem follow)
	$(COMPOSE) logs

shell: ## Acessa shell do container
	$(COMPOSE) exec $(SERVICE_CRON) bash

run-once: ## Executa uma vez e remove o container
	$(COMPOSE) run --rm $(SERVICE)

test: ## Executa validação de regras de extração
	$(COMPOSE) run --rm $(SERVICE) python scripts/validate_extraction_rules.py --batch-mode

test-local: ## Executa validação localmente (sem Docker)
	python scripts/validate_extraction_rules.py --batch-mode

validate-rules: ## Valida regras de extração
	$(COMPOSE) run --rm $(SERVICE) python scripts/validate_extraction_rules.py

analyze-boletos: ## Analisa boletos
	$(COMPOSE) run --rm $(SERVICE) python scripts/analyze_boletos.py

status: ## Verifica status do sistema
	$(COMPOSE) run --rm $(SERVICE) python run_ingestion.py --status

diagnose: ## Executa diagnóstico de falhas
	$(COMPOSE) run --rm $(SERVICE) python scripts/check_problematic_pdfs.py

ps: ## Lista containers ativos
	$(COMPOSE) ps

stats: ## Mostra estatísticas de recursos
	docker stats nfse-scrapper-cron --no-stream

clean: ## Remove containers, volumes e imagens
	$(COMPOSE) down -v
	docker system prune -f

clean-all: clean ## Limpeza completa (incluindo imagens)
	docker rmi $$(docker images -q 'scrapper*')

backup-data: ## Backup dos dados
	tar -czf backup_$$(date +%Y%m%d_%H%M%S).tar.gz data/

env-check: ## Verifica variáveis de ambiente
	@echo "Verificando .env..."
	@test -f .env && echo "✅ .env encontrado" || echo "❌ .env NÃO encontrado - copie de .env.example"
	@grep -q "EMAIL_HOST" .env && echo "✅ EMAIL_HOST configurado" || echo "❌ EMAIL_HOST não configurado"
	@grep -q "EMAIL_USER" .env && echo "✅ EMAIL_USER configurado" || echo "❌ EMAIL_USER não configurado"
	@grep -q "EMAIL_PASS" .env && echo "✅ EMAIL_PASS configurado" || echo "❌ EMAIL_PASS não configurado"

install-local: ## Instala dependências localmente (desenvolvimento)
	pip install -r requirements.txt

dev: ## Modo desenvolvimento (com rebuild)
	$(COMPOSE) up --build $(SERVICE)

prod: build up ## Deploy em produção

# Atalhos
b: build
u: up
d: down
l: logs
r: restart
s: shell
t: test
