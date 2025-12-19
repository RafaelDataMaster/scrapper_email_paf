class ScrapperException(Exception):
    """Exceção base para o projeto Scrapper NFe."""
    pass

class ExtractionError(ScrapperException):
    """Levantada quando falha a extração de texto de um arquivo.
    
    Deve ser usada apenas para falhas críticas irrecuperáveis:
    - Arquivo corrompido além de reparo
    - Arquivo sem permissão de leitura
    - Formato não suportado
    
    Falhas recuperáveis (ex: texto insuficiente) devem retornar string vazia.
    """
    pass

class IngestionError(ScrapperException):
    """Levantada quando falha a conexão ou download de e-mails."""
    pass
