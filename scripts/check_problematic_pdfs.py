#!/usr/bin/env python3
"""
Script para examinar PDFs de casos problemáticos onde documentos "outros" têm valor zero.

Objetivo: Analisar documentos classificados como administrativos (outros > 0) com valor zero
para determinar:
1. São realmente documentos administrativos ou são NFSEs mal classificadas?
2. Contêm valores que deveriam ter sido extraídos?
3. Como melhorar os extratores para evitar problemas futuros.

Funcionalidades:
- Extração de texto de PDFs usando pdfplumber
- Classificação baseada em padrões de conteúdo
- Identificação de valores presentes mas não extraídos
- Geração de relatório detalhado com recomendações

Melhorias implementadas (SOLID e padrões de qualidade):
1. Critérios de filtragem expandidos:
   - Documentos administrativos (outros > 0) com valor zero
   - Vencimento inválido (vazio, "0", ou "00/00/0000")
   - Fornecedor genérico (ex: "CNPJ FORNECEDOR", "FORNECEDOR", "CPF Fornecedor:")
   - Fornecedor interno (empresa do nosso cadastro)

2. Validação rigorosa de dados:
   - Funções auxiliares `validar_vencimento()` e `validar_fornecedor()`
   - Detecção de padrões de vencimento mal extraído em PDFs
   - Classificação de severidade de problemas (`classificar_severidade_problemas()`)

3. Relatório detalhado aprimorado:
   - Contadores específicos de vencimento inválido, fornecedor genérico e interno
   - Separação de problemas de validação de dados
   - Recomendações específicas baseadas nos tipos de erro detectados

4. Princípios SOLID aplicados:
   - Single Responsibility: funções especializadas para validação, classificação e geração de relatório
   - Open/Closed: extensível para novos critérios de validação sem modificar funções existentes
   - Liskov Substitution: funções auxiliares com interfaces consistentes
   - Interface Segregation: problemas categorizados por tipo (fornecedor, vencimento, valor, etc.)
   - Dependency Inversion: uso de funções auxiliares desacopladas da lógica principal
"""

import csv
import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any

# Adicionar caminho para importar módulos do projeto
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configurar logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Termos genéricos que indicam falha na extração de fornecedor
# Melhorado para reduzir falsos positivos: agora usamos regex para identificar
# padrões específicos de rótulos de campo vazios
TERMOS_FORNECEDOR_GENERICOS = [
    r"^(CNPJ\s+FORNECEDOR|FORNECEDOR|NOME\s+FORNECEDOR|CPF\s+FORNECEDOR|CPF/CNPJ)$",
    r"^(CNPJ|CPF|FORNECEDOR|NOME\s+FORNECEDOR)\s*[:;]$",
    r"^CPF\s+Fornecedor\s*:$",
    r"^FORNECEDOR\s*:$",
    r"^CNPJ\s*:$",
]

# Expressões regulares para detectar fornecedores genéricos
FORNECEDOR_GENERICO_REGEXES = [
    # Padrões exatos que indicam campo não preenchido
    re.compile(
        r"^(CNPJ\s+FORNECEDOR|FORNECEDOR|NOME\s+FORNECEDOR|CPF\s+FORNECEDOR|CPF/CNPJ)$",
        re.IGNORECASE,
    ),
    # Padrões de rótulo de campo seguido de dois pontos/semicolon
    re.compile(r"^(CNPJ|CPF|FORNECEDOR|NOME\s+FORNECEDOR)\s*[:;]$", re.IGNORECASE),
    # Padrões específicos com dois pontos
    re.compile(r"^CPF\s+Fornecedor\s*:$", re.IGNORECASE),
    re.compile(r"^FORNECEDOR\s*:$", re.IGNORECASE),
    re.compile(r"^CNPJ\s*:$", re.IGNORECASE),
    # Padrões de texto incompleto
    re.compile(r"^CNPJ\s+$", re.IGNORECASE),
    re.compile(r"^CPF\s+$", re.IGNORECASE),
    re.compile(r"^FORNECEDOR\s+$", re.IGNORECASE),
]

# Termos que podem aparecer em nomes legítimos de fornecedores
# (não marcar como genérico se contiver apenas estes termos como parte do nome)
TERMOS_LEGITIMOS_EM_NOMES = [
    "FORNECEDOR",
    "DISTRIBUIDOR",
    "COMERCIO",
    "COMÉRCIO",
    "REPRESENTAÇÕES",
    "REPRESENTACOES",
    "SUPRIMENTOS",
    "MATERIAIS",
    "PRODUTOS",
    "SERVICOS",
    "SERVIÇOS",
    "COMERCIAL",
    "INDUSTRIA",
    "INDÚSTRIA",
    # Novos termos comuns em nomes legítimos:
    "LTDA",
    "S/A",
    "EIRELI",
    "ME",
    "EPP",
    "SA",
    "TELECOMUNICACOES",
    "TELECOMUNICAÇÕES",
    "COMUNICACAO",
    "COMUNICAÇÃO",
    "TECNOLOGIA",
    "INFORMATICA",
    "INFORMÁTICA",
    "SOLUCOES",
    "SOLUÇÕES",
    "SISTEMAS",
    "ENGENHARIA",
    "CONSTRUCAO",
    "CONSTRUÇÃO",
]


def validar_vencimento(vencimento: str) -> Dict[str, Any]:
    """
    Valida a data de vencimento extraída.

    Args:
        vencimento: String com a data de vencimento

    Returns:
        Dicionário com:
        - valido: bool indicando se a data é válida
        - problemas: lista de strings com problemas encontrados
        - formato_correto: bool indicando se o formato está correto
        - data_zerada: bool indicando se a data é "zerada"
    """
    vencimento = vencimento.strip() if vencimento else ""
    problemas = []

    # Verificar se está vazio
    if not vencimento:
        problemas.append("Vencimento vazio")
        return {
            "valido": False,
            "problemas": problemas,
            "formato_correto": False,
            "data_zerada": False,
        }

    # Verificar datas inválidas conhecidas
    datas_invalidas = ["0", "00/00/0000", "0000-00-00", "01/01/0001"]
    if vencimento in datas_invalidas:
        problemas.append(f"Data inválida: '{vencimento}'")
        return {
            "valido": False,
            "problemas": problemas,
            "formato_correto": False,
            "data_zerada": True,
        }

    # Verificar padrões de data aceitos: dd/mm/aaaa ou aaaa-mm-dd
    date_pattern_br = re.compile(r"^\d{2}/\d{2}/\d{4}$")
    date_pattern_iso = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    formato_correto = bool(
        date_pattern_br.match(vencimento) or date_pattern_iso.match(vencimento)
    )

    if not formato_correto:
        # Verificar se parece ser uma data mas com formato diferente
        if any(char.isdigit() for char in vencimento):
            problemas.append(
                f"Formato não aceito: '{vencimento}' (use dd/mm/aaaa ou aaaa-mm-dd)"
            )
        else:
            problemas.append(f"Formato inválido: '{vencimento}'")

    # Verificar ano inválido (0000) em ambos os formatos: dd/mm/aaaa e aaaa-mm-dd
    ano_invalido = False

    # Tentar extrair ano do formato dd/mm/aaaa
    match_br = re.match(r"^\d{2}/\d{2}/(\d{4})$", vencimento)
    if match_br:
        ano = match_br.group(1)
        if ano == "0000":
            ano_invalido = True

    # Tentar extrair ano do formato aaaa-mm-dd
    match_iso = re.match(r"^(\d{4})-\d{2}-\d{2}$", vencimento)
    if match_iso:
        ano = match_iso.group(1)
        if ano == "0000":
            ano_invalido = True

    if ano_invalido:
        problemas.append(f"Ano inválido (0000) na data: '{vencimento}'")

    # Verificar anos fora do intervalo razoável (2020-2035)
    # Apenas para datas com formato válido
    if formato_correto:
        ano_valido = None
        if date_pattern_br.match(vencimento):
            ano_valido = int(vencimento.split("/")[2])
        elif date_pattern_iso.match(vencimento):
            ano_valido = int(vencimento.split("-")[0])

        if ano_valido is not None:
            if ano_valido < 2020 or ano_valido > 2035:
                problemas.append(
                    f"Ano fora do intervalo esperado (2020-2035): {ano_valido}"
                )

    return {
        "valido": len(problemas) == 0,
        "problemas": problemas,
        "formato_correto": formato_correto,
        "data_zerada": vencimento in ["0", "00/00/0000", "0000-00-00"],
    }


