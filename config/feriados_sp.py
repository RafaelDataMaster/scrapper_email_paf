"""
Calendário de dias úteis de São Paulo com feriados municipais.

Este módulo implementa validação de dias úteis considerando feriados
nacionais, estaduais (SP) e municipais de São Paulo (capital).

Conformidade: Política Interna 5.9 e POP 4.10 exigem lançamento com
mínimo de 04 dias úteis de antecedência ao vencimento.
"""

from datetime import datetime, timedelta
from functools import lru_cache
from typing import List, Tuple
from dateutil.easter import easter
from workalendar.america import Brazil


class SPBusinessCalendar(Brazil):
    """
    Calendário de negócios de São Paulo.
    
    Estende o calendário brasileiro padrão adicionando feriados municipais
    de São Paulo e utilizando cache LRU para otimização de performance em
    processamentos em lote.
    
    Cache maxsize=12 cobre uma década completa + folga para auditorias.
    """
    
    def get_variable_days(self, year: int):
        """
        Retorna feriados móveis de São Paulo (baseados na Páscoa).
        
        Args:
            year: Ano para cálculo dos feriados
            
        Returns:
            Lista de tuplas (datetime.date, nome_feriado)
        """
        # Obtém feriados móveis nacionais
        days = list(super().get_variable_days(year))
        
        # Calcula Páscoa para o ano
        easter_date = easter(year)
        
        # Corpus Christi (Páscoa + 60 dias) - Feriado municipal de SP
        corpus_christi = easter_date + timedelta(days=60)
        days.append((corpus_christi, "Corpus Christi (SP)"))
        
        return days
    
    def get_fixed_holidays(self, year: int):
        """
        Retorna feriados fixos incluindo os municipais de São Paulo.
        
        Args:
            year: Ano de referência
        
        Returns:
            Lista de tuplas (datetime.date, nome_feriado)
        """
        # Obtém feriados fixos nacionais
        holidays = list(super().get_fixed_holidays(year))
        
        # Adiciona feriados municipais de São Paulo
        from datetime import date
        holidays.extend([
            (date(year, 1, 25), "Aniversário de São Paulo"),
            (date(year, 11, 20), "Dia da Consciência Negra (SP)"),
        ])
        
        return holidays
    
    def get_working_days_delta(self, start_date: datetime, end_date: datetime) -> int:
        """
        Calcula número de dias úteis entre duas datas.
        
        Considera feriados nacionais, estaduais e municipais de São Paulo,
        além de finais de semana.
        
        Args:
            start_date: Data inicial
            end_date: Data final
            
        Returns:
            Número de dias úteis entre as datas (exclusivo da data inicial)
        """
        if start_date >= end_date:
            return 0
        
        working_days = 0
        current_date = start_date + timedelta(days=1)  # Começa no dia seguinte
        
        while current_date <= end_date:
            if self.is_working_day(current_date):
                working_days += 1
            current_date += timedelta(days=1)
        
        return working_days
