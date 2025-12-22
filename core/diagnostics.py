"""
Módulo centralizado para diagnóstico e análise de qualidade de extração.

Este módulo consolida a lógica de validação e relatórios de diagnóstico,
eliminando duplicação entre scripts de validação e análise.

Conformidade: Implementa validação de 04 dias úteis conforme Política
Interna 5.9 e POP 4.10 (Master Internet).
"""
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
from core.models import InvoiceData, BoletoData
from config.feriados_sp import SPBusinessCalendar

@dataclass
class DiagnosticReport:
    """
    Resultado da análise de qualidade.
    
    Attributes:
        total_arquivos: Total de arquivos processados
        nfse_sucesso: Quantidade de NFSe extraídas com sucesso
        nfse_falhas: Quantidade de NFSe com falhas
        boleto_sucesso: Quantidade de Boletos extraídos com sucesso
        boleto_falhas: Quantidade de Boletos com falhas
        taxa_sucesso_nfse: Percentual de sucesso nas NFSe
        taxa_sucesso_boleto: Percentual de sucesso nos Boletos
        falhas_detalhadas: Lista de dicionários com detalhes das falhas
    """
    total_arquivos: int
    nfse_sucesso: int
    nfse_falhas: int
    boleto_sucesso: int
    boleto_falhas: int
    taxa_sucesso_nfse: float
    taxa_sucesso_boleto: float
    falhas_detalhadas: List[Dict]