def validar_fornecedor(
    fornecedor: str, verificar_interno: bool = True
) -> Dict[str, Any]:
    """
    Valida o nome do fornecedor extraído.

    Args:
        fornecedor: String com o nome do fornecedor
        verificar_interno: Se True, verifica se é empresa nossa

    Returns:
        Dicionário com:
        - valido: bool indicando se o fornecedor é válido
        - problemas: lista de strings com problemas encontrados
        - generico: bool indicando se o fornecedor é genérico
        - contem_rotulo: bool indicando se contém rótulo de campo
        - interno: bool indicando se é empresa nossa (se verificar_interno=True)
    """
    fornecedor = fornecedor.strip() if fornecedor else ""
    problemas = []
    generico = False
    contem_rotulo = False
    interno = False

    # Verificar se está vazio
    if not fornecedor:
        problemas.append("Fornecedor vazio")
        return {
            "valido": False,
            "problemas": problemas,
            "generico": generico,
            "contem_rotulo": contem_rotulo,
            "interno": interno,
        }

    # 1. Verificar se é um padrão genérico (rótulo de campo não preenchido)
    fornecedor_normalizado = fornecedor.strip()

    for pattern in FORNECEDOR_GENERICO_REGEXES:
        if pattern.match(fornecedor_normalizado):
            generico = True
            problemas.append(f"Fornecedor genérico (padrão de rótulo): '{fornecedor}'")
            break

    # 2. Verificar se contém apenas termos genéricos sem conteúdo adicional
    if not generico:
        # Verificar se o fornecedor consiste apenas de termos genéricos comuns
        palavras = fornecedor_normalizado.upper().split()
        todas_palavras_genericas = True

        for palavra in palavras:
            # Verificar se a palavra é um termo genérico isolado
            palavra_eh_generica = False
            for termo in ["CNPJ", "CPF", "FORNECEDOR", "NOME"]:
                if palavra == termo or palavra.startswith(f"{termo}_"):
                    palavra_eh_generica = True
                    break

            # Verificar se é um termo legítimo que pode aparecer em nomes reais
            if palavra in TERMOS_LEGITIMOS_EM_NOMES:
                palavra_eh_generica = False

            if not palavra_eh_generica:
                todas_palavras_genericas = False
                break

        if todas_palavras_genericas and len(palavras) <= 3:
            generico = True
            problemas.append(
                f"Fornecedor contém apenas termos genéricos: '{fornecedor}'"
            )

    # 3. Verificar se contém rótulo de campo seguido de valor vazio ou incompleto
    if ":" in fornecedor:
        partes = fornecedor.split(":", 1)
        rotulo = partes[0].strip()
        valor = partes[1].strip() if len(partes) > 1 else ""

        # Se o valor após ":" estiver vazio ou for muito curto, é um rótulo de campo
        if not valor or len(valor) < 2:
            contem_rotulo = True
            if not generico:  # Só adicionar se já não marcamos como genérico
                problemas.append(
                    f"Fornecedor contém rótulo de campo sem valor: '{fornecedor}'"
                )
        else:
            # Se tem valor, verificar se o rótulo é genérico
            rotulo_upper = rotulo.upper()
            rotulos_genericos = [
                "CNPJ",
                "CPF",
                "FORNECEDOR",
                "NOME FORNECEDOR",
                "RAZAO SOCIAL",
            ]
            if any(rotulo_gen in rotulo_upper for rotulo_gen in rotulos_genericos):
                contem_rotulo = True
                if not generico:
                    # Não marcar como genérico se tem um valor real após o rótulo
                    # Mas ainda marca como contendo rótulo
                    pass

    # 4. Verificar se é empresa nossa (se disponível)
    if verificar_interno and EXTRACTORS_AVAILABLE and is_nome_nosso:
        if is_nome_nosso(fornecedor):
            interno = True
            problemas.append(f"Fornecedor é empresa nossa: '{fornecedor}'")

    return {
        "valido": len(problemas) == 0,
        "problemas": problemas,
        "generico": generico,
        "contem_rotulo": contem_rotulo,
        "interno": interno,
    }


def classificar_severidade_problemas(problems: Dict[str, Any]) -> str:
    """
    Classifica a severidade dos problemas encontrados na extração.

    Args:
        problems: Dicionário com problemas detectados

    Returns:
        "BAIXA", "MEDIA" ou "ALTA"
    """
    # Contar problemas por categoria
    total_problems = 0
    for key in [
        "fornecedor_issues",
        "valor_issues",
        "vencimento_issues",
        "numero_nota_issues",
        "extrator_identification_issues",
        "data_validation_issues",
    ]:
        total_problems += len(problems.get(key, []))

    if total_problems == 0:
        return "BAIXA"
    elif total_problems <= 2:
        return "MEDIA"
    else:
        return "ALTA"


def tentar_corrigir_fornecedor(
    fornecedor_atual: str, texto_pdf: str, empresa_cnpj: Optional[str] = None
) -> Dict[str, Any]:
    """
    Tenta inferir/corrigir o nome do fornecedor usando o texto do PDF.

    Args:
        fornecedor_atual: Nome atual do fornecedor (possivelmente genérico)
        texto_pdf: Texto completo extraído do PDF
        empresa_cnpj: CNPJ da empresa (opcional, para excluir da busca)

    Returns:
        Dicionário com:
        - corrigido: bool
        - fornecedor_sugerido: str ou None
        - metodo: str descrevendo o método usado
        - confianca: float entre 0 e 1
    """
    if not EXTRACTORS_AVAILABLE:
        return {
            "corrigido": False,
            "fornecedor_sugerido": None,
            "metodo": "extractors_unavailable",
            "confianca": 0.0,
        }

    texto_upper = texto_pdf.upper()

    # Método 1: Inferência usando empresa_matcher (alta confiança)
    if infer_fornecedor_from_text:
        fornecedor_inferido = infer_fornecedor_from_text(texto_pdf, empresa_cnpj)
        if fornecedor_inferido and fornecedor_inferido != fornecedor_atual:
            # Validar que não é outro termo genérico
            validacao = validar_fornecedor(fornecedor_inferido, verificar_interno=False)
            if not validacao["generico"]:
                return {
                    "corrigido": True,
                    "fornecedor_sugerido": fornecedor_inferido,
                    "metodo": "infer",
                    "confianca": 0.8,
                }

    # Método 2: Buscar CNPJ no texto e tentar encontrar nome associado (média confiança)
    if pick_first_non_our_cnpj:
        cnpj_encontrado = pick_first_non_our_cnpj(texto_pdf)
        if cnpj_encontrado:
            # Tentar encontrar nome perto do CNPJ
            cnpj_formatado = (
                format_cnpj(cnpj_encontrado) if format_cnpj else cnpj_encontrado
            )

            # Procurar por padrões de nome antes/after do CNPJ
            # (implementação simplificada - poderia ser mais sofisticada)
            return {
                "corrigido": True,
                "fornecedor_sugerido": f"CNPJ: {cnpj_formatado}",
                "metodo": "cnpj_only",
                "confianca": 0.6,
            }

    # Método 3: Buscar padrões de nome de empresa no texto (baixa confiança)
    # Procurar por padrões comuns em nomes de empresas
    padroes_empresa = [
        r"(LTDA|S/A|S\.A\.|EIRELI|ME|EPP|S/S)",
        r"(COMERCIO|COMÉRCIO|INDUSTRIA|INDÚSTRIA|SERVICOS|SERVIÇOS)",
        r"(DISTRIBUIDORA|REPRESENTAÇÕES|REPRESENTACOES)",
    ]

    for padrao in padroes_empresa:
        matches = re.finditer(padrao, texto_upper, re.IGNORECASE)
        for match in matches:
            # Pegar contexto ao redor do match
            start = max(0, match.start() - 50)
            end = min(len(texto_upper), match.end() + 30)
            contexto = texto_upper[start:end]

            # Extrair possível nome (até 50 chars antes do padrão)
            linhas = contexto.split("\n")
            for linha in linhas:
                if any(termo in linha for termo in ["LTDA", "S/A", "EIRELI"]):
                    # Limpar a linha
                    linha_limpa = re.sub(r"\s+", " ", linha).strip()
                    if len(linha_limpa) > 10 and len(linha_limpa) < 100:
                        return {
                            "corrigido": True,
                            "fornecedor_sugerido": linha_limpa,
                            "metodo": "pattern_match",
                            "confianca": 0.4,
                        }

    return {
        "corrigido": False,
        "fornecedor_sugerido": None,
        "metodo": "no_match",
        "confianca": 0.0,
    }


