import os
import pandas as pd
from config import settings
from core.processor import BaseInvoiceProcessor

def main():
    processor = BaseInvoiceProcessor() # Futuramente usaremos uma Factory aqui
    lista_resultados = []
    
    pasta_origem = settings.DIR_ENTRADA 
    
    print(f"Iniciando processamento em: {pasta_origem}")

    for root, dirs, files in os.walk(pasta_origem):
        for file in files:
            if file.lower().endswith('.pdf'):
                caminho = os.path.join(root, file)
                print(f"Processando: {file}")
                
                try:
                    # A mágica acontece aqui: O processador usa o strategy + regex
                    resultado = processor.process(caminho)
                    
                    # Converte o objeto InvoiceData para dicionário para o Pandas
                    lista_resultados.append(resultado.__dict__) 
                    
                except Exception as e:
                    print(f"Erro no arquivo {file}: {e}")

    # Gerar CSV
    if lista_resultados:
        df = pd.DataFrame(lista_resultados)
        df.to_csv(settings.ARQUIVO_SAIDA, index=False, sep=',', encoding='utf-8')
        print(f"Processamento concluído. Arquivo salvo: {settings.ARQUIVO_SAIDA}")

if __name__ == "__main__":
    main()