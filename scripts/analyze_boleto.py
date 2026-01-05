import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pdfplumber


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    boleto_path = os.path.join(base_dir, "temp_email", "email_20260105_125519_9b0b0752", "02_Boleto-47925-Parcela-1.pdf")

    print(f"Analisando: {boleto_path}")

    with pdfplumber.open(boleto_path) as pdf:
        print(f"Total de paginas: {len(pdf.pages)}")

        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ''
            print(f"\n--- Pagina {i+1} ---")
            print(text)

if __name__ == "__main__":
    main()
