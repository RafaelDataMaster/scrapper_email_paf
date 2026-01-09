# Multi-stage build para otimizar o tamanho da imagem
FROM python:3.11-slim as base

# Metadados da imagem
LABEL maintainer="rafael.ferreira@soumaster.com.br"
LABEL description="Sistema de extração de NFSe e Boletos de emails com OCR"

# Variáveis de ambiente Python
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Instala dependências do sistema necessárias para OCR e processamento de PDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Tesseract OCR + pacote de idioma português
    tesseract-ocr \
    tesseract-ocr-por \
    # Poppler para conversão PDF -> imagem
    poppler-utils \
    # Dependências para pdf2image e pdfplumber
    libpoppler-dev \
    # Utilitários gerais
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Download do traineddata otimizado (fast/int8) para português
# tessdata_fast é ~4x mais rápido que tessdata_best com perda mínima de precisão
RUN wget -q https://github.com/tesseract-ocr/tessdata_fast/raw/main/por.traineddata \
    -O /usr/share/tesseract-ocr/4.00/tessdata/por.traineddata \
    || echo "Fallback: usando traineddata do pacote Debian"

# Desativa multithreading interno do Tesseract para evitar thrashing de CPU
# Melhor performance em processamento paralelo de múltiplos documentos
ENV OMP_THREAD_LIMIT=1

# Cria usuário não-root para segurança
RUN useradd -m -u 1000 scrapper && \
    mkdir -p /app && \
    chown -R scrapper:scrapper /app

# Define diretório de trabalho
WORKDIR /app

# Copia requirements primeiro (otimização de cache do Docker)
COPY --chown=scrapper:scrapper requirements.txt .

# Instala dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código da aplicação
COPY --chown=scrapper:scrapper . .

# Cria estrutura de diretórios necessária
RUN mkdir -p \
    data/output \
    data/debug_output \
    temp_email \
    failed_cases_pdf \
    && chown -R scrapper:scrapper /app

# Muda para usuário não-root
USER scrapper

# Define caminhos dos binários no Linux (diferentes do Windows!)
ENV TESSERACT_CMD=/usr/bin/tesseract \
    POPPLER_PATH=/usr/bin

# Healthcheck para verificar se o Tesseract está disponível
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD tesseract --version || exit 1

# Comando padrão (pode ser sobrescrito no docker-compose)
CMD ["python", "run_ingestion.py"]
