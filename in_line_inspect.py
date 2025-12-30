from core.processor import BaseInvoiceProcessor

p=BaseInvoiceProcessor()

doc=p.process(r"C:\Users\rafael.ferreira\Documents\scrapper\failed_cases_pdf\00000244773\EZZE SEGURO  BOLETO.pdf")

print('last_extractor', getattr(p,'last_extractor',None))

print('fornecedor', getattr(doc,'fornecedor_nome',None))

print('valor', getattr(doc,'valor_documento',None))

print('emissao', getattr(doc,'data_emissao',None))

print('venc', getattr(doc,'vencimento',None))

print('linha_digitavel', getattr(doc,'linha_digitavel',None))

print('texto_bruto', getattr(doc,'texto_bruto',None))
