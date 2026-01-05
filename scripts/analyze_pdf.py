import os
import sys

import pdfplumber

# Adicionar o diretório pai ao path para importar módulos do projeto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def analyze_pdf(file_path):
    """Analisa um PDF e exibe informações de cada página."""
    print(f"\n{'='*60}")
    print(f"Arquivo: {file_path}")
    print(f"{'='*60}")

    try:
        with pdfplumber.open(file_path) as pdf:
            print(f"Total de páginas: {len(pdf.pages)}")

            all_text = ""
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ''
                all_text += text + "\n"
                print(f"\n--- Página {i+1} ---")
                print(f"Tamanho do texto: {len(text)} caracteres")
                print(f"\nConteúdo (primeiros 3000 chars):")
                print("-" * 40)
                print(text[:3000] if len(text) > 3000 else text)
                print("-" * 40)

            # Resumo final
            print(f"\n{'='*60}")
            print("RESUMO DO DOCUMENTO")
            print(f"{'='*60}")
            print(f"Total de páginas: {len(pdf.pages)}")
            print(f"Total de caracteres: {len(all_text)}")

            # Procurar valores monetários
            import re
            valores = re.findall(r'R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})', all_text)
            if valores:
                valores_float = [float(v.replace('.', '').replace(',', '.')) for v in valores]
                print(f"\nValores monetários encontrados: {len(valores)}")
                print(f"Menor valor: R$ {min(valores_float):,.2f}")
                print(f"Maior valor: R$ {max(valores_float):,.2f}")

            # Procurar CNPJ
            cnpjs = re.findall(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', all_text)
            if cnpjs:
                print(f"\nCNPJs encontrados: {set(cnpjs)}")

            # Procurar vencimento
            vencimentos = re.findall(r'VENCIMENTO[:\s]*(\d{2}/\d{2}/\d{4})', all_text, re.IGNORECASE)
            if vencimentos:
                print(f"\nVencimentos encontrados: {vencimentos}")

            # Procurar total
            totais = re.findall(r'(?:VALOR\s+TOTAL|TOTAL\s+A\s+PAGAR|TOTAL\s+GERAL)[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})', all_text, re.IGNORECASE)
            if totais:
                print(f"\nTotais encontrados: {totais}")

    except Exception as e:
        print(f"Erro ao processar {file_path}: {e}")
        import traceback
        traceback.print_exc()


def main():
    # Diretório do caso problemático
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    case_dir = os.path.join(base_dir, "temp_email", "email_20260105_125519_9b0b0752")

    print(f"Analisando diretório: {case_dir}")

    # Listar arquivos PDF
    if os.path.exists(case_dir):
        pdf_files = [f for f in os.listdir(case_dir) if f.lower().endswith('.pdf')]
        print(f"PDFs encontrados: {pdf_files}")

        for pdf_file in pdf_files:
            file_path = os.path.join(case_dir, pdf_file)
            analyze_pdf(file_path)
    else:
        print(f"Diretório não encontrado: {case_dir}")

    # Também podemos analisar PDFs passados como argumentos
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            if os.path.exists(arg) and arg.lower().endswith('.pdf'):
                analyze_pdf(arg)


if __name__ == "__main__":
    main()
