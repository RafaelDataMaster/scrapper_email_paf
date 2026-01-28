"""
Detector de empresa específico para e-mails sem anexo.

Este módulo é otimizado para detectar empresas a partir do corpo de e-mails
encaminhados, onde o contexto é diferente de documentos PDF/XML:

- Remove domínios internos (soumaster.com.br) que causam falsos positivos
- Remove URLs de tracking (click.*, track.*)
- Prioriza contexto seguro (campo "Para:", "Tomador:", etc.)
- Ignora contexto de "frase de segurança" e similares

Para emails COM anexo, use o módulo core.empresa_matcher que é otimizado
para trabalhar com os extratores de PDF/XML.
"""

import re
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from config.empresas import EMPRESAS_CADASTRO

from core.empresa_matcher import (
    empresa_codigo_from_razao,
    iter_cnpjs_in_text,
    normalize_cnpj_to_digits,
)


class EmpresaDetectorEmail:
    """
    Detecta qual empresa do cadastro está mencionada no texto de e-mails.
    
    Otimizado para e-mails encaminhados (sem anexo), onde precisa analisar
    o corpo do e-mail para encontrar a empresa destinatária da NF-e.
    """

    # Domínios a ignorar (são domínios corporativos internos, não indicam empresa)
    DOMINIOS_IGNORAR = {
        'soumaster.com.br',
        'soumaster.com',
        'gmail.com',
        'outlook.com',
        'hotmail.com',
        'yahoo.com',
        'yahoo.com.br',
    }

    # Padrões de URL a remover (tracking, analytics, etc.)
    URL_PATTERNS_REMOVER = [
        r'https?://click\.[^\s]+',       # click.omie.com, etc.
        r'https?://track\.[^\s]+',       # tracking URLs
        r'https?://[^\s]*\.cdn\.[^\s]+', # CDN URLs
        r'https?://cdn\.[^\s]+',         # CDN URLs
        r'https?://[^\s]+/track/[^\s]+', # /track/ paths
        r'https?://[^\s]+/click/[^\s]+', # /click/ paths
        r'href="[^"]*"',                 # Remove href attributes
        r'src="[^"]*"',                  # Remove src attributes
    ]

    # Palavras a ignorar no match por nome (muito genéricas)
    STOPWORDS = {
        'SERVICO', 'SERVICOS', 'SERVICE',
        'CONSULTORIA',
        'GESTAO', 'INTEGRADA',
        'COMERCIO', 'INDUSTRIA',
        'TECNOLOGIA', 'SOLUCOES',
        'SISTEMA', 'SISTEMAS',
        'EMPRESA', 'EMPRESAS',
        'ADMINISTRACAO', 'ADMINISTRADORA',
        'PARTICIPACOES', 'SOCIETARIAS',
        'GRUPO', 'HOLDING',
        'COMPANHIA', 'CIA',
        'LTDA', 'SA', 'S/A', 'EIRELI', 'EPP', 'ME',
        'PROVEDOR', 'ACESSO', 'INTERNET',
        'TELECOM', 'TELECOMUNICACOES', 'COMUNICACAO',
        'MATRIZ', 'FILIAL',
        'BRASIL', 'BRASILEIRA',
        'REDE',
        # Palavras comuns em HTML/emails
        'CLICK', 'TRACK', 'VIEW', 'OPEN',
        'LINK', 'HTTP', 'HTTPS', 'WWW',
        'STYLE', 'WIDTH', 'HEIGHT', 'FONT',
        'ALIGN', 'CENTER', 'LEFT', 'RIGHT',
        'VISTA',  # SPE VISTA ALEGRE - muito genérico
        'ALEGRE',
        'PAULO', 'SAO',  # Muito genérico
    }

    def __init__(self):
        self.cadastro = self._load_cadastro()
        self.empresas_por_codigo = self._build_codigo_map()

    def _load_cadastro(self) -> Dict[str, Dict]:
        """Carrega cadastro normalizado."""
        normalized = {}
        for cnpj, payload in (EMPRESAS_CADASTRO or {}).items():
            cnpj_digits = normalize_cnpj_to_digits(str(cnpj))
            if cnpj_digits:
                normalized[cnpj_digits] = payload
        return normalized

    def _build_codigo_map(self) -> Dict[str, List[str]]:
        """Mapeia código -> lista de CNPJs."""
        mapa = defaultdict(list)
        for cnpj, payload in self.cadastro.items():
            razao = payload.get("razao_social", "")
            codigo = empresa_codigo_from_razao(razao)
            if codigo:
                mapa[codigo.upper()].append(cnpj)
        return dict(mapa)

    def _limpar_texto(self, texto: str) -> str:
        """Remove domínios a ignorar, URLs de tracking e limpa texto para análise."""
        texto_limpo = texto

        # Remove URLs de tracking/analytics
        for pattern in self.URL_PATTERNS_REMOVER:
            texto_limpo = re.sub(pattern, ' ', texto_limpo, flags=re.IGNORECASE)

        # Remove domínios específicos
        for dominio in self.DOMINIOS_IGNORAR:
            # Remove menções ao domínio (e-mails, URLs)
            texto_limpo = re.sub(
                rf'[a-zA-Z0-9._%+-]*@{re.escape(dominio)}',
                ' ',
                texto_limpo,
                flags=re.IGNORECASE
            )
            texto_limpo = re.sub(
                rf'https?://[^\s]*{re.escape(dominio)}[^\s]*',
                ' ',
                texto_limpo,
                flags=re.IGNORECASE
            )
            texto_limpo = re.sub(
                rf'\b{re.escape(dominio)}\b',
                ' ',
                texto_limpo,
                flags=re.IGNORECASE
            )

        # Remove tags HTML comuns que podem conter palavras-chave
        texto_limpo = re.sub(r'<style[^>]*>.*?</style>', ' ', texto_limpo, flags=re.IGNORECASE | re.DOTALL)
        texto_limpo = re.sub(r'<script[^>]*>.*?</script>', ' ', texto_limpo, flags=re.IGNORECASE | re.DOTALL)

        return texto_limpo

    def _aparece_em_contexto_seguro(self, codigo: str, texto_upper: str) -> bool:
        """
        Verifica se o código aparece em contexto seguro (destinatário, razão social)
        vs contexto irrelevante (frase de segurança, senha).
        """
        # Padrões de contexto SEGURO (empresa é mencionada como destinatária)
        padroes_seguros = [
            rf'Para:\s*[^<\n]*{re.escape(codigo)}',  # Para: RBC Rede...
            rf'To:\s*[^<\n]*{re.escape(codigo)}',     # To: RBC Rede...
            rf'Tomador[:\s]+[^\n]*{re.escape(codigo)}',  # Tomador: RBC...
            rf'Destinat[áa]rio[:\s]+[^\n]*{re.escape(codigo)}',  # Destinatário: RBC...
            rf'Cliente[:\s]+[^\n]*{re.escape(codigo)}',  # Cliente: RBC...
        ]
        
        for pattern in padroes_seguros:
            if re.search(pattern, texto_upper, re.IGNORECASE):
                return True
        
        return False

    def _aparece_em_contexto_ignorar(self, codigo: str, texto_upper: str) -> bool:
        """
        Verifica se o código aparece apenas em contexto a ignorar
        (frase de segurança, senha, etc.)
        """
        # Padrões de contexto a IGNORAR
        padroes_ignorar = [
            rf'frase\s+de\s+seguran[çc]a[^:]*:[^\n]*{re.escape(codigo)}',
            rf'senha[^:]*:[^\n]*{re.escape(codigo)}',
            rf'password[^:]*:[^\n]*{re.escape(codigo)}',
            rf'security\s+phrase[^:]*:[^\n]*{re.escape(codigo)}',
        ]
        
        for pattern in padroes_ignorar:
            if re.search(pattern, texto_upper, re.IGNORECASE):
                return True
        
        return False

    def detectar(self, texto: str) -> Tuple[Optional[str], Optional[str], List[str]]:
        """
        Detecta empresa no texto de um e-mail.

        Args:
            texto: Corpo do e-mail (texto plano ou HTML)

        Returns:
            Tupla (codigo_empresa, metodo, lista_matches):
            - codigo_empresa: código da empresa detectada (ex: "CSC", "RBC") ou None
            - metodo: como foi detectada ("cnpj", "nome_exato", "nome_parcial") ou None
            - lista_matches: todos os matches encontrados para debug
        """
        if not texto:
            return None, None, []

        texto_limpo = self._limpar_texto(texto)
        texto_upper = texto_limpo.upper()
        matches_encontrados = []

        # 1) Primeiro tenta por CNPJ (mais confiável)
        for cnpj_digits, _start, _end, raw in iter_cnpjs_in_text(texto_limpo):
            if cnpj_digits in self.cadastro:
                payload = self.cadastro[cnpj_digits]
                razao = payload.get("razao_social", "")
                codigo = empresa_codigo_from_razao(razao)
                matches_encontrados.append(f"CNPJ:{codigo}:{raw}")
                # Retorna imediatamente se achou CNPJ nosso
                return codigo, "cnpj", matches_encontrados

        # 2) Tenta por código exato (word boundary)
        codigos_contexto_seguro = []
        codigos_contexto_normal = []
        
        for codigo, _cnpjs in self.empresas_por_codigo.items():
            # Ignora códigos muito curtos ou stopwords
            if len(codigo) < 3 or codigo in self.STOPWORDS:
                continue

            # Busca como palavra completa
            pattern = rf'\b{re.escape(codigo)}\b'
            if re.search(pattern, texto_upper):
                # Verifica contexto
                em_contexto_seguro = self._aparece_em_contexto_seguro(codigo, texto_upper)
                em_contexto_ignorar = self._aparece_em_contexto_ignorar(codigo, texto_upper)
                
                if em_contexto_seguro:
                    matches_encontrados.append(f"CODIGO_EXATO:{codigo}:SEGURO")
                    codigos_contexto_seguro.append(codigo)
                elif not em_contexto_ignorar:
                    matches_encontrados.append(f"CODIGO_EXATO:{codigo}")
                    codigos_contexto_normal.append(codigo)
                else:
                    matches_encontrados.append(f"CODIGO_EXATO:{codigo}:IGNORADO")

        # Prioriza códigos em contexto seguro
        if len(codigos_contexto_seguro) == 1:
            return codigos_contexto_seguro[0], "nome_exato", matches_encontrados
        
        # Se há múltiplos seguros, pega o primeiro (geralmente o destinatário)
        if len(codigos_contexto_seguro) > 1:
            return codigos_contexto_seguro[0], "nome_exato", matches_encontrados
        
        # Se não tem seguros, usa normais (se único)
        if len(codigos_contexto_normal) == 1:
            return codigos_contexto_normal[0], "nome_exato", matches_encontrados

        # 3) Tenta por razão social parcial (mais arriscado)
        for _cnpj, payload in self.cadastro.items():
            razao = payload.get("razao_social", "")
            codigo = empresa_codigo_from_razao(razao)

            # Extrai palavras significativas da razão social
            palavras = re.findall(r'\b[A-Z]{3,}\b', razao.upper())
            palavras_uteis = [p for p in palavras if p not in self.STOPWORDS and len(p) >= 4]

            for palavra in palavras_uteis[:2]:  # Só as 2 primeiras palavras úteis
                if re.search(rf'\b{re.escape(palavra)}\b', texto_upper):
                    matches_encontrados.append(f"NOME_PARCIAL:{codigo}:{palavra}")

        # Se encontrou matches parciais únicos
        codigos_parciais = list(set(
            m.split(":")[1] for m in matches_encontrados if m.startswith("NOME_PARCIAL:")
        ))
        if len(codigos_parciais) == 1:
            return codigos_parciais[0], "nome_parcial", matches_encontrados

        # Não conseguiu determinar com certeza
        return None, None, matches_encontrados


# Instância singleton para uso direto
_detector_instance: Optional[EmpresaDetectorEmail] = None


def get_detector() -> EmpresaDetectorEmail:
    """Retorna instância singleton do detector."""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = EmpresaDetectorEmail()
    return _detector_instance


def find_empresa_in_email(texto: str) -> Tuple[Optional[str], Optional[str], List[str]]:
    """
    Função de conveniência para detectar empresa em texto de e-mail.
    
    Args:
        texto: Corpo do e-mail (texto plano ou HTML)
        
    Returns:
        Tupla (codigo_empresa, metodo, lista_matches)
    """
    return get_detector().detectar(texto)