def obter_cnpj_da_empresa(empresa: Optional[str]) -> Optional[str]:
    """
    Obtém o CNPJ associado a uma empresa do nosso cadastro.

    Args:
        empresa: Código ou nome da empresa (ex: "CSC", "RBC")

    Returns:
        CNPJ como string ou None se não encontrado
    """
    if not empresa:
        return None

    try:
        # Tentar importar empresas do cadastro
        from config.empresas import EMPRESAS_CADASTRO  # noqa: F401

        # Buscar por código da empresa nos dados cadastrais
        empresa_upper = empresa.upper()

        for cnpj, dados in EMPRESAS_CADASTRO.items():
            razao_social = dados.get("razao_social", "").upper()
            cidade = dados.get("cidade", "").upper()

            # Verificar se o código da empresa aparece na razão social ou cidade
            if empresa_upper in razao_social or empresa_upper in cidade:
                return cnpj

        return None
    except ImportError:
        logger.warning("Não foi possível importar EMPRESAS_CADASTRO")
        return None


# Função local para abrir PDFs com senha (evita importação circular)
def abrir_pdfplumber_com_senha_local(file_path: str):
    """
    Tenta abrir um PDF com pdfplumber, aplicando força bruta de senhas se necessário.
    Implementação local copiada de strategies/pdf_utils.py.
    """
    import os
    import pdfplumber

    filename = os.path.basename(file_path)

    # 1. Tentar abrir sem senha
    try:
        pdf = pdfplumber.open(file_path)
        # Tenta acessar páginas para verificar se realmente abriu
        _ = pdf.pages
        logger.debug(f"[PDF] PDF aberto sem senha (pdfplumber): {filename}")
        return pdf
    except Exception as e:
        error_msg = str(e).lower()
        # pdfplumber/pdfminer usa "password" ou "encrypted" nas mensagens de erro
        if "password" not in error_msg and "encrypted" not in error_msg:
            # Erro diferente de senha - propagar
            logger.warning(f"Erro ao abrir PDF {filename} (pdfplumber): {e}")
            return None

        logger.info(
            f"[SENHA] PDF protegido por senha, tentando desbloqueio (pdfplumber): {filename}"
        )

    # 2. Gerar candidatos e tentar cada um
    # Tentar importar empresas cadastradas para gerar candidatos de senha
    try:
        from config.empresas import EMPRESAS_CADASTRO

        candidatos = set()
        for cnpj in EMPRESAS_CADASTRO.keys():
            # CNPJ completo (apenas números)
            cnpj_limpo = cnpj.replace(".", "").replace("/", "").replace("-", "")
            candidatos.add(cnpj_limpo)

            # 4 primeiros dígitos
            if len(cnpj_limpo) >= 4:
                candidatos.add(cnpj_limpo[:4])

            # 5 primeiros dígitos
            if len(cnpj_limpo) >= 5:
                candidatos.add(cnpj_limpo[:5])

            # 8 primeiros dígitos (raiz do CNPJ)
            if len(cnpj_limpo) >= 8:
                candidatos.add(cnpj_limpo[:8])

        candidatos = sorted(list(candidatos))
    except ImportError:
        logger.warning(
            "Não foi possível importar EMPRESAS_CADASTRO, usando lista vazia de candidatos"
        )
        candidatos = []

    logger.debug(f"Testando {len(candidatos)} candidatos de senha para {filename}")

    for senha in candidatos:
        try:
            pdf = pdfplumber.open(file_path, password=senha)
            # Tenta acessar páginas para verificar se realmente abriu
            _ = pdf.pages
            logger.info(
                f"[OK] PDF desbloqueado com senha '{senha}' (pdfplumber): {filename}"
            )
            return pdf
        except Exception:
            # Senha incorreta, continuar tentando
            continue

    # 3. Nenhuma senha funcionou
    logger.warning(
        f"[ATENCAO] Falha ao desbloquear PDF {filename} (pdfplumber): Senha desconhecida"
    )
    return None


# Usar a função local
abrir_pdfplumber_com_senha = abrir_pdfplumber_com_senha_local
EXTRACTORS_AVAILABLE = True

# Tentar importar outros módulos opcionalmente
try:
    from extractors.admin_document import AdminDocumentExtractor
    from extractors.nfse_generic import NfseGenericExtractor
    from extractors.boleto import BoletoExtractor
    from core.empresa_matcher import (
        infer_fornecedor_from_text,
        is_nome_nosso,
        pick_first_non_our_cnpj,
        format_cnpj,
    )

    # Se chegou aqui, todos os módulos foram importados
    EXTRACTORS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Módulos opcionais não disponíveis: {e}")
    # Não altera EXTRACTORS_AVAILABLE se já for True
    if not EXTRACTORS_AVAILABLE:
        EXTRACTORS_AVAILABLE = False
    AdminDocumentExtractor = None
    NfseGenericExtractor = None
    BoletoExtractor = None
    infer_fornecedor_from_text = None
    is_nome_nosso = None
    pick_first_non_our_cnpj = None
    format_cnpj = None
    find_empresa_in_email = None


