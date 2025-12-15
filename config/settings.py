import os

# --- Caminhos de Binários Externos ---
# Centralizamos aqui para não espalhar caminhos pelo código
# Dica: No futuro, você pode trocar isso por os.getenv('TESSERACT_PATH')
TESSERACT_CMD = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
POPPLER_PATH = r'C:\Poppler\Release-25.12.0-0\poppler-25.12.0\Library\bin'

# --- Parâmetros do OCR ---
# --psm 6: Assume um bloco único de texto uniforme (vital para notas fiscais)
OCR_CONFIG = r'--psm 6'
OCR_LANG = 'por'

# --- Parâmetros de Diretórios ---
DIR_ENTRADA = r'nfs/'
ARQUIVO_SAIDA = 'carga_notas_fiscais.csv'