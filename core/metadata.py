"""
Metadados de contexto para processamento em lote.

Este módulo define estruturas de dados para armazenar contexto
do e-mail (assunto, remetente, corpo) que enriquece a extração.

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