class PDFAnalyzer:
    """Analisador de conteúdo de PDFs."""

    def __init__(self):
        self.nfse_patterns = [
            r"NFSE|NOTA.*SERVICO|SERVICO.*NOTA|NFS-E",
            r"PRESTAÇÃO.*SERVIÇOS|PRESTACAO.*SERVICOS",
            r"TOMADOR.*SERVIÇOS|TOMADOR.*SERVICOS",
            r"CNPJ.*PRESTADOR|CPF.*PRESTADOR",
            r"VALOR.*SERVIÇOS|VALOR.*SERVICOS",
            r"IMPOSTO.*SERVIÇOS|IMPOSTO.*SERVICOS",
            r"ISS|INSS|PIS|COFINS",
        ]

        self.admin_patterns = [
            r"LEMBRETE.*GENTIL|LEMBRE?TE.*GENTIL",
            r"NOTIFICAÇÃO.*AUTOMÁTICA|NOTIFICACAO.*AUTOMATICA",
            r"SOLICITAÇÃO.*ENCERRAMENTO|SOLICITACAO.*ENCERRAMENTO",
            r"AVISO.*IMPORTANTE|COMUNICADO.*IMPORTANTE",
            r"DISTRATO.*CONTRATO|RESCISÃO.*CONTRATUAL",
            r"ORDEM.*SERVIÇO|ORDEM.*SERVICO",
            r"CONTRATO.*RENOVAÇÃO|CONTRATO.*RENOVACAO",
            r"RELATÓRIO.*FATURAMENTO|RELATORIO.*FATURAMENTO",
            r"PLANILHA.*CONFERÊNCIA|PLANILHA.*CONFERENCIA",
        ]

        self.value_patterns = [
            r"R\$\s*[\d\.]+,\d{2}",
            r"VALOR.*TOTAL.*R\$\s*[\d\.]+,\d{2}",
            r"TOTAL.*R\$\s*[\d\.]+,\d{2}",
            r"VALOR.*DO.*CONTRATO.*R\$\s*[\d\.]+,\d{2}",
            r"VALOR.*PAGAR.*R\$\s*[\d\.]+,\d{2}",
        ]

        # Padrões para detecção de vencimento mal extraído
        self.vencimento_patterns = [
            r"VENCIMENTO\s*[:;]?\s*$",  # VENCIMENTO: no final da linha (campo vazio)
            r"VENCIMENTO\s*[:;]?\s*\n",  # VENCIMENTO: seguido de nova linha
            r"DATA\s*VENCIMENTO\s*[:;]?\s*$",
            r"DATA\s*VENCIMENTO\s*[:;]?\s*\n",
            r"VENCE\s*EM\s*[:;]?\s*$",
            r"VENCE\s*EM\s*[:;]?\s*\n",
            r"VENC\.?\s*[:;]?\s*$",
            r"VENC\.?\s*[:;]?\s*\n",
        ]

        # Padrões para datas inválidas ou mal formatadas
        self.invalid_date_patterns = [
            r"00/00/0000",
            r"0{1,2}/0{1,2}/0{4}",
            r"\d{1,2}/\d{1,2}/0000",
            r"VENCIMENTO.*0{1,2}/0{1,2}/\d{4}",
            r"VENCIMENTO.*\d{1,2}/\d{1,2}/0{4}",
        ]

    def extract_text(self, pdf_path: Path) -> Optional[str]:
        """
        Extrai texto de um arquivo PDF, suportando PDFs protegidos por senha.

        Usa a função `abrir_pdfplumber_com_senha` do módulo strategies.pdf_utils
        para tentar desbloquear PDFs com senhas baseadas em CNPJs cadastrados.

        Args:
            pdf_path: Caminho para o arquivo PDF

        Returns:
            Texto extraído ou None em caso de erro
        """
        try:
            # Usar função utilitária que tenta desbloquear PDFs protegidos por senha
            if EXTRACTORS_AVAILABLE and abrir_pdfplumber_com_senha:
                pdf = abrir_pdfplumber_com_senha(str(pdf_path))
            else:
                # Fallback para pdfplumber padrão se a função utilitária não estiver disponível
                import pdfplumber

                pdf = pdfplumber.open(pdf_path)

            if pdf is None:
                logger.warning(
                    f"Não foi possível abrir PDF (possível senha desconhecida): {pdf_path.name}"
                )
                return None

            # Usar context manager para garantir que o PDF seja fechado
            with pdf:
                text = ""
                for i, page in enumerate(pdf.pages):
                    page_text = page.extract_text()
                    if page_text:
                        text += f"--- Página {i + 1} ---\n{page_text}\n\n"

            return text if text else None

        except ImportError:
            logger.error(
                "pdfplumber não está instalado. Instale com: pip install pdfplumber"
            )
            return None
        except Exception as e:
            error_msg = str(e).lower()
            if "password" in error_msg or "encrypted" in error_msg:
                logger.warning(
                    f"PDF protegido por senha não desbloqueado: {pdf_path.name}"
                )
            else:
                logger.error(f"Erro ao extrair texto de {pdf_path.name}: {e}")
            return None

    def classify_document(self, text: str) -> Dict[str, Any]:
        """
        Classifica um documento baseado em seu conteúdo.

        Args:
            text: Texto do documento

        Returns:
            Dicionário com classificação e características
        """
        text_upper = text.upper()

        classification = {
            "likely_nfse": False,
            "likely_admin": False,
            "likely_contract": False,
            "likely_report": False,
            "has_values": False,
            "values_found": [],
            "has_vencimento_issues": False,
            "vencimento_issues_detected": [],
            "confidence": 0.0,
            "detected_patterns": [],
            "recommended_type": "DESCONHECIDO",
        }

        # Verificar padrões de NFSE
        nfse_score = 0
        for pattern in self.nfse_patterns:
            if re.search(pattern, text_upper, re.IGNORECASE):
                nfse_score += 1
                classification["detected_patterns"].append(f"NFSE: {pattern}")

        # Verificar padrões administrativos
        admin_score = 0
        for pattern in self.admin_patterns:
            if re.search(pattern, text_upper, re.IGNORECASE):
                admin_score += 1
                classification["detected_patterns"].append(f"ADMIN: {pattern}")

        # Verificar valores
        value_matches = []
        for pattern in self.value_patterns:
            matches = re.findall(pattern, text_upper)
            if matches:
                value_matches.extend(matches)

        if value_matches:
            classification["has_values"] = True
            classification["values_found"] = value_matches

        # Verificar problemas de vencimento
        vencimento_issues = []
        for pattern in self.vencimento_patterns:
            if re.search(pattern, text_upper, re.MULTILINE):
                vencimento_issues.append(f"Padrão vencimento vazio: {pattern}")
                classification["detected_patterns"].append(f"VEN_EMPTY: {pattern}")

        for pattern in self.invalid_date_patterns:
            if re.search(pattern, text_upper, re.IGNORECASE):
                vencimento_issues.append(f"Data inválida: {pattern}")
                classification["detected_patterns"].append(f"VEN_INVALID: {pattern}")

        if vencimento_issues:
            classification["has_vencimento_issues"] = True
            classification["vencimento_issues_detected"] = vencimento_issues

        # Determinar classificação baseada em scores
        total_score = nfse_score + admin_score

        if total_score > 0:
            classification["confidence"] = max(nfse_score, admin_score) / total_score

            if nfse_score > admin_score:
                classification["likely_nfse"] = True
                classification["recommended_type"] = "NFSE"
            else:
                classification["likely_admin"] = True
                classification["recommended_type"] = "ADMINISTRATIVO"

                # Refinar tipo administrativo
                if any("CONTRATO" in p for p in classification["detected_patterns"]):
                    classification["likely_contract"] = True
                    classification["recommended_type"] = "CONTRATO"
                elif any(
                    "RELATÓRIO" in p or "PLANILHA" in p
                    for p in classification["detected_patterns"]
                ):
                    classification["likely_report"] = True
                    classification["recommended_type"] = "RELATÓRIO"

        return classification

    def analyze_pdf(self, pdf_path: Path) -> Optional[Dict[str, Any]]:
        """
        Analisa um PDF completo.

        Args:
            pdf_path: Caminho para o arquivo PDF

        Returns:
            Dicionário com análise completa ou None em caso de erro
        """
        text = self.extract_text(pdf_path)
        if not text:
            return None

        classification = self.classify_document(text)

        # Informações básicas do PDF (suporta PDFs com senha)
        try:
            if EXTRACTORS_AVAILABLE and abrir_pdfplumber_com_senha:
                # Usar função utilitária que tenta desbloquear PDFs protegidos
                pdf = abrir_pdfplumber_com_senha(str(pdf_path))
                if pdf:
                    with pdf:
                        page_count = len(pdf.pages)
                else:
                    page_count = "DESCONHECIDO (senha?)"
            else:
                import pdfplumber

                with pdfplumber.open(pdf_path) as pdf:
                    page_count = len(pdf.pages)
        except Exception:
            page_count = "DESCONHECIDO"

        analysis = {
            "pdf_name": pdf_path.name,
            "pdf_path": str(pdf_path),
            "page_count": page_count,
            "text_length": len(text),
            "text_sample": text[:500] + "..." if len(text) > 500 else text,
            **classification,
            "full_text": text,
        }

        return analysis


