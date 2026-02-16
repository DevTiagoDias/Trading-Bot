"""
Order Manager - Gestor de Execução de Ordens
Lida com execução robusta de ordens no MT5 com tratamento de erros
"""

import MetaTrader5 as mt5
from typing import Optional, Dict, Any, Tuple
from enum import Enum
from datetime import datetime
import time
from core.logger import get_logger
from strategies.base import TradingSignal, SignalType


class OrderType(Enum):
    """Tipos de ordem MT5"""
    BUY = mt5.ORDER_TYPE_BUY
    SELL = mt5.ORDER_TYPE_SELL
    BUY_LIMIT = mt5.ORDER_TYPE_BUY_LIMIT
    SELL_LIMIT = mt5.ORDER_TYPE_SELL_LIMIT
    BUY_STOP = mt5.ORDER_TYPE_BUY_STOP
    SELL_STOP = mt5.ORDER_TYPE_SELL_STOP


class FillingType(Enum):
    """Tipos de preenchimento de ordem"""
    FOK = mt5.ORDER_FILLING_FOK  # Fill or Kill
    IOC = mt5.ORDER_FILLING_IOC  # Immediate or Cancel
    RETURN = mt5.ORDER_FILLING_RETURN  # Return


class OrderResult:
    """Resultado de uma operação de ordem"""
    
    def __init__(
        self,
        success: bool,
        ticket: int = 0,
        retcode: int = 0,
        comment: str = "",
        request: Optional[Dict] = None,
        volume: float = 0.0,
        price: float = 0.0
    ):
        self.success = success
        self.ticket = ticket
        self.retcode = retcode
        self.comment = comment
        self.request = request
        self.volume = volume
        self.price = price
        self.timestamp = datetime.now()

    def __repr__(self) -> str:
        status = "SUCCESS" if self.success else "FAILED"
        return f"OrderResult({status}, ticket={self.ticket}, retcode={self.retcode})"


