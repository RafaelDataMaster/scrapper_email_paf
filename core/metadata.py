"""
Metadados de contexto para processamento em lote.

Este módulo define estruturas de dados para armazenar contexto
do e-mail (assunto, remetente, corpo) que enriquece a extração.

Inclui extração de:
- Links de NF-e de prefeituras (SP, RJ, etc.)
- Códigos de verificação/autenticação
- Números de nota fiscal da URL
- Nome do fornecedor do assunto do e-mail

Princípios SOLID aplicados:
- SRP: Classe focada apenas em metadados de e-mail/lote
- OCP: Extensível via herança sem modificar código existente
"""
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class EmailMetadata:
    """
    Metadados de contexto do e-mail original.

    Armazena informações que não estão no PDF mas são úteis para
    enriquecimento e fallback na extração de dados.

    Attributes:
        batch_id: Identificador único do lote (pasta)
        email_subject: Assunto do e-mail (usado para tabela MVP)
        email_sender_name: Nome do remetente (fallback para fornecedor)
        email_sender_address: Endereço de e-mail do remetente
        email_body_text: Corpo do e-mail (para buscar CNPJs/pedidos)
        received_date: Data de recebimento do e-mail (ISO format)
        attachments: Lista de nomes dos arquivos anexos
        created_at: Data de criação do metadata (ISO format)
    """
    batch_id: str
    email_subject: Optional[str] = None
    email_sender_name: Optional[str] = None
    email_sender_address: Optional[str] = None
    email_body_text: Optional[str] = None
    received_date: Optional[str] = None
    attachments: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().strftime('%Y-%m-%dT%H:%M:%S'))

    # Campos extras para extensibilidade
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário serializável."""
        return asdict(self)

    def to_json(self) -> str:
        """Serializa para JSON formatado."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def save(self, folder_path: Path) -> Path:
        """
        Salva metadata.json na pasta do lote.

        Args:
            folder_path: Caminho da pasta do lote

        Returns:
            Path do arquivo salvo
        """
        folder_path = Path(folder_path)
        folder_path.mkdir(parents=True, exist_ok=True)

        metadata_file = folder_path / "metadata.json"
        metadata_file.write_text(self.to_json(), encoding='utf-8')

        return metadata_file

    @classmethod
    def load(cls, folder_path: Path) -> Optional['EmailMetadata']:
        """
        Carrega metadata.json de uma pasta de lote.

        Args:
            folder_path: Caminho da pasta do lote

        Returns:
            EmailMetadata ou None se não existir
        """
        metadata_file = Path(folder_path) / "metadata.json"

        if not metadata_file.exists():
            return None

        try:
            data = json.loads(metadata_file.read_text(encoding='utf-8'))
            return cls(**data)
        except (json.JSONDecodeError, TypeError, KeyError):
            return None

    @classmethod
    def create_for_batch(
        cls,
        batch_id: str,
        subject: Optional[str] = None,
        sender_name: Optional[str] = None,
        sender_address: Optional[str] = None,
        body_text: Optional[str] = None,
        received_date: Optional[str] = None,
        attachments: Optional[List[str]] = None,
    ) -> 'EmailMetadata':
        """
        Factory method para criar metadata de um lote de e-mail.

        Args:
            batch_id: ID único do lote
            subject: Assunto do e-mail
            sender_name: Nome do remetente
            sender_address: E-mail do remetente
            body_text: Corpo do e-mail
            received_date: Data de recebimento
            attachments: Lista de anexos

        Returns:
            EmailMetadata configurado
        """
        return cls(
            batch_id=batch_id,
            email_subject=subject,
            email_sender_name=sender_name,
            email_sender_address=sender_address,
            email_body_text=body_text,
            received_date=received_date,
            attachments=attachments or [],
        )

    @classmethod
    def create_legacy(cls, batch_id: str, file_paths: List[str]) -> 'EmailMetadata':
        """
        Factory method para criar metadata simulado para PDFs legados.

        Usado pelo script de validação quando não há e-mail de origem
        (failed_cases_pdf com documentos antigos).

        Args:
            batch_id: ID do lote (geralmente nome da pasta)
            file_paths: Lista de caminhos dos arquivos

        Returns:
            EmailMetadata com campos mínimos preenchidos
        """
        return cls(
            batch_id=batch_id,
            attachments=[Path(p).name for p in file_paths],
            extra={'legacy_mode': True, 'source': 'failed_cases_pdf'}
        )

    def get_fallback_fornecedor(self) -> Optional[str]:
        """
        Retorna nome do remetente como fallback para fornecedor.

        Útil quando OCR falha ao extrair o nome do fornecedor.
        """
        return self.email_sender_name

    def extract_valor_from_body(self) -> float:
        """
        Extrai valor monetário do corpo do e-mail.

        Útil para e-mails onde a NF é apenas um link mas o valor
        está no corpo do e-mail (ex: Omie, prefeituras).

        Returns:
            Valor extraído (float) ou 0.0 se não encontrado
        """
        try:
            from extractors.email_body_extractor import EmailBodyExtractor

            extractor = EmailBodyExtractor()
            result = extractor.extract(
                body_text=self.email_body_text,
                subject=self.email_subject
            )

            return result.valor_total
        except ImportError:
            # Fallback se o extrator não estiver disponível
            return self._extract_valor_fallback()

    def _extract_valor_fallback(self) -> float:
        """
        Extração simples de valor (fallback).

        Usa regex básico para extrair valor R$ X.XXX,XX.
        """
        import re

        text = f"{self.email_subject or ''} {self.email_body_text or ''}"
        if not text.strip():
            return 0.0

        # Padrão simples: R$ 1.234,56
        pattern = r'R\$\s*([\d]{1,3}(?:\.[\d]{3})*,[\d]{2})'
        matches = re.findall(pattern, text)

        if not matches:
            return 0.0

        # Converte e retorna o maior valor encontrado
        valores = []
        for match in matches:
            try:
                valor_str = match.replace('.', '').replace(',', '.')
                valor = float(valor_str)
                if 0.01 <= valor <= 10_000_000:
                    valores.append(valor)
            except ValueError:
                continue

        return max(valores) if valores else 0.0

    def extract_vencimento_from_body(self) -> Optional[str]:
        """
        Extrai data de vencimento do corpo do e-mail.

        Returns:
            Data em formato ISO (YYYY-MM-DD) ou None
        """
        try:
            from extractors.email_body_extractor import EmailBodyExtractor

            extractor = EmailBodyExtractor()
            result = extractor.extract(
                body_text=self.email_body_text,
                subject=self.email_subject
            )

            return result.vencimento
        except ImportError:
            return None

    def extract_all_from_body(self) -> Dict[str, Any]:
        """
        Extrai todos os dados possíveis do corpo do e-mail.

        Usa o EmailBodyExtractor para extrair:
        - valor_total
        - vencimento
        - numero_nota
        - link_nfe
        - codigo_verificacao
        - fornecedor_nome

        Returns:
            Dicionário com todos os dados extraídos
        """
        try:
            from extractors.email_body_extractor import EmailBodyExtractor

            extractor = EmailBodyExtractor()
            result = extractor.extract(
                body_text=self.email_body_text,
                subject=self.email_subject
            )

            return result.to_dict()
        except ImportError:
            return {
                'valor_total': self._extract_valor_fallback(),
                'vencimento': None,
                'numero_nota': self.extract_numero_nota_from_context(),
                'link_nfe': self.extract_link_nfe_from_context(),
                'codigo_verificacao': self.extract_codigo_verificacao_from_body(),
                'fornecedor_nome': self.email_sender_name,
            }

    def extract_cnpj_from_body(self) -> Optional[str]:
        """
        Tenta extrair CNPJ do corpo do e-mail.

        Útil quando o PDF não contém CNPJ legível.

        Returns:
            CNPJ formatado ou None
        """
        import re

        if not self.email_body_text:
            return None

        # Padrão CNPJ: 00.000.000/0000-00
        pattern = r'\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b'
        match = re.search(pattern, self.email_body_text)

        return match.group(0) if match else None

    def extract_numero_pedido_from_context(self) -> Optional[str]:
        """
        Tenta extrair número de pedido do assunto ou corpo do e-mail.

        Returns:
            Número do pedido ou None
        """
        import re

        # Combina assunto e corpo para busca
        text = f"{self.email_subject or ''} {self.email_body_text or ''}"

        if not text.strip():
            return None

        # Padrões comuns de número de pedido
        patterns = [
            r'\b(?:PEDIDO|PC|PED)[:\s#]*(\d{4,10})\b',
            r'\b(?:ORDEM|OC)[:\s#]*(\d{4,10})\b',
            r'\bNR\.?\s*PEDIDO[:\s#]*(\d{4,10})\b',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def is_legacy(self) -> bool:
        """Verifica se este metadata é de modo legado (sem e-mail real)."""
        return self.extra.get('legacy_mode', False)

    def _normalize_date(self, date_str: str) -> Optional[str]:
        """
        Normaliza uma string de data para o formato DD/MM/YYYY.

        Aceita formatos:
        - DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY
        - DD/MM/YY, DD-MM-YY, DD.MM.YY

        Args:
            date_str: String com a data em formato variado

        Returns:
            Data formatada como DD/MM/YYYY ou None se inválida
        """
        import re

        if not date_str:
            return None

        # Remove espaços extras
        date_str = date_str.strip()

        # Padrão para capturar dia, mês e ano com diferentes separadores
        match = re.match(r'(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})', date_str)
        if not match:
            return None

        dia, mes, ano = match.groups()

        # Converte ano de 2 dígitos para 4 dígitos
        if len(ano) == 2:
            ano_int = int(ano)
            # Assume que anos 00-30 são 2000-2030, e 31-99 são 1931-1999
            if ano_int <= 30:
                ano = f"20{ano}"
            else:
                ano = f"19{ano}"

        # Valida dia e mês
        try:
            dia_int = int(dia)
            mes_int = int(mes)
            if not (1 <= dia_int <= 31 and 1 <= mes_int <= 12):
                return None
        except ValueError:
            return None

        # Formata com zeros à esquerda
        return f"{int(dia):02d}/{int(mes):02d}/{ano}"

    def extract_numero_nota_from_context(self) -> Optional[str]:
        """
        Tenta extrair número da nota/fatura do assunto ou corpo do e-mail.

        Procura por padrões como:
        - "Fatura 50446" ou "Fatura: 50446"
        - "NF 12345" ou "NF-e 12345" ou "NFe 12345"
        - "NFS-e 12345" ou "NFSe 12345"
        - "Nota Fiscal 12345"
        - "Nº: 50446" ou "Nº 50446"
        - "Número: 12345"
        - "2025/44" ou "2025-44" (padrão composto ano/sequencial)

        Returns:
            Número da nota/fatura ou None
        """
        import re

        # Prioriza assunto do e-mail, depois corpo
        sources = [
            (self.email_subject or '', 'subject'),
            (self.email_body_text or '', 'body')
        ]

        for text, source in sources:
            if not text.strip():
                continue

            # Remove URLs para evitar falsos positivos (ex: 2017-01 de URLs de imagem)
            text_clean = re.sub(r'https?://[^\s<>"]+', ' ', text)
            text_clean = re.sub(r'<[^>]+>', ' ', text_clean)  # Remove tags HTML
            # Remove padrões de nome de arquivo de imagem (ex: 2017-01-20-b.png)
            text_clean = re.sub(r'\b\d{4}-\d{2}-\d{2}[^/\s]*\.(png|jpg|jpeg|gif|bmp)\b', ' ', text_clean, flags=re.IGNORECASE)

            # Padrões de número de nota/fatura (ordem de prioridade)
            patterns = [
                # "Fatura 50446" ou "Fatura: 50446" ou "Fatura Nº 50446"
                r'\b[Ff]atura\s*(?:N[ºo°]\.?\s*)?[:\s]*(\d{3,10})\b',
                # "NF 12345" ou "NF-e 12345" ou "NFe 12345" ou "NF: 12345"
                r'\bNF(?:-?[Ee])?\s*[:\s]*(\d{3,15})\b',
                # "NFS-e 12345" ou "NFSe 12345" ou "NFS-e: 12345"
                r'\bNFS-?[Ee]\s*[:\s]*(\d{3,15})\b',
                # "Nota Fiscal 12345" ou "Nota Fiscal Nº 12345"
                r'\b[Nn]ota\s+[Ff]iscal\s*(?:N[ºo°]\.?\s*)?[:\s]*(\d{3,15})\b',
                # "Nº: 50446" ou "Nº 50446" ou "N°: 50446" ou "No: 50446"
                r'\bN[ºo°]\.?\s*[:\s]*(\d{3,10})\b',
                # "Número: 12345" ou "Numero: 12345"
                r'\b[Nn][úu]mero\s*[:\s]*(\d{3,10})\b',
                # "Documento 12345" ou "Doc. 12345"
                r'\b[Dd]oc(?:umento)?\.?\s*[:\s]*(\d{3,10})\b',
                # Padrão composto "Nota Fatura - 2025-44" (com contexto de nota/fatura)
                r'(?i)(?:nota|fatura|nf)[^\d]{0,10}(20\d{2}[/\-]\d{1,6})\b',
            ]

            for pattern in patterns:
                match = re.search(pattern, text_clean)
                if match:
                    numero = match.group(1)
                    # Valida que não é apenas um ano (ex: 2025)
                    if numero.isdigit() and len(numero) == 4 and numero.startswith('20'):
                        continue  # Provavelmente é só um ano, pula
                    return numero

        return None

    def extract_link_nfe_from_context(self) -> Optional[str]:
        """
        Extrai link de NF-e/verificação do corpo do e-mail.

        Prioriza links de prefeituras conhecidas:
        - nfe.prefeitura.sp.gov.br
        - notacarioca.rio.gov.br
        - Outros portais gov.br

        Returns:
            URL do link de NF-e ou None
        """
        import re

        if not self.email_body_text:
            return None

        text = self.email_body_text

        # Padrões de links de prefeituras (ordem de prioridade)
        patterns_prioritarios = [
            # Prefeitura SP - padrão com verificação
            r'(https?://nfe\.prefeitura\.sp\.gov\.br/contribuinte/notaprint\.aspx\?[^\s<>"\']+)',
            # Prefeitura SP - padrão simples
            r'(https?://nfe\.prefeitura\.sp\.gov\.br/nfe\.aspx\?[^\s<>"\']+)',
            # Nota Carioca RJ
            r'(https?://notacarioca\.rio\.gov\.br/nfse\.aspx\?[^\s<>"\']+)',
            # Qualquer prefeitura gov.br com nf/nfe
            r'(https?://[^\s]*\.gov\.br/[^\s]*(?:nf|nfse|nota)[^\s<>"\']*)',
            # ISSNet, Ginfes, Betha (sistemas de NFS-e)
            r'(https?://[^\s]*(?:issnet|ginfes|betha)[^\s]*\.com\.br[^\s<>"\']+)',
            # Omie - links de tracking (contém URL real codificada)
            r'(https?://click\.omie\.com\.br/[^\s<>"\']+)',
            # Omie - links diretos de NFS-e
            r'(https?://[^\s]*omie\.com\.br[^\s]*nfse[^\s<>"\']*)',
        ]

        for pattern in patterns_prioritarios:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                url = match.group(1)
                # Remove entidades HTML escapadas
                url = url.replace('&amp;', '&')
                # Remove trailing de pontuação
                url = re.sub(r'[.,;:!?\)\]]+$', '', url)
                return url

        return None

    def extract_codigo_verificacao_from_link(self, link: Optional[str] = None) -> Optional[str]:
        """
        Extrai código de verificação/autenticação de um link de NF-e.

        Padrões suportados:
        - verificacao=BTE1S3EG (Prefeitura SP)
        - cod=R4ZF (Prefeitura SP/RJ)
        - codigo=XXXX (genérico)

        Args:
            link: URL para extrair código. Se None, usa extract_link_nfe_from_context()

        Returns:
            Código de verificação ou None
        """
        import re

        if link is None:
            link = self.extract_link_nfe_from_context()

        if not link:
            # Se não tem link, tenta extrair do corpo diretamente
            return self.extract_codigo_verificacao_from_body()

        # Padrões de código na URL (ordem de prioridade)
        patterns = [
            r'verificacao=([A-Za-z0-9]{4,12})',
            r'cod=([A-Za-z0-9]{4,12})',
            r'codigo=([A-Za-z0-9]{4,12})',
            r'auth=([A-Za-z0-9]{4,20})',
            r'token=([A-Za-z0-9\-_]{8,})',
        ]

        for pattern in patterns:
            match = re.search(pattern, link, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def extract_codigo_verificacao_from_body(self) -> Optional[str]:
        """
        Extrai código de verificação/autenticação do corpo do e-mail.

        Procura padrões como:
        - "Código de Autenticação: BTE1S3EG"
        - "Código de Verificação: 77CC8D93D"
        - "Código: O1IGTTNV"

        Returns:
            Código de verificação ou None
        """
        import re

        text = f"{self.email_subject or ''} {self.email_body_text or ''}"

        if not text.strip():
            return None

        # Padrões de código no texto (ordem de prioridade)
        patterns = [
            # Padrões explícitos com label
            r'[Cc]ódigo\s*(?:de\s+)?[Aa]utenticação[:\s]+([A-Z0-9]{4,12})',
            r'[Cc]ódigo\s*(?:de\s+)?[Vv]erificação[:\s]+([A-Z0-9]{4,12})',
            r'[Cc]ód\.?\s*(?:de\s+)?[Aa]ut(?:enticação)?\.?[:\s]+([A-Z0-9]{4,12})',
            r'[Cc]ód\.?\s*(?:de\s+)?[Vv]erif(?:icação)?\.?[:\s]+([A-Z0-9]{4,12})',
            # Padrão Omie/genérico: "Código: XXXXXXXX"
            r'[Cc]ódigo[:\s]+([A-Z0-9]{6,12})\b',
            # Padrão com "Cód." abreviado
            r'[Cc]ód\.?[:\s]+([A-Z0-9]{6,12})\b',
            # Padrão "Autenticação:" ou "Verificação:" sem "Código"
            r'[Aa]utenticação[:\s]+([A-Z0-9]{6,12})\b',
            r'[Vv]erificação[:\s]+([A-Z0-9]{6,12})\b',
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                codigo = match.group(1)
                # Filtra falsos positivos (palavras comuns)
                if codigo.upper() not in ['PENDENTE', 'AGUARDANDO', 'CONFIRMA', 'CONSULTA']:
                    return codigo

        return None

    def extract_numero_nf_from_link(self, link: Optional[str] = None) -> Optional[str]:
        """
        Extrai número da NF de um link de prefeitura.

        Padrões suportados:
        - nf=255046631
        - nf=4219090
        - numero=12345

        Args:
            link: URL para extrair número. Se None, usa extract_link_nfe_from_context()

        Returns:
            Número da NF ou None
        """
        import re

        if link is None:
            link = self.extract_link_nfe_from_context()

        if not link:
            return None

        # Padrões de número de NF na URL
        patterns = [
            r'nf=(\d{3,15})',
            r'numero=(\d{3,15})',
            r'nota=(\d{3,15})',
        ]

        for pattern in patterns:
            match = re.search(pattern, link, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def format_aviso_email_sem_anexo(self) -> Optional[str]:
        """
        Formata string de aviso para e-mails sem anexo.

        Combina link + código de verificação em formato padronizado
        para a coluna de observações/avisos.

        Returns:
            String formatada ou None se não houver dados relevantes

        Exemplo:
            "[SEM ANEXO] Link: https://nfe.prefeitura.sp.gov.br/... | Código: BTE1S3EG | NF: 4219090"
        """
        link = self.extract_link_nfe_from_context()
        codigo = self.extract_codigo_verificacao_from_link(link) or self.extract_codigo_verificacao_from_body()
        numero_nf = self.extract_numero_nf_from_link(link) or self.extract_numero_nota_from_context()

        partes = ["[SEM ANEXO]"]

        if link:
            # Trunca link se muito longo
            link_display = link if len(link) <= 100 else link[:97] + "..."
            # Indica se é link de tracking (Omie)
            if 'click.omie.com.br' in link:
                partes.append(f"Link (Omie): {link_display}")
            else:
                partes.append(f"Link: {link_display}")

        if codigo:
            partes.append(f"Código: {codigo}")

        if numero_nf:
            partes.append(f"NF: {numero_nf}")

        # Se não encontrou nada útil além do marcador
        if len(partes) == 1:
            return None

        return " | ".join(partes)

    def extract_fornecedor_from_subject(self) -> Optional[str]:
        """
        Extrai nome do fornecedor do assunto do e-mail.

        Analisa o assunto para identificar o nome da empresa emissora,
        filtrando empresas próprias do grupo (soumaster, master, etc.).

        Padrões suportados:
        - "Movidesk - NFS-e + Boleto Nº 193866" → "Movidesk"
        - "Interfocus Tecnologia - NFS-e + Boleto Nº 10227" → "Interfocus Tecnologia"
        - "Nota Fiscal de Serviços Eletrônica - NFS-e No. 255046631" → None (genérico)
        - "Nota Carioca No. 00002764 emitida" → None (portal, não fornecedor)

        Returns:
            Nome do fornecedor ou None
        """
        import re

        if not self.email_subject:
            return None

        subject = self.email_subject

        # Remove prefixos de encaminhamento
        subject = re.sub(r'^(ENC|FW|FWD|RE|RES)[:\s]+', '', subject, flags=re.IGNORECASE).strip()

        # Lista de termos a ignorar (não são fornecedores)
        termos_ignorar = [
            # Portais de NF-e
            'nota fiscal', 'nfs-e', 'nfse', 'nf-e', 'nfe', 'danfe',
            'nota carioca', 'nota do milhão', 'nota eletrônica', 'nota eletronica',
            # Termos genéricos
            'fatura', 'boleto', 'cobrança', 'cobranca', 'pagamento',
            'serviços eletrônica', 'servicos eletronica',
            # Campanhas e slogans (não são fornecedores)
            'agora com pix', 'pague com pix', 'aceita pix', 'via pix',
            'faturamento', 'fatura eletronica', 'fatura eletrônica',
            # Empresas próprias do grupo (soumaster/master)
            'soumaster', 'master internet', 'master-tv', 'master tv',
            'rbc', 'rede brasileira', 'vip comunicacao', 'vip comunicação',
            'ative', 'vale telecom', 'minas digital', 'hd telecom',
            'netlog', 'gyga', 'prime service', 'csc', 'carrier',
            'op11', 'zeus', 'exata', 'orion', 'device company',
            'moc comunicacao', 'omc provedor',
        ]

        # Lista de domínios de e-mail próprios a ignorar como fornecedor
        dominios_proprios = [
            'soumaster.com.br', 'masterinternet.com.br', 'rbctelecom.com.br',
            'vipcomunicacao.com.br', 'ativetelecom.com.br',
        ]

        # Verifica se o remetente é de empresa própria
        if self.email_sender_address:
            sender_lower = self.email_sender_address.lower()
            for dominio in dominios_proprios:
                if dominio in sender_lower:
                    # Remetente é interno, tenta extrair fornecedor do assunto
                    break

        # Padrão 1: "NomeFornecedor - NFS-e + Boleto Nº XXXX"
        # Captura tudo antes do primeiro " - NFS" ou " - Boleto" ou " - Fatura"
        match = re.match(r'^([^-]+?)\s*-\s*(?:NFS|Boleto|Fatura|Nota)', subject, re.IGNORECASE)
        if match:
            fornecedor = match.group(1).strip()

            # Verifica se não é termo a ignorar
            fornecedor_lower = fornecedor.lower()
            if not any(termo in fornecedor_lower for termo in termos_ignorar):
                # Limpa caracteres extras
                fornecedor = re.sub(r'\s+', ' ', fornecedor).strip()
                if len(fornecedor) >= 3:  # Mínimo 3 caracteres
                    return fornecedor

        # Padrão 2: "Agora com Pix - Nota Fiscal Eletronica - Faturamento - RPS No - XXXX - UNE - Cliente - CODIGO"
        # Este é padrão TOTVS/UNE - tenta extrair do corpo do e-mail
        if 'UNE - Cliente -' in subject or 'Agora com Pix' in subject:
            # Formato TOTVS: busca fornecedor no corpo do e-mail
            fornecedor_body = self._extract_fornecedor_from_body()
            if fornecedor_body:
                return fornecedor_body
            return None

        # Padrão 3: Busca nome de empresa conhecido no assunto
        # Empresas conhecidas (fornecedores comuns)
        empresas_conhecidas = [
            'movidesk', 'interfocus', 'totvs', 'zendesk', 'omie',
            'locaweb', 'uol', 'google', 'microsoft', 'adobe',
            'amazon', 'aws', 'azure', 'salesforce', 'hubspot',
            'resultados digitais', 'rd station', 'conta azul',
            'pipefy', 'monday', 'asana', 'trello', 'slack',
            'zoom', 'teams', 'webex', 'meet',
        ]

        subject_lower = subject.lower()
        for empresa in empresas_conhecidas:
            if empresa in subject_lower:
                # Retorna com capitalização correta
                return empresa.title()

        return None

    def _extract_fornecedor_from_body(self) -> Optional[str]:
        """
        Extrai nome do fornecedor do corpo do e-mail.

        Busca padrões como:
        - "Razão Social: EMPRESA LTDA"
        - "Prestador: EMPRESA"
        - "Emitente: EMPRESA"
        - "De: empresa@dominio.com.br" (e-mail original encaminhado)

        Returns:
            Nome do fornecedor ou None
        """
        import re

        if not self.email_body_text:
            return None

        text = self.email_body_text

        # Padrões para extrair fornecedor do corpo
        patterns = [
            # Razão Social explícita
            r'[Rr]az[aã]o\s+[Ss]ocial[:\s]+([A-ZÀ-Ú][A-ZÀ-Úa-zà-ú\s&\-\.]+?)(?:\s*[-–]\s*|\s*\n|\s*CNPJ)',
            # Prestador de serviço
            r'[Pp]restador[:\s]+([A-ZÀ-Ú][A-ZÀ-Úa-zà-ú\s&\-\.]+?)(?:\s*[-–]\s*|\s*\n|\s*CNPJ)',
            # Emitente
            r'[Ee]mitente[:\s]+([A-ZÀ-Ú][A-ZÀ-Úa-zà-ú\s&\-\.]+?)(?:\s*[-–]\s*|\s*\n|\s*CNPJ)',
            # Nome da empresa no cabeçalho do e-mail original
            r'De:\s*([A-ZÀ-Ú][A-ZÀ-Úa-zà-ú\s&\-\.]+?)\s*<[^>]+@(?!soumaster|master)',
            # "Empresa: NOME"
            r'[Ee]mpresa[:\s]+([A-ZÀ-Ú][A-ZÀ-Úa-zà-ú\s&\-\.]+?)(?:\s*[-–]\s*|\s*\n)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                fornecedor = match.group(1).strip()
                # Remove pontuação final
                fornecedor = re.sub(r'[\.,;:]+$', '', fornecedor).strip()
                # Valida tamanho
                if 3 <= len(fornecedor) <= 100:
                    return fornecedor

        return None

    def extract_fornecedor_from_context(self) -> Optional[str]:
        """
        Extrai fornecedor de múltiplas fontes com priorização.

        Ordem de prioridade:
        1. Nome extraído do assunto do e-mail
        2. Nome extraído do corpo do e-mail
        3. Nome do remetente (se não for empresa própria)
        4. None

        Returns:
            Nome do fornecedor ou None
        """
        # Tenta extrair do assunto primeiro
        fornecedor = self.extract_fornecedor_from_subject()
        if fornecedor:
            return fornecedor

        # Tenta extrair do corpo do e-mail
        fornecedor = self._extract_fornecedor_from_body()
        if fornecedor:
            return fornecedor

        # Fallback: usa nome do remetente se não for empresa própria
        if self.email_sender_name:
            sender_lower = self.email_sender_name.lower()

            # Lista de nomes a ignorar (funcionários internos)
            nomes_ignorar = [
                'natalia', 'natália', 'rafael', 'lucas', 'maria',
                'analista', 'gerente', 'coordenador', 'diretor',
                'financeiro', 'fiscal', 'contabil', 'contábil',
                'soumaster', 'master',
            ]

            if not any(nome in sender_lower for nome in nomes_ignorar):
                return self.email_sender_name

        return None

    def extract_vencimento_from_context(self) -> Optional[str]:
        """
        Tenta extrair data de vencimento do assunto ou corpo do e-mail.

        Procura por padrões como:
        - "Vencimento: 15/01/2025"
        - "Vence em 15-01-2025"
        - "Data venc.: 15.01.2025"
        - "Vencto: 15/01/2025"
        - "Dt. Vencimento 15/01/25"

        Returns:
            Data formatada DD/MM/YYYY ou None
        """
        import re

        # Combina assunto e corpo para busca
        text = f"{self.email_subject or ''} {self.email_body_text or ''}"

        if not text.strip():
            return None

        # Padrões de vencimento no texto (ordem de prioridade)
        patterns = [
            # "Vencimento: 15/01/2025" ou "Vencimento 15/01/2025" ou "vencimento em 15/01/2025"
            r'[Vv]encimento\s+(?:em|para|dia|no dia)?[:\s]*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})',
            r'[Vv]encimento[:\s]*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})',
            # "Vencto: 15/01/2025" ou "Vencto 15/01/2025"
            r'[Vv]encto\.?[:\s]*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})',
            # "Vence em 15/01/2025" ou "Vencem dia 15/01/2025"
            r'[Vv]ence(?:m)?\s+(?:em|dia|no dia)?[:\s]*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})',
            # "Data de vencimento: 15/01/2025" ou "Dt. Vencimento 15/01/2025"
            r'[Dd](?:ata|t)\.?\s+(?:de\s+)?[Vv]enc(?:imento|to)?\.?[:\s]*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})',
            # "Data venc.: 15/01/2025"
            r'[Dd]ata\s+[Vv]enc\.?[:\s]*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})',
            # "Prazo: 15/01/2025" ou "Prazo pagamento: 15/01/2025"
            r'[Pp]razo(?:\s+(?:de\s+)?pagamento)?[:\s]*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})',
            # "Pagar até 15/01/2025"
            r'[Pp]agar\s+at[ée][:\s]*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                normalized = self._normalize_date(match.group(1))
                if normalized:
                    return normalized

        return None