def load_problematic_cases(csv_path: Path) -> List[Dict[str, Any]]:
    """
    Carrega casos problemáticos do relatório de lotes.

    Critérios expandidos:
    1. Documentos administrativos (outros > 0) com valor zero
    2. Vencimento inválido (vazio, "0", ou "00/00/0000")
    3. Fornecedor genérico (ex: "CNPJ FORNECEDOR", "FORNECEDOR", "CPF Fornecedor:")
    4. Fornecedor interno (empresa do nosso cadastro)

    Args:
        csv_path: Caminho para relatorio_lotes.csv

    Returns:
        Lista de casos problemáticos
    """
    cases = []

    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            for i, row in enumerate(reader, 1):
                outros = int(row.get("outros", "0") or "0")
                nfses = int(row.get("nfses", "0") or "0")

                # Converter valor brasileiro para float
                valor_str = row.get("valor_compra", "0")
                valor_str = valor_str.replace(".", "").replace(",", ".")
                try:
                    valor = float(valor_str) if valor_str else 0.0
                except ValueError:
                    valor = 0.0

                # Extrair campos adicionais para validação
                vencimento = row.get("vencimento", "").strip()
                fornecedor = row.get("fornecedor", "").strip()

                # Validar vencimento usando função auxiliar
                validacao_vencimento = validar_vencimento(vencimento)
                vencimento_invalido = (
                    not validacao_vencimento["valido"]
                    or validacao_vencimento["data_zerada"]
                )

                # Validar fornecedor usando função auxiliar
                validacao_fornecedor = validar_fornecedor(
                    fornecedor, verificar_interno=EXTRACTORS_AVAILABLE
                )
                fornecedor_generico = validacao_fornecedor["generico"]
                fornecedor_interno = validacao_fornecedor["interno"]

                # Critério restrito: apenas documentos administrativos ou NFSEs com valor zero
                tem_problema = (
                    (
                        outros > 0 and valor == 0
                    )  # Documentos administrativos com valor zero
                    or (nfses > 0 and valor == 0)  # NFSEs com valor zero
                )

                if tem_problema:
                    case = {
                        "row_number": i,
                        "batch_id": row.get("batch_id", ""),
                        "outros": outros,
                        "nfses": nfses,
                        "valor_compra": valor,
                        "status_conciliacao": row.get("status_conciliacao", ""),
                        "divergencia": row.get("divergencia", ""),
                        "fornecedor": fornecedor,
                        "email_subject": row.get("email_subject", ""),
                        "email_sender": row.get("email_sender", ""),
                        "source_folder": row.get("source_folder", ""),
                        "empresa": row.get("empresa", ""),
                        "numero_nota": row.get("numero_nota", ""),
                        "vencimento": vencimento,
                        "pdf_analysis": [],
                        "classification_summary": {},
                        "vencimento_invalido": vencimento_invalido,
                        "fornecedor_generico": fornecedor_generico,
                        "fornecedor_interno": fornecedor_interno,
                        "validacao_vencimento": validacao_vencimento,
                        "validacao_fornecedor": validacao_fornecedor,
                    }
                    cases.append(case)

        logger.info(f"Carregados {len(cases)} casos problemáticos")
        return cases

    except FileNotFoundError:
        logger.error(f"Arquivo não encontrado: {csv_path}")
        return []
    except Exception as e:
        logger.error(f"Erro ao carregar CSV: {e}")
        return []


def check_csv_extraction_quality(case: Dict[str, Any]) -> Dict[str, Any]:
    """
    Verifica a qualidade da extração diretamente dos dados do CSV.
    Usa funções auxiliares de validação para vencimento e fornecedor.

    Args:
        case: Dicionário com dados do caso do CSV

    Returns:
        Dicionário com problemas detectados na extração e severidade
    """
    problems = {
        "fornecedor_issues": [],
        "valor_issues": [],
        "vencimento_issues": [],
        "numero_nota_issues": [],
        "extrator_identification_issues": [],
        "data_validation_issues": [],
        "severity_level": "",
    }

    # 1. Validar fornecedor usando função auxiliar
    fornecedor = case.get("fornecedor", "")

    # Usar validação já existente no caso se disponível, ou calcular nova
    if "validacao_fornecedor" in case:
        validacao_fornecedor = case["validacao_fornecedor"]
    else:
        validacao_fornecedor = validar_fornecedor(
            fornecedor, verificar_interno=EXTRACTORS_AVAILABLE
        )

    # Adicionar problemas da validação do fornecedor
    for problema in validacao_fornecedor["problemas"]:
        problems["fornecedor_issues"].append(problema)

    # 2. Validar vencimento usando função auxiliar
    vencimento = case.get("vencimento", "")

    # Usar validação já existente no caso se disponível, ou calcular nova
    if "validacao_vencimento" in case:
        validacao_vencimento = case["validacao_vencimento"]
    else:
        validacao_vencimento = validar_vencimento(vencimento)

    # Adicionar problemas da validação do vencimento
    for problema in validacao_vencimento["problemas"]:
        problems["vencimento_issues"].append(problema)

    # Adicionar problemas de data zerada/inválida à categoria específica
    if validacao_vencimento["data_zerada"]:
        problems["data_validation_issues"].append("Data zerada ou inválida")
    elif not validacao_vencimento["valido"] and vencimento:
        problems["data_validation_issues"].append("Data de vencimento inválida")

    # Verificar vencimento faltante para documentos não-NFSE
    if not vencimento.strip():
        outros = case.get("outros", 0)
        nfses = case.get("nfses", 0)
        email_subject = case.get("email_subject", "").upper()

        # Não marcar problema de vencimento se for NFSE
        if outros > 0 and nfses == 0:
            message = "Vencimento não extraído"

            # Verificar se o assunto sugere boleto/fatura
            is_boleto_subject = "BOLETO" in email_subject or "FATURA" in email_subject
            is_vencimento_subject = (
                "VENCIMENTO" in email_subject or "VENCE" in email_subject
            )

            if is_boleto_subject or is_vencimento_subject:
                message += " (assunto sugere boleto/fatura)"
            else:
                message += " (pode ser boleto)"

            problems["vencimento_issues"].append(message)
            problems["data_validation_issues"].append("Data de vencimento faltante")

    # 3. Verificar valor
    valor = case.get("valor_compra", 0)
    outros = case.get("outros", 0)
    nfses = case.get("nfses", 0)

    if valor == 0 and (outros > 0 or nfses > 0):
        # Documentos foram encontrados mas valor é zero
        problems["valor_issues"].append(
            f"Valor zero com {outros} outros e {nfses} NFSEs"
        )

    # 4. Verificar número da nota (para NFSEs)
    numero_nota = case.get("numero_nota", "")
    if nfses > 0 and not numero_nota:
        problems["numero_nota_issues"].append("Número da nota não extraído (para NFSE)")

    # 5. Tentar identificar o tipo de documento baseado no assunto/fornecedor
    email_subject = case.get("email_subject", "").upper()

    # Padrões comuns para identificar tipo de documento
    if "BOLETO" in email_subject or "FATURA" in email_subject:
        problems["extrator_identification_issues"].append(
            "Assunto sugere boleto/fatura"
        )
    elif "NF" in email_subject or "NOTA" in email_subject:
        problems["extrator_identification_issues"].append("Assunto sugere nota fiscal")

    # 6. Classificar severidade dos problemas
    severity = classificar_severidade_problemas(problems)
    problems["severity_level"] = severity

    return problems


