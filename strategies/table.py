"""
Estratégia de extração para PDFs com estrutura tabular.

Este módulo detecta e extrai tabelas de PDFs, convertendo para formato
texto estruturado "chave: valor" que facilita a extração por regex.

Motivação:
    Boletos e notas fiscais frequentemente têm layouts onde rótulos
    (cabeçalhos) estão em uma linha e valores em linhas separadas.
    A extração nativa não preserva essa relação, dificultando o parse.

Formato de saída:
    ```
    === DADOS ESTRUTURADOS ===
    Beneficiário: EMPRESA LTDA
    CNPJ: 12.345.678/0001-90
    Valor: 1.234,56
    ```

Quando usar:
    - PDFs com tabelas visíveis (bordas)
    - Documentos onde a extração nativa retorna valores desalinhados
    - Boletos com campos em formato tabular

Inclui suporte a PDFs protegidos por senha, tentando desbloquear
automaticamente usando CNPJs das empresas cadastradas.

Example:
    >>> from strategies.table import TablePdfStrategy
    >>> strategy = TablePdfStrategy()
    >>> texto = strategy.extract("boleto.pdf")
    >>> if "=== DADOS ESTRUTURADOS ===" in texto:
    ...     print("Tabelas detectadas e convertidas")
"""
import logging

from core.interfaces import TextExtractionStrategy

from .pdf_utils import abrir_pdfplumber_com_senha

logger = logging.getLogger(__name__)


class TablePdfStrategy(TextExtractionStrategy):
    """
    Estratégia para PDFs com estrutura tabular.

    Detecta tabelas via pdfplumber e converte para texto estruturado "chave: valor",
    facilitando a extração por regex em documentos com layouts complexos.

    Útil para boletos onde rótulos (cabeçalhos) estão em uma linha e
    valores estão em linhas separadas (formato tabular).

    Inclui suporte a PDFs protegidos por senha, tentando desbloquear
    automaticamente usando CNPJs das empresas cadastradas.
    """

    def extract(self, file_path: str) -> str:
        """
        Extrai texto + tabelas estruturadas de um PDF.

        Implementa desbloqueio automático de PDFs protegidos usando CNPJs
        das empresas cadastradas como candidatos a senha.

        Args:
            file_path (str): Caminho do arquivo PDF.

        Returns:
            str: Texto com tabelas convertidas para formato "chave: valor".
        """
        try:
            # Usa função utilitária que tenta desbloquear PDFs protegidos
            pdf = abrir_pdfplumber_com_senha(file_path)

            if pdf is None:
                logger.debug(f"Não foi possível abrir PDF: {file_path}")
                return ""

            try:
                if not pdf.pages:
                    return ""

                full_text = ""
                has_tables = False

                for page in pdf.pages:
                    # Extrai texto normal primeiro (com layout preservado)
                    page_text = page.extract_text(layout=True) or ""
                    full_text += page_text + "\n"

                    # Tenta detectar e extrair tabelas
                    tables = page.extract_tables()

                    if tables:
                        has_tables = True
                        full_text += "\n=== DADOS ESTRUTURADOS ===\n"

                        for table in tables:
                            if not table or len(table) < 2:
                                continue

                            # Assume primeira linha como cabeçalho
                            headers = table[0]

                            # Processa linhas de dados
                            for row in table[1:]:
                                if not row:
                                    continue

                                # Converte para formato "Chave: Valor"
                                for header, value in zip(headers, row):
                                    if header and value:
                                        # Remove espaços extras
                                        header_clean = str(header).strip()
                                        value_clean = str(value).strip()

                                        if header_clean and value_clean:
                                            full_text += f"{header_clean}: {value_clean}\n"

                                full_text += "\n"  # Separa registros

                # Validação: só retorna se encontrou tabelas e tem conteúdo suficiente
                if not has_tables or len(full_text.strip()) < 50:
                    return ""

                return full_text

            finally:
                pdf.close()

        except Exception as e:
            logger.debug(f"Erro na extração de tabelas de {file_path}: {e}")
            return ""