class ExtractionDiagnostics:
    """
    Classe responsável por análise de qualidade de extração.
    
    Centraliza as regras de validação e geração de relatórios para
    evitar duplicação entre scripts de diagnóstico e validação.
    
    Conformidade: Valida prazo de 04 dias úteis (Política 5.9 e POP 4.10).
    """
    
    # Calendário de SP com cache LRU (feriados nacionais + municipais)
    _calendario = SPBusinessCalendar()
    
    @staticmethod
    def validar_prazo_vencimento(dt_classificacao: Optional[str], 
                                  vencimento: Optional[str]) -> Tuple[bool, int]:
        """
        Valida se há no mínimo 04 dias úteis entre classificação e vencimento.
        
        Conformidade: Política Interna 5.9 e POP 4.10 exigem lançamento com
        antecedência mínima de 04 dias úteis ao vencimento.
        
        Considera:
        - Feriados nacionais
        - Feriados estaduais de São Paulo
        - Feriados municipais de São Paulo (capital)
        - Finais de semana (sábado e domingo)
        
        Args:
            dt_classificacao: Data de classificação no formato ISO (YYYY-MM-DD)
            vencimento: Data de vencimento no formato ISO (YYYY-MM-DD)
            
        Returns:
            Tupla (prazo_ok, quantidade_dias_uteis)
            - prazo_ok: True se >= 4 dias úteis, False caso contrário
            - quantidade_dias_uteis: Número de dias úteis calculado
            
        Examples:
            >>> # Exemplo: classificação 03/01/2025, vencimento 30/01/2025
            >>> # Considerando 25/01 feriado (Aniversário SP)
            >>> ok, dias = ExtractionDiagnostics.validar_prazo_vencimento(
            ...     "2025-01-03", "2025-01-30")
            >>> assert dias >= 4
        """
        if not dt_classificacao or not vencimento:
            # Se não tem datas, não pode validar (retorna False, 0)
            return (False, 0)
        
        try:
            dt_class = datetime.strptime(dt_classificacao, '%Y-%m-%d')
            dt_venc = datetime.strptime(vencimento, '%Y-%m-%d')
            
            # Calcula dias úteis usando calendário de SP
            dias_uteis = ExtractionDiagnostics._calendario.get_working_days_delta(
                dt_class, dt_venc
            )
            
            # Conformidade: mínimo 04 dias úteis
            prazo_ok = dias_uteis >= 4
            
            return (prazo_ok, dias_uteis)
            
        except (ValueError, TypeError):
            # Erro no parse das datas
            return (False, 0)
    
    @staticmethod
    def classificar_nfse(result: InvoiceData, validar_prazo: bool = True) -> Tuple[bool, List[str]]:
        """
        Classifica uma NFSe como sucesso ou falha.
        
        Critérios de SUCESSO (Conformidade PAF):
        - Número da Nota preenchido
        - Valor > 0
        - Razão Social (fornecedor_nome) preenchida
        - Prazo de 04 dias úteis ao vencimento (se houver vencimento e validar_prazo=True)
        
        Args:
            result: Dados extraídos da NFSe
            validar_prazo: Se False, ignora validação de prazo (útil para documentos antigos)
            
        Returns:
            Tupla (é_sucesso, lista_de_motivos_falha)
            
        Note:
            Use validar_prazo=False ao processar documentos históricos/antigos onde
            o vencimento já passou e não faz sentido validar os 4 dias úteis.
        """
        motivos = []
        
        # Validações básicas
        tem_numero = result.numero_nota and result.numero_nota.strip()
        tem_valor = result.valor_total > 0
        tem_fornecedor = bool(result.fornecedor_nome and result.fornecedor_nome.strip())
        
        if not tem_numero:
            motivos.append('SEM_NUMERO')
        if not tem_valor:
            motivos.append('VALOR_ZERO')
        if not result.cnpj_prestador:
            motivos.append('SEM_CNPJ')
        if not tem_fornecedor:
            motivos.append('SEM_RAZAO_SOCIAL')
        
        # Validação de prazo (Política 5.9 e POP 4.10) - OPCIONAL
        if validar_prazo and result.vencimento:
            prazo_ok, dias_uteis = ExtractionDiagnostics.validar_prazo_vencimento(
                result.dt_classificacao, result.vencimento
            )
            if not prazo_ok:
                motivos.append(f'PRAZO_INSUFICIENTE_{dias_uteis}d')
        
        # Sucesso: tem campos obrigatórios + prazo OK (se aplicável)
        sucesso = tem_numero and tem_valor and tem_fornecedor
        if validar_prazo and result.vencimento:
            prazo_ok, _ = ExtractionDiagnostics.validar_prazo_vencimento(
                result.dt_classificacao, result.vencimento
            )
            sucesso = sucesso and prazo_ok
        
        return (sucesso, motivos)
    
    @staticmethod
    def classificar_boleto(result: BoletoData, validar_prazo: bool = True) -> Tuple[bool, List[str]]:
        """
        Classifica um Boleto como sucesso ou falha.
        
        Critérios de SUCESSO (Conformidade PAF):
        - Valor > 0
        - Vencimento OU Linha Digitável
        - Razão Social (fornecedor_nome) preenchida
        - Prazo de 04 dias úteis ao vencimento (se validar_prazo=True)
        
        Args:
            result: Dados extraídos do boleto
            validar_prazo: Se False, ignora validação de prazo (útil para documentos antigos)
            
        Returns:
            Tupla (é_sucesso, lista_de_motivos_falha)
            
        Note:
            Use validar_prazo=False ao processar documentos históricos/antigos onde
            o vencimento já passou e não faz sentido validar os 4 dias úteis.
        """
        motivos = []
        
        # Validações básicas
        tem_valor = result.valor_documento > 0
        tem_identificacao = result.vencimento or result.linha_digitavel
        tem_fornecedor = bool(result.fornecedor_nome and result.fornecedor_nome.strip())
        
        if not tem_valor:
            motivos.append('VALOR_ZERO')
        if not result.vencimento:
            motivos.append('SEM_VENCIMENTO')
        if not result.linha_digitavel:
            motivos.append('SEM_LINHA_DIGITAVEL')
        if not tem_fornecedor:
            motivos.append('SEM_RAZAO_SOCIAL')
        
        # Validação de prazo (Política 5.9 e POP 4.10) - OPCIONAL
        prazo_ok = True
        if validar_prazo and result.vencimento:
            prazo_ok, dias_uteis = ExtractionDiagnostics.validar_prazo_vencimento(
                result.dt_classificacao, result.vencimento
            )
            if not prazo_ok:
                motivos.append(f'PRAZO_INSUFICIENTE_{dias_uteis}d')
        
        # Sucesso: tem campos obrigatórios + prazo OK (se validação ativa)
        sucesso = tem_valor and tem_identificacao and tem_fornecedor
        if validar_prazo:
            sucesso = sucesso and prazo_ok
        
        return (sucesso, motivos)
    
    @staticmethod
    def gerar_relatorio_texto(dados: Dict) -> str:
        """
        Gera relatório de qualidade em formato texto.
        
        Args:
            dados: Dicionário com estatísticas de extração contendo:
                - total: Total de arquivos processados
                - nfse_ok: NFSe extraídas com sucesso
                - nfse_falha: NFSe com falhas
                - boleto_ok: Boletos extraídos com sucesso
                - boleto_falha: Boletos com falhas
                - erros: Quantidade de erros críticos
                - nfse_falhas_detalhe: Lista de dict com detalhes das falhas NFSe
                - boleto_falhas_detalhe: Lista de dict com detalhes das falhas Boleto
            
        Returns:
            String formatada do relatório
            
        Examples:
            >>> dados = {'total': 10, 'nfse_ok': 8, 'nfse_falha': 2, 
            ...          'boleto_ok': 5, 'boleto_falha': 1, 'erros': 0,
            ...          'nfse_falhas_detalhe': [], 'boleto_falhas_detalhe': []}
            >>> relatorio = ExtractionDiagnostics.gerar_relatorio_texto(dados)
            >>> assert 'RELATÓRIO DE QUALIDADE' in relatorio
        """
        linhas = []
        linhas.append("=" * 80)
        linhas.append("📊 RELATÓRIO DE QUALIDADE DA EXTRAÇÃO")
        linhas.append("=" * 80)
        linhas.append("")
        
        linhas.append(f"📅 Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        linhas.append(f"📦 Total de arquivos: {dados['total']}")
        linhas.append("")
        
        # NFSe
        linhas.append("--- NFSe ---")
        linhas.append(f"✅ Completas: {dados['nfse_ok']}")
        linhas.append(f"⚠️ Com falhas: {dados['nfse_falha']}")
        total_nfse = dados['nfse_ok'] + dados['nfse_falha']
        if total_nfse > 0:
            taxa = (dados['nfse_ok'] / total_nfse) * 100
            linhas.append(f"📈 Taxa de sucesso: {taxa:.1f}%")
        
        # Boletos
        linhas.append("")
        linhas.append("--- Boletos ---")
        linhas.append(f"✅ Completos: {dados['boleto_ok']}")
        linhas.append(f"⚠️ Com falhas: {dados['boleto_falha']}")
        total_boleto = dados['boleto_ok'] + dados['boleto_falha']
        if total_boleto > 0:
            taxa = (dados['boleto_ok'] / total_boleto) * 100
            linhas.append(f"📈 Taxa de sucesso: {taxa:.1f}%")
        
        linhas.append("")
        linhas.append(f"❌ Erros: {dados['erros']}")
        
        # Detalhes das falhas NFSe
        if dados.get('nfse_falhas_detalhe'):
            linhas.append("")
            linhas.append("=" * 80)
            linhas.append("🔍 FALHAS - NFSe")
            linhas.append("=" * 80)
            for item in dados['nfse_falhas_detalhe']:
                linhas.append("")
                linhas.append(f"📄 {item['arquivo_origem']}")
                linhas.append(f"   Motivo: {item.get('motivo_falha', 'N/A')}")
                linhas.append(f"   Número: {item.get('numero_nota', 'N/A')}")
                linhas.append(f"   Valor: R$ {item.get('valor_total', 0):,.2f}")
        
        # Detalhes das falhas Boletos
        if dados.get('boleto_falhas_detalhe'):
            linhas.append("")
            linhas.append("=" * 80)
            linhas.append("🔍 FALHAS - BOLETOS")
            linhas.append("=" * 80)
            for item in dados['boleto_falhas_detalhe']:
                linhas.append("")
                linhas.append(f"📄 {item['arquivo_origem']}")
                linhas.append(f"   Motivo: {item.get('motivo_falha', 'N/A')}")
                linhas.append(f"   Valor: R$ {item.get('valor_documento', 0):,.2f}")
        
        return "\n".join(linhas)
    
    @staticmethod
    def salvar_relatorio(dados: Dict, caminho_arquivo) -> None:
        """
        Gera e salva o relatório em arquivo de texto.
        
        Args:
            dados: Dicionário com estatísticas de extração
            caminho_arquivo: Path ou string com caminho do arquivo de saída
        """
        relatorio = ExtractionDiagnostics.gerar_relatorio_texto(dados)
        
        with open(caminho_arquivo, 'w', encoding='utf-8') as f:
            f.write(relatorio)
    
    @staticmethod
    def diagnosticar_tipo_falha(arquivo: str, texto_snippet: str, numero_nota: str, valor: float) -> str:
        """
        Tenta classificar automaticamente o tipo de falha de extração.
        
        Args:
            arquivo: Nome do arquivo origem
            texto_snippet: Trecho do texto extraído
            numero_nota: Número da nota extraído (pode ser vazio)
            valor: Valor extraído
            
        Returns:
            String com diagnóstico sugerido
            
        Examples:
            >>> diag = ExtractionDiagnostics.diagnosticar_tipo_falha(
            ...     "boleto123.pdf", "BOLETO BANCÁRIO", "", 0.0
            ... )
            >>> assert "BOLETO/RECIBO" in diag
        """
        texto_lower = texto_snippet.lower()
        arquivo_lower = arquivo.lower()
        
        # Verifica se é boleto/recibo (não deveria ser processado como NFSe)
        if "boleto" in arquivo_lower or "recibo" in arquivo_lower:
            return "BOLETO/RECIBO (Ignorar se não for NF)."
        
        # Verifica se é locação (layout atípico)
        if "locação" in texto_lower or "locacao" in texto_lower:
            return "LOCAÇÃO (Layout atípico)."
        
        # Diagnóstico específico por campo
        if valor == 0.0 or not valor:
            return "Regex de VALOR falhou."
        
        if not numero_nota or numero_nota == "VAZIO":
            return "Regex de NÚMERO DA NOTA falhou."
        
        return "Falha genérica de extração."
