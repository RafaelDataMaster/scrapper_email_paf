"""scripts/debug_pdf.py

Debug de extração de PDFs com foco no MVP (colunas PAF prioritárias).

Foco atual (MVP):
- DATA (processamento), SETOR, EMPRESA, FORNECEDOR, NF (vazio), EMISSÃO, VALOR, VENCIMENTO

Observação:
- A coluna NF fica vazia por enquanto (preenchimento virá da etapa de validação via API da OpenAI).

Uso:
    python scripts/debug_pdf.py <arquivo.pdf> [--full-text]
"""

import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

import pdfplumber

from _init_env import setup_project_path

# Inicializa o ambiente do projeto
setup_project_path()

from core.processor import BaseInvoiceProcessor
from core.models import InvoiceData, BoletoData

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    END = '\033[0m'


def _fmt_iso_date(iso_date: Optional[str]) -> str:
    if not iso_date:
        return ""
    try:
        return datetime.strptime(iso_date, '%Y-%m-%d').strftime('%d/%m/%Y')
    except Exception:
        return ""


def _fmt_money(value: float) -> str:
    try:
        return f"R$ {float(value):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    except Exception:
        return "R$ 0,00"


def print_mvp_row(doc, filename: str) -> None:
    """Exibe as colunas MVP (com NF vazio) em formato legível."""
    print(f"\n{Colors.HEADER}{'='*80}")
    print(f"MVP - COLUNAS PAF (NF VAZIO) - {Path(filename).name}")
    print(f"{'='*80}{Colors.END}")

    # Campos comuns
    data_proc = _fmt_iso_date(getattr(doc, 'data_processamento', None))
    setor = getattr(doc, 'setor', None) or ""
    empresa = getattr(doc, 'empresa', None) or ""
    fornecedor = getattr(doc, 'fornecedor_nome', None) or ""
    venc = _fmt_iso_date(getattr(doc, 'vencimento', None))

    # Campos por tipo
    emissao = ""
    valor = 0.0
    if isinstance(doc, InvoiceData):
        emissao = _fmt_iso_date(getattr(doc, 'data_emissao', None))
        valor = float(getattr(doc, 'valor_total', 0.0) or 0.0)
    elif isinstance(doc, BoletoData):
        emissao = _fmt_iso_date(getattr(doc, 'data_emissao', None))
        valor = float(getattr(doc, 'valor_documento', 0.0) or 0.0)

    # NF (MVP): sempre vazio
    nf = ""

    row = {
        "DATA": data_proc,
        "SETOR": setor,
        "EMPRESA": empresa,
        "FORNECEDOR": fornecedor,
        "NF": nf,
        "EMISSÃO": emissao,
        "VALOR": _fmt_money(valor),
        "VENCIMENTO": venc,
    }

    print(f"{Colors.BOLD}{'COLUNA':<12} | {'DADO'}{Colors.END}")
    print("-" * 60)
    for col, val in row.items():
        val_str = str(val)
        if val_str == "":
            print(f"{col:<12} | {Colors.YELLOW}(vazio){Colors.END}")
        elif val_str == "R$ 0,00":
            print(f"{col:<12} | {Colors.RED}{val_str}{Colors.END}")
        else:
            print(f"{col:<12} | {Colors.GREEN}{val_str}{Colors.END}")
    print("-" * 60)

    # Sugestão (opcional): vem em obs_interna via pipeline (não altera o MVP)
    obs_interna = getattr(doc, 'obs_interna', None) or ""
    m = None
    try:
        import re
        m = re.search(r"\bNF_CANDIDATE=([0-9]{3,12})\b.*?\(conf=([0-9.]+)", obs_interna)
    except Exception:
        m = None

    if m:
        nf_candidate = m.group(1)
        nf_conf = m.group(2)
        print(f"{Colors.CYAN}NF (MVP): vazio | NF (sugestão): {nf_candidate} (conf={nf_conf}){Colors.END}")
    else:
        print(f"{Colors.CYAN}NF está vazio no MVP (preenchimento virá de etapa futura).{Colors.END}")


def debug_file(pdf_path: str, show_full_text: bool = False) -> None:
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        print(f"{Colors.RED}Erro: Arquivo não encontrado: {pdf_path}{Colors.END}")
        return

    print(f"Processando: {pdf_file}...")

    # Mantém --full-text (extração simples via pdfplumber) para inspeção humana.
    if show_full_text:
        try:
            raw = ""
            with pdfplumber.open(str(pdf_file)) as pdf:
                for page in pdf.pages:
                    raw += (page.extract_text() or "") + "\n"
            print(f"\n{Colors.CYAN}{'='*30} TEXTO BRUTO INÍCIO {'='*30}{Colors.END}")
            print(raw)
            print(f"{Colors.CYAN}{'='*30} TEXTO BRUTO FIM {'='*31}{Colors.END}\n")
        except Exception as e:
            print(f"{Colors.RED}Erro ao ler texto bruto (pdfplumber): {e}{Colors.END}")

    # Pipeline real (inclui estratégia de extração e seleção de extrator)
    processor = BaseInvoiceProcessor()
    doc = processor.process(str(pdf_file))
    print_mvp_row(doc, str(pdf_file))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Debug PDF para Tabela PAF')
    parser.add_argument('pdf_files', nargs='+', help='Arquivos PDF para processar')

    parser.add_argument('--full-text', action='store_true', help='Exibir o texto bruto extraído do PDF')
    
    args = parser.parse_args()

    for pdf in args.pdf_files:
        debug_file(pdf, show_full_text=args.full_text)