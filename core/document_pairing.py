"""
Serviço de Pareamento de Documentos NF↔Boleto.

Este módulo implementa a lógica para identificar e parear notas fiscais
com seus respectivos boletos dentro de um mesmo lote (email).

Casos tratados:
1. 1 NF + 1 Boleto → 1 par (caso simples)
2. N NFs + N Boletos pareados → N pares (múltiplas notas no mesmo email)
3. 1 NF + 0 Boletos → 1 par sem boleto (status CONFERIR)
4. 0 NF + 1 Boleto → 1 par sem NF (usa valor do boleto)
5. Documentos duplicados (XML + PDF da mesma nota) → agrupados em 1 par
6. Documentos auxiliares (demonstrativos, atestados) → ignorados no pareamento
7. NOVO: Pareamento forçado por lote (1 NF zerada + 1 Boleto no mesmo email)

Estratégias de pareamento (em ordem de prioridade):
1. Número da nota normalizado (ex: "202500000000119" e "2025/119" → mesmo par)
2. Valor exato quando não há número da nota identificável (caso Locaweb)
3. Agrupamento por valor para documentos duplicados
4. NOVO: Fallback por lote - força pareamento se sobrar 1 nota + 1 boleto

Status de pareamento:
- OK: Valores conferem dentro da tolerância
- DIVERGENTE: Valores diferentes mas pareados por número
- CONFERIR: Sem boleto para comparação
- PAREADO_FORCADO: Pareamento forçado por lote (mesma origem de e-mail)
- DIVERGENTE_VALOR: Pareamento forçado com valores divergentes
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

if TYPE_CHECKING:
    from core.batch_result import BatchResult


@dataclass
class DocumentPair:
    """
    Representa um par NF↔Boleto ou documento avulso.

    Cada par gera uma linha no relatório de lotes.

    Attributes:
        pair_id: Identificador único do par (batch_id + sufixo)
        batch_id: ID do lote original
        numero_nota: Número da nota (chave de pareamento)
        valor_nf: Valor da nota fiscal
        valor_boleto: Valor do boleto (0 se não houver)
        vencimento: Data de vencimento
        fornecedor: Nome do fornecedor
        cnpj_fornecedor: CNPJ do fornecedor
        status: Status de conciliação (OK/DIVERGENTE/CONFERIR)
        divergencia: Descrição da divergência
        diferenca: Diferença de valores
        documentos_nf: Lista de documentos de nota (NFSE, DANFE, OUTRO)
        documentos_boleto: Lista de boletos
        email_subject: Assunto do email (contexto)
        email_sender: Remetente do email (contexto)
        source_folder: Pasta de origem
    """
    pair_id: str
    batch_id: str
    numero_nota: Optional[str] = None
    valor_nf: float = 0.0
    valor_boleto: float = 0.0
    vencimento: Optional[str] = None
    fornecedor: Optional[str] = None
    cnpj_fornecedor: Optional[str] = None
    data_emissao: Optional[str] = None
    status: str = "CONFERIR"
    divergencia: Optional[str] = None
    diferenca: float = 0.0
    documentos_nf: List[str] = field(default_factory=list)
    documentos_boleto: List[str] = field(default_factory=list)
    email_subject: Optional[str] = None
    email_sender: Optional[str] = None
    email_date: Optional[str] = None  # Data de recebimento do email (ISO format)
    source_folder: Optional[str] = None

    # Empresa (CSC, RBC, MASTER, etc.)
    empresa: Optional[str] = None

    # Contadores para compatibilidade com relatório
    total_documents: int = 0
    total_errors: int = 0
    danfes: int = 0
    boletos: int = 0
    nfses: int = 0
    outros: int = 0
    avisos: int = 0

    # Flag para indicar pareamento forçado
    pareamento_forcado: bool = False

    def to_summary(self) -> Dict[str, Any]:
        """
        Converte o par para dicionário de resumo (formato do relatório de lotes).

        Returns:
            Dicionário compatível com o formato esperado pelo relatório
        """
        return {
            'batch_id': self.pair_id,
            'data': self.email_date,  # Data do email (não data de processamento)
            'status_conciliacao': self.status,
            'divergencia': self.divergencia,
            'diferenca_valor': self.diferenca,
            'fornecedor': self.fornecedor,
            'vencimento': self.vencimento,
            'numero_nota': self.numero_nota,
            'valor_compra': self.valor_nf,
            'valor_boleto': self.valor_boleto,
            'total_documents': self.total_documents,
            'total_errors': self.total_errors,
            'danfes': self.danfes,
            'boletos': self.boletos,
            'nfses': self.nfses,
            'outros': self.outros,
            'avisos': self.avisos,
            'email_subject': self.email_subject,
            'email_sender': self.email_sender,
            'empresa': self.empresa,
            'source_folder': self.source_folder,
        }


class DocumentPairingService:
    """
    Serviço para parear documentos NF↔Boleto dentro de um lote.

    Identifica pares por número da nota ou valor, gerando
    uma estrutura que permite separar múltiplas notas do mesmo email.

    Trata corretamente:
    - Documentos duplicados (XML + PDF da mesma nota)
    - Números de nota em formatos diferentes (202500000000119 vs 2025/119)
    - Documentos auxiliares (demonstrativos, atestados)
    """

    # Tolerância para comparação de valores (em reais)
    TOLERANCIA_VALOR = 0.01

    # Padrões para extrair número da nota do nome do arquivo
    PATTERNS_NUMERO_NOTA = [
        # NF 2025.119.pdf, NF 2025-119.pdf, NF 2025/119.pdf
        r'NF[_\s\-]*(\d{4}[\.\/\-]\d+)',
        # NF 119.pdf, NF-119.pdf
        r'NF[_\s\-]*(\d+)',
        # nfse_202500000000119.xml
        r'nfse[_\-]*(\d+)',
        # Nota_fiscal_123.pdf
        r'[Nn]ota[_\s\-]*[Ff]iscal[_\s\-]*(\d+)',
        # BOLETO NF 2025.119.pdf
        r'BOLETO[_\s\-]*NF[_\s\-]*(\d{4}[\.\/\-]\d+)',
        r'BOLETO[_\s\-]*NF[_\s\-]*(\d+)',
    ]

    # Palavras que indicam documentos auxiliares (não são notas fiscais)
    # Esses documentos serão ignorados no pareamento
    AUXILIAR_KEYWORDS = [
        'demonstrativo', 'atestado', 'recibo', 'comprovante',
        'declaracao', 'declaração', 'termo', 'contrato',
        'recs', 'recebimento',  # Recibos de entrega
    ]

    def pair_documents(self, batch: 'BatchResult') -> List[DocumentPair]:
        """
        Analisa o lote e retorna lista de pares NF↔Boleto.

        Implementa pareamento flexível com fallback por lote:
        - Se sobrar 1 nota (mesmo zerada) e 1 boleto, força pareamento
        - Marca como PAREADO_FORCADO ou DIVERGENTE_VALOR

        Args:
            batch: Resultado do processamento em lote

        Returns:
            Lista de DocumentPair, um para cada par identificado
        """
        import logging
        logger = logging.getLogger(__name__)
        from core.models import BoletoData, DanfeData, InvoiceData, OtherDocumentData

        # Separa documentos por tipo
        notas_raw: List[Tuple[Optional[str], float, Any]] = []  # (numero_nota, valor, documento)
        boletos_raw: List[Tuple[Optional[str], float, Any]] = []  # (numero_ref, valor, documento)

        # Coleta notas (NFSE, DANFE) - AGORA ACEITA VALOR ZERO TAMBÉM
        for doc in batch.documents:
            if isinstance(doc, (InvoiceData, DanfeData)):
                # Verifica se é documento auxiliar (demonstrativo, etc)
                if self._is_documento_auxiliar(doc):
                    continue
                numero = self._extract_numero_nota(doc)
                valor = doc.valor_total or 0.0
                # Mudança: aceita notas com valor 0 para pareamento por lote
                notas_raw.append((numero, valor, doc))
            elif isinstance(doc, OtherDocumentData):
                # Outros documentos: verifica se é auxiliar
                is_aux = self._is_documento_auxiliar(doc)
                if not is_aux:
                    valor = doc.valor_total or 0.0
                    numero = self._extract_numero_nota(doc)
                    notas_raw.append((numero, valor, doc))
                    logger.debug(f"OutrosDocumento incluído: arquivo={doc.arquivo_origem}, valor={valor}, numero={numero}")
                else:
                    logger.debug(f"OutrosDocumento ignorado (auxiliar): arquivo={doc.arquivo_origem}, valor={doc.valor_total if hasattr(doc, 'valor_total') else 'N/A'}")
            elif isinstance(doc, BoletoData):
                numero = self._extract_numero_boleto(doc)
                valor = doc.valor_documento or 0.0
                if valor > 0:
                    boletos_raw.append((numero, valor, doc))

        # Se não há notas nem boletos, retorna par vazio
        if not notas_raw and not boletos_raw:
            return [self._create_empty_pair(batch)]

        # NOVO: Tenta pareamento forçado por lote ANTES do agrupamento
        # Se temos exatamente 1 nota e 1 boleto no mesmo lote, força o pareamento
        forced_pair = self._try_forced_pairing(notas_raw, boletos_raw, batch)
        if forced_pair:
            self._update_document_counts(forced_pair, batch)
            return forced_pair

        # Agrupa documentos duplicados (mesmo valor = provavelmente mesma nota)
        # Filtra notas com valor > 0 para agrupamento normal
        notas_com_valor = [(n, v, d) for n, v, d in notas_raw if v > 0]
        notas_agrupadas = self._agrupar_por_valor_e_numero(notas_com_valor) if notas_com_valor else {}
        boletos_agrupados = self._agrupar_boletos(boletos_raw)

        # Pareia notas com boletos
        pairs = self._parear_notas_boletos(notas_agrupadas, boletos_agrupados, batch)

        # NOVO: Se tem boletos órfãos e notas zeradas, tenta pareamento forçado
        if not pairs or self._has_orphan_documents(pairs, notas_raw, boletos_raw):
            forced = self._try_forced_pairing_orphans(pairs, notas_raw, boletos_raw, batch)
            if forced:
                pairs = forced

        # Se não tem pares, cria par com tudo
        if not pairs:
            pairs = self._create_fallback_pair(notas_raw, boletos_raw, batch)

        # Atualiza contadores de documentos em cada par
        self._update_document_counts(pairs, batch)

        return pairs

    def _try_forced_pairing(
        self,
        notas: List[Tuple[Optional[str], float, Any]],
        boletos: List[Tuple[Optional[str], float, Any]],
        batch: 'BatchResult'
    ) -> Optional[List[DocumentPair]]:
        """
        Tenta pareamento forçado por lote.

        Condição: 1 nota COM VALOR ZERO + 1 boleto = força pareamento.
        Útil para e-mails onde a NF veio como link e o boleto como PDF.

        IMPORTANTE: Só força pareamento quando a nota tem valor 0.
        Se a nota tem valor > 0, deixa o pareamento normal decidir.

        Returns:
            Lista com 1 DocumentPair se forçado, None caso contrário
        """
        # Condição: exatamente 1 nota e 1 boleto
        if len(notas) != 1 or len(boletos) != 1:
            return None

        numero_nota, valor_nf, doc_nota = notas[0]
        numero_bol, valor_boleto, doc_boleto = boletos[0]

        # Se valores conferem, não precisa forçar - pareamento normal funciona
        if abs(valor_nf - valor_boleto) <= self.TOLERANCIA_VALOR and valor_nf > 0:
            return None

        # MUDANÇA: Só força pareamento se a nota tem valor ZERO
        # Se nota tem valor > 0, deixa o pareamento normal decidir (mesmo divergente)
        if valor_nf > 0:
            return None

        # Pareamento forçado: nota sem valor, usa valor do boleto como referência
        status = "PAREADO_FORCADO"
        divergencia = f"Nota sem valor (R$ 0,00) pareada com boleto (R$ {valor_boleto:.2f}) por lote"

        # Extrai dados do boleto como principal (mais confiável)
        fornecedor = getattr(doc_boleto, 'fornecedor_nome', None) or getattr(doc_nota, 'fornecedor_nome', None)
        vencimento = getattr(doc_boleto, 'vencimento', None) or getattr(doc_nota, 'vencimento', None)
        data_emissao = getattr(doc_nota, 'data_emissao', None) or getattr(doc_boleto, 'data_emissao', None)

        # Usa número da nota ou referência do boleto
        numero_final = numero_nota or numero_bol

        # Calcula diferença
        diferenca = valor_nf - valor_boleto if valor_nf > 0 else -valor_boleto

        # Identifica empresa
        empresa = self._extract_empresa(batch, [doc_nota, doc_boleto])

        pair = DocumentPair(
            pair_id=batch.batch_id,
            batch_id=batch.batch_id,
            numero_nota=numero_final,
            valor_nf=valor_nf,
            valor_boleto=valor_boleto,
            vencimento=vencimento,
            fornecedor=self._normalize_fornecedor(fornecedor) if fornecedor else None,
            cnpj_fornecedor=getattr(doc_boleto, 'cnpj_beneficiario', None) or getattr(doc_nota, 'cnpj_prestador', None),
            data_emissao=data_emissao,
            status=status,
            divergencia=divergencia,
            diferenca=diferenca,
            documentos_nf=[getattr(doc_nota, 'arquivo_origem', '')],
            documentos_boleto=[getattr(doc_boleto, 'arquivo_origem', '')],
            email_subject=batch.email_subject,
            email_sender=batch.email_sender,
            email_date=batch.email_date,
            source_folder=batch.source_folder,
            empresa=empresa,
            pareamento_forcado=True,
        )

        return [pair]

    def _has_orphan_documents(
        self,
        pairs: List[DocumentPair],
        notas: List[Tuple[Optional[str], float, Any]],
        boletos: List[Tuple[Optional[str], float, Any]]
    ) -> bool:
        """
        Verifica se há documentos órfãos (não pareados).
        """
        # Conta documentos nos pares
        docs_nf_pareados = sum(len(p.documentos_nf) for p in pairs)
        docs_bol_pareados = sum(len(p.documentos_boleto) for p in pairs)

        # Verifica se há órfãos
        return docs_nf_pareados < len(notas) or docs_bol_pareados < len(boletos)

    def _try_forced_pairing_orphans(
        self,
        pairs: List[DocumentPair],
        notas: List[Tuple[Optional[str], float, Any]],
        boletos: List[Tuple[Optional[str], float, Any]],
        batch: 'BatchResult'
    ) -> Optional[List[DocumentPair]]:
        """
        Tenta parear documentos órfãos de forma forçada.

        Cenário: 1 nota sem valor + 1 boleto órfão → força pareamento
        """
        # Identifica notas zeradas
        notas_zeradas = [(n, v, d) for n, v, d in notas if v == 0]

        # Identifica boletos órfãos (não estão em nenhum par)
        arquivos_boleto_pareados = set()
        for pair in pairs:
            arquivos_boleto_pareados.update(pair.documentos_boleto)

        boletos_orfaos = [
            (n, v, d) for n, v, d in boletos
            if getattr(d, 'arquivo_origem', '') not in arquivos_boleto_pareados
        ]

        # Se tem exatamente 1 nota zerada e 1 boleto órfão, força
        if len(notas_zeradas) == 1 and len(boletos_orfaos) == 1:
            # Remove pares existentes que tenham a nota zerada ou boleto órfão
            novo_pair = self._try_forced_pairing(notas_zeradas, boletos_orfaos, batch)
            if novo_pair:
                # Mantém outros pares válidos e adiciona o forçado
                outros_pares = [
                    p for p in pairs
                    if p.valor_nf > 0 and p.valor_boleto > 0
                ]
                return outros_pares + novo_pair

        return None

    def _extract_empresa(self, batch: 'BatchResult', docs: List[Any]) -> Optional[str]:
        """
        Extrai código da empresa dos documentos ou do batch.
        """
        # Tenta do correlation_result
        if batch.correlation_result:
            empresa = getattr(batch.correlation_result, 'empresa', None)
            if empresa:
                return empresa

        # Tenta dos documentos
        for doc in docs:
            empresa = getattr(doc, 'empresa', None)
            if empresa:
                return empresa

        return None

    def _is_documento_auxiliar(self, doc: Any) -> bool:
        """
        Verifica se o documento é auxiliar (demonstrativo, atestado, etc).

        Documentos auxiliares não devem ser tratados como notas fiscais.
        """
        import logging
        logger = logging.getLogger(__name__)

        arquivo = (getattr(doc, 'arquivo_origem', '') or '').lower()
        texto = (getattr(doc, 'texto_bruto', '') or '').lower()[:500]
        fornecedor = (getattr(doc, 'fornecedor_nome', '') or '').lower()

        # 1. Verifica se é atestado/declaração (mesmo se tiver valor)
        if fornecedor.startswith('atestamos') or fornecedor.startswith('declaramos'):
            logger.debug(f"Documento é auxiliar: fornecedor '{fornecedor}' começa com atestamos/declaramos")
            return True

        if 'atestamos' in texto[:200] or 'declaramos' in texto[:200]:
            logger.debug(f"Documento é auxiliar: texto contém atestamos/declaramos")
            return True

        # 2. Documentos com valor total positivo não são considerados auxiliares
        # (a menos que sejam atestados - já tratado acima)
        if hasattr(doc, 'valor_total') and doc.valor_total and doc.valor_total > 0:
            logger.debug(f"Documento NÃO é auxiliar: valor_total positivo (R$ {doc.valor_total})")
            return False

        # 3. Verifica no nome do arquivo por palavras-chave auxiliares
        for keyword in self.AUXILIAR_KEYWORDS:
            if keyword in arquivo:
                logger.debug(f"Documento é auxiliar: keyword '{keyword}' encontrado em arquivo '{arquivo}'")
                return True

        # 4. Verifica se é um demonstrativo (arquivo que contém "demonstrativo" no nome)
        if 'demonstrativo' in arquivo:
            logger.debug(f"Documento é auxiliar: arquivo contém 'demonstrativo'")
            return True

        logger.debug(f"Documento NÃO é auxiliar: nenhum critério atendido")
        return False

    def _agrupar_por_valor_e_numero(
        self,
        notas: List[Tuple[Optional[str], float, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Agrupa notas por valor e número normalizado.

        Documentos com mesmo valor são candidatos a serem duplicatas.
        Usamos o número da nota normalizado como chave final.

        Returns:
            Dict com chave = numero_normalizado, valor = {valor, docs, numero_original}
        """
        grupos: Dict[str, Dict[str, Any]] = {}

        for numero, valor, doc in notas:
            # Extrai sufixo numérico para normalização
            numero_norm = self._normalizar_numero_nota(numero) if numero else None

            # Tenta encontrar grupo existente com mesmo valor ou número similar
            grupo_encontrado = None

            for key, grupo in grupos.items():
                # Mesmo valor com tolerância?
                mesmo_valor = abs(grupo['valor'] - valor) <= self.TOLERANCIA_VALOR

                # Número similar? (um contém o outro ou são equivalentes)
                numero_similar = False
                if numero_norm and grupo.get('numero_norm'):
                    numero_similar = self._numeros_equivalentes(numero_norm, grupo['numero_norm'])

                if mesmo_valor or numero_similar:
                    grupo_encontrado = key
                    break

            if grupo_encontrado:
                # Adiciona ao grupo existente
                grupos[grupo_encontrado]['docs'].append(doc)
                # Prefere número mais curto/limpo como principal
                if numero and (not grupos[grupo_encontrado]['numero'] or
                              len(numero) < len(grupos[grupo_encontrado]['numero'])):
                    grupos[grupo_encontrado]['numero'] = numero
                    grupos[grupo_encontrado]['numero_norm'] = numero_norm
            else:
                # Cria novo grupo
                key = numero_norm or f"valor_{valor}"
                grupos[key] = {
                    'valor': valor,
                    'numero': numero,
                    'numero_norm': numero_norm,
                    'docs': [doc]
                }

        return grupos

    def _agrupar_boletos(
        self,
        boletos: List[Tuple[Optional[str], float, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Agrupa boletos por número/referência.
        """
        grupos: Dict[str, Dict[str, Any]] = {}

        for numero, valor, doc in boletos:
            numero_norm = self._normalizar_numero_nota(numero) if numero else None

            # Tenta encontrar grupo existente
            grupo_encontrado = None
            for key, grupo in grupos.items():
                if numero_norm and grupo.get('numero_norm'):
                    if self._numeros_equivalentes(numero_norm, grupo['numero_norm']):
                        grupo_encontrado = key
                        break

            if grupo_encontrado:
                grupos[grupo_encontrado]['docs'].append(doc)
                grupos[grupo_encontrado]['valor'] += valor
            else:
                key = numero_norm or f"boleto_{valor}"
                grupos[key] = {
                    'valor': valor,
                    'numero': numero,
                    'numero_norm': numero_norm,
                    'docs': [doc]
                }

        return grupos

    def _normalizar_numero_nota(self, numero: str) -> str:
        """
        Normaliza número da nota extraindo apenas os dígitos significativos.

        Exemplos:
        - "202500000000119" → "119"
        - "2025/119" → "119"
        - "2025.119" → "119"
        - "NF-119" → "119"
        """
        if not numero:
            return ""

        numero = str(numero).strip()

        # Remove prefixos comuns
        numero = re.sub(r'^(NF|NFSE|NFE|NOTA)[_\s\-]*', '', numero, flags=re.IGNORECASE)

        # Se tem formato ano/numero ou ano.numero, extrai só o número
        match = re.search(r'(\d{4})[\.\/\-](\d+)$', numero)
        if match:
            return match.group(2).lstrip('0') or '0'

        # Se é número longo (tipo 202500000000119), extrai sufixo significativo
        if numero.isdigit() and len(numero) > 8:
            # Remove zeros à esquerda e prefixo de ano (2025...)
            sufixo = numero.lstrip('0')
            # Se começa com ano (2025, 2024, etc), remove
            if len(sufixo) >= 4 and sufixo[:4].isdigit():
                ano = int(sufixo[:4])
                if 2020 <= ano <= 2030:
                    sufixo = sufixo[4:].lstrip('0') or '0'
            return sufixo

        # Caso simples: remove zeros à esquerda
        if numero.isdigit():
            return numero.lstrip('0') or '0'

        return numero

    def _numeros_equivalentes(self, num1: str, num2: str) -> bool:
        """
        Verifica se dois números de nota são equivalentes.

        Considera equivalentes se:
        - São iguais
        - Um é sufixo do outro (119 e 202500000000119)
        - Diferem apenas em zeros à esquerda
        """
        if not num1 or not num2:
            return False

        # Igualdade direta
        if num1 == num2:
            return True

        # Normaliza ambos
        n1 = num1.lstrip('0') or '0'
        n2 = num2.lstrip('0') or '0'

        if n1 == n2:
            return True

        # Verifica se um é sufixo do outro
        if n1.endswith(n2) or n2.endswith(n1):
            return True

        return False

    def _parear_notas_boletos(
        self,
        notas: Dict[str, Dict[str, Any]],
        boletos: Dict[str, Dict[str, Any]],
        batch: 'BatchResult'
    ) -> List[DocumentPair]:
        """
        Pareia grupos de notas com grupos de boletos.
        """
        pairs = []
        boletos_usados: Set[str] = set()

        for _nota_key, nota_grupo in notas.items():
            valor_nf = nota_grupo['valor']
            numero_nota = nota_grupo['numero']
            numero_norm = nota_grupo.get('numero_norm', '')
            docs_nf = nota_grupo['docs']

            # Procura boleto correspondente
            boleto_match = None
            boleto_key_match = None

            for bol_key, bol_grupo in boletos.items():
                if bol_key in boletos_usados:
                    continue

                bol_numero_norm = bol_grupo.get('numero_norm', '')

                # Tenta parear por número
                if numero_norm and bol_numero_norm:
                    if self._numeros_equivalentes(numero_norm, bol_numero_norm):
                        boleto_match = bol_grupo
                        boleto_key_match = bol_key
                        break

                # Tenta parear por valor
                if abs(valor_nf - bol_grupo['valor']) <= self.TOLERANCIA_VALOR:
                    boleto_match = bol_grupo
                    boleto_key_match = bol_key
                    break

            if boleto_match and boleto_key_match:
                boletos_usados.add(boleto_key_match)

            # Fallback: se nota não tem número, usa o número do boleto
            numero_final = numero_nota
            if not numero_final and boleto_match:
                numero_final = boleto_match.get('numero')

            # Cria o par
            suffix = f"_{numero_final}" if numero_final and len(notas) > 1 else ""
            pair = self._create_pair(
                batch=batch,
                numero_nota=numero_final,
                valor_nf=valor_nf,
                valor_boleto=boleto_match['valor'] if boleto_match else 0.0,
                docs_nf=docs_nf,
                docs_boleto=boleto_match['docs'] if boleto_match else [],
                suffix=suffix
            )
            pairs.append(pair)

        # Boletos órfãos (sem nota correspondente)
        for bol_key, bol_grupo in boletos.items():
            if bol_key not in boletos_usados:
                pair = self._create_pair(
                    batch=batch,
                    numero_nota=bol_grupo['numero'],
                    valor_nf=0.0,
                    valor_boleto=bol_grupo['valor'],
                    docs_nf=[],
                    docs_boleto=bol_grupo['docs'],
                    suffix=f"_bol_{bol_grupo['numero']}" if bol_grupo['numero'] else "_bol"
                )
                pairs.append(pair)

        return pairs

    def _create_fallback_pair(
        self,
        notas_raw: List[Tuple[Optional[str], float, Any]],
        boletos_raw: List[Tuple[Optional[str], float, Any]],
        batch: 'BatchResult'
    ) -> List[DocumentPair]:
        """
        Cria par de fallback quando o pareamento normal falha.
        """
        # Pega o maior valor de nota como principal
        valor_nf = max((n[1] for n in notas_raw), default=0.0)
        valor_boleto = sum(b[1] for b in boletos_raw)

        numero = None
        for num, _, _doc in notas_raw:
            if num:
                numero = num
                break

        pair = self._create_pair(
            batch=batch,
            numero_nota=numero,
            valor_nf=valor_nf,
            valor_boleto=valor_boleto,
            docs_nf=[n[2] for n in notas_raw],
            docs_boleto=[b[2] for b in boletos_raw],
            suffix=""
        )

        return [pair]

    def _extract_numero_nota(self, doc: Any) -> Optional[str]:
        """
        Extrai número da nota do documento.

        Prioriza:
        1. Campo numero_nota do documento
        2. Campo numero_documento (para OtherDocumentData como faturas EMC)
        3. Número extraído do nome do arquivo
        """
        # Tenta campo numero_nota
        numero = getattr(doc, 'numero_nota', None)
        if numero:
            return str(numero)

        # Tenta campo numero_documento (usado por OtherDocumentData)
        numero_doc = getattr(doc, 'numero_documento', None)
        if numero_doc:
            return str(numero_doc)

        # Tenta extrair do nome do arquivo
        arquivo = getattr(doc, 'arquivo_origem', '')
        return self._extract_numero_from_filename(arquivo)

    def _extract_numero_boleto(self, doc: Any) -> Optional[str]:
        """
        Extrai número de referência do boleto.

        Prioriza:
        1. Número extraído do nome do arquivo (mais confiável quando tem "NF XXXX")
        2. Campo numero_documento
        3. Campo referencia_nfse (pode estar errado em alguns casos)
        """
        arquivo = getattr(doc, 'arquivo_origem', '')

        # Prioridade 1: Número no nome do arquivo (ex: "BOLETO NF 2025.122.pdf")
        # Este é o mais confiável porque vem do nome original do arquivo
        numero_arquivo = self._extract_numero_from_filename(arquivo)
        if numero_arquivo:
            return numero_arquivo

        # Prioridade 2: numero_documento
        numero = getattr(doc, 'numero_documento', None)
        if numero:
            return str(numero)

        # Prioridade 3: referencia_nfse (fallback - pode estar errado)
        ref = getattr(doc, 'referencia_nfse', None)
        if ref:
            return str(ref)

        return None

    def _extract_numero_from_filename(self, filename: str) -> Optional[str]:
        """
        Extrai número da nota do nome do arquivo.

        Exemplos:
        - "02_NF 2025.119.pdf" → "2025.119"
        - "03_BOLETO NF 2025.119.pdf" → "2025.119"
        - "nfse_202500000000119.xml" → "202500000000119"
        """
        if not filename:
            return None

        for pattern in self.PATTERNS_NUMERO_NOTA:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def _create_empty_pair(self, batch: 'BatchResult') -> DocumentPair:
        """
        Cria par vazio para lotes sem documentos processáveis.
        """
        return DocumentPair(
            pair_id=batch.batch_id,
            batch_id=batch.batch_id,
            email_subject=batch.email_subject,
            email_sender=batch.email_sender,
            email_date=batch.email_date,
            source_folder=batch.source_folder,
            status="CONFERIR",
            divergencia="Nenhum documento com valor encontrado",
        )

    def _create_pair(
        self,
        batch: 'BatchResult',
        numero_nota: Optional[str],
        valor_nf: float,
        valor_boleto: float,
        docs_nf: List[Any],
        docs_boleto: List[Any],
        suffix: str = ""
    ) -> DocumentPair:
        """
        Cria um DocumentPair com todos os dados calculados.
        """
        # Gera ID do par
        pair_id = f"{batch.batch_id}{suffix}"

        # Extrai dados do primeiro documento de nota
        fornecedor = None
        cnpj = None
        vencimento = None
        data_emissao = None
        empresa = None

        for doc in docs_nf:
            if not fornecedor:
                fornecedor = getattr(doc, 'fornecedor_nome', None)
            if not cnpj:
                cnpj = getattr(doc, 'cnpj_prestador', None) or getattr(doc, 'cnpj_emitente', None)
            if not vencimento:
                vencimento = getattr(doc, 'vencimento', None)
            if not data_emissao:
                data_emissao = getattr(doc, 'data_emissao', None)
            if not empresa:
                empresa = getattr(doc, 'empresa', None)

        # Fallback para dados do boleto
        for doc in docs_boleto:
            if not fornecedor:
                fornecedor = getattr(doc, 'fornecedor_nome', None)
            if not cnpj:
                cnpj = getattr(doc, 'cnpj_beneficiario', None)
            if not vencimento:
                vencimento = getattr(doc, 'vencimento', None)
            if not data_emissao:
                data_emissao = getattr(doc, 'data_emissao', None)
            if not empresa:
                empresa = getattr(doc, 'empresa', None)

        # Calcula status e divergência
        diferenca = round(valor_nf - valor_boleto, 2)
        status, divergencia = self._calculate_status(valor_nf, valor_boleto, diferenca, docs_boleto)

        # Adiciona avisos do correlation_result (documento administrativo e valor genérico)
        if batch.correlation_result and batch.correlation_result.divergencia:
            import re

            # Aviso de documento administrativo
            if "POSSÍVEL DOCUMENTO ADMINISTRATIVO" in batch.correlation_result.divergencia:
                admin_match = re.search(r'\[POSSÍVEL DOCUMENTO ADMINISTRATIVO[^\]]*\]', batch.correlation_result.divergencia)
                if admin_match:
                    admin_aviso = admin_match.group(0)
                    if divergencia:
                        if admin_aviso not in divergencia:
                            divergencia += f" {admin_aviso}"
                    else:
                        divergencia = admin_aviso

            # Aviso de valor extraído de documento genérico
            if "VALOR EXTRAÍDO DE DOCUMENTO GENÉRICO" in batch.correlation_result.divergencia:
                outros_match = re.search(r'\[VALOR EXTRAÍDO DE DOCUMENTO GENÉRICO[^\]]*\]', batch.correlation_result.divergencia)
                if outros_match:
                    outros_aviso = outros_match.group(0)
                    if divergencia:
                        if outros_aviso not in divergencia:
                            divergencia += f" {outros_aviso}"
                    else:
                        divergencia = outros_aviso

        # Adiciona alerta de vencimento se não encontrado (mas deixa vencimento vazio)
        if not vencimento:
            aviso = " [VENCIMENTO NÃO ENCONTRADO - verificar urgente]"
            if divergencia:
                divergencia += aviso
            else:
                divergencia = aviso.strip()
            # Não define fallback - deixa vencimento vazio/nulo

        # Normaliza fornecedor
        if fornecedor:
            fornecedor = self._normalize_fornecedor(fornecedor)

        return DocumentPair(
            pair_id=pair_id,
            batch_id=batch.batch_id,
            numero_nota=numero_nota,
            valor_nf=valor_nf,
            valor_boleto=valor_boleto,
            vencimento=vencimento,
            fornecedor=fornecedor,
            cnpj_fornecedor=cnpj,
            data_emissao=data_emissao,
            status=status,
            divergencia=divergencia,
            diferenca=diferenca,
            documentos_nf=[getattr(d, 'arquivo_origem', '') for d in docs_nf],
            documentos_boleto=[getattr(d, 'arquivo_origem', '') for d in docs_boleto],
            email_subject=batch.email_subject,
            email_sender=batch.email_sender,
            email_date=batch.email_date,
            source_folder=batch.source_folder,
            empresa=empresa,
        )

    def _calculate_status(
        self,
        valor_nf: float,
        valor_boleto: float,
        diferenca: float,
        docs_boleto: List[Any],
        pareamento_forcado: bool = False
    ) -> Tuple[str, Optional[str]]:
        """
        Calcula status de conciliação e mensagem de divergência.

        Status possíveis:
        - CONCILIADO: NF e boleto encontrados, valores conferem
        - DIVERGENTE: AMBOS têm valor > 0 mas valores conflitam
        - CONFERIR: Só tem NF (sem boleto) OU só tem boleto (sem NF com valor)
        - PAREADO_FORCADO: Pareamento forçado por lote (nota sem valor)
        - DIVERGENTE_VALOR: Pareamento forçado com valores divergentes

        Returns:
            Tupla (status, divergencia)
        """
        has_boleto = len(docs_boleto) > 0 and valor_boleto > 0
        has_nf = valor_nf > 0

        if has_boleto and has_nf:
            # Ambos têm valor - compara para ver se conferem
            if abs(diferenca) <= self.TOLERANCIA_VALOR:
                return "CONCILIADO", None
            elif pareamento_forcado:
                return "DIVERGENTE_VALOR", (
                    f"Pareamento forçado | Valor NF: R$ {valor_nf:.2f} | "
                    f"Valor boleto: R$ {valor_boleto:.2f} | "
                    f"Diferença: R$ {diferenca:.2f}"
                )
            else:
                return "DIVERGENTE", (
                    f"Valor compra: R$ {valor_nf:.2f} | "
                    f"Valor boleto: R$ {valor_boleto:.2f} | "
                    f"Diferença: R$ {diferenca:.2f}"
                )
        elif has_boleto and not has_nf:
            # Só tem boleto (sem NF ou NF com valor 0) - precisa conferir
            if pareamento_forcado:
                return "PAREADO_FORCADO", (
                    f"Nota sem valor pareada com boleto por lote | "
                    f"Valor boleto: R$ {valor_boleto:.2f}"
                )
            else:
                return "CONFERIR", f"Conferir boleto (R$ {valor_boleto:.2f}) - NF sem valor encontrada"
        else:
            # Só tem NF (sem boleto) - precisa conferir
            return "CONFERIR", f"Conferir valor (R$ {valor_nf:.2f}) - sem boleto para comparação"

    def _normalize_fornecedor(self, fornecedor: str) -> str:
        """
        Normaliza nome do fornecedor removendo sujeiras comuns.
        """
        if not fornecedor:
            return ""

        # Remove quebras de linha e espaços extras
        normalized = " ".join(fornecedor.split())

        # Remove prefixos comuns indesejados
        prefixos_remover = ["CNPJ", "CPF", "RAZÃO SOCIAL", "RAZAO SOCIAL", "NOME:", "Beneficiário"]
        for prefixo in prefixos_remover:
            if normalized.upper().startswith(prefixo.upper()):
                normalized = normalized[len(prefixo):].strip()
                if normalized.startswith(":") or normalized.startswith("-"):
                    normalized = normalized[1:].strip()

        return normalized.strip()

    def _update_document_counts(self, pairs: List[DocumentPair], batch: 'BatchResult') -> None:
        """
        Atualiza contadores de documentos em cada par.

        Distribui os contadores proporcionalmente ou atribui ao primeiro par.
        """


        # Conta tipos no batch
        total_danfes = len(batch.danfes)
        total_boletos = len(batch.boletos)
        total_nfses = len(batch.nfses)
        total_outros = len(batch.outros)
        total_avisos = len(batch.avisos)
        total_errors = batch.total_errors

        if len(pairs) == 1:
            # Único par recebe todos os contadores
            pairs[0].danfes = total_danfes
            pairs[0].boletos = total_boletos
            pairs[0].nfses = total_nfses
            pairs[0].outros = total_outros
            pairs[0].avisos = total_avisos
            pairs[0].total_errors = total_errors
            pairs[0].total_documents = len(pairs[0].documentos_nf) + len(pairs[0].documentos_boleto)
        else:
            # Múltiplos pares: conta documentos específicos de cada par
            for pair in pairs:
                pair.danfes = sum(1 for f in pair.documentos_nf if any(
                    f == getattr(d, 'arquivo_origem', '') for d in batch.danfes
                ))
                pair.nfses = sum(1 for f in pair.documentos_nf if any(
                    f == getattr(d, 'arquivo_origem', '') for d in batch.nfses
                ))
                pair.outros = sum(1 for f in pair.documentos_nf if any(
                    f == getattr(d, 'arquivo_origem', '') for d in batch.outros
                ))
                pair.boletos = len(pair.documentos_boleto)
                pair.avisos = 0  # Avisos ficam no primeiro par
                pair.total_documents = len(pair.documentos_nf) + len(pair.documentos_boleto)
                pair.total_errors = 0  # Erros ficam no primeiro par

            # Primeiro par recebe avisos e erros
            if pairs:
                pairs[0].avisos = total_avisos
                pairs[0].total_errors = total_errors


def pair_batch_documents(batch: 'BatchResult') -> List[DocumentPair]:
    """
    Função de conveniência para parear documentos de um lote.

    Args:
        batch: Resultado do processamento em lote

    Returns:
        Lista de DocumentPair
    """
    service = DocumentPairingService()
    return service.pair_documents(batch)
