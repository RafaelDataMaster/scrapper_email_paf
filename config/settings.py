import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

# Carrega as variáveis do arquivo .env para o ambiente
load_dotenv()

# Caminhos Base
BASE_DIR = Path(__file__).resolve().parent.parent
DIR_SAIDA = BASE_DIR / "data" / "output"
DIR_TEMP = BASE_DIR / "temp_email"  # Nova pasta temporária para o gap de ingestão

# --- Caminhos de Debug (Test Rules) ---
DIR_DEBUG_INPUT = BASE_DIR / "failed_cases_pdf"  # Pasta de input para testes de regras
DIR_DEBUG_OUTPUT = BASE_DIR / "data" / "debug_output"
DEBUG_CSV_NFSE_SUCESSO = DIR_DEBUG_OUTPUT / "nfse_sucesso.csv"
DEBUG_CSV_NFSE_FALHA = DIR_DEBUG_OUTPUT / "nfse_falha.csv"
DEBUG_CSV_BOLETO_SUCESSO = DIR_DEBUG_OUTPUT / "boletos_sucesso.csv"
DEBUG_CSV_BOLETO_FALHA = DIR_DEBUG_OUTPUT / "boletos_falha.csv"
DEBUG_CSV_DANFE_SUCESSO = DIR_DEBUG_OUTPUT / "danfe_sucesso.csv"
DEBUG_CSV_DANFE_FALHA = DIR_DEBUG_OUTPUT / "danfe_falha.csv"
DEBUG_CSV_OUTROS_SUCESSO = DIR_DEBUG_OUTPUT / "outros_sucesso.csv"
DEBUG_CSV_OUTROS_FALHA = DIR_DEBUG_OUTPUT / "outros_falha.csv"
DEBUG_RELATORIO_QUALIDADE = DIR_DEBUG_OUTPUT / "relatorio_qualidade.txt"

# --- Caminhos de Binários Externos ---
# Centralizamos aqui para não espalhar caminhos pelo código
# Detecta automaticamente se está no Docker (Linux) ou Windows
import platform

is_linux = platform.system() == 'Linux'

# Defaults diferentes para Linux (Docker) e Windows (desenvolvimento)
if is_linux:
    TESSERACT_CMD = os.getenv('TESSERACT_CMD', '/usr/bin/tesseract')
    POPPLER_PATH = os.getenv('POPPLER_PATH', '/usr/bin')
else:
    TESSERACT_CMD = os.getenv('TESSERACT_CMD', r'C:\Program Files\Tesseract-OCR\tesseract.exe')
    POPPLER_PATH = os.getenv('POPPLER_PATH', r'C:\Poppler\Release-25.12.0-0\poppler-25.12.0\Library\bin')

# --- Parâmetros do OCR ---
# --psm 6: Assume um bloco único de texto uniforme (vital para notas fiscais)
# load_system_dawg=0 e load_freq_dawg=0: Desativa dicionários de linguagem
# Otimização para leitura de códigos/números (não prosa), economiza CPU
OCR_CONFIG = r'--psm 6 -c load_system_dawg=0 -c load_freq_dawg=0'
OCR_LANG = 'por'

# --- Modo híbrido (PDF com texto + partes em imagem) ---
# Alguns PDFs possuem camada de texto parcial e campos importantes como imagem.
# Quando habilitado, o leitor pode complementar o texto nativo com OCR.
HYBRID_OCR_COMPLEMENT = os.getenv('HYBRID_OCR_COMPLEMENT', '1') == '1'

# --- Parâmetros de Diretórios (Legado/Compatibilidade) ---
ARQUIVO_SAIDA = 'carga_notas_fiscais.csv'

# --- Configurações de E-mail (Lendo do ambiente com valores default seguros) ---
EMAIL_HOST = os.getenv('EMAIL_HOST', '')
EMAIL_USER = os.getenv('EMAIL_USER', '')
EMAIL_PASS = os.getenv('EMAIL_PASS', '')
EMAIL_FOLDER = os.getenv('EMAIL_FOLDER', 'INBOX')

# Validação básica para não rodar sem config
if not all([EMAIL_HOST, EMAIL_USER, EMAIL_PASS]):
    print("⚠️ AVISO: Credenciais de e-mail não configuradas totalmente no .env")

# --- Configurações PAF (Planilha de Autorização de Faturamento) ---
# Responsável pela classificação que aparecerá na coluna 15 (TRAT PAF) da planilha
TRAT_PAF_RESPONSAVEL = os.getenv('TRAT_PAF_RESPONSAVEL', 'SISTEMA_AUTO')

# --- Configuração de Exportação NF ---
# Controla se a coluna NF (5) e Nº FAT (13) são preenchidas na exportação PAF.
#
# Comportamento atual:
# - DANFE/NFSe: exporta numero_nota extraído do PDF
# - Boleto: exporta referencia_nfse (herdado da DANFE/NFSe via correlação) ou numero_documento
# - Diagnóstico NÃO exige numero_nota para considerar NFSe como "sucesso" (por padrão)

# Se True, a coluna NF (e Nº FAT relacionado) é exportada em branco no to_sheets_row().
# Default: False - exporta numero_nota extraído do PDF (DANFE/NFSe) ou referencia_nfse (Boleto)
PAF_EXPORT_NF_EMPTY = os.getenv('PAF_EXPORT_NF_EMPTY', '0') == '1'

# Se True, a validação/diagnóstico exige número de NF na NFSe (numero_nota).
# Para o MVP, default é False.
PAF_EXIGIR_NUMERO_NF = os.getenv('PAF_EXIGIR_NUMERO_NF', '0') == '1'

# --- Configuração de Logging com Rotação ---
# Conformidade: Rastreabilidade exigida pela Política Interna
# RotatingFileHandler evita crescimento descontrolado de logs
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "scrapper.log"

# Configuração do logger raiz
logger = logging.getLogger('scrapper')
logger.setLevel(logging.INFO)

# Handler com rotação: 10MB por arquivo, mantém 5 backups
rotating_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=10 * 1024 * 1024,  # 10MB
    backupCount=5,
    encoding='utf-8'
)

# Formato detalhado para auditoria
log_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
rotating_handler.setFormatter(log_formatter)
logger.addHandler(rotating_handler)

# Também envia para console
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)
