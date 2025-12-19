# 🚀 Git Workflow - Para Implementar Futuramente

> **STATUS**: Documentação para referência futura  
> **ATUAL**: Usando fluxo simples (main apenas)

---

## 📌 Quando Implementar

Considere adotar este workflow quando:
- [ ] MVP validado e rodando em produção
- [ ] Mais pessoas entrarem no projeto
- [ ] Precisar de ambiente de homologação/staging
- [ ] Deploy automático for implementado

---

## 🌳 Estrutura de Branches (Futura)

```
main (produção)
  ↑
develop (staging)
  ↑
feature/* (desenvolvimento)
```

---

## 📝 Convenção de Commits

**Já pode usar agora:**

```bash
feat:     Nova funcionalidade
fix:      Correção de bug
docs:     Apenas documentação
refactor: Refatoração de código
test:     Testes
chore:    Manutenção (deps, config)
perf:     Performance
```

**Exemplos do seu projeto:**
```bash
git commit -m "feat(extractors): adiciona suporte a XML NFSe"
git commit -m "fix(ocr): corrige timeout em PDFs grandes"
git commit -m "docs(boletos): atualiza guia de vinculação"
git commit -m "test(extractors): adiciona testes unitários"
```

---

## 🎯 Workflow Atual (Simples)

**O que você já está fazendo:**

```bash
# Desenvolve
git add .
git commit -m "feat: adiciona feature X"
git push origin main

# Docker puxa de main
# MkDocs deploya de main
```

✅ **Isso está perfeito para MVP!**

---

## 🔄 Workflow Futuro (Quando escalar)

### 1. Nova Feature

```bash
git checkout develop
git pull
git checkout -b feature/xml-nfse
# ... desenvolve ...
git commit -m "feat(extractors): adiciona XMLExtractor"
git checkout develop
git merge feature/xml-nfse --no-ff
git push origin develop
```

### 2. Release para Produção

```bash
# Quando develop estiver estável
git checkout main
git merge develop --no-ff
git tag -a v1.2.0 -m "Release 1.2.0"
git push origin main --tags
```

### 3. Hotfix Urgente

```bash
git checkout main
git checkout -b hotfix/ocr-timeout
git commit -m "fix(ocr): adiciona timeout"
git checkout main
git merge hotfix/ocr-timeout --no-ff
git tag -a v1.0.1 -m "Hotfix: timeout"
git push --tags

# Também aplica no develop
git checkout develop
git merge hotfix/ocr-timeout
```

---

## 📦 Versionamento Semântico

```
v1.0.0 → Primeira versão em produção
v1.1.0 → Nova feature (boletos, XML)
v1.1.1 → Bugfix
v2.0.0 → Breaking change
```

---

## 🤖 CI/CD Futuro

### GitHub Actions (quando implementar)

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
      - run: pip install -r requirements.txt
      - run: pytest
      - run: docker build .
```

---

## 📋 Checklist de Transição

Quando decidir migrar para workflow completo:

- [ ] Criar branch `develop`
- [ ] Configurar branch protection no GitHub
- [ ] Implementar CI/CD (GitHub Actions)
- [ ] Documentar processo no README
- [ ] Treinar equipe (se houver)
- [ ] Criar templates de PR/Issues

---

## 💡 Por Enquanto

**Continue assim:**
1. Desenvolva direto na `main`
2. Use commits semânticos (já ajuda!)
3. Tags quando lançar versão (`v1.0.0`)
4. Docker puxa de `main`

**Quando sentir necessidade** de staging/homologação, volte aqui e implemente o workflow completo.

---

**Última atualização:** 2025-12-18  
**Status:** 📝 Referência futura