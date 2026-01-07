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

Estratégias de pareamento (em ordem de prioridade):
1. Número da nota normalizado (ex: "202500000000119" e "2025/119" → mesmo par)
2. Valor exato quando não há número da nota identificável (caso Locaweb)
3. Agrupamento por valor para documentos duplicados
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

if TYPE_CHECKING:
    from core.batch_result import BatchResult
    from core.models import (
        BoletoData,
        DanfeData,
        DocumentData,
        InvoiceData,
        OtherDocumentData,
    )


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
    source_folder: Optional[str] = None

    # Contadores para compatibilidade com relatório
    total_documents: int = 0
    total_errors: int = 0
    danfes: int = 0
    boletos: int = 0
    nfses: int = 0
    outros: int = 0
    avisos: int = 0

    def to_summary(self) -> Dict[str, Any]:
        """
        Converte o par para dicionário de resumo (formato do relatório de lotes).

        Returns:
            Dicionário compatível com o formato esperado pelo relatório
        """
        return {
            'batch_id': self.pair_id,
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

        Args:
            batch: Resultado do processamento em lote

        Returns:
            Lista de DocumentPair, um para cada par identificado
        """
        from core.models import BoletoData, DanfeData, InvoiceData, OtherDocumentData

        # Separa documentos por tipo
        notas_raw: List[Tuple[Optional[str], float, Any]] = []  # (numero_nota, valor, documento)
        boletos_raw: List[Tuple[Optional[str], float, Any]] = []  # (numero_ref, valor, documento)

        # Coleta notas (NFSE, DANFE)
        for doc in batch.documents:
            if isinstance(doc, (InvoiceData, DanfeData)):
                # Verifica se é documento auxiliar (demonstrativo, etc)
                if self._is_documento_auxiliar(doc):
                    continue
                numero = self._extract_numero_nota(doc)
                valor = doc.valor_total or 0.0
                if valor > 0:  # Só considera documentos com valor
                    notas_raw.append((numero, valor, doc))
            elif isinstance(doc, OtherDocumentData):
                # Outros documentos: verifica se é auxiliar
                if not self._is_documento_auxiliar(doc):
                    valor = doc.valor_total or 0.0
                    if valor > 0:
                        numero = self._extract_numero_nota(doc)
                        notas_raw.append((numero, valor, doc))
            elif isinstance(doc, BoletoData):
                numero = self._extract_numero_boleto(doc)
                valor = doc.valor_documento or 0.0
                if valor > 0:
                    boletos_raw.append((numero, valor, doc))

        # Se não há notas nem boletos, retorna par vazio
        if not notas_raw and not boletos_raw:
            return [self._create_empty_pair(batch)]

        # Agrupa documentos duplicados (mesmo valor = provavelmente mesma nota)
        notas_agrupadas = self._agrupar_por_valor_e_numero(notas_raw)
        boletos_agrupados = self._agrupar_boletos(boletos_raw)

        # Pareia notas com boletos
        pairs = self._parear_notas_boletos(notas_agrupadas, boletos_agrupados, batch)

        # Se não tem pares, cria par com tudo
        if not pairs:
            pairs = self._create_fallback_pair(notas_raw, boletos_raw, batch)

        # Atualiza contadores de documentos em cada par
        self._update_document_counts(pairs, batch)

        return pairs

    def _is_documento_auxiliar(self, doc: Any) -> bool:
        """
        Verifica se o documento é auxiliar (demonstrativo, atestado, etc).

        Documentos auxiliares não devem ser tratados como notas fiscais.
        """
        arquivo = (getattr(doc, 'arquivo_origem', '') or '').lower()
        texto = (getattr(doc, 'texto_bruto', '') or '').lower()[:500]
        fornecedor = (getattr(doc, 'fornecedor_nome', '') or '').lower()

        # Verifica no nome do arquivo
        for keyword in self.AUXILIAR_KEYWORDS:
            if keyword in arquivo:
                return True

        # Verifica se fornecedor começa com "ATESTAMOS" ou similar
        if fornecedor.startswith('atestamos') or fornecedor.startswith('declaramos'):
            return True

        # Verifica no texto bruto
        if 'atestamos' in texto[:200] or 'declaramos' in texto[:200]:
            return True

        # Verifica se é um demonstrativo (arquivo que contém "demonstrativo" no nome)
        if 'demonstrativo' in arquivo:
            return True

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

        for nota_key, nota_grupo in notas.items():
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
        valor_nf = max((n[1] for n in notas), default=0.0)
        valor_boleto = sum(b[1] for b in boletos)

        numero = None
        for num, _, doc in notas:
            if num:
                numero = num
                break

        pair = self._create_pair(
            batch=batch,
            numero_nota=numero,
            valor_nf=valor_nf,
            valor_boleto=valor_boleto,
            docs_nf=[n[2] for n in notas],
            docs_boleto=[b[2] for b in boletos],
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

        for doc in docs_nf:
            if not fornecedor:
                fornecedor = getattr(doc, 'fornecedor_nome', None)
            if not cnpj:
                cnpj = getattr(doc, 'cnpj_prestador', None) or getattr(doc, 'cnpj_emitente', None)
            if not vencimento:
                vencimento = getattr(doc, 'vencimento', None)
            if not data_emissao:
                data_emissao = getattr(doc, 'data_emissao', None)

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

        # Calcula status e divergência
        diferenca = round(valor_nf - valor_boleto, 2)
        status, divergencia = self._calculate_status(valor_nf, valor_boleto, diferenca, docs_boleto)

        # Adiciona alerta de vencimento se não encontrado
        if not vencimento:
            aviso = " [VENCIMENTO NÃO ENCONTRADO - verificar urgente]"
            if divergencia:
                divergencia += aviso
            else:
                divergencia = aviso.strip()
            # Define data atual como vencimento de alerta
            from datetime import date
            vencimento = date.today().isoformat()

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
            source_folder=batch.source_folder,
        )

    def _calculate_status(
        self,
        valor_nf: float,
        valor_boleto: float,
        diferenca: float,
        docs_boleto: List[Any]
    ) -> Tuple[str, Optional[str]]:
        """
        Calcula status de conciliação e mensagem de divergência.

        Returns:
            Tupla (status, divergencia)
        """
        has_boleto = len(docs_boleto) > 0 and valor_boleto > 0

        if has_boleto:
            if abs(diferenca) <= self.TOLERANCIA_VALOR:
                return "OK", None
            else:
                return "DIVERGENTE", (
                    f"Valor compra: R$ {valor_nf:.2f} | "
                    f"Valor boleto: R$ {valor_boleto:.2f} | "
                    f"Diferença: R$ {diferenca:.2f}"
                )
        else:
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
        from core.models import (
            BoletoData,
            DanfeData,
            EmailAvisoData,
            InvoiceData,
            OtherDocumentData,
        )

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
