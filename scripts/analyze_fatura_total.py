import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pdfplumber


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fatura_path = os.path.join(base_dir, "temp_email", "email_20260105_125519_9b0b0752", "01_Fatura-50446.pdf")

    print(f"Analisando: {fatura_path}")
    print("=" * 80)

    with pdfplumber.open(fatura_path) as pdf:
        total_pages = len(pdf.pages)
        print(f"Total de paginas: {total_pages}")
        print()

        # Analisar últimas 3 páginas em busca do total
        for i in range(max(0, total_pages - 3), total_pages):
            page = pdf.pages[i]
            text = page.extract_text() or ''

            print(f"{'='*60}")
            print(f"PÁGINA {i + 1}")
            print(f"{'='*60}")
            print(text)
            print()

        # Procurar padrões de total em todo o documento
        print("=" * 80)
        print("ANÁLISE DE VALORES TOTAIS")
        print("=" * 80)

        all_text = ""
        for page in pdf.pages:
            all_text += (page.extract_text() or '') + "\n"

        # Procurar padrões de total
        total_patterns = [
            (r'(?i)TOTAL\s+(?:GERAL|DA\s+FATURA|A\s+PAGAR|LÍQUIDO)[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})', 'Total com label'),
            (r'(?i)VALOR\s+TOTAL[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})', 'Valor Total'),
            (r'(?i)SUBTOTAL[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})', 'Subtotal'),
            (r'(?i)TOTAL[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})', 'Total simples'),
            (r'(?i)FATURA\s+Nº?\s*:?\s*\d+[^\n]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})', 'Fatura com valor'),
        ]

        print("\nPadrões de total encontrados:")
        for pattern, name in total_patterns:
            matches = re.findall(pattern, all_text)
            if matches:
                print(f"  {name}: {matches}")

        # Procurar maiores valores
        print("\n" + "=" * 80)
        print("MAIORES VALORES ENCONTRADOS")
        print("=" * 80)

        all_values = re.findall(r'R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})', all_text)
        if all_values:
            values_float = sorted(
                [float(v.replace('.', '').replace(',', '.')) for v in all_values],
                reverse=True
            )
            print(f"Total de valores encontrados: {len(values_float)}")
            print(f"Top 10 maiores valores:")
            for i, v in enumerate(values_float[:10]):
                print(f"  {i+1}. R$ {v:,.2f}")

        # Verificar se última página tem resumo
        print("\n" + "=" * 80)
        print("ÚLTIMA PÁGINA - BUSCA POR RESUMO/TOTAL")
        print("=" * 80)

        last_page_text = pdf.pages[-1].extract_text() or ''

        # Procurar linha com maior valor na última página
        last_values = re.findall(r'R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})', last_page_text)
        if last_values:
            last_values_float = [float(v.replace('.', '').replace(',', '.')) for v in last_values]
            print(f"Valores na última página: {[f'R$ {v:,.2f}' for v in last_values_float]}")
            print(f"Maior valor na última página: R$ {max(last_values_float):,.2f}")

        # Somar todos os valores VALOR TOTAL (última coluna)
        print("\n" + "=" * 80)
        print("SOMA DOS ITENS DE LOCAÇÃO")
        print("=" * 80)

        # Padrão: linha com item termina em valor com R$
        # Ex: 75499 NOTEBOOK DELL LATITUDE 3470 02/08/2025 01/09/2025 R$ 130,00 R$ 0,00 R$ 130,00
        item_values = re.findall(r'R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})\s*$', all_text, re.MULTILINE)
        if item_values:
            item_values_float = [float(v.replace('.', '').replace(',', '.')) for v in item_values]
            total_soma = sum(item_values_float)
            print(f"Total de itens encontrados: {len(item_values_float)}")
            print(f"Soma dos valores finais de cada linha: R$ {total_soma:,.2f}")


if __name__ == "__main__":
    main()
