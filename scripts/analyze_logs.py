#!/usr/bin/env python3
"""
Script para análise automatizada de logs do sistema de extração de documentos.

Analisa o arquivo logs/scrapper.log para identificar:
- Erros e warnings críticos
- PDFs protegidos por senha
- Lotes lentos (timeouts)
- Falhas de extração
- Estatísticas de uso de extratores
- Problemas operacionais

Uso:
    python scripts/analyze_logs.py                    # Análise completa
    python scripts/analyze_logs.py --today            # Apenas logs de hoje
    python scripts/analyze_logs.py --errors-only      # Apenas erros
    python scripts/analyze_logs.py --batch <id>       # Buscar lote específico
    python scripts/analyze_logs.py --summary          # Resumo estatístico
    python scripts/analyze_logs.py --output report.md # Salvar relatório
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Adiciona o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class LogEntry:
    """Representa uma entrada de log."""
    timestamp: datetime
    module: str
    level: str
    message: str
    raw_line: str


@dataclass
class BatchStats:
    """Estatísticas de um lote específico."""
    batch_id: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_seconds: float = 0.0
    is_slow: bool = False
    extractors_tried: List[str] = field(default_factory=list)
    extractor_used: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    pdf_count: int = 0
    documents_extracted: int = 0


@dataclass
class LogAnalysis:
    """Resultado da análise de logs."""
    # Estatísticas gerais
    total_lines: int = 0
    date_range: Tuple[Optional[datetime], Optional[datetime]] = (None, None)
    
    # Contadores por nível
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    
    # Problemas específicos
    password_protected_pdfs: List[Dict[str, Any]] = field(default_factory=list)
    pdf_open_errors: List[Dict[str, Any]] = field(default_factory=list)
    slow_batches: List[BatchStats] = field(default_factory=list)
    no_extractor_matches: List[Dict[str, Any]] = field(default_factory=list)
    
    # Estatísticas de extratores
    extractor_usage: Counter = field(default_factory=Counter)
    extractor_success: Counter = field(default_factory=Counter)
    extractor_failure: Counter = field(default_factory=Counter)
    
    # Estatísticas de lotes
    batch_stats: Dict[str, BatchStats] = field(default_factory=dict)
    total_batches: int = 0
    completed_batches: int = 0
    failed_batches: int = 0
    
    # Sessões
    sessions: List[Dict[str, Any]] = field(default_factory=list)
    
    # Erros por módulo
    errors_by_module: Counter = field(default_factory=Counter)
    warnings_by_module: Counter = field(default_factory=Counter)
    
    # Padrões encontrados
    common_errors: List[Tuple[str, int]] = field(default_factory=list)
    common_warnings: List[Tuple[str, int]] = field(default_factory=list)


class LogParser:
    """Parser para arquivo de log."""
    
    # Regex para parsear linhas de log
    LOG_PATTERN = re.compile(
        r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+-\s+([^\s]+)\s+-\s+(\w+)\s+-\s+(.*)$'
    )
    
    # Padrões para identificar tipos específicos de log
    BATCH_PATTERN = re.compile(r'\[(\d+)/(\d+)\]\s+(email_[\w_]+)')
    SLOW_BATCH_PATTERN = re.compile(r'\[(\d+)/(\d+)\]\s+(email_[\w_]+).*?(\d+\.\d+)s.*LENTO')
    BATCH_DURATION_PATTERN = re.compile(r'(email_[\w_]+).*?(\d+\.\d+)s')
    PDF_PASSWORD_PATTERN = re.compile(r'Falha ao desbloquear PDF\s+([^\s]+)')
    PDF_OPEN_ERROR_PATTERN = re.compile(r'Erro ao abrir PDF\s+([^\s]+)')
    EXTRACTOR_TRY_PATTERN = re.compile(r'Testando extrator:\s+(\w+)')
    EXTRACTOR_RESULT_PATTERN = re.compile(r'Resultado do can_handle de\s+(\w+):\s+(\w+)')
    NO_EXTRACTOR_PATTERN = re.compile(r'Nenhum extrator compatível')
    SESSION_START_PATTERN = re.compile(r'Iniciando ingest[ãa]o')
    SESSION_END_PATTERN = re.compile(r'Ingest[ãa]o\s+(COMPLETED|INTERRUPTED|FINISHED)')
    
    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.entries: List[LogEntry] = []
        
    def parse(self, filter_date: Optional[datetime] = None) -> List[LogEntry]:
        """Parseia o arquivo de log."""
        entries = []
        
        if not self.log_path.exists():
            print(f"❌ Arquivo de log não encontrado: {self.log_path}")
            return entries
        
        with open(self.log_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                    
                entry = self._parse_line(line)
                if entry:
                    # Filtro por data
                    if filter_date:
                        if entry.timestamp.date() != filter_date.date():
                            continue
                    entries.append(entry)
                else:
                    # Linha pode ser continuação da anterior (stack trace, etc)
                    if entries and line_num > 1:
                        entries[-1].message += f"\n{line}"
                        entries[-1].raw_line += f"\n{line}"
        
        self.entries = entries
        return entries
    
    def _parse_line(self, line: str) -> Optional[LogEntry]:
        """Parseia uma única linha de log."""
        match = self.LOG_PATTERN.match(line)
        if not match:
            return None
        
        timestamp_str, module, level, message = match.groups()
        
        try:
            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return None
        
        return LogEntry(
            timestamp=timestamp,
            module=module,
            level=level.upper(),
            message=message,
            raw_line=line
        )


class LogAnalyzer:
    """Analisador de logs."""
    
    def __init__(self, entries: List[LogEntry]):
        self.entries = entries
        self.analysis = LogAnalysis(total_lines=len(entries))
        
    def analyze(self) -> LogAnalysis:
        """Executa análise completa dos logs."""
        if not self.entries:
            return self.analysis
        
        # Determina range de datas
        timestamps = [e.timestamp for e in self.entries]
        self.analysis.date_range = (min(timestamps), max(timestamps))
        
        # Análise por tipo de entrada
        self._analyze_levels()
        self._analyze_batches()
        self._analyze_extractors()
        self._analyze_pdf_issues()
        self._analyze_sessions()
        self._analyze_common_patterns()
        
        return self.analysis
    
    def _analyze_levels(self):
        """Conta entradas por nível de log."""
        for entry in self.entries:
            if entry.level == 'ERROR' or entry.level == 'CRITICAL' or entry.level == 'FATAL':
                self.analysis.error_count += 1
                self.analysis.errors_by_module[entry.module] += 1
            elif entry.level == 'WARNING':
                self.analysis.warning_count += 1
                self.analysis.warnings_by_module[entry.module] += 1
            elif entry.level == 'INFO':
                self.analysis.info_count += 1
    
    def _analyze_batches(self):
        """Analisa estatísticas de lotes."""
        current_batch: Optional[str] = None
        _batch_start: Optional[datetime] = None
        
        for entry in self.entries:
            # Identifica batch no log
            batch_match = LogParser.BATCH_PATTERN.search(entry.message)
            if batch_match:
                _, _, batch_id = batch_match.groups()
                current_batch = batch_id
                
                if batch_id not in self.analysis.batch_stats:
                    self.analysis.batch_stats[batch_id] = BatchStats(batch_id=batch_id)
                    self.analysis.total_batches += 1
                
                # Verifica se é lento
                slow_match = LogParser.SLOW_BATCH_PATTERN.search(entry.message)
                if slow_match:
                    duration = float(slow_match.group(4))
                    self.analysis.batch_stats[batch_id].is_slow = True
                    self.analysis.batch_stats[batch_id].duration_seconds = duration
                    self.analysis.slow_batches.append(self.analysis.batch_stats[batch_id])
                else:
                    # Tenta extrair duração mesmo sem flag de LENTO
                    dur_match = LogParser.BATCH_DURATION_PATTERN.search(entry.message)
                    if dur_match:
                        duration = float(dur_match.group(2))
                        self.analysis.batch_stats[batch_id].duration_seconds = duration
                        if duration > 20:  # Considera lento acima de 20s
                            self.analysis.batch_stats[batch_id].is_slow = True
                            if self.analysis.batch_stats[batch_id] not in self.analysis.slow_batches:
                                self.analysis.slow_batches.append(self.analysis.batch_stats[batch_id])
            
            # Acumula erros/warnings por batch
            if current_batch and current_batch in self.analysis.batch_stats:
                if entry.level in ('ERROR', 'CRITICAL'):
                    self.analysis.batch_stats[current_batch].errors.append(entry.message)
                    self.analysis.failed_batches += 1
                elif entry.level == 'WARNING':
                    self.analysis.batch_stats[current_batch].warnings.append(entry.message)
    
    def _analyze_extractors(self):
        """Analisa uso de extratores."""
        current_batch: Optional[str] = None
        
        for entry in self.entries:
            # Identifica batch atual
            batch_match = LogParser.BATCH_PATTERN.search(entry.message)
            if batch_match:
                current_batch = batch_match.group(3)
            
            # Extrator sendo testado
            try_match = LogParser.EXTRACTOR_TRY_PATTERN.search(entry.message)
            if try_match:
                extractor_name = try_match.group(1)
                self.analysis.extractor_usage[extractor_name] += 1
                if current_batch and current_batch in self.analysis.batch_stats:
                    if extractor_name not in self.analysis.batch_stats[current_batch].extractors_tried:
                        self.analysis.batch_stats[current_batch].extractors_tried.append(extractor_name)
            
            # Resultado do extrator
            result_match = LogParser.EXTRACTOR_RESULT_PATTERN.search(entry.message)
            if result_match:
                extractor_name, result = result_match.groups()
                if result.lower() == 'true':
                    self.analysis.extractor_success[extractor_name] += 1
                    if current_batch and current_batch in self.analysis.batch_stats:
                        self.analysis.batch_stats[current_batch].extractor_used = extractor_name
                else:
                    self.analysis.extractor_failure[extractor_name] += 1
            
            # Nenhum extrator compatível
            if LogParser.NO_EXTRACTOR_PATTERN.search(entry.message):
                self.analysis.no_extractor_matches.append({
                    'timestamp': entry.timestamp,
                    'batch_id': current_batch,
                    'message': entry.message
                })
    
    def _analyze_pdf_issues(self):
        """Analisa problemas com PDFs."""
        for entry in self.entries:
            # PDFs protegidos por senha
            pwd_match = LogParser.PDF_PASSWORD_PATTERN.search(entry.message)
            if pwd_match:
                pdf_name = pwd_match.group(1)
                self.analysis.password_protected_pdfs.append({
                    'timestamp': entry.timestamp,
                    'pdf_name': pdf_name,
                    'module': entry.module,
                    'message': entry.message
                })
            
            # Erros ao abrir PDFs
            open_match = LogParser.PDF_OPEN_ERROR_PATTERN.search(entry.message)
            if open_match:
                pdf_name = open_match.group(1)
                self.analysis.pdf_open_errors.append({
                    'timestamp': entry.timestamp,
                    'pdf_name': pdf_name,
                    'module': entry.module,
                    'message': entry.message
                })
    
    def _analyze_sessions(self):
        """Analisa sessões de processamento."""
        current_session: Optional[Dict[str, Any]] = None
        
        for entry in self.entries:
            # Início de sessão
            if LogParser.SESSION_START_PATTERN.search(entry.message):
                current_session = {
                    'start_time': entry.timestamp,
                    'end_time': None,
                    'status': 'RUNNING',
                    'batches_processed': 0,
                    'emails_scanned': 0,
                    'documents_extracted': 0
                }
            
            # Fim de sessão
            end_match = LogParser.SESSION_END_PATTERN.search(entry.message)
            if end_match and current_session:
                status = end_match.group(1)
                current_session['end_time'] = entry.timestamp
                current_session['status'] = status
                self.analysis.sessions.append(current_session)
                current_session = None
            
            # Extrai métricas da sessão se disponíveis
            if current_session:
                # Tenta encontrar métricas em mensagens de info
                if 'emails escaneados' in entry.message.lower():
                    # Extrai números da mensagem
                    numbers = re.findall(r'(\d+)\s+emails?', entry.message.lower())
                    if numbers:
                        current_session['emails_scanned'] = int(numbers[0])
                
                if 'documentos extra' in entry.message.lower():
                    numbers = re.findall(r'(\d+)\s+documentos?', entry.message.lower())
                    if numbers:
                        current_session['documents_extracted'] = int(numbers[0])
    
    def _analyze_common_patterns(self):
        """Analisa padrões comuns de erros e warnings."""
        error_messages = []
        warning_messages = []
        
        for entry in self.entries:
            # Limpa a mensagem para agrupar similares
            clean_msg = self._clean_message_for_grouping(entry.message)
            
            if entry.level in ('ERROR', 'CRITICAL'):
                error_messages.append(clean_msg)
            elif entry.level == 'WARNING':
                warning_messages.append(clean_msg)
        
        # Conta ocorrências
        error_counter = Counter(error_messages)
        warning_counter = Counter(warning_messages)
        
        self.analysis.common_errors = error_counter.most_common(10)
        self.analysis.common_warnings = warning_counter.most_common(10)
    
    def _clean_message_for_grouping(self, message: str) -> str:
        """Limpa mensagem para agrupamento (remove IDs únicos, etc)."""
        # Remove timestamps dentro da mensagem
        cleaned = re.sub(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}', '', message)
        # Remove IDs de email específicos
        cleaned = re.sub(r'email_\d{8}_\d{6}_\w+', 'email_<ID>', cleaned)
        # Remove números específicos de lote
        cleaned = re.sub(r'\[\d+/\d+\]', '[X/Y]', cleaned)
        # Remove nomes de arquivos PDF específicos
        cleaned = re.sub(r'\d{10,}\.pdf', '<PDF>.pdf', cleaned)
        # Normaliza espaços
        cleaned = ' '.join(cleaned.split())
        return cleaned


class ReportGenerator:
    """Gerador de relatórios."""
    
    def __init__(self, analysis: LogAnalysis):
        self.analysis = analysis
    
    def generate_console_report(self) -> str:
        """Gera relatório para exibição no console."""
        lines = []
        
        lines.append("=" * 80)
        lines.append("RELATORIO DE ANALISE DE LOGS")
        lines.append("=" * 80)
        
        # Período analisado
        start, end = self.analysis.date_range
        if start and end:
            lines.append(f"\n[PERIODO] Analisado: {start.strftime('%Y-%m-%d %H:%M')} ate {end.strftime('%Y-%m-%d %H:%M')}")
            duration = end - start
            lines.append(f"[DURACAO] Total: {duration}")
        
        lines.append(f"[ENTRADAS] Total analisadas: {self.analysis.total_lines}")
        
        # Resumo por nível
        lines.append("\n" + "-" * 40)
        lines.append("RESUMO POR NÍVEL")
        lines.append("-" * 40)
        lines.append(f"   [ERROS] {self.analysis.error_count}")
        lines.append(f"   [WARNINGS] {self.analysis.warning_count}")
        lines.append(f"   [INFO] {self.analysis.info_count}")
        
        # Problemas críticos
        lines.append("\n" + "-" * 40)
        lines.append("PROBLEMAS CRÍTICOS IDENTIFICADOS")
        lines.append("-" * 40)
        
        lines.append(f"\n[PDF-SENHA] Protegidos por senha: {len(self.analysis.password_protected_pdfs)}")
        if self.analysis.password_protected_pdfs:
            for pdf in self.analysis.password_protected_pdfs[:5]:
                lines.append(f"   • {pdf['pdf_name']} ({pdf['timestamp'].strftime('%H:%M:%S')})")
            if len(self.analysis.password_protected_pdfs) > 5:
                lines.append(f"   ... e mais {len(self.analysis.password_protected_pdfs) - 5} PDFs")
        
        lines.append(f"\n[PDF-ERRO] Erros ao abrir PDFs: {len(self.analysis.pdf_open_errors)}")
        if self.analysis.pdf_open_errors:
            for pdf in self.analysis.pdf_open_errors[:5]:
                lines.append(f"   • {pdf['pdf_name']} ({pdf['timestamp'].strftime('%H:%M:%S')})")
            if len(self.analysis.pdf_open_errors) > 5:
                lines.append(f"   ... e mais {len(self.analysis.pdf_open_errors) - 5} erros")
        
        lines.append(f"\n[LOTES-LENTOS] (>20s): {len(self.analysis.slow_batches)}")
        if self.analysis.slow_batches:
            # Ordena por duração (mais lentos primeiro)
            sorted_slow = sorted(self.analysis.slow_batches, key=lambda x: x.duration_seconds, reverse=True)
            for batch in sorted_slow[:5]:
                lines.append(f"   • {batch.batch_id}: {batch.duration_seconds:.1f}s")
            if len(sorted_slow) > 5:
                lines.append(f"   ... e mais {len(sorted_slow) - 5} lotes lentos")
        
        lines.append(f"\n[SEM-EXTRATOR] Documentos sem extrator compativel: {len(self.analysis.no_extractor_matches)}")
        
        # Estatísticas de extratores
        if self.analysis.extractor_usage:
            lines.append("\n" + "-" * 40)
            lines.append("USO DE EXTRATORES")
            lines.append("-" * 40)
            
            for extractor, count in self.analysis.extractor_usage.most_common():
                success = self.analysis.extractor_success.get(extractor, 0)
                failure = self.analysis.extractor_failure.get(extractor, 0)
                success_rate = (success / (success + failure) * 100) if (success + failure) > 0 else 0
                lines.append(f"   [{extractor}]")
                lines.append(f"      Testado: {count}x | Sucesso: {success} | Falha: {failure} | Taxa: {success_rate:.1f}%")
        
        # Erros por módulo
        if self.analysis.errors_by_module:
            lines.append("\n" + "-" * 40)
            lines.append("ERROS POR MÓDULO")
            lines.append("-" * 40)
            for module, count in self.analysis.errors_by_module.most_common():
                lines.append(f"   {module}: {count} erros")
        
        # Padrões comuns
        if self.analysis.common_errors:
            lines.append("\n" + "-" * 40)
            lines.append("ERROS MAIS COMUNS")
            lines.append("-" * 40)
            for error, count in self.analysis.common_errors[:5]:
                lines.append(f"   ({count}x) {error[:70]}{'...' if len(error) > 70 else ''}")
        
        if self.analysis.common_warnings:
            lines.append("\n" + "-" * 40)
            lines.append("WARNINGS MAIS COMUNS")
            lines.append("-" * 40)
            for warning, count in self.analysis.common_warnings[:5]:
                lines.append(f"   ({count}x) {warning[:70]}{'...' if len(warning) > 70 else ''}")
        
        # Sessões
        if self.analysis.sessions:
            lines.append("\n" + "-" * 40)
            lines.append("SESSÕES DE PROCESSAMENTO")
            lines.append("-" * 40)
            for i, session in enumerate(self.analysis.sessions, 1):
                status_emoji = "[OK]" if session['status'] == 'COMPLETED' else "[AVISO]"
                lines.append(f"   {status_emoji} Sessão {i}:")
                lines.append(f"      Início: {session['start_time'].strftime('%Y-%m-%d %H:%M:%S')}")
                if session['end_time']:
                    lines.append(f"      Fim: {session['end_time'].strftime('%Y-%m-%d %H:%M:%S')}")
                    duration = session['end_time'] - session['start_time']
                    lines.append(f"      Duração: {duration}")
                lines.append(f"      Status: {session['status']}")
                if session['emails_scanned']:
                    lines.append(f"      E-mails: {session['emails_scanned']}")
                if session['documents_extracted']:
                    lines.append(f"      Documentos: {session['documents_extracted']}")
        
        # Recomendações
        lines.append("\n" + "=" * 80)
        lines.append("RECOMENDACOES")
        lines.append("=" * 80)
        
        recommendations = self._generate_recommendations()
        for rec in recommendations:
            lines.append(f"   • {rec}")
        
        lines.append("\n" + "=" * 80)
        
        return "\n".join(lines)
    
    def generate_markdown_report(self) -> str:
        """Gera relatório em formato Markdown."""
        lines = []
        
        lines.append("# Relatorio de Analise de Logs")
        lines.append("")
        
        # Metadata
        start, end = self.analysis.date_range
        if start and end:
            lines.append(f"**Período:** {start.strftime('%Y-%m-%d %H:%M')} - {end.strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"**Total de entradas:** {self.analysis.total_lines}")
        lines.append("")
        
        # Resumo
        lines.append("## Resumo")
        lines.append("")
        lines.append(f"- Erros: {self.analysis.error_count}")
        lines.append(f"- Warnings: {self.analysis.warning_count}")
        lines.append(f"- Info: {self.analysis.info_count}")
        lines.append(f"- PDFs protegidos por senha: {len(self.analysis.password_protected_pdfs)}")
        lines.append(f"- Erros ao abrir PDFs: {len(self.analysis.pdf_open_errors)}")
        lines.append(f"- Lotes lentos: {len(self.analysis.slow_batches)}")
        lines.append(f"- Sem extrator compativel: {len(self.analysis.no_extractor_matches)}")
        lines.append("")
        
        # PDFs protegidos
        if self.analysis.password_protected_pdfs:
            lines.append("## PDFs Protegidos por Senha")
            lines.append("")
            lines.append("| Timestamp | PDF | Módulo |")
            lines.append("|-----------|-----|--------|")
            for pdf in self.analysis.password_protected_pdfs[:20]:
                lines.append(f"| {pdf['timestamp'].strftime('%Y-%m-%d %H:%M:%S')} | {pdf['pdf_name']} | {pdf['module']} |")
            if len(self.analysis.password_protected_pdfs) > 20:
                lines.append(f"| ... | +{len(self.analysis.password_protected_pdfs) - 20} mais | ... |")
            lines.append("")
        
        # Lotes lentos
        if self.analysis.slow_batches:
            lines.append("## Lotes Lentos (>20s)")
            lines.append("")
            lines.append("| Batch ID | Duração (s) | Extratores Testados | Erros |")
            lines.append("|----------|-------------|---------------------|-------|")
            sorted_slow = sorted(self.analysis.slow_batches, key=lambda x: x.duration_seconds, reverse=True)
            for batch in sorted_slow[:20]:
                extractors = ", ".join(batch.extractors_tried[:3]) if batch.extractors_tried else "N/A"
                errors = len(batch.errors)
                lines.append(f"| {batch.batch_id} | {batch.duration_seconds:.1f} | {extractors} | {errors} |")
            lines.append("")
        
        # Extratores
        if self.analysis.extractor_usage:
            lines.append("## Estatísticas de Extratores")
            lines.append("")
            lines.append("| Extrator | Testado | Sucesso | Falha | Taxa % |")
            lines.append("|----------|---------|---------|-------|--------|")
            for extractor, count in self.analysis.extractor_usage.most_common():
                success = self.analysis.extractor_success.get(extractor, 0)
                failure = self.analysis.extractor_failure.get(extractor, 0)
                rate = (success / (success + failure) * 100) if (success + failure) > 0 else 0
                lines.append(f"| {extractor} | {count} | {success} | {failure} | {rate:.1f}% |")
            lines.append("")
        
        # Recomendações
        lines.append("## Recomendacoes")
        lines.append("")
        for rec in self._generate_recommendations():
            lines.append(f"- {rec}")
        lines.append("")
        
        return "\n".join(lines)
    
    def _generate_recommendations(self) -> List[str]:
        """Gera recomendações baseadas na análise."""
        recommendations = []
        
        if len(self.analysis.password_protected_pdfs) > 5:
            recommendations.append(
                f"Muitos PDFs protegidos por senha ({len(self.analysis.password_protected_pdfs)}). "
                "Verifique se há CNPJs cadastrados incorretamente ou senhas padrão não cobertas."
            )
        
        if len(self.analysis.slow_batches) > 10:
            avg_duration = sum(b.duration_seconds for b in self.analysis.slow_batches) / len(self.analysis.slow_batches)
            recommendations.append(
                f"Detectados {len(self.analysis.slow_batches)} lotes lentos. "
                f"Duração média: {avg_duration:.1f}s. Considere otimizar timeouts ou verificar PDFs muito grandes."
            )
        
        if self.analysis.no_extractor_matches:
            recommendations.append(
                f"{len(self.analysis.no_extractor_matches)} documentos não tiveram extrator compatível. "
                "Considere criar novos extratores ou verificar se são documentos válidos."
            )
        
        # Verifica extratores com baixa taxa de sucesso
        for extractor, _count in self.analysis.extractor_usage.most_common():
            success = self.analysis.extractor_success.get(extractor, 0)
            failure = self.analysis.extractor_failure.get(extractor, 0)
            total = success + failure
            if total > 10:
                rate = success / total
                if rate < 0.1:  # Menos de 10% de sucesso
                    recommendations.append(
                        f"{extractor} tem apenas {rate*100:.1f}% de taxa de sucesso. "
                        "Verifique se o padrão de detecção está muito restritivo."
                    )
        
        if not recommendations:
            recommendations.append("Nenhum problema crítico identificado nos logs analisados.")
        
        return recommendations


def find_batch_in_logs(entries: List[LogEntry], batch_id: str) -> List[LogEntry]:
    """Busca entradas relacionadas a um batch específico."""
    batch_pattern = re.compile(re.escape(batch_id))
    return [e for e in entries if batch_pattern.search(e.raw_line)]


def main():
    """Função principal."""
    parser = argparse.ArgumentParser(
        description='Analisa logs do sistema de extração de documentos'
    )
    parser.add_argument(
        '--log-file',
        type=str,
        default='logs/scrapper.log',
        help='Caminho do arquivo de log (default: logs/scrapper.log)'
    )
    parser.add_argument(
        '--today',
        action='store_true',
        help='Analisa apenas logs de hoje'
    )
    parser.add_argument(
        '--errors-only',
        action='store_true',
        help='Mostra apenas erros e warnings'
    )
    parser.add_argument(
        '--batch',
        type=str,
        metavar='ID',
        help='Busca logs específicos de um batch (ex: email_20260126_100118_e63793d2)'
    )
    parser.add_argument(
        '--summary',
        action='store_true',
        help='Mostra apenas resumo estatístico'
    )
    parser.add_argument(
        '--output',
        '-o',
        type=str,
        help='Salva relatório em arquivo (Markdown)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=0,
        help='Limita análise às últimas N linhas (0 = todas)'
    )
    
    args = parser.parse_args()
    
    log_path = Path(args.log_file)
    
    # Determina filtro de data
    filter_date = None
    if args.today:
        filter_date = datetime.now()
    
    # Parseia logs
    print(f"[ANALISE] Analisando logs: {log_path}")
    if filter_date:
        print(f"[DATA] Filtrando por data: {filter_date.date()}")
    
    parser_obj = LogParser(log_path)
    entries = parser_obj.parse(filter_date=filter_date)
    
    if not entries:
        print("[ERRO] Nenhuma entrada de log encontrada.")
        return 1
    
    print(f"[OK] {len(entries)} entradas encontradas")
    
    # Modo batch específico
    if args.batch:
        batch_entries = find_batch_in_logs(entries, args.batch)
        print(f"\n[LOTE] Logs para batch: {args.batch}")
        print("=" * 80)
        for entry in batch_entries:
            level_emoji = "[ERRO]" if entry.level == 'ERROR' else "[WARN]" if entry.level == 'WARNING' else "[INFO]"
            print(f"{level_emoji} [{entry.timestamp.strftime('%H:%M:%S')}] [{entry.level}] {entry.module}")
            print(f"   {entry.message[:200]}{'...' if len(entry.message) > 200 else ''}")
            print()
        return 0
    
    # Analisa
    analyzer = LogAnalyzer(entries)
    analysis = analyzer.analyze()
    
    # Gera relatório
    report_gen = ReportGenerator(analysis)
    
    if args.errors_only:
        # Mostra apenas erros
        print("\n[ERROS] ENCONTRADOS:")
        print("=" * 80)
        for entry in entries:
            if entry.level in ('ERROR', 'CRITICAL', 'FATAL'):
                print(f"\n[{entry.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {entry.module}")
                print(f"{entry.message}")
    
    elif args.summary:
        # Apenas resumo
        print(f"\n{'='*40}")
        print("RESUMO")
        print(f"{'='*40}")
        print(f"Erros: {analysis.error_count}")
        print(f"Warnings: {analysis.warning_count}")
        print(f"PDFs protegidos: {len(analysis.password_protected_pdfs)}")
        print(f"PDFs com erro: {len(analysis.pdf_open_errors)}")
        print(f"Lotes lentos: {len(analysis.slow_batches)}")
        print(f"Sem extrator: {len(analysis.no_extractor_matches)}")
    
    else:
        # Relatório completo
        report = report_gen.generate_console_report()
        print(report)
        
        # Salva em arquivo se solicitado
        if args.output:
            md_report = report_gen.generate_markdown_report()
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(md_report)
            print(f"\n💾 Relatório salvo em: {output_path}")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
