"""
Script para testar qual extrator seria usado para um PDF.

Útil para:
- Verificar se um PDF está sendo roteado para o extrator correto
- Testar performance de extração (tempo de can_handle e extract)
- Debug de problemas de classificação de documentos

Uso:
    python scripts/test_extractor_routing.py <caminho_pdf>
    python scripts/test_extractor_routing.py <caminho_pdf> --texto  # mostra texto OCR
"""

import sys
import time
from pathlib import Path

# Adiciona o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent))


def extract_text_simple(pdf_path: str) -> str:
    """Extrai texto do PDF usando PyMuPDF + Tesseract (OCR) diretamente."""
    import fitz  # PyMuPDF
    import pytesseract
    from PIL import Image
    import io
    from config import settings
    
    # Configura caminho do Tesseract
    pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
    
    doc = fitz.open(pdf_path)
    all_text = []
    
    for page_num, page in enumerate(doc):
        # Tenta texto nativo primeiro
        text = page.get_text()
        
        # Se texto nativo for muito curto, usa OCR
        if len(text.strip()) < 500:
            print(f"  Página {page_num + 1}: texto nativo curto ({len(text.strip())} chars), aplicando OCR...")
            # Renderiza página como imagem
            mat = fitz.Matrix(2.0, 2.0)  # 2x zoom para melhor OCR
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            
            # OCR com Tesseract
            text = pytesseract.image_to_string(img, lang='por')
            print(f"  OCR extraiu: {len(text)} caracteres")
        else:
            print(f"  Página {page_num + 1}: usando texto nativo ({len(text.strip())} chars)")
        
        all_text.append(text)
    
    doc.close()
    return "\n".join(all_text)


def get_all_extractors():
    """Retorna todos os extratores na ordem de prioridade do registro."""
    from core.extractors import EXTRACTOR_REGISTRY
    return EXTRACTOR_REGISTRY


def main():
    show_text = "--texto" in sys.argv or "-t" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    
    if len(args) < 1:
        print("Uso: python scripts/test_extractor_routing.py <caminho_pdf> [--texto]")
        print()
        print("Opções:")
        print("  --texto, -t    Mostra o texto extraído do PDF")
        sys.exit(1)

    pdf_path = args[0]
    
    if not Path(pdf_path).exists():
        print(f"Arquivo não encontrado: {pdf_path}")
        sys.exit(1)

    print(f"\n📄 Arquivo: {Path(pdf_path).name}")
    print("=" * 60)
    print("Extraindo texto...")
    
    t0 = time.time()
    texto = extract_text_simple(pdf_path)
    t_extract = time.time() - t0
    
    print(f"\n✅ Texto extraído: {len(texto)} caracteres em {t_extract:.1f}s")
    
    if show_text:
        print("\n" + "=" * 60)
        print("TEXTO EXTRAÍDO:")
        print("=" * 60)
        print(texto[:3000])
        if len(texto) > 3000:
            print(f"\n... [{len(texto) - 3000} caracteres omitidos]")
        print("=" * 60)
    
    # Importa extratores
    extractors = get_all_extractors()
    
    # Testa can_handle de cada extrator na ordem de prioridade
    print("\n🔍 TESTE DE EXTRATORES (ordem de prioridade)\n")
    
    extrator_usado = None
    for ext_cls in extractors:
        t0 = time.time()
        try:
            result = ext_cls.can_handle(texto)
        except Exception as e:
            print(f"  ❌ {ext_cls.__name__}: ERRO - {e}")
            continue
        t_check = time.time() - t0
        
        status = "✅ SIM" if result else "   não"
        warning = " ⚠️ LENTO!" if t_check > 1 else ""
        print(f"  {status} {ext_cls.__name__} ({t_check*1000:.1f}ms){warning}")
        
        if result and extrator_usado is None:
            extrator_usado = ext_cls
            print(f"       👆 ESTE SERÁ O EXTRATOR USADO")
    
    # Se encontrou extrator, roda a extração
    if extrator_usado:
        print(f"\n📊 EXTRAÇÃO COM {extrator_usado.__name__}\n")
        t0 = time.time()
        try:
            dados = extrator_usado().extract(texto)
            t_ext = time.time() - t0
            
            warning = " ⚠️ LENTO!" if t_ext > 5 else ""
            print(f"  ⏱️  Tempo: {t_ext:.2f}s{warning}")
            print()
            
            # Mostra campos extraídos
            for k, v in dados.items():
                if v is not None and v != "" and v != 0:
                    print(f"  ✓ {k}: {v}")
                else:
                    print(f"    {k}: {v}")
        except Exception as e:
            print(f"  ❌ ERRO na extração: {e}")
    else:
        print("\n⚠️  Nenhum extrator reconheceu este documento!")


if __name__ == "__main__":
    main()
