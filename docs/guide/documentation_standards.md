# Padrões de Documentação e Código

Para manter a qualidade e a consistência do projeto `scrapper_nfe`, adotamos os seguintes padrões. Todos os Pull Requests devem seguir estas diretrizes.

## 1. Docstrings (Python)

Utilizamos o estilo **Google Docstrings**. Todo módulo, classe e método público deve ser documentado.

### Estrutura Básica
```python
def funcao_exemplo(parametro_a: str, parametro_b: int = 0) -> bool:
    """
    Resumo curto do que a função faz (uma linha).

    Descrição detalhada se necessário. Pode ter múltiplos parágrafos.
    Explique o 'porquê' e comportamentos complexos aqui.

    Args:
        parametro_a (str): Descrição do parâmetro A.
        parametro_b (int, optional): Descrição do B. Padrão é 0.

    Returns:
        bool: True se sucesso, False caso contrário.

    Raises:
        ValueError: Se parametro_a estiver vazio.

    Example:
        >>> funcao_exemplo("teste", 10)
        True
    """
    pass
```

### Regras de Ouro
*   **Tipagem:** Sempre use *Type Hints* (`: str`, `-> dict`) na assinatura do método, não apenas na docstring.
*   **Imperativo:** Use verbos no imperativo para o resumo: "Calcula o total" em vez de "Calculando o total".
*   **Português:** Como o domínio é fiscal brasileiro, a documentação deve ser em **Português (PT-BR)**, mas o código (nomes de variáveis) pode ser em Inglês ou Português (mantenha a consistência do arquivo).

## 2. Documentação de Arquitetura (Markdown)

A documentação na pasta `docs/` segue a estrutura do **MkDocs Material**.

*   **Admonitions:** Use caixas de alerta para destacar informações críticas.
    ```markdown
    !!! warning "Atenção"
        O OCR é um processo custoso. Use apenas quando necessário.
    
    !!! tip "Dica"
        Para testar regex, use o site regex101.com.
    ```

*   **Diagramas:** Use **Mermaid** para fluxogramas. Não suba imagens `.png` de diagramas, pois são difíceis de editar.
    ```mermaid
    graph LR
    A[Texto] --> B[Regex]
    ```

## 3. Mensagens de Commit (Conventional Commits)

Seguimos o padrão [Conventional Commits](https://www.conventionalcommits.org/).

*   `feat:` Nova funcionalidade (ex: `feat: adiciona extrator de Curitiba`)
*   `fix:` Correção de bug (ex: `fix: corrige regex de data em SP`)
*   `docs:` Apenas documentação (ex: `docs: atualiza guia de instalação`)
*   `refactor:` Mudança de código que não altera funcionalidade (ex: `refactor: move classes para pasta core`)
*   `test:` Adição ou correção de testes

## 4. Checklist de Qualidade

Antes de submeter código:
- [ ] O código roda sem erros?
- [ ] Novos métodos têm Docstrings?
- [ ] Se criou um novo Extrator, ele foi registrado em `core/extractors.py`?
- [ ] O `mkdocs serve` mostra a documentação renderizada corretamente?