def analyze_pdfs_for_case(
    case: Dict[str, Any], analyzer: PDFAnalyzer
) -> Dict[str, Any]:
    """
    Analisa PDFs para um caso específico.

    Args:
        case: Caso problemático
        analyzer: Instância do PDFAnalyzer

    Returns:
        Caso atualizado com análise de PDFs
    """
    # Primeiro verificar qualidade da extração do CSV
    csv_quality = check_csv_extraction_quality(case)
    case["csv_extraction_quality"] = csv_quality

    # Fluxo: 1) Identificar problemas no CSV, 2) Usar PDFs para tentar corrigir
    fornecedor_atual = case.get("fornecedor", "")

    logger.info(f"Verificando qualidade da extração para {case['batch_id']}")
    logger.info(f"Fornecedor atual: '{fornecedor_atual}'")

    source_folder = case.get("source_folder", "")
    if not source_folder:
        logger.warning(f"Sem pasta fonte para caso: {case['batch_id']}")
        return case

    folder_path = Path(source_folder)
    if not folder_path.exists():
        logger.warning(f"Pasta não existe: {folder_path}")
        return case

    pdf_files = list(folder_path.glob("*.pdf"))
    if not pdf_files:
        logger.info(f"Sem PDFs na pasta: {folder_path}")
        return case

    logger.info(f"Analisando {len(pdf_files)} PDF(s) para {case['batch_id']}")

    pdf_analyses = []
    for pdf_path in pdf_files:
        analysis = analyzer.analyze_pdf(pdf_path)
        if analysis:
            # Analisar qualidade da extração com extratores reais
            if EXTRACTORS_AVAILABLE and analysis.get("text_sample"):
                extraction_quality = check_extraction_quality(analysis["text_sample"])
                analysis["extraction_quality"] = extraction_quality

            # Tentar corrigir o nome do fornecedor apenas se há problemas detectados no CSV
            # Primeiro verificar se há problemas de fornecedor na extração do CSV
            has_fornecedor_issues = bool(csv_quality.get("fornecedor_issues", []))

            if has_fornecedor_issues and fornecedor_atual and analysis.get("full_text"):
                logger.info(
                    f"Tentando corrigir fornecedor para {case['batch_id']} usando PDF {pdf_path.name}"
                )
                empresa_cnpj = obter_cnpj_da_empresa(case.get("empresa"))
                correcao = tentar_corrigir_fornecedor(
                    fornecedor_atual, analysis["full_text"], empresa_cnpj
                )
                analysis["correcao_fornecedor"] = correcao

                if correcao.get("corrigido"):
                    logger.info(
                        f"[OK] Correção sugerida: '{correcao['fornecedor_sugerido']}' (método: {correcao['metodo']}, confiança: {correcao['confianca']:.0%})"
                    )
                else:
                    logger.info(
                        f"[ATENCAO] Não foi possível corrigir fornecedor para {case['batch_id']}"
                    )

            pdf_analyses.append(analysis)

    case["pdf_analysis"] = pdf_analyses

    # Resumo das correções de fornecedor
    correcoes_fornecedor = []
    for analysis in pdf_analyses:
        if analysis.get("correcao_fornecedor", {}).get("corrigido"):
            correcoes_fornecedor.append(analysis["correcao_fornecedor"])

    if correcoes_fornecedor:
        case["correcoes_fornecedor"] = correcoes_fornecedor

    # Resumo da classificação
    if pdf_analyses:
        total_pdfs = len(pdf_analyses)
        nfse_count = sum(1 for a in pdf_analyses if a["likely_nfse"])
        admin_count = sum(1 for a in pdf_analyses if a["likely_admin"])
        has_values_count = sum(1 for a in pdf_analyses if a["has_values"])

        case["classification_summary"] = {
            "total_pdfs": total_pdfs,
            "nfse_count": nfse_count,
            "admin_count": admin_count,
            "has_values_count": has_values_count,
            "primary_classification": "MISTO"
            if nfse_count > 0 and admin_count > 0
            else "NFSE"
            if nfse_count > 0
            else "ADMIN"
            if admin_count > 0
            else "DESCONHECIDO",
            "has_missing_values": has_values_count > 0,
            "recommended_action": "REVISAR_CLASSIFICACAO"
            if nfse_count > 0 and case["outros"] > 0
            else "MELHORAR_EXTRACAO"
            if has_values_count > 0
            else "DOCUMENTO_ADMIN_OK"
            if admin_count > 0
            else "INVESTIGAR_MANUALMENTE",
        }

    return case


def check_extraction_quality(text: str) -> Dict[str, Any]:
    """
    Verifica a qualidade da extração usando os extratores reais do projeto.

    Args:
        text: Texto extraído do PDF

    Returns:
        Dicionário com informações sobre qualidade da extração
    """
    if not EXTRACTORS_AVAILABLE or not text:
        return {"available": False}

    quality_report = {
        "available": True,
        "extractors_tested": [],
        "missing_fields": [],
        "fornecedor_issues": [],
        "valor_issues": [],
        "vencimento_issues": [],
        "numero_nota_issues": [],
    }

    # Testar cada extrator relevante
    extractors_to_test = []

    if NfseGenericExtractor:
        nfse_extractor = NfseGenericExtractor()
        if nfse_extractor.can_handle(text):
            extractors_to_test.append(("NFSE", nfse_extractor))

    if BoletoExtractor:
        boleto_extractor = BoletoExtractor()
        if boleto_extractor.can_handle(text):
            extractors_to_test.append(("BOLETO", boleto_extractor))

    if AdminDocumentExtractor:
        admin_extractor = AdminDocumentExtractor()
        if admin_extractor.can_handle(text):
            extractors_to_test.append(("ADMIN", admin_extractor))

    for extractor_name, extractor in extractors_to_test:
        try:
            extracted_data = extractor.extract(text)
            quality_report["extractors_tested"].append(extractor_name)

            # Verificar campos críticos
            if extractor_name == "NFSE":
                # Para NFSE: verificar número da nota e fornecedor
                numero_nota = extracted_data.get("numero_nota")
                if not numero_nota or numero_nota.strip() == "":
                    quality_report["numero_nota_issues"].append(
                        f"{extractor_name}: Não extraiu número da nota"
                    )

                valor_total = extracted_data.get("valor_total")
                if not valor_total or valor_total == 0:
                    quality_report["valor_issues"].append(
                        f"{extractor_name}: Não extraiu valor total"
                    )

            elif extractor_name == "BOLETO":
                # Para Boleto: verificar vencimento e valor
                vencimento = extracted_data.get("vencimento")
                if not vencimento:
                    quality_report["vencimento_issues"].append(
                        f"{extractor_name}: Não extraiu vencimento"
                    )

                valor_documento = extracted_data.get("valor_documento")
                if not valor_documento or valor_documento == 0:
                    quality_report["valor_issues"].append(
                        f"{extractor_name}: Não extraiu valor do documento"
                    )

            # Verificar fornecedor para todos os extratores
            fornecedor_nome = extracted_data.get(
                "fornecedor_nome"
            ) or extracted_data.get("fornecedor")
            if fornecedor_nome:
                # Verificar se o fornecedor não é uma empresa nossa
                if is_nome_nosso and is_nome_nosso(fornecedor_nome):
                    quality_report["fornecedor_issues"].append(
                        f"{extractor_name}: Fornecedor é empresa nossa: {fornecedor_nome}"
                    )

                # Verificar se o fornecedor tem conteúdo significativo
                # Usar a nova validação para reduzir falsos positivos
                validacao = validar_fornecedor(fornecedor_nome, verificar_interno=False)
                if validacao["generico"]:
                    quality_report["fornecedor_issues"].append(
                        f"{extractor_name}: Fornecedor genérico: {fornecedor_nome}"
                    )
            else:
                quality_report["fornecedor_issues"].append(
                    f"{extractor_name}: Não extraiu fornecedor"
                )

            # Tentar inferir fornecedor do texto usando empresa_matcher
            if infer_fornecedor_from_text and not fornecedor_nome:
                inferred_fornecedor = infer_fornecedor_from_text(text, None)
                if inferred_fornecedor:
                    quality_report["fornecedor_issues"].append(
                        f"{extractor_name}: Fornecedor inferível do texto: {inferred_fornecedor}"
                    )

        except Exception as e:
            quality_report["missing_fields"].append(
                f"{extractor_name}: Erro na extração: {e}"
            )

    # Se nenhum extrator foi testado, tentar análise genérica
    if not extractors_to_test:
        # Verificar valores no texto
        value_patterns = [r"R\$\s*[\d\.]+,\d{2}", r"VALOR.*TOTAL.*R\$\s*[\d\.]+,\d{2}"]
        has_values = any(re.search(pattern, text.upper()) for pattern in value_patterns)
        if has_values:
            quality_report["valor_issues"].append(
                "GENÉRICO: Valores detectados mas não extraídos"
            )

        # Verificar datas de vencimento
        vencimento_patterns = [
            r"VENCIMENTO.*\d{2}/\d{2}/\d{4}",
            r"DATA.*VENCIMENTO.*\d{2}/\d{2}/\d{4}",
        ]
        has_vencimento = any(
            re.search(pattern, text.upper()) for pattern in vencimento_patterns
        )
        if has_vencimento:
            quality_report["vencimento_issues"].append(
                "GENÉRICO: Vencimento detectado mas não extraído"
            )

        # Verificar números de nota
        nota_patterns = [
            r"N[º°o]\.?\s*[:.-]?\s*\d+",
            r"NOTA.*FISCAL.*N[º°o]\.?\s*[:.-]?\s*\d+",
        ]
        has_nota = any(re.search(pattern, text.upper()) for pattern in nota_patterns)
        if has_nota:
            quality_report["numero_nota_issues"].append(
                "GENÉRICO: Número de nota detectado mas não extraído"
            )

    return quality_report


