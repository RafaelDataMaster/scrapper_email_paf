import re
import unicodedata
from datetime import datetime
from typing import Dict, Any, Optional
from core.extractors import BaseExtractor, register_extractor
from config.bancos import NOMES_BANCOS

@register_extractor
class BoletoExtractor(BaseExtractor):
    """
    Extrator especializado em Boletos Bancários.
    
    Identifica e extrai campos específicos de boletos:
    - Linha digitável (código de barras)
    - CNPJ do beneficiário
    - Valor do documento
    - Data de vencimento
    - Número do documento
    - Possível referência à NFSe
    """
    
    @classmethod
    def can_handle(cls, text: str) -> bool:
        """
        Verifica se o documento é um boleto.
        
        Critérios:
        - Presença de "Linha Digitável" ou código de barras padrão
        - Palavras-chave: "Beneficiário", "Vencimento", "Valor do Documento"
        - Ausência de "NFS-e" ou "Nota Fiscal de Serviço"
        """
        def _strip_accents(value: str) -> str:
            if not value:
                return ""
            normalized = unicodedata.normalize('NFKD', value)
            return ''.join(ch for ch in normalized if not unicodedata.combining(ch))

        # Normaliza para ficar tolerante a acentos/extrações estranhas do PDF.
        # Além disso, alguns PDFs quebram palavras no meio (ex: "Bene\nficiário").
        # Para a classificação, usamos também uma versão compactada (só A-Z0-9).
        text_upper = (text or "").upper()
        text_norm_upper = _strip_accents(text_upper)
        text_compact = re.sub(r"[^A-Z0-9]+", "", text_norm_upper)
        
        # Indicadores positivos de boleto
        # Observação: alguns PDFs (especialmente com OCR/híbrido) podem corromper letras
        # em palavras-chave (ex: BENEFICIÁRIO → BENEFICI?RIO, NÚMERO → N?MERO). Por isso,
        # incluímos também alguns *stems* (BENEFICI, NOSSO) para a classificação.
        boleto_keywords = [
            'LINHA DIGITÁVEL',
            'LINHA DIGITAVEL',
            'BENEFICI',
            'BENEFICIÁRIO',
            'BENEFICIARIO',
            'VENCIMENTO',
            'VALOR DO DOCUMENTO',
            'NOSSO',
            'NOSSO NÚMERO',
            'NOSSO NUMERO',
            'CÓDIGO DE BARRAS',
            'CODIGO DE BARRAS',
            'AGÊNCIA/CÓDIGO',
            'AGENCIA/CODIGO',
            'CEDENTE'
        ]
        
        # Indicadores negativos (se é NFSe, não é boleto puro)
        nfse_keywords = ['NFS-E', 'NOTA FISCAL DE SERVIÇO ELETRÔNICA', 'NOTA FISCAL DE SERVICO ELETRONICA', 'PREFEITURA']
        
        def _kw_compact(kw: str) -> str:
            return re.sub(r"[^A-Z0-9]+", "", _strip_accents((kw or "").upper()))

        boleto_score = sum(1 for kw in boleto_keywords if _kw_compact(kw) and _kw_compact(kw) in text_compact)
        nfse_score = sum(1 for kw in nfse_keywords if _kw_compact(kw) and _kw_compact(kw) in text_compact)
        
        # Também verifica padrão de linha digitável (5 blocos numéricos)
        linha_digitavel = re.search(r'\d{5}[\.\s]\d{5}\s+\d{5}[\.\s]\d{6}\s+\d{5}[\.\s]\d{6}', text)
        
        # É boleto se:
        # - Tem alta pontuação de palavras-chave de boleto OU linha digitável
        # - E não tem muitas palavras de NFSe
        # Garante retorno booleano (evita retornar match object)
        has_linha_digitavel = bool(linha_digitavel)
        return bool((boleto_score >= 3 or has_linha_digitavel) and nfse_score < 2)

    def extract(self, text: str) -> Dict[str, Any]:
        """
        Extrai dados estruturados do boleto.
        
        Campos Core PAF (Prioridade Alta):
        - Razão Social do beneficiário (fornecedor_nome)
        - Dados bancários normalizados (banco_nome, agencia, conta_corrente)
        """
        data = {}
        data['tipo_documento'] = 'BOLETO'
        
        # Campos básicos (já existentes)
        data['cnpj_beneficiario'] = self._extract_cnpj_beneficiario(text)
        data['valor_documento'] = self._extract_valor(text)
        data['vencimento'] = self._extract_vencimento(text)
        data['numero_documento'] = self._extract_numero_documento(text)
        data['data_emissao'] = self._extract_data_documento(text)
        data['linha_digitavel'] = self._extract_linha_digitavel(text)
        data['nosso_numero'] = self._extract_nosso_numero(text)
        data['referencia_nfse'] = self._extract_referencia_nfse(text)
        
        # Campos Core PAF (Prioridade Alta)
        data['fornecedor_nome'] = self._extract_fornecedor_nome(text)
        data['empresa'] = self._extract_pagador_nome(text)
        data['cnpj_pagador'] = self._extract_cnpj_pagador(text)
        data['banco_nome'] = self._extract_banco_nome(text, data.get('linha_digitavel'))
        data['agencia'] = self._extract_agencia(text)
        data['conta_corrente'] = self._extract_conta_corrente(text)
        
        return data

    def _extract_cnpj_pagador(self, text: str) -> Optional[str]:
        """Extrai CNPJ do pagador (quando houver) a partir de seções comuns."""
        if not text:
            return None

        # 1) Próximo a "Dados do Pagador" (1-8 linhas seguintes)
        lines = [ln.strip() for ln in (text or '').splitlines() if (ln or '').strip()]
        for i, ln in enumerate(lines):
            if re.search(r'(?i)\bDados\s+do\s+Pagador\b', ln):
                for j in range(i + 1, min(i + 9, len(lines))):
                    m = re.search(r'(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})', lines[j])
                    if m:
                        return m.group(1)

        # 2) Linha com "CPF/CNPJ" ou "CNPJ" junto do nome
        m = re.search(
            r'(?i)\b(?:CPF/CNPJ|CNPJ)\s*:?\s*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})',
            text,
        )
        if m:
            return m.group(1)

        return None

    def _normalize_entity_name(self, raw: str) -> str:
        name = (raw or '').strip()
        name = re.sub(r'\s+', ' ', name)
        # remove CNPJ/CPF e números soltos (ex: nro do documento na mesma linha)
        name = re.sub(r'\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b', ' ', name)
        name = re.sub(r'\b\d{3}\.\d{3}\.\d{3}-\d{2}\b', ' ', name)
        name = re.sub(r'\b\d+[\./]\d+\b', ' ', name)  # ex: 2025.122
        name = re.sub(r'\b\d{4,}\b', ' ', name)
        name = re.sub(r'\s+', ' ', name).strip(' -:;')
        return name.strip()

    def _looks_like_header_or_label(self, s: str) -> bool:
        if not s:
            return True
        s_up = s.upper()
        # Cabeçalhos/labels que frequentemente aparecem após "Beneficiário" e não são nome
        bad_tokens = [
            'VENCIMENTO',
            'VALOR DO DOCUMENTO',
            'COOPERATIVA',
            'CÓD.',
            'COD.',
            'CÓDIGO',
            'CARTEIRA',
            'ESPÉCIE',
            'ACEITE',
            'PROCESSAMENTO',
            'NOSSO NÚMERO',
            'NOSSO NUMERO',
            'AGÊNCIA',
            'AGENCIA',
            'CONTA',
        ]
        return any(t in s_up for t in bad_tokens)

    def _looks_like_currency_or_amount_line(self, s: str) -> bool:
        if not s:
            return False
        s_up = s.upper()
        if 'R$' in s_up:
            return True
        # Ex: "Real 1 14.338.304/0001-78 01/09/2025 352,08"
        if re.search(r"\bREAL\b", s_up) and re.search(r"\b\d{1,3}(?:\.\d{3})*,\d{2}\b", s):
            return True
        # Linhas tabulares com data+valor geralmente não são razão social
        if re.search(r"\b\d{2}/\d{2}/\d{4}\b", s) and re.search(r"\b\d{1,3}(?:\.\d{3})*,\d{2}\b", s):
            return True
        return False

    def _looks_like_linha_digitavel_line(self, s: str) -> bool:
        if not s:
            return False
        # padrão comum de linha digitável: 5+5 5+6 5+6
        if re.search(r"\d{5}[\.\s]\d{5}\s+\d{5}[\.\s]\d{6}\s+\d{5}[\.\s]\d{6}", s):
            return True
        # ou uma linha majoritariamente numérica longa
        digits = re.sub(r"\D+", "", s)
        if len(digits) >= 40 and len(digits) > (len(s) * 0.6):
            return True
        return False

    def _extract_name_before_cnpj_in_line(self, line: str, cnpj: str) -> Optional[str]:
        """Extrai um nome plausível imediatamente antes de um CNPJ em uma mesma linha."""
        if not line or not cnpj:
            return None
        idx = line.find(cnpj)
        if idx < 0:
            return None

        prefix = line[:idx]
        # remove eventual sufixo "- CNPJ" (muito comum antes do número)
        prefix = re.sub(r"(?i)[-–]?\s*CNPJ\s*$", " ", prefix).strip()
        # Remove cabeçalhos/labels frequentes que poluem o prefixo
        prefix = re.sub(
            r"(?i)\b(BENEFICI[ÁA]RIO|BENEFICIARIO|VENCIMENTO|VALOR\s+DO\s+DOCUMENTO|VALOR\s+DOCUMENTO|AG[EÊ]NCIA\s*/\s*C[ÓO]DIGO|AGENCIA\s*/\s*CODIGO|RECIBO\s+DE\s+ENTREGA|COMPROVANTE\s+DE\s+ENTREGA|PAGADOR|NOSSO\s+N[ÚU]MERO)\b",
            " ",
            prefix,
        )
        prefix = re.sub(r"\s+", " ", prefix).strip()
        # pega o último bloco de nome em caixa alta/normal
        m = re.search(r"([A-ZÀ-ÿ][A-ZÀ-ÿ\s&\.\-/]{5,160})\s*$", prefix)
        if not m:
            return None
        cand = self._normalize_entity_name(m.group(1))
        # precisa ter letras de verdade (evita capturar "A"/"A - CNPJ")
        if not re.search(r"[A-ZÀ-ÿ]", cand):
            return None
        if len(cand) >= 5 and not self._looks_like_header_or_label(cand):
            return cand
        return None

    def _format_name_with_cnpj(self, name: str, cnpj: str) -> str:
        name_clean = re.sub(r'\s+', ' ', (name or '').strip()).strip(' -')
        return f"{name_clean} - CNPJ {cnpj}".strip()

    def _extract_pagador_nome(self, text: str) -> Optional[str]:
        """Extrai o nome do pagador (EMPRESA) a partir de seções comuns do boleto."""
        if not text:
            return None

        lines = [ln.strip() for ln in (text or '').splitlines()]
        lines = [ln for ln in lines if ln]

        # 1) Seção "Dados do Pagador" → normalmente o nome aparece 1-3 linhas depois
        for i, ln in enumerate(lines):
            if re.search(r'(?i)\bDados\s+do\s+Pagador\b', ln):
                for j in range(i + 1, min(i + 6, len(lines))):
                    cand = lines[j]
                    if re.search(r'(?i)\bNome\s+do\s+pagador\b', cand):
                        continue
                    if re.search(r'(?i)\bEndere[cç]o\b|\bBairro\b|\bMunic[ií]pio\b|\bMensagem\b', cand):
                        break
                    # Se vier junto com número do documento, remove o sufixo numérico.
                    cand = re.sub(r'\s+\d{4}[\./-]\d+\b.*$', '', cand).strip()
                    cand = self._normalize_entity_name(cand)
                    if len(cand) >= 5 and not self._looks_like_header_or_label(cand):
                        return cand

        # 2) Linha explícita com label "Pagador" + CNPJ
        m = re.search(
            r'(?im)^\s*Pagador\b[^\n]*\n\s*([A-ZÀ-ÿ][A-ZÀ-ÿ\s&\.\-]{5,120})\s+\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b',
            text,
        )
        if m:
            cand = self._normalize_entity_name(m.group(1))
            if len(cand) >= 5 and not self._looks_like_header_or_label(cand):
                return cand

        # 3) Fallback: linhas contendo "CPF/CNPJ" ou "- <CNPJ>" (muito comum em PDFs como o da Locaweb)
        # Ex: "CSC GESTAO INTEGRADA S/A - 38.323.227/0001-40"
        # Ex: "CSC ... - CPF/CNPJ: 38.323..."
        best: Optional[str] = None
        best_score = -999
        for ln in lines:
            ln_up = ln.upper()

            mline = re.search(
                r'^(.*?)(?:\s*[-–]\s*(?:CPF/CNPJ\s*:?\s*)?)\s*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})\b',
                ln,
                flags=re.IGNORECASE,
            )
            if not mline:
                continue
            name_raw = mline.group(1).strip()
            if not name_raw:
                continue

            cand = self._normalize_entity_name(name_raw)
            if len(cand) < 5:
                continue
            if self._looks_like_header_or_label(cand):
                continue
            if self._looks_like_currency_or_amount_line(ln):
                continue

            score = 0
            if 'CSC' in ln_up:
                score += 5
            if 'PAGADOR' in ln_up:
                score += 1

            if score > best_score:
                best_score = score
                best = cand

        if best:
            return best

        return None

    def _extract_data_documento(self, text: str) -> Optional[str]:
        """Extrai a data do documento/emissão (para preencher EMISSÃO no MVP)."""
        if not text:
            return None

        # 1) "Data do documento" - muitas vezes a data está na linha seguinte
        lines = [ln.rstrip() for ln in (text or '').splitlines()]
        for i, ln in enumerate(lines):
            if re.search(r'(?i)\bData\s+do\s+documento\b', ln):
                # tenta mesma linha
                m_same = re.search(r'(\d{2}/\d{2}/\d{4})', ln)
                if m_same:
                    try:
                        dt = datetime.strptime(m_same.group(1), '%d/%m/%Y')
                        return dt.strftime('%Y-%m-%d')
                    except ValueError:
                        pass
                # tenta próximas linhas
                for j in range(i + 1, min(i + 4, len(lines))):
                    m = re.search(r'\b(\d{2}/\d{2}/\d{4})\b', lines[j])
                    if m:
                        try:
                            dt = datetime.strptime(m.group(1), '%d/%m/%Y')
                            return dt.strftime('%Y-%m-%d')
                        except ValueError:
                            continue

        # 2) "Data de Emissão" (pode estar longe do valor, usa DOTALL)
        m = re.search(r'(?is)Data\s+de\s+Emiss[aã]o[\s\S]{0,120}?(\d{2}/\d{2}/\d{4})', text)
        if m:
            try:
                dt = datetime.strptime(m.group(1), '%d/%m/%Y')
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                pass

        # 3) Regra operacional (boletos): se não houver label explícito,
        # usa a MENOR data presente no documento (ex: data de geração do título).
        dates = []
        for d in re.findall(r'\b(\d{2}/\d{2}/\d{4})\b', text):
            try:
                dt = datetime.strptime(d, '%d/%m/%Y')
                if 2020 <= dt.year <= 2035:
                    dates.append(dt)
            except ValueError:
                continue
        if dates:
            return min(dates).strftime('%Y-%m-%d')

        return None

    def _extract_cnpj_beneficiario(self, text: str) -> Optional[str]:
        """
        Extrai CNPJ do beneficiário (quem está recebendo o pagamento).
        Busca próximo a palavras como "Beneficiário" ou "Cedente".
        """
        # Padrão: Procura CNPJ após "Beneficiário" ou "Cedente"
        patterns = [
            r'(?i)Benefici[aá]rio.*?(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})',
            r'(?i)Cedente.*?(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})',
            r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}'  # Fallback: qualquer CNPJ
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1) if match.lastindex else match.group(0)
        return None

    def _extract_valor(self, text: str) -> float:
        """
        Extrai o valor do documento do boleto.
        
        Implementa 3 níveis de fallback para extração robusta:
        1. Padrões específicos (com/sem R$)
        2. Heurística do maior valor monetário encontrado
        3. Extração do valor da linha digitável (10 últimos dígitos em centavos)
        
        Returns:
            float: Valor do documento em reais ou 0.0 se não encontrado.
        """
        # Padrão: Procura "Valor do Documento" ou valores monetários
        # Aceita formatos com ou sem R$
        patterns = [
            # Com R$ explícito
            r'(?i)Valor\s+do\s+Documento\s*[:\s]*R\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
            r'(?i)Valor\s+Nominal\s*[:\s]*R\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
            r'(?i)Valor\s+Cobrado\s*[:\s]*R\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
            
            # Sem R$ explícito (valor logo após o rótulo)
            # Útil para boletos com layout tabular
            r'(?i)Valor\s+do\s+Documento[\s\n]+(\d{1,3}(?:\.\d{3})*,\d{2})\b',
            r'(?i)Valor\s+Nominal[\s\n]+(\d{1,3}(?:\.\d{3})*,\d{2})\b',
            
            # Genérico com R$
            r'(?i)Valor\s*[:\s]*R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                valor_str = match.group(1)
                valor = float(valor_str.replace('.', '').replace(',', '.'))
                if valor > 0:
                    return valor
        
        # Fallback Nível 2: Heurística do maior valor monetário encontrado
        # Útil quando o texto está "amassado" e os rótulos estão longe dos valores
        todos_valores = re.findall(r'R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})', text)
        
        if todos_valores:
            valores_float = [
                float(v.replace('.', '').replace(',', '.'))
                for v in todos_valores
            ]
            if valores_float:
                maior_valor = max(valores_float)
                if maior_valor > 0:
                    return maior_valor
        
        # Fallback Nível 3: Extrai valor da linha digitável
        # Formato padrão: últimos 14 dígitos contêm fator de vencimento (4) + valor (10)
        # Exemplo: 75691.31407 01130.051202 02685.970010 3 11690000625000
        #          11690000625000 → 1169 (fator) + 0000625000 (valor em centavos = R$ 6.250,00)
        linha_digitavel_match = re.search(
            r'\d{5}[\.\s]\d{5}\s+\d{5}[\.\s]\d{6}\s+\d{5}[\.\s]\d{6}\s+\d\s+(\d{4})(\d{10})',
            text
        )
        if linha_digitavel_match:
            # Segundo grupo: 10 dígitos do valor em centavos
            valor_centavos_str = linha_digitavel_match.group(2)
            try:
                valor_centavos = int(valor_centavos_str)
                valor = valor_centavos / 100.0
                if valor > 0:
                    return valor
            except ValueError:
                pass
        
        return 0.0

    def _extract_vencimento(self, text: str) -> Optional[str]:
        """
        Extrai a data de vencimento do boleto.
        
        Estratégia (ordem):
        1) Datas ancoradas em rótulos (mesma linha ou próximas linhas): "Vencimento" / "Data de Vencimento".
        2) Fallback: maior data encontrada no PDF, preferindo datas que NÃO estejam em contexto de
           "processamento"/"documento"/"emissão".
        """
        if not text:
            return None

        def parse_br_date(s: str) -> Optional[datetime]:
            try:
                dt = datetime.strptime(s, '%d/%m/%Y')
                # Evita datas muito fora do esperado (ajusta conforme necessário)
                if 2020 <= dt.year <= 2035:
                    return dt
            except ValueError:
                return None
            return None

        # 1) Âncoras explícitas no texto inteiro (quando a data vem na mesma linha)
        # Não retornamos no primeiro match: alguns PDFs trazem "DATA DE VENCIMENTO" em linhas
        # ligadas a "DATA DO PROCESSAMENTO" (falso positivo). Selecionamos por score.
        anchored_candidates: list[tuple[datetime, int]] = []
        anchored_patterns = [
            (re.compile(r'(?i)\bDATA\s+DE\s+VENCIMENTO\b[^\n\d]{0,60}(\d{2}/\d{2}/\d{4})'), 3),
            (re.compile(r'(?i)\bData\s+de\s+Vencimento\b[^\n\d]{0,60}(\d{2}/\d{2}/\d{4})'), 3),
            (re.compile(r'(?i)\bData\s+Vencimento\b[^\n\d]{0,60}(\d{2}/\d{2}/\d{4})'), 2),
            (re.compile(r'(?i)\bVencimento\b[^\n\d]{0,60}(\d{2}/\d{2}/\d{4})'), 1),
        ]

        for rx, base in anchored_patterns:
            for m in rx.finditer(text):
                dt = parse_br_date(m.group(1))
                if not dt:
                    continue
                window = text[max(0, m.start() - 140):min(len(text), m.end() + 80)].upper()
                score = base
                if 'DATA DO PROCESSAMENTO' in window or 'PROCESSAMENTO' in window:
                    score -= 4
                if 'NUMERO DO DOCUMENTO' in window or 'NÚMERO DO DOCUMENTO' in window:
                    score += 1
                if 'VALOR DO DOCUMENTO' in window:
                    score += 1
                anchored_candidates.append((dt, score))

        # 1b) Âncora por linhas: "Vencimento" pode estar sozinho (e a data vir na linha seguinte)
        lines = [ln.strip() for ln in text.splitlines()]
        lines = [ln for ln in lines if ln]
        candidates: list[tuple[datetime, int]] = []

        venc_label = re.compile(r'(?i)\bVencimento\b')
        date_re = re.compile(r'\b(\d{2}/\d{2}/\d{4})\b')

        for i, ln in enumerate(lines):
            matches = list(venc_label.finditer(ln))
            if not matches:
                continue

            ln_up = ln.upper()
            ctx_up = " ".join(lines[max(0, i - 1):min(len(lines), i + 2)]).upper()

            def base_score() -> int:
                score = 0
                if ln_up.strip() == 'VENCIMENTO':
                    score += 3
                if 'NUMERO DO DOCUMENTO' in ln_up or 'NÚMERO DO DOCUMENTO' in ln_up:
                    score += 2
                if 'VALOR DO DOCUMENTO' in ln_up:
                    score += 2
                # penaliza contextos que normalmente não representam vencimento real
                if 'DATA DO PROCESSAMENTO' in ctx_up or 'PROCESSAMENTO' in ctx_up:
                    score -= 3
                if 'DATA DO DOCUMENTO' in ctx_up or 'DATA DE EMISS' in ctx_up or 'EMISS' in ctx_up:
                    score -= 1
                return score

            # Caso em que a linha é só o label (muito comum em boletos)
            if date_re.search(ln) is None and len(ln) <= 30:
                for j in range(i + 1, min(i + 3, len(lines))):
                    m = date_re.search(lines[j])
                    if m:
                        dt = parse_br_date(m.group(1))
                        if dt:
                            score = base_score()
                            # bônus se a próxima linha começa com a data (layout tabular clássico)
                            if lines[j].lstrip().startswith(m.group(1)):
                                score += 2
                            candidates.append((dt, score))
                            break
                continue

            # Para cada ocorrência de 'Vencimento' na linha, pega a PRIMEIRA data logo depois
            for mlabel in matches:
                tail = ln[mlabel.end():mlabel.end() + 140]
                mdate = date_re.search(tail)
                if mdate:
                    dt = parse_br_date(mdate.group(1))
                    if dt:
                        candidates.append((dt, base_score()))

                # Se não achou na mesma linha, tenta a próxima linha (layout tabular)
                if not mdate:
                    for j in range(i + 1, min(i + 3, len(lines))):
                        m2 = date_re.search(lines[j])
                        if m2:
                            dt = parse_br_date(m2.group(1))
                            if dt:
                                score = base_score()
                                if lines[j].lstrip().startswith(m2.group(1)):
                                    score += 2
                                candidates.append((dt, score))
                                break

        if candidates:
            # Escolhe por score e, em empate, pela maior data.
            best_dt, _best_score = max(candidates, key=lambda x: (x[1], x[0]))
            return best_dt.strftime('%Y-%m-%d')

        if anchored_candidates:
            best_dt, _best_score = max(anchored_candidates, key=lambda x: (x[1], x[0]))
            return best_dt.strftime('%Y-%m-%d')

        # 2) Fallback: "maior data" do PDF, mas filtrando contextos que raramente são vencimento
        all_dates = []
        for m in re.finditer(r'\b(\d{2}/\d{2}/\d{4})\b', text):
            d = m.group(1)
            dt = parse_br_date(d)
            if not dt:
                continue
            ctx = text[max(0, m.start() - 60):min(len(text), m.end() + 60)].upper()
            all_dates.append((dt, ctx))

        if not all_dates:
            return None

        negative_ctx = (
            'PROCESSAMENTO',
            'DATA DO DOCUMENTO',
            'DATA DO PROCESSAMENTO',
            'DATA DE EMISS',
            'EMISS',
        )

        preferred = [dt for dt, ctx in all_dates if not any(tok in ctx for tok in negative_ctx)]
        pick = max(preferred) if preferred else max(dt for dt, _ in all_dates)
        return pick.strftime('%Y-%m-%d')

    def _extract_numero_documento(self, text: str) -> Optional[str]:
        """
        Extrai o número do documento/fatura referenciado no boleto.
        
        Comum em boletos de serviços (pode conter o número da NF).
        Evita capturar números muito curtos (1 dígito) que são genéricos.
        Aceita formatos: "123", "2025.122", "2/1", "NF-12345", etc.
        """
        patterns = [
            # 1. PRIORIDADE ALTA - Layout tabular com data: "Nº Documento ... data ... X/Y"
            # Comum em boletos VSP/Itaú onde data vem antes do número
            r'(?i)N.?\s*Documento.*?\d{2}/\d{2}/\d{4}\s+(\d+/\d+)',
            
            # 2-6. Padrões específicos com diferentes variações de "número"
            r'(?i)N[uú]mero\s+do\s+Documento\s*[:\s]*([0-9]+(?:\.[0-9]+)?)',  # Com ú ou u
            r'(?i)Numero\s+do\s+Documento\s*[:\s]*([0-9]+(?:\.[0-9]+)?)',  # Sem acento
            r'(?i)Num\.?\s*Documento\s*[:\s]*([0-9]+(?:\.[0-9]+)?)',
            r'(?i)N[ºº°]\s*Documento\s*[:\s]*([0-9]+(?:[/\.][0-9]+)?)',  # Aceita / ou .
            r'(?i)N\.\s*documento\s*[:\s]*([0-9]+(?:\.[0-9]+)?)',
            
            # 7. Busca "Número do Documento" seguido do valor na próxima linha
            r'(?i)N.mero\s+do\s+Documento\s+.+?\n\s+.+?\s+([0-9]+\.[0-9]+)',  # Qualquer char em "Número"
            
            # 8. Padrão contextual: palavra "documento" seguida de número (NÃO data)
            # Regex negativa para evitar capturar datas DD/MM/YYYY
            r'(?i)documento\s+(?!\d{2}/\d{2}/\d{4})([0-9]+(?:\.[0-9]+)?)',
            
            # 9. Genérico: busca por padrão ano.número (ex: 2025.122)
            r'\b(20\d{2}\.\d+)\b'  # 2024.xxx, 2025.xxx, etc.
        ]
        
        for i, pattern in enumerate(patterns):
            # Padrão 0 (índice 0) precisa de re.DOTALL para atravessar linhas
            flags = re.DOTALL if i == 0 else 0
            match = re.search(pattern, text, flags)
            if match:
                numero = match.group(1).strip()
                # Valida: deve ter pelo menos 2 caracteres e não ser apenas "1"
                if len(numero) >= 2 or (len(numero) == 1 and numero != '1'):
                    return numero
        
        return None

    def _extract_linha_digitavel(self, text: str) -> Optional[str]:
        """
        Extrai a linha digitável do boleto (código de barras formatado).
        Formato padrão: 5 blocos numéricos separados por espaços/pontos.
        """
        # Formato completo: XXXXX.XXXXX XXXXX.XXXXXX XXXXX.XXXXXX X XXXXXXXXXXXXXX
        patterns = [
            r'(\d{5}[\.\s]\d{5}\s+\d{5}[\.\s]\d{6}\s+\d{5}[\.\s]\d{6}\s+\d\s+\d{14})',
            r'(\d{5}\.\d{5}\s+\d{5}\.\d{6}\s+\d{5}\.\d{6})'  # Formato mais curto
        ]
        
        text_cleaned = text.replace('\n', ' ')
        
        for pattern in patterns:
            match = re.search(pattern, text_cleaned)
            if match:
                return match.group(1).strip()
        
        return None

    def _extract_nosso_numero(self, text: str) -> Optional[str]:
        """
        Extrai o "Nosso Número" (identificação interna do banco).
        Formatos comuns: "12345", "12345-6", "109/00000507-1"
        """
        patterns = [
            # Formato bancário completo: XXX/XXXXXXX-X (ex: 109/00000507-1)
            # Padrão robusto: 2-3 dígitos / 7+ dígitos - 1 dígito
            # Evita capturar CNPJ que tem formato diferente
            r'(?i)Nosso\s+N.mero.*?(\d{2,3}/\d{7,}-\d+)',
            
            # Formato simples sem encoding específico
            r'(?i)Nosso\s+Numero.*?(\d{2,3}/\d{7,}-\d+)',
            
            # Fallback: qualquer sequência de dígitos com separadores
            r'(?i)Nosso\s+N[úu]mero\s*[:\s]*([\d\-/]+)',
            r'(?i)Nosso\s+Numero\s*[:\s]*([\d\-/]+)'
        ]
        
        for i, pattern in enumerate(patterns):
            # Primeiros 2 padrões precisam de DOTALL para atravessar linhas
            flags = re.DOTALL if i < 2 else 0
            match = re.search(pattern, text, flags)
            if match:
                numero = match.group(1).strip()
                # Validação: não deve ser parte de CNPJ (que tem pontos)
                if '.' not in numero or numero.count('/') == 1:
                    return numero
        
        # Fallback genérico: busca padrão XXX/XXXXXXXX-X sem label
        # Usado quando "Nosso Número" está como imagem ou ausente
        # Formato: 3 dígitos / 8 dígitos - 1 dígito (ex: 109/42150105-8)
        # Evita Agência/Conta que tem 4 dígitos ou espaços (ex: "2938 / 0053345-8")
        fallback_pattern = r'\b(\d{3}/\d{8}-\d)\b'
        match = re.search(fallback_pattern, text)
        if match:
            return match.group(1)
        
        return None

    def _extract_referencia_nfse(self, text: str) -> Optional[str]:
        """
        Tenta encontrar uma referência explícita a um número de NFSe no boleto.
        Alguns boletos incluem "Ref. NF 12345" ou similar.
        """
        patterns = [
            r'(?i)Ref\.?\s*NF[:\s-]*(\d+)',
            r'(?i)Refer[eê]ncia\s*NF[:\s-]*(\d+)',
            r'(?i)Nota\s+Fiscal\s*n?[º°]?\s*[:\s]*(\d+)',
            r'(?i)NF\s*[:\s-]*(\d+)',
            r'(?i)N\.?\s*F\.?\s*[:\s-]*(\d+)',
            r'(?i)NFSe\s*[:\s-]*(\d+)',
            r'(?i)NFS-e\s*[:\s-]*(\d+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        
        return None
    
    def _extract_fornecedor_nome(self, text: str) -> Optional[str]:
        """
        Extrai a Razão Social do beneficiário (fornecedor).
        
        Busca por texto após labels como "Beneficiário" ou "Cedente",
        ou logo após o CNPJ do beneficiário.
        
        Conformidade: Campo obrigatório para coluna FORNECEDOR da planilha PAF.
        
        Returns:
            str: Razão Social ou None se não encontrado
        """
        if not text:
            return None

        # 0) Caso "intermediador a serviço de <fornecedor> - CNPJ <cnpj>"
        # Ex: "Yapay a serviço de Locaweb S/A - CNPJ 02..."
        m = re.search(
            r'(?im)^\s*(.+?\ba\s+servi[cç]o\s+de\s+.+?)\s*[-–]\s*CNPJ\s*[:\-]?\s*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})\b',
            text,
        )
        if m:
            return self._format_name_with_cnpj(m.group(1), m.group(2))

        # 0b) Fallback: qualquer linha "<nome> - CNPJ <cnpj>" que não pareça ser o pagador
        best_line: Optional[str] = None
        best_score = -999
        for m2 in re.finditer(
            r'(?im)^\s*([^\n]{5,220}?)\s*[-–]\s*CNPJ\s*[:\-]?\s*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})\b',
            text,
        ):
            raw_name = m2.group(1).strip()
            cnpj = m2.group(2)
            raw_up = raw_name.upper()

            # evita pegar lixo como linha digitável
            if self._looks_like_linha_digitavel_line(raw_name):
                continue
            if not re.search(r"[A-ZÀ-ÿ]", raw_name):
                continue

            # ignora possíveis linhas do pagador
            if 'CSC' in raw_up:
                continue
            if self._looks_like_currency_or_amount_line(raw_name):
                continue

            score = 0
            if re.search(r'(?i)\bS/?A\b|\bLTDA\b', raw_name):
                score += 1
            if score > best_score:
                best_score = score
                best_line = self._format_name_with_cnpj(raw_name, cnpj)

        if best_line:
            return best_line

        # 1) Se já conseguimos achar o CNPJ do beneficiário, isso é o sinal mais confiável.
        # (executa DEPOIS do caso especial "a serviço de" para não retornar lixo tipo "A - CNPJ").
        cnpj_benef = self._extract_cnpj_beneficiario(text)
        if cnpj_benef:
            for ln in (text or '').splitlines():
                if cnpj_benef in ln:
                    cand = self._extract_name_before_cnpj_in_line(ln, cnpj_benef)
                    if cand:
                        return cand

        lines = [ln.strip() for ln in (text or '').splitlines()]
        lines = [ln for ln in lines if ln]

        # 1) Bloco "Beneficiário ..." (muitas vezes é cabeçalho) → pega próxima linha com nome+cnpj
        for i, ln in enumerate(lines):
            if re.search(r'(?i)\bBenefici[aá]rio\b', ln):
                # Caso comum: tudo vem na mesma linha, com cabeçalhos no começo.
                # Ex: "Beneficiário Vencimento Valor do Documento MAIS ... 18.363..."
                m_cnpj = re.search(r'(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})', ln)
                if m_cnpj:
                    cand_inline = self._extract_name_before_cnpj_in_line(ln, m_cnpj.group(1))
                    if cand_inline:
                        return cand_inline

                # tenta nome + CNPJ na mesma linha
                m_same = re.search(
                    r'([A-ZÀ-ÿ][A-ZÀ-ÿ\s&\.\-]{5,120})\s+\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b',
                    ln,
                )
                if m_same:
                    cand = self._normalize_entity_name(m_same.group(1))
                    if len(cand) >= 5 and not self._looks_like_header_or_label(cand):
                        return cand

                # tenta na(s) próxima(s) linhas
                for j in range(i + 1, min(i + 5, len(lines))):
                    next_ln = lines[j]
                    # interrompe se já entrou em seção de pagador/endereço
                    if re.search(r'(?i)\bDados\s+do\s+Pagador\b|\bPagador\b', next_ln):
                        break
                    m = re.search(
                        r'^\s*([A-ZÀ-ÿ][A-ZÀ-ÿ\s&\.\-]{5,120})\s+\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b',
                        next_ln,
                    )
                    if m:
                        cand = self._normalize_entity_name(m.group(1))
                        if len(cand) >= 5 and not self._looks_like_header_or_label(cand):
                            return cand

                    # Alguns PDFs trazem só o nome (sem CNPJ) logo após o cabeçalho.
                    cand2 = self._normalize_entity_name(next_ln)
                    if len(cand2) >= 8 and not self._looks_like_header_or_label(cand2) and not self._looks_like_currency_or_amount_line(next_ln):
                        # evita capturar linhas óbvias de endereço/UF/CEP
                        if not re.search(r'(?i)\bCEP\b|\bMG\b|\bSP\b|\bRJ\b|\bBAIRRO\b|\bAVENIDA\b|\bRUA\b', cand2):
                            return cand2

        # 2) "Beneficiário final <NOME> <CNPJ>" (bem comum em ficha de compensação)
        m = re.search(
            r'(?i)Benefici[aá]rio\s+final\s+([A-ZÀ-ÿ][A-ZÀ-ÿ\s&\.\-]{5,120})\s+\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b',
            text,
        )
        if m:
            cand = self._normalize_entity_name(m.group(1))
            if len(cand) >= 5 and not self._looks_like_header_or_label(cand):
                return cand
        
        # Fallback: busca texto após CNPJ do beneficiário
        cnpj_match = re.search(r'(?i)Benefici[aá]rio.*?(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})', text)
        if cnpj_match:
            start_pos = cnpj_match.end()
            text_after = text[start_pos:start_pos+100]
            nome_match = re.search(r'([A-ZÀÁÂÃÇÉÊÍÓÔÕÚ][A-Za-zÀ-ÿ\s&\.\-]{5,80})', text_after)
            if nome_match:
                nome = self._normalize_entity_name(nome_match.group(1))
                if len(nome) >= 5 and not self._looks_like_header_or_label(nome):
                    return nome
        
        return None
    
    def _extract_banco_nome(self, text: str, linha_digitavel: Optional[str]) -> Optional[str]:
        """
        Identifica o nome do banco emissor do boleto.
        
        Usa o código bancário (3 primeiros dígitos da linha digitável)
        para mapear para o nome oficial do banco.
        
        Fallback: Se código não estiver no mapeamento, retorna "BANCO_XXX".
        
        Args:
            text: Texto do boleto
            linha_digitavel: Linha digitável já extraída
            
        Returns:
            str: Nome do banco ou "BANCO_XXX" para códigos não mapeados
        """
        if linha_digitavel:
            # Extrai os 3 primeiros dígitos (código do banco)
            codigo_banco = linha_digitavel[:3]
            # Mapeia para nome oficial usando dicionário
            return NOMES_BANCOS.get(codigo_banco, f"BANCO_{codigo_banco}")
        
        # Fallback: busca código do banco no texto
        match = re.search(r'(?i)(?:Banco|C[oó]digo\s+Banco)[^\d]*(\d{3})', text)
        if match:
            codigo = match.group(1)
            return NOMES_BANCOS.get(codigo, f"BANCO_{codigo}")
        
        return None
    
    def _extract_agencia(self, text: str) -> Optional[str]:
        """
        Extrai o número da agência bancária normalizado.
        
        Normalização:
        - Remove espaços e pontos
        - Mantém formato "1234-5" (número-dígito verificador)
        - Se não houver dígito, retorna apenas o número
        
        Conformidade: Formato normalizado facilita integração futura com CNAB.
        
        Returns:
            str: Agência no formato "1234-5" ou None
        """
        patterns = [
            # Aceita formatos com pontos e espaços: "1.234 - 5"
            r'(?i)Ag[eê]ncia[^\d]*([\d\.\s]{2,15})\s*[-–]?\s*(\d)?',
            r'(?i)Ag[\.\s]*[:\s]*([\d\.\s]{2,15})\s*[-–]?\s*(\d)?',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                numero_raw = match.group(1).strip()
                digito = match.group(2) if match.lastindex and match.lastindex >= 2 else None

                # Remove tudo que não for dígito do número-base
                numero = re.sub(r'\D', '', numero_raw)

                if not numero:
                    continue
                
                # Formata com hífen se houver dígito
                if digito:
                    return f"{numero}-{digito}"
                return numero
        
        return None
    
    def _extract_conta_corrente(self, text: str) -> Optional[str]:
        """
        Extrai o número da conta corrente normalizado.
        
        Normalização:
        - Remove espaços e pontos
        - Mantém formato "123456-7" (número-dígito verificador)
        - Se não houver dígito, retorna apenas o número
        
        Returns:
            str: Conta corrente no formato "123456-7" ou None
        """
        patterns = [
            r'(?i)Conta\s+Corrente[^\d]*(\d{1,12})[\s\-]?(\d)?',
            r'(?i)C/?C[^\d]*(\d{1,12})[\s\-]?(\d)?',
            r'(?i)Conta[^\d]*(\d{1,12})[\s\-]?(\d)?',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                numero = match.group(1).strip()
                digito = match.group(2) if match.lastindex >= 2 else None
                
                # Remove pontos e espaços
                numero = numero.replace('.', '').replace(' ', '')
                
                # Valida tamanho mínimo (evita capturar IDs pequenos)
                if len(numero) < 4:
                    continue
                
                # Formata com hífen se houver dígito
                if digito:
                    return f"{numero}-{digito}"
                return numero
        
        return None
