"""
Script de Orquestração de Ingestão de E-mails.

Este módulo é responsável por conectar ao servidor de e-mail, baixar anexos PDF
de notas fiscais e encaminhá-los para o pipeline de processamento.

Funcionalidades:
1.  Conexão segura via IMAP (configurada via .env).
2.  Filtragem de e-mails por assunto.
3.  Download de anexos para pasta temporária (com tratamento de colisão de nomes).
4.  Execução do processador de extração.
5.  Geração de relatório CSV.

Usage:
    python run_ingestion.py
"""

import os
import shutil
import uuid
from pathlib import Path
from config import settings
from ingestors.imap import ImapIngestor
from core.processor import BaseInvoiceProcessor
import pandas as pd

def main():
    # 1. Verificação de Segurança
    if not settings.EMAIL_PASS:
        print("❌ Erro: Senha de e-mail não encontrada no arquivo .env")
        print("   Por favor, configure o arquivo .env com suas credenciais.")
        return

    # 2. Preparar ambiente local (Gap: Bytes -> Disco)
    # Limpa e recria a pasta temporária para garantir que não processamos lixo antigo
    if os.path.exists(settings.DIR_TEMP):
        shutil.rmtree(settings.DIR_TEMP)
    os.makedirs(settings.DIR_TEMP)
    print(f"📂 Diretório temporário criado: {settings.DIR_TEMP}")

    # 3. Conexão
    print(f"🔌 Conectando a {settings.EMAIL_HOST} como {settings.EMAIL_USER}...")
    ingestor = ImapIngestor(
        host=settings.EMAIL_HOST,
        user=settings.EMAIL_USER,
        password=settings.EMAIL_PASS,
        folder=settings.EMAIL_FOLDER
    )

    try:
        ingestor.connect()
    except Exception as e:
        print(f"❌ Falha na conexão: {e}")
        return

    # 4. Busca (Fetch)
    # Dica: Comece filtrando por um assunto específico para testar
    assunto_teste = "ENC" 
    print(f"🔍 Buscando e-mails com assunto: '{assunto_teste}'...")
    
    try:
        anexos = ingestor.fetch_attachments(subject_filter=assunto_teste)
    except Exception as e:
        print(f"❌ Erro ao buscar e-mails: {e}")
        return
    
    if not anexos:
        print("📭 Nenhum anexo encontrado.")
        return

    print(f"📦 {len(anexos)} anexo(s) encontrado(s). Iniciando processamento...")

    # 5. Processamento
    processor = BaseInvoiceProcessor()
    resultados = []

    for item in anexos:
        filename = item['filename']
        content_bytes = item['content']
        
        # Salva o arquivo físico para o processador ler (Resolvendo o Gap)
        # GERA UM NOME ÚNICO PARA EVITAR SOBRESCRITA
        unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
        file_path = settings.DIR_TEMP / unique_filename
        
        try:
            with open(file_path, 'wb') as f:
                f.write(content_bytes)
                
            print(f"  Processing: {filename} (Salvo como: {unique_filename})...")
            
            # O processador agora lê o arquivo que acabamos de salvar
            result = processor.process(str(file_path))
            
            # Enriquece o resultado com dados do e-mail
            data_dict = result.__dict__
            data_dict['email_source'] = item['source']
            data_dict['email_subject'] = item['subject']
            
            resultados.append(data_dict)
            print(f"  ✅ Sucesso: {result.numero_nota} - {result.cnpj_prestador}")
            
        except Exception as e:
            print(f"  ⚠️ Falha ao processar {filename}: {e}")

    # 6. Relatório Final
    if resultados:
        # Garante que o diretório de saída existe
        os.makedirs(settings.DIR_SAIDA, exist_ok=True)
        output_file = settings.DIR_SAIDA / "relatorio_ingestao.csv"
        
        df = pd.DataFrame(resultados)
        df.to_csv(output_file, index=False, sep=',', encoding='utf-8-sig')
        print(f"\n🚀 Processamento concluído! Relatório salvo em: {output_file}")
    else:
        print("\n⚠️ Nenhum resultado processado com sucesso.")
    
    # Opcional: Limpeza
    # shutil.rmtree(settings.DIR_TEMP)

if __name__ == "__main__":
    main()
