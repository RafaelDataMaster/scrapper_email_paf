"""
Utilitários compartilhados para manipulação de PDFs.

Este módulo centraliza funções de abertura de PDFs com tratamento
de senha, evitando duplicação de código entre as estratégias.

Funcionalidades:
    - Geração de candidatos de senha baseados em CNPJs cadastrados
    - Abertura de PDFs com tentativa automática de desbloqueio
    - Suporte para pdfplumber e pypdfium2
"""
import logging
import os
from typing import Any, List, Optional

import pdfplumber
import pypdfium2 as pdfium

from config.empresas import EMPRESAS_CADASTRO

logger = logging.getLogger(__name__)


def gerar_candidatos_senha() -> List[str]:
    """
    Gera uma lista de candidatos a senha baseada nos CNPJs configurados.

    Para cada CNPJ da lista de empresas, gera:
        - O CNPJ completo (apenas números)
        - Os 4 primeiros dígitos
        - Os 5 primeiros dígitos
        - Os 8 primeiros dígitos (raiz do CNPJ)

    Returns:
        List[str]: Lista de candidatos a senha únicos, ordenados.
    """
    candidatos = set()

    for cnpj in EMPRESAS_CADASTRO.keys():
        # CNPJ completo (apenas números, já está assim no dicionário)
        cnpj_limpo = cnpj.replace(".", "").replace("/", "").replace("-", "")
        candidatos.add(cnpj_limpo)

        # 4 primeiros dígitos
        if len(cnpj_limpo) >= 4:
            candidatos.add(cnpj_limpo[:4])

        # 5 primeiros dígitos
        if len(cnpj_limpo) >= 5:
            candidatos.add(cnpj_limpo[:5])

        # 8 primeiros dígitos (raiz do CNPJ - comum como senha)
        if len(cnpj_limpo) >= 8:
            candidatos.add(cnpj_limpo[:8])

    # Converter para lista e ordenar para consistência
    return sorted(list(candidatos))


def abrir_pdfplumber_com_senha(file_path: str) -> Optional[Any]:
    """
    Tenta abrir um PDF com pdfplumber, aplicando força bruta de senhas se necessário.

    Estratégia de desbloqueio:
        1. Tenta abrir sem senha
        2. Se falhar com erro de senha, itera sobre candidatos de senha
        3. Retorna o documento aberto ou None se falhar

    Args:
        file_path (str): Caminho do arquivo PDF.

    Returns:
        Optional[pdfplumber.PDF]: Documento PDF aberto ou None se falhar.

    Note:
        O chamador é responsável por fechar o documento (usar com `with` ou chamar .close()).
    """
    filename = os.path.basename(file_path)

    # 1. Tentar abrir sem senha
    try:
        pdf = pdfplumber.open(file_path)
        # Tenta acessar páginas para verificar se realmente abriu
        _ = pdf.pages
        logger.debug(f"📄 PDF aberto sem senha (pdfplumber): {filename}")
        return pdf
    except Exception as e:
        error_msg = str(e).lower()
        # pdfplumber/pdfminer usa "password" ou "encrypted" nas mensagens de erro
        if "password" not in error_msg and "encrypted" not in error_msg:
            # Erro diferente de senha - propagar
            logger.warning(f"Erro ao abrir PDF {filename} (pdfplumber): {e}")
            return None

        logger.info(f"🔐 PDF protegido por senha, tentando desbloqueio (pdfplumber): {filename}")

    # 2. Gerar candidatos e tentar cada um
    candidatos = gerar_candidatos_senha()
    logger.debug(f"Testando {len(candidatos)} candidatos de senha para {filename}")

    for senha in candidatos:
        try:
            pdf = pdfplumber.open(file_path, password=senha)
            # Tenta acessar páginas para verificar se realmente abriu
            _ = pdf.pages
            logger.info(f"✅ PDF desbloqueado com senha '{senha}' (pdfplumber): {filename}")
            return pdf
        except Exception:
            # Senha incorreta, continuar tentando
            continue

    # 3. Nenhuma senha funcionou
    logger.warning(f"⚠️ Falha ao desbloquear PDF {filename} (pdfplumber): Senha desconhecida")
    return None


def abrir_pypdfium_com_senha(file_path: str) -> Optional[Any]:
    """
    Tenta abrir um PDF com pypdfium2, aplicando força bruta de senhas se necessário.

    Estratégia de desbloqueio:
        1. Tenta abrir sem senha
        2. Se falhar com "Incorrect password", itera sobre candidatos de senha
        3. Retorna o documento aberto ou None se falhar

    Args:
        file_path (str): Caminho do arquivo PDF.

    Returns:
        Optional[pdfium.PdfDocument]: Documento PDF aberto ou None se falhar.

    Note:
        O chamador é responsável por fechar o documento (chamar .close()).
    """
    filename = os.path.basename(file_path)

    # 1. Tentar abrir sem senha
    try:
        pdf = pdfium.PdfDocument(file_path)
        logger.debug(f"📄 PDF aberto sem senha (pypdfium2): {filename}")
        return pdf
    except pdfium.PdfiumError as e:
        error_msg = str(e).lower()
        if "password" not in error_msg:
            # Erro diferente de senha - propagar
            logger.warning(f"Erro ao abrir PDF {filename} (pypdfium2): {e}")
            return None

        logger.info(f"🔐 PDF protegido por senha, tentando desbloqueio (pypdfium2): {filename}")

    # 2. Gerar candidatos e tentar cada um
    candidatos = gerar_candidatos_senha()
    logger.debug(f"Testando {len(candidatos)} candidatos de senha para {filename}")

    for senha in candidatos:
        try:
            pdf = pdfium.PdfDocument(file_path, password=senha)
            logger.info(f"✅ PDF desbloqueado com senha '{senha}' (pypdfium2): {filename}")
            return pdf
        except pdfium.PdfiumError:
            # Senha incorreta, continuar tentando
            continue

    # 3. Nenhuma senha funcionou
    logger.warning(f"⚠️ Falha ao desbloquear PDF {filename} (pypdfium2): Senha desconhecida")
    return None
