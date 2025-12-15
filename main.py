from strategies.fallback import smart_extraction_strategy

def processar_arquivos(pasta):
    # Instancia a estratégia inteligente
    extrator_texto = smart_extraction_strategy()

    for arquivo in arquivos_da_pasta:
        try:
            # POLIMORFISMO PURO: Não importa se é PDF texto ou imagem scan
            texto_bruto = extrator_texto.extract(arquivo)
            
            print(f"Sucesso lendo {arquivo}!")
            # ... Passa o texto_bruto para a próxima fase (Extração de Dados) ...
            
        except Exception as e:
            print(f"Erro ao processar {arquivo}: {e}")