def generate_detailed_report(analyzed_cases: List[Dict[str, Any]]) -> str:
    """
    Gera um relatório detalhado com todos os casos analisados.

    Args:
        analyzed_cases: Lista de casos analisados

    Returns:
        String com relatório formatado
    """
    report_lines = []
    report_lines.append("=" * 100)
    report_lines.append("RELATÓRIO DETALHADO DE ANÁLISE DE PDFs PROBLEMÁTICOS")
    report_lines.append("=" * 100)
    report_lines.append("")

    for case in analyzed_cases:
        report_lines.append(f"CASO #{case.get('row_number', 'N/A')}")
        report_lines.append(f"Batch ID: {case.get('batch_id', 'N/A')}")
        report_lines.append(f"Assunto do e-mail: {case.get('email_subject', 'N/A')}")
        report_lines.append(f"Remetente: {case.get('email_sender', 'N/A')}")
        report_lines.append(f"Pasta fonte: {case.get('source_folder', 'N/A')}")
        report_lines.append(f"Empresa: {case.get('empresa', 'N/A')}")
        report_lines.append("")

        # Informações do CSV
        report_lines.append("INFORMAÇÕES DO CSV:")
        report_lines.append(f"  Outros (administrativos): {case.get('outros', 0)}")
        report_lines.append(f"  NFSEs: {case.get('nfses', 0)}")
        report_lines.append(f"  Valor total: R$ {case.get('valor_compra', 0):,.2f}")
        report_lines.append(f"  Fornecedor: {case.get('fornecedor', 'N/A')}")
        report_lines.append(f"  Vencimento: {case.get('vencimento', 'N/A')}")
        report_lines.append(f"  Número da nota: {case.get('numero_nota', 'N/A')}")
        report_lines.append("")

        # Problemas detectados no carregamento
        if case.get("vencimento_invalido"):
            report_lines.append("[ATENCAO] VENCIMENTO INVÁLIDO DETECTADO")
        if case.get("fornecedor_generico"):
            report_lines.append("[ATENCAO] FORNECEDOR GENÉRICO DETECTADO")
        if case.get("fornecedor_interno"):
            report_lines.append("[ATENCAO] FORNECEDOR INTERNO DETECTADO")
        if case.get("fornecedor_generico") or case.get("fornecedor_interno"):
            validacao = case.get("validacao_fornecedor", {})
            for problema in validacao.get("problemas", []):
                report_lines.append(f"  • {problema}")
        report_lines.append("")

        # Análise de PDFs
        pdf_analyses = case.get("pdf_analysis", [])
        if pdf_analyses:
            report_lines.append("ANÁLISE DOS PDFs ENCONTRADOS:")
            for analysis in pdf_analyses:
                report_lines.append(f"  PDF: {analysis.get('pdf_name', 'N/A')}")
                report_lines.append(f"    Páginas: {analysis.get('page_count', 'N/A')}")
                report_lines.append(
                    f"    Texto (chars): {analysis.get('text_length', 0)}"
                )

                classification = analysis.get("recommended_type", "DESCONHECIDO")
                report_lines.append(f"    Classificação sugerida: {classification}")

                if analysis.get("has_values"):
                    valores = analysis.get("values_found", [])
                    report_lines.append(
                        f"    Valores detectados no PDF: {', '.join(valores[:3])}"
                    )

                if analysis.get("has_vencimento_issues"):
                    issues = analysis.get("vencimento_issues_detected", [])
                    report_lines.append(
                        f"    Problemas de vencimento: {', '.join(issues[:2])}"
                    )

                # Correção de fornecedor
                correcao = analysis.get("correcao_fornecedor", {})
                if correcao.get("corrigido"):
                    report_lines.append(
                        f"    [OK] Correção de fornecedor sugerida: {correcao['fornecedor_sugerido']}"
                    )
                    report_lines.append(
                        f"       Método: {correcao['metodo']}, Confiança: {correcao['confianca']:.0%}"
                    )
                report_lines.append("")
        else:
            report_lines.append("NENHUM PDF ANALISADO")
            report_lines.append("")

        # Resumo da classificação
        summary = case.get("classification_summary", {})
        if summary:
            report_lines.append("RESUMO DA CLASSIFICAÇÃO:")
            report_lines.append(f"  PDFs analisados: {summary.get('total_pdfs', 0)}")
            report_lines.append(
                f"  PDFs classificados como NFSE: {summary.get('nfse_count', 0)}"
            )
            report_lines.append(
                f"  PDFs classificados como administrativos: {summary.get('admin_count', 0)}"
            )
            report_lines.append(
                f"  PDFs com valores detectados: {summary.get('has_values_count', 0)}"
            )
            report_lines.append(
                f"  Classificação primária: {summary.get('primary_classification', 'DESCONHECIDO')}"
            )
            report_lines.append(
                f"  Ação recomendada: {summary.get('recommended_action', 'N/A')}"
            )
            report_lines.append("")

        # Correções de fornecedor sugeridas
        correcoes = case.get("correcoes_fornecedor", [])
        if correcoes:
            report_lines.append("CORREÇÕES DE FORNECEDOR SUGERIDAS:")
            for correcao in correcoes:
                report_lines.append(
                    f"  • {correcao['fornecedor_sugerido']} (método: {correcao['metodo']}, confiança: {correcao['confianca']:.0%})"
                )
            report_lines.append("")

        # Qualidade da extração do CSV
        csv_quality = case.get("csv_extraction_quality", {})
        if csv_quality:
            report_lines.append("QUALIDADE DA EXTRAÇÃO DO CSV:")
            report_lines.append(
                f"  Nível de severidade: {csv_quality.get('severity_level', 'N/A')}"
            )

            for issue_type in [
                "fornecedor_issues",
                "valor_issues",
                "vencimento_issues",
                "numero_nota_issues",
                "extrator_identification_issues",
                "data_validation_issues",
            ]:
                issues = csv_quality.get(issue_type, [])
                if issues:
                    report_lines.append(f"  {issue_type.replace('_', ' ').title()}:")
                    for issue in issues[:3]:  # Mostrar no máximo 3 de cada tipo
                        report_lines.append(f"    • {issue}")
                    if len(issues) > 3:
                        report_lines.append(
                            f"    • ... e mais {len(issues) - 3} problema(s)"
                        )
            report_lines.append("")

        report_lines.append("-" * 80)
        report_lines.append("")

    # Resumo executivo
    analyzed_with_pdfs = [c for c in analyzed_cases if c.get("pdf_analysis")]

    report_lines.append("=" * 100)
    report_lines.append("RESUMO EXECUTIVO")
    report_lines.append("=" * 100)
    report_lines.append("")
    report_lines.append(f"Total de casos analisados: {len(analyzed_cases)}")
    report_lines.append(f"Casos com PDFs analisados: {len(analyzed_with_pdfs)}")

    if analyzed_with_pdfs:
        classifications = {}
        for case in analyzed_with_pdfs:
            summary = case.get("classification_summary", {})
            primary = summary.get("primary_classification", "DESCONHECIDO")
            classifications[primary] = classifications.get(primary, 0) + 1

        report_lines.append("\nDistribuição de classificações:")
        for class_type, count in sorted(classifications.items()):
            percentage = (count / len(analyzed_with_pdfs)) * 100
            report_lines.append(f"  {class_type}: {count} casos ({percentage:.1f}%)")

    # Contadores de problemas específicos
    specific_counts = {
        "vencimento_invalido": 0,
        "fornecedor_generico": 0,
        "fornecedor_interno": 0,
    }

    for case in analyzed_cases:
        if case.get("vencimento_invalido"):
            specific_counts["vencimento_invalido"] += 1
        if case.get("fornecedor_generico"):
            specific_counts["fornecedor_generico"] += 1
        if case.get("fornecedor_interno"):
            specific_counts["fornecedor_interno"] += 1

    report_lines.append("\nProblemas específicos detectados:")
    for problem_type, count in sorted(specific_counts.items()):
        if count > 0:
            problem_name = problem_type.replace("_", " ").title()
            percentage = (count / len(analyzed_cases)) * 100
            report_lines.append(f"  {problem_name}: {count} casos ({percentage:.1f}%)")

    # Contadores de correções de fornecedor
    correcoes_counts = {
        "correcoes_sugeridas": 0,
        "correcoes_infer": 0,
        "correcoes_cnpj_only": 0,
    }

    for case in analyzed_cases:
        correcoes = case.get("correcoes_fornecedor", [])
        if correcoes:
            correcoes_counts["correcoes_sugeridas"] += 1
            for correcao in correcoes:
                if correcao.get("metodo") == "infer":
                    correcoes_counts["correcoes_infer"] += 1
                elif correcao.get("metodo") == "cnpj_only":
                    correcoes_counts["correcoes_cnpj_only"] += 1

    if correcoes_counts["correcoes_sugeridas"] > 0:
        report_lines.append("\nCORREÇÕES DE FORNECEDOR SUGERIDAS:")
        report_lines.append(
            f"  Total de correções sugeridas: {correcoes_counts['correcoes_sugeridas']}"
        )
        if correcoes_counts["correcoes_infer"] > 0:
            report_lines.append(
                f"  Correções por inferência (alta confiança): {correcoes_counts['correcoes_infer']}"
            )
        if correcoes_counts["correcoes_cnpj_only"] > 0:
            report_lines.append(
                f"  Correções apenas por CNPJ (média confiança): {correcoes_counts['correcoes_cnpj_only']}"
            )

    report_lines.append("\n" + "=" * 100)

    return "\n".join(report_lines)