class OrderManager:
    """
    Gerenciador de execução de ordens
    Lida com envio, modificação e fechamento de ordens com retry logic
    """

    # Códigos de retorno MT5
    RETCODE_SUCCESS = 10009
    RETCODE_DONE = 10008
    RETCODE_PLACED = 10009
    RETCODE_REQUOTE = 10004
    RETCODE_REJECT = 10006
    RETCODE_INVALID_PRICE = 10016
    RETCODE_INVALID_STOPS = 10016
    RETCODE_INVALID_VOLUME = 10014
    RETCODE_MARKET_CLOSED = 10018
    RETCODE_NO_MONEY = 10019
    RETCODE_PRICE_OFF = 10015
    RETCODE_INVALID_FILL = 10030
    RETCODE_TRADE_DISABLED = 10017

    def __init__(self, magic_number: int = 123456, deviation: int = 20):
        """
        Args:
            magic_number: Número mágico para identificar ordens do bot
            deviation: Desvio máximo de preço permitido em pontos
        """
        self.logger = get_logger()
        self.magic_number = magic_number
        self.deviation = deviation
        
        self.logger.info(f"OrderManager inicializado (Magic: {magic_number}, Deviation: {deviation})")

    def execute_signal(
        self,
        signal: TradingSignal,
        volume: float,
        comment: str = ""
    ) -> OrderResult:
        """
        Executa um sinal de trading
        
        Args:
            signal: Sinal a executar
            volume: Volume da ordem
            comment: Comentário da ordem
            
        Returns:
            OrderResult com resultado da execução
        """
        if signal.signal_type == SignalType.BUY:
            return self.open_position(
                symbol=signal.symbol,
                order_type=OrderType.BUY,
                volume=volume,
                sl=signal.stop_loss,
                tp=signal.take_profit,
                comment=comment or f"{signal.reason[:30]}"
            )
        
        elif signal.signal_type == SignalType.SELL:
            return self.open_position(
                symbol=signal.symbol,
                order_type=OrderType.SELL,
                volume=volume,
                sl=signal.stop_loss,
                tp=signal.take_profit,
                comment=comment or f"{signal.reason[:30]}"
            )
        
        else:
            self.logger.warning(f"Tipo de sinal não suportado para execução: {signal.signal_type}")
            return OrderResult(False, comment="Tipo de sinal não suportado")

    def open_position(
        self,
        symbol: str,
        order_type: OrderType,
        volume: float,
        price: Optional[float] = None,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: str = "",
        max_retries: int = 3
    ) -> OrderResult:
        """
        Abre uma posição
        
        Args:
            symbol: Símbolo
            order_type: Tipo de ordem (BUY ou SELL)
            volume: Volume
            price: Preço (None para market)
            sl: Stop Loss
            tp: Take Profit
            comment: Comentário
            max_retries: Máximo de tentativas
            
        Returns:
            OrderResult
        """
        # Obtém informações do símbolo
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            error_msg = f"Símbolo {symbol} não encontrado"
            self.logger.error(error_msg)
            return OrderResult(False, comment=error_msg)

        # Verifica se o símbolo está visível
        if not symbol_info.visible:
            if not mt5.symbol_select(symbol, True):
                error_msg = f"Falha ao selecionar símbolo {symbol}"
                self.logger.error(error_msg)
                return OrderResult(False, comment=error_msg)

        # Determina tipo de preenchimento automaticamente
        filling_type = self._get_filling_type(symbol_info)
        
        # Normaliza volume
        volume = self._normalize_volume(volume, symbol_info)
        
        # Obtém preço se não fornecido
        if price is None:
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                error_msg = f"Falha ao obter tick para {symbol}"
                self.logger.error(error_msg)
                return OrderResult(False, comment=error_msg)
            
            price = tick.ask if order_type == OrderType.BUY else tick.bid

        # Normaliza preços
        price = self._normalize_price(price, symbol_info)
        if sl is not None:
            sl = self._normalize_price(sl, symbol_info)
        if tp is not None:
            tp = self._normalize_price(tp, symbol_info)

        # Tenta executar com retries
        for attempt in range(1, max_retries + 1):
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": order_type.value,
                "price": price,
                "sl": sl or 0.0,
                "tp": tp or 0.0,
                "deviation": self.deviation,
                "magic": self.magic_number,
                "comment": comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": filling_type.value,
            }

            # Envia ordem
            result = mt5.order_send(request)
            
            if result is None:
                error = mt5.last_error()
                self.logger.error(f"order_send retornou None: {error}")
                return OrderResult(False, comment=f"Erro MT5: {error}")

            # Processa resultado
            retcode = result.retcode

            # Sucesso
            if retcode in [self.RETCODE_SUCCESS, self.RETCODE_DONE]:
                self.logger.info(
                    f"Ordem executada com sucesso! "
                    f"Ticket: {result.order} | {symbol} | "
                    f"{'BUY' if order_type == OrderType.BUY else 'SELL'} | "
                    f"Volume: {volume} | Price: {result.price:.5f}"
                )
                
                return OrderResult(
                    success=True,
                    ticket=result.order,
                    retcode=retcode,
                    comment=result.comment,
                    request=request,
                    volume=volume,
                    price=result.price
                )

            # Requote - tenta novamente com novo preço
            elif retcode == self.RETCODE_REQUOTE:
                self.logger.warning(f"Requote recebido (tentativa {attempt}/{max_retries})")
                
                # Obtém novo preço
                tick = mt5.symbol_info_tick(symbol)
                if tick is not None:
                    price = tick.ask if order_type == OrderType.BUY else tick.bid
                    price = self._normalize_price(price, symbol_info)
                    self.logger.info(f"Novo preço após requote: {price:.5f}")
                    time.sleep(0.5)
                    continue
                else:
                    error_msg = "Falha ao obter novo preço após requote"
                    self.logger.error(error_msg)
                    return OrderResult(False, retcode=retcode, comment=error_msg)

            # Preenchimento inválido - tenta outro tipo
            elif retcode == self.RETCODE_INVALID_FILL:
                self.logger.warning(f"Tipo de preenchimento inválido, tentando alternativa")
                filling_type = self._get_alternative_filling(filling_type)
                continue

            # Outros erros
            else:
                error_msg = self._get_error_message(retcode)
                self.logger.error(
                    f"Falha na execução (tentativa {attempt}/{max_retries}): "
                    f"RetCode {retcode} - {error_msg}"
                )
                
                # Não retenta em erros críticos
                if retcode in [
                    self.RETCODE_MARKET_CLOSED,
                    self.RETCODE_NO_MONEY,
                    self.RETCODE_TRADE_DISABLED,
                    self.RETCODE_INVALID_VOLUME
                ]:
                    return OrderResult(
                        success=False,
                        retcode=retcode,
                        comment=error_msg,
                        request=request
                    )
                
                time.sleep(1)

        # Todas as tentativas falharam
        return OrderResult(
            success=False,
            retcode=retcode if 'retcode' in locals() else 0,
            comment="Máximo de tentativas excedido"
        )

    def close_position(self, ticket: int, volume: Optional[float] = None) -> OrderResult:
        """
        Fecha uma posição
        
        Args:
            ticket: Ticket da posição
            volume: Volume a fechar (None para fechar total)
            
        Returns:
            OrderResult
        """
        # Obtém posição
        position = mt5.positions_get(ticket=ticket)
        if position is None or len(position) == 0:
            error_msg = f"Posição {ticket} não encontrada"
            self.logger.error(error_msg)
            return OrderResult(False, comment=error_msg)

        position = position[0]
        symbol = position.symbol
        position_volume = position.volume
        position_type = position.type

        # Determina volume a fechar
        close_volume = volume if volume is not None else position_volume

        # Determina tipo de ordem oposta
        close_type = OrderType.SELL if position_type == mt5.ORDER_TYPE_BUY else OrderType.BUY

        # Obtém preço atual
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            error_msg = f"Falha ao obter tick para {symbol}"
            self.logger.error(error_msg)
            return OrderResult(False, comment=error_msg)

        price = tick.bid if close_type == OrderType.SELL else tick.ask

        # Fecha posição
        result = self.open_position(
            symbol=symbol,
            order_type=close_type,
            volume=close_volume,
            price=price,
            comment=f"Close #{ticket}"
        )

        if result.success:
            self.logger.info(f"Posição {ticket} fechada com sucesso")

        return result

    def close_all_positions(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Fecha todas as posições
        
        Args:
            symbol: Símbolo específico ou None para todos
            
        Returns:
            Dicionário com resultado
        """
        positions = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        
        if positions is None or len(positions) == 0:
            self.logger.info("Nenhuma posição aberta para fechar")
            return {"closed": 0, "failed": 0}

        closed = 0
        failed = 0

        for position in positions:
            result = self.close_position(position.ticket)
            if result.success:
                closed += 1
            else:
                failed += 1

        self.logger.info(f"Fechamento em lote: {closed} fechadas, {failed} falharam")
        
        return {"closed": closed, "failed": failed, "total": len(positions)}

    def modify_position(
        self,
        ticket: int,
        sl: Optional[float] = None,
        tp: Optional[float] = None
    ) -> OrderResult:
        """
        Modifica SL/TP de uma posição
        
        Args:
            ticket: Ticket da posição
            sl: Novo Stop Loss (None para não modificar)
            tp: Novo Take Profit (None para não modificar)
            
        Returns:
            OrderResult
        """
        # Obtém posição
        position = mt5.positions_get(ticket=ticket)
        if position is None or len(position) == 0:
            error_msg = f"Posição {ticket} não encontrada"
            self.logger.error(error_msg)
            return OrderResult(False, comment=error_msg)

        position = position[0]
        symbol = position.symbol

        # Obtém informações do símbolo
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            error_msg = f"Informações do símbolo {symbol} não encontradas"
            self.logger.error(error_msg)
            return OrderResult(False, comment=error_msg)

        # Normaliza preços
        if sl is not None:
            sl = self._normalize_price(sl, symbol_info)
        else:
            sl = position.sl

        if tp is not None:
            tp = self._normalize_price(tp, symbol_info)
        else:
            tp = position.tp

        # Cria requisição
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": symbol,
            "sl": sl,
            "tp": tp,
            "position": ticket
        }

        # Envia modificação
        result = mt5.order_send(request)

        if result is None:
            error = mt5.last_error()
            self.logger.error(f"Falha na modificação: {error}")
            return OrderResult(False, comment=f"Erro MT5: {error}")

        if result.retcode in [self.RETCODE_SUCCESS, self.RETCODE_DONE]:
            self.logger.info(f"Posição {ticket} modificada: SL={sl:.5f}, TP={tp:.5f}")
            return OrderResult(success=True, ticket=ticket, retcode=result.retcode)
        else:
            error_msg = self._get_error_message(result.retcode)
            self.logger.error(f"Falha na modificação: {error_msg}")
            return OrderResult(success=False, retcode=result.retcode, comment=error_msg)

    def _get_filling_type(self, symbol_info) -> FillingType:
        """Determina o melhor tipo de preenchimento para o símbolo"""
        filling = symbol_info.filling_mode
        
        if filling & mt5.SYMBOL_FILLING_FOK:
            return FillingType.FOK
        elif filling & mt5.SYMBOL_FILLING_IOC:
            return FillingType.IOC
        else:
            return FillingType.RETURN

    def _get_alternative_filling(self, current: FillingType) -> FillingType:
        """Retorna tipo de preenchimento alternativo"""
        if current == FillingType.FOK:
            return FillingType.IOC
        elif current == FillingType.IOC:
            return FillingType.RETURN
        else:
            return FillingType.FOK

    def _normalize_volume(self, volume: float, symbol_info) -> float:
        """Normaliza volume conforme especificações do símbolo"""
        min_volume = symbol_info.volume_min
        max_volume = symbol_info.volume_max
        volume_step = symbol_info.volume_step

        volume = max(min_volume, min(volume, max_volume))
        volume = round(volume / volume_step) * volume_step
        
        return round(volume, 2)

    def _normalize_price(self, price: float, symbol_info) -> float:
        """Normaliza preço conforme especificações do símbolo"""
        digits = symbol_info.digits
        return round(price, digits)

    def _get_error_message(self, retcode: int) -> str:
        """Retorna mensagem de erro amigável"""
        error_messages = {
            10004: "Requote - preço mudou",
            10006: "Ordem rejeitada",
            10013: "Ordem inválida",
            10014: "Volume inválido",
            10015: "Preço inválido",
            10016: "Stops inválidos",
            10017: "Trading desabilitado",
            10018: "Mercado fechado",
            10019: "Saldo insuficiente",
            10030: "Tipo de preenchimento inválido",
        }
        
        return error_messages.get(retcode, f"Erro desconhecido: {retcode}")
