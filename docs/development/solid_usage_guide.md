# Guia Rápido: Usando o Código Refatorado

Este guia mostra como usar as novas funcionalidades SOLID implementadas no projeto.

---

## 📚 Índice

1. [Adicionando Novos Tipos de Documento](#1-adicionando-novos-tipos-de-documento)
2. [Implementando Google Sheets Exporter](#2-implementando-google-sheets-exporter)
3. [Testando com Mocks](#3-testando-com-mocks)
4. [Criando Estratégias Customizadas](#4-criando-estratégias-customizadas)

---

## 1. Adicionando Novos Tipos de Documento

**Exemplo:** Adicionar suporte para "Nota Fiscal de Produto" (NFP)

### Passo 1: Criar o Modelo em `core/models.py`

```python
@dataclass
class NotaFiscalProduto(DocumentData):
    """Modelo para Nota Fiscal de Produto."""
    
    # Campos específicos de NFP
    cnpj_emitente: Optional[str] = None
    numero_nfp: Optional[str] = None
    valor_produtos: float = 0.0
    valor_icms: float = 0.0
    chave_acesso: Optional[str] = None
    
    @property
    def doc_type(self) -> str:
        return 'NFP'
    
    def to_dict(self) -> dict:
        return {
            'tipo_documento': self.doc_type,
            'arquivo_origem': self.arquivo_origem,
            'cnpj_emitente': self.cnpj_emitente,
            'numero_nfp': self.numero_nfp,
            'valor_produtos': self.valor_produtos,
            'valor_icms': self.valor_icms,
            'chave_acesso': self.chave_acesso,
            'texto_bruto': self.texto_bruto[:200] if self.texto_bruto else None
        }
```

### Passo 2: Criar o Extrator em `extractors/nfp.py`

```python
from core.extractors import register_extractor, BaseExtractor

@register_extractor
class NotaFiscalProdutoExtractor(BaseExtractor):
    """Extrator para Nota Fiscal de Produto."""
    
    @staticmethod
    def can_handle(text: str) -> bool:
        keywords = ['DANFE', 'NOTA FISCAL ELETRÔNICA', 'NFe']
        return any(kw in text.upper() for kw in keywords)
    
    def extract(self, text: str) -> dict:
        return {
            'tipo_documento': 'NFP',
            'cnpj_emitente': self._extract_cnpj(text),
            'numero_nfp': self._extract_numero(text),
            'chave_acesso': self._extract_chave_acesso(text),
            # ... mais extrações
        }
```

### Passo 3: Atualizar `core/processor.py`

```python
# Importar o novo modelo
from core.models import InvoiceData, BoletoData, NotaFiscalProduto

# Adicionar no método process():
elif extracted_data.get('tipo_documento') == 'NFP':
    return NotaFiscalProduto(
        arquivo_origem=os.path.basename(file_path),
        texto_bruto=' '.join(raw_text.split())[:500],
        cnpj_emitente=extracted_data.get('cnpj_emitente'),
        numero_nfp=extracted_data.get('numero_nfp'),
        # ... mais campos
    )
```

### Passo 4: Adicionar Nome de Arquivo em `run_ingestion.py`

```python
# No mapeamento de arquivos de saída:
arquivo_saida_map = {
    'NFSE': 'relatorio_nfse.csv',
    'BOLETO': 'relatorio_boletos.csv',
    'NFP': 'relatorio_nfp.csv',  # ✅ Nova entrada
}
```

**Pronto!** O sistema agora suporta NFP sem modificar a lógica de orquestração. ✨

---

## 2. Implementando Google Sheets Exporter

### Passo 1: Instalar Dependências

```bash
pip install gspread oauth2client
```

### Passo 2: Completar a Implementação em `core/exporters.py`

```python
import logging
import gspread
from oauth2client.service_account import ServiceAccountCredentials

logger = logging.getLogger(__name__)

class GoogleSheetsExporter(DataExporter):
    """Exportador para Google Sheets."""
    
    def __init__(self, credentials_path: str, spreadsheet_id: str):
        self.credentials_path = credentials_path
        self.spreadsheet_id = spreadsheet_id
        
        # Autenticar
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            credentials_path, scope
        )
        self.client = gspread.authorize(creds)
    
    def export(self, data: List[DocumentData], destination: str) -> None:
        """
        Exporta documentos para Google Sheets.
        
        Args:
            data: Lista de documentos
            destination: Nome da aba/sheet
        """
        if not data:
            raise ValueError("Lista de dados vazia.")
        
        # Abre a planilha
        sheet = self.client.open_by_key(self.spreadsheet_id)
        
        # Tenta pegar a aba, ou cria se não existir
        try:
            worksheet = sheet.worksheet(destination)
            worksheet.clear()  # Limpa dados antigos
        except gspread.WorksheetNotFound:
            worksheet = sheet.add_worksheet(
                title=destination, 
                rows=len(data)+1, 
                cols=10
            )
        
        # Converte para lista de dicionários
        records = [doc.to_dict() for doc in data]
        
        # Extrai headers e valores
        headers = list(records[0].keys())
        values = [headers] + [
            [str(record.get(h, '')) for h in headers] 
            for record in records
        ]
        
        # Atualiza a planilha
        worksheet.update('A1', values)
        logger.info(f"✅ {len(data)} registros exportados para '{destination}'")
```

### Passo 3: Usar no `run_ingestion.py`

```python
# Configurar exportador
if settings.USE_GOOGLE_SHEETS:
    exporter = GoogleSheetsExporter(
        credentials_path='credentials/service_account.json',
        spreadsheet_id='1AbCdEfGhIjKlMnOpQrStUvWxYz'
    )
else:
    exporter = CsvExporter()

# Exportar (código permanece igual!)
for doc_type, documentos in documentos_por_tipo.items():
    # ... código existente
    # ✅ Funciona com qualquer exportador!
```

---

## 3. Testando com Mocks

### Testando Processamento sem Arquivo Real

```python
import logging
from unittest.mock import Mock
from core.processor import BaseInvoiceProcessor
from core.interfaces import TextExtractionStrategy

# Configurar logging para testes
logging.basicConfig(level=logging.INFO)

def test_processar_sem_arquivo_real():
    # Criar estratégia mock
    mock_reader = Mock(spec=TextExtractionStrategy)
    mock_reader.extract.return_value = """
        NOTA FISCAL DE SERVIÇO Nº 12345
        CNPJ Prestador: 12.345.678/0001-90
        Valor Total: R$ 1.500,00
        Data: 15/12/2025
    """
    
    # Injetar no processor
    processor = BaseInvoiceProcessor(reader=mock_reader)
    
    # Processar (sem precisar de PDF real!)
    result = processor.process("fake.pdf")
    
    # Validar
    assert result.doc_type == 'NFSE'
    assert result.numero_nota == '12345'
    assert result.cnpj_prestador == '12.345.678/0001-90'
    logging.info("✅ Teste passou sem arquivo real!")
```

### Testando Ingestão sem Email Real

```python
import logging
from unittest.mock import Mock
from run_ingestion import main
from core.interfaces import EmailIngestorStrategy

def test_ingestao_sem_email_real():
    # Criar ingestor mock
    mock_ingestor = Mock(spec=EmailIngestorStrategy)
    mock_ingestor.fetch_attachments.return_value = [
        {
            'filename': 'boleto_teste.pdf',
            'content': b'%PDF-1.4 fake content',
            'source': 'test@example.com',
            'subject': 'Boleto para testes'
        }
    ]
    
    # Executar ingestão com mock
    main(ingestor=mock_ingestor)
    
    # Verificar que foi chamado
    mock_ingestor.connect.assert_called_once()
    mock_ingestor.fetch_attachments.assert_called_once()
    logging.info("✅ Ingestão testada sem conectar em email real!")
```

---

## 4. Criando Estratégias Customizadas

### Exemplo: Estratégia Somente para Tabelas

```python
from core.interfaces import TextExtractionStrategy
import camelot

class CamelotTableStrategy(TextExtractionStrategy):
    """Estratégia usando Camelot para extração de tabelas."""
    
    def extract(self, file_path: str) -> str:
        try:
            # Extrai todas as tabelas
            tables = camelot.read_pdf(file_path, pages='all')
            
            if not tables:
                return ""
            
            # Concatena todas as tabelas em texto
            text_parts = []
            for table in tables:
                df = table.df
                text_parts.append(df.to_string())
            
            result = "\n\n".join(text_parts)
            
            # Validação mínima
            if len(result.strip()) < 50:
                return ""
            
            return result
            
        except Exception as e:
            # Falha recuperável: retorna string vazia
            return ""
```

### Usando Estratégia Customizada

```python
from strategies.fallback import SmartExtractionStrategy
from minha_estrategia import CamelotTableStrategy

# Criar fallback customizado
custom_strategy = SmartExtractionStrategy()
custom_strategy.strategies = [
    CamelotTableStrategy(),  # Tenta Camelot primeiro
    NativePdfStrategy(),      # Depois nativo
    TesseractOcrStrategy()    # Por último OCR
]

# Injetar no processor
processor = BaseInvoiceProcessor(reader=custom_strategy)
```

---

## 🎯 Checklist de Boas Práticas

Ao estender o sistema, siga estas diretrizes:

### ✅ Para Novos Tipos de Documento

- [ ] Herdar de `DocumentData`
- [ ] Implementar propriedade `doc_type`
- [ ] Implementar método `to_dict()`
- [ ] Criar extrator com `@register_extractor`
- [ ] Adicionar testes em `tests/test_extractors.py`

### ✅ Para Novas Estratégias

- [ ] Herdar de `TextExtractionStrategy`
- [ ] Retornar `""` em falhas recuperáveis
- [ ] Lançar `ExtractionError` apenas em falhas críticas
- [ ] Validar texto extraído (mínimo 50 caracteres)
- [ ] Adicionar testes em `tests/test_strategies.py`

### ✅ Para Novos Exportadores

- [ ] Herdar de `DataExporter`
- [ ] Implementar método `export(data, destination)`
- [ ] Usar `doc.to_dict()` para conversão
- [ ] Lançar `ValueError` se lista vazia
- [ ] Adicionar testes de exportação

---

## 📚 Referências

- [Relatório Completo de Refatoração](solid_refactoring_report.md)
- [Testes de Validação](../../tests/test_solid_refactoring.py)
- [Documentação de Estratégias](../api/strategies.md)

---

**Dúvidas?** Consulte os testes em `tests/test_solid_refactoring.py` - eles servem como exemplos práticos de uso! 🚀