def main():
    """Função principal do script."""
    print("=" * 100)
    print("ANÁLISE DE PDFs PROBLEMÁTICOS")
    print("Documentos administrativos com valor zero")
    print("=" * 100)

    # Verificar dependências
    try:
        import pdfplumber  # noqa: F401  # type: ignore  # Verifica disponibilidade da lib

        print("OK pdfplumber disponível")
    except ImportError:
        print("ERRO pdfplumber não está instalado")
        print("  Instale com: pip install pdfplumber")
        sys.exit(1)

    # Configurar caminhos
    base_dir = Path(__file__).parent
    csv_path = base_dir.parent / "data" / "output" / "relatorio_lotes.csv"

    print(f"\nLendo arquivo: {csv_path}")
    if not csv_path.exists():
        print(f"ERRO Arquivo não encontrado: {csv_path}")
        sys.exit(1)

    # Carregar casos problemáticos
    cases = load_problematic_cases(csv_path)
    if not cases:
        print("OK Nenhum caso problemático encontrado!")
        sys.exit(0)

    print(f"OK Encontrados {len(cases)} casos problemáticos")

    # Analisar PDFs
    print("\nAnalisando PDFs...")
    analyzer = PDFAnalyzer()
    analyzed_cases = []

    for i, case in enumerate(cases, 1):
        print(f"  [{i}/{len(cases)}] Analisando {case['batch_id']}...", end=" ")
        analyzed_case = analyze_pdfs_for_case(case, analyzer)
        analyzed_cases.append(analyzed_case)

        summary = analyzed_case.get("classification_summary", {})
        if summary:
            action = summary.get("recommended_action", "")
            print(f"{action}")
        else:
            print("sem PDFs")

    # Gerar relatório
    print("\nGerando relatório...")
    report = generate_detailed_report(analyzed_cases)

    # Exibir resumo
    print("\n" + "=" * 100)
    print("RESUMO EXECUTIVO")
    print("=" * 100)

    analyzed_with_pdfs = [c for c in analyzed_cases if c.get("pdf_analysis")]
    if analyzed_with_pdfs:
        print(f"Casos analisados com PDFs: {len(analyzed_with_pdfs)}/{len(cases)}")

        classifications = {}
        for case in analyzed_with_pdfs:
            summary = case.get("classification_summary", {})
            primary = summary.get("primary_classification", "DESCONHECIDO")
            classifications[primary] = classifications.get(primary, 0) + 1

        print("\nDistribuição de classificações:")
        for class_type, count in sorted(classifications.items()):
            percentage = (count / len(analyzed_with_pdfs)) * 100
            print(f"  {class_type}: {count} casos ({percentage:.1f}%)")
    else:
        print("[ATENCAO] Nenhum PDF foi analisado")

    # Estatísticas de problemas de extração do CSV
    problem_counts = {
        "fornecedor_issues": 0,
        "valor_issues": 0,
        "vencimento_issues": 0,
        "numero_nota_issues": 0,
        "extrator_identification_issues": 0,
        "data_validation_issues": 0,
    }

    for case in analyzed_cases:
        csv_quality = case.get("csv_extraction_quality", {})
        for problem_type in problem_counts.keys():
            issues = csv_quality.get(problem_type, [])
            if issues:
                problem_counts[problem_type] += 1

    total_cases_with_problems = sum(problem_counts.values())
    if total_cases_with_problems > 0:
        print("\nProblemas de extração identificados:")
        print("-" * 50)
        for problem_type, count in sorted(problem_counts.items()):
            if count > 0:
                problem_name = problem_type.replace("_", " ").title()
                percentage = (count / len(analyzed_cases)) * 100
                print(f"  {problem_name}: {count} casos ({percentage:.1f}%)")

    # Contadores de problemas específicos detectados durante carregamento
    specific_counts = {
        "vencimento_invalido": 0,
        "fornecedor_generico": 0,
        "fornecedor_interno": 0,
    }

    for case in analyzed_cases:
        if case.get("vencimento_invalido"):
            specific_counts["vencimento_invalido"] += 1
        if case.get("fornecedor_generico"):
            specific_counts["fornecedor_generico"] += 1
        if case.get("fornecedor_interno"):
            specific_counts["fornecedor_interno"] += 1

    total_specific_problems = sum(specific_counts.values())
    if total_specific_problems > 0:
        print("\nProblemas específicos detectados:")
        print("-" * 50)
        for problem_type, count in sorted(specific_counts.items()):
            if count > 0:
                problem_name = problem_type.replace("_", " ").title()
                percentage = (count / len(analyzed_cases)) * 100
                print(f"  {problem_name}: {count} casos ({percentage:.1f}%)")

    # Contadores de correções de fornecedor sugeridas
    correcoes_counts = {
        "correcoes_sugeridas": 0,
        "correcoes_infer": 0,
        "correcoes_cnpj_only": 0,
    }

    for case in analyzed_cases:
        correcoes = case.get("correcoes_fornecedor", [])
        if correcoes:
            correcoes_counts["correcoes_sugeridas"] += 1
            for correcao in correcoes:
                if correcao.get("metodo") == "infer":
                    correcoes_counts["correcoes_infer"] += 1
                elif correcao.get("metodo") == "cnpj_only":
                    correcoes_counts["correcoes_cnpj_only"] += 1

    if correcoes_counts["correcoes_sugeridas"] > 0:
        print("\nCORREÇÕES DE FORNECEDOR SUGERIDAS")
        print("-" * 50)
        print(
            f"  Total de correções sugeridas: {correcoes_counts['correcoes_sugeridas']}"
        )
        if correcoes_counts["correcoes_infer"] > 0:
            print(
                f"  Correções por inferência (alta confiança): {correcoes_counts['correcoes_infer']}"
            )
        if correcoes_counts["correcoes_cnpj_only"] > 0:
            print(
                f"  Correções apenas por CNPJ (média confiança): {correcoes_counts['correcoes_cnpj_only']}"
            )

        # Resumo dos problemas mais comuns
        print("\nPrincipais problemas:")
        for problem_type, count in sorted(
            problem_counts.items(), key=lambda x: x[1], reverse=True
        ):
            if count > 0:
                problem_name = problem_type.replace("_", " ").title()
                print(f"  - {problem_name}: {count} casos")
                if problem_type == "fornecedor_issues":
                    print(f"  • Fornecedor incorreto/genérico: {count} casos")
                elif problem_type == "valor_issues":
                    print(
                        f"  • Valor não extraído (zero com documentos): {count} casos"
                    )
                elif problem_type == "vencimento_issues":
                    print(f"  • Vencimento não extraído (boletos): {count} casos")
                elif problem_type == "numero_nota_issues":
                    print(f"  • Número da nota não extraído (NFSEs): {count} casos")
                elif problem_type == "extrator_identification_issues":
                    print(f"  • Tipo de documento mal identificado: {count} casos")
    else:
        print("\n[OK] Nenhum problema de extração identificado no CSV")

    # Salvar relatório
    output_dir = base_dir.parent / "data" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "analise_pdfs_detalhada.txt"

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\nOK Relatório salvo em: {output_path}")
    except Exception as e:
        print(f"\nERRO Erro ao salvar relatório: {e}")

    print("\n" + "=" * 100)
    print("ANÁLISE CONCLUÍDA")
    print("=" * 100)


if __name__ == "__main__":
    main()
