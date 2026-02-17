"""
Gestor de Execução de Ordens ECN com tratamento robusto de erros.

Implementa:
- Mapeamento automático de filling_mode
- Tratamento de requotes (Erro 10004)
- Tratamento de rejeições (Erro 10013)
- Validação de ordens antes de envio
"""

import MetaTrader5 as mt5
import asyncio
from typing import Dict, Any, Optional, Literal
from datetime import datetime

from core.logger import get_logger
from core.mt5_client import MT5Client

logger = get_logger(__name__)


class OrderManager:
    """
    Gestor de ordens para trading no MetaTrader 5.
    
    Gerencia envio de ordens de mercado com tratamento inteligente
    de erros específicos de brokers ECN/STP.
    """
    
    def __init__(
        self,
        mt5_client: MT5Client,
        magic_number: int = 987654321,
        deviation: int = 20,
        max_retries: int = 3
    ):
        """
        Inicializa gestor de ordens.
        
        Args:
            mt5_client: Cliente MT5 conectado
            magic_number: Número mágico para identificar ordens do robô
            deviation: Desvio de preço permitido (pontos)
            max_retries: Máximo de tentativas em caso de requote
        """
        self.mt5_client = mt5_client
        self.magic_number = magic_number
        self.deviation = deviation
        self.max_retries = max_retries
        
        logger.info(
            f"OrderManager inicializado - "
            f"Magic: {magic_number}, Deviation: {deviation}"
        )
    
    async def send_market_order(
        self,
        symbol: str,
        order_type: Literal['BUY', 'SELL'],
        volume: float,
        stop_loss: float,
        take_profit: float,
        comment: str = "AI Robot"
    ) -> Dict[str, Any]:
        """
        Envia ordem de mercado com tratamento completo de erros.
        
        Args:
            symbol: Nome do símbolo
            order_type: 'BUY' ou 'SELL'
            volume: Volume em lotes
            stop_loss: Preço de stop loss
            take_profit: Preço de take profit
            comment: Comentário da ordem
            
        Returns:
            Dicionário com resultado da execução
        """
        logger.info(
            f"Preparando ordem {order_type} - "
            f"{symbol} {volume:.2f} lots, SL: {stop_loss}, TP: {take_profit}"
        )
        
        # Garante conexão
        if not await self.mt5_client.ensure_connected():
            return self._order_failed("Sem conexão com MT5")
        
        # Obtém informações do símbolo
        symbol_info = await self.mt5_client.get_symbol_info(symbol)
        
        if symbol_info is None:
            return self._order_failed(f"Símbolo {symbol} inválido")
        
        # Determina tipo de ordem MT5
        if order_type == 'BUY':
            mt5_order_type = mt5.ORDER_TYPE_BUY
            price = symbol_info['ask']
        else:
            mt5_order_type = mt5.ORDER_TYPE_SELL
            price = symbol_info['bid']
        
        # Determina filling mode automaticamente
        filling_mode = self._get_filling_mode(symbol_info['filling_mode'])
        
        logger.info(f"Filling mode detectado: {filling_mode}")
        
        # Tenta enviar ordem com retry em caso de requote
        for attempt in range(1, self.max_retries + 1):
            # Atualiza preço a cada tentativa
            symbol_info = await self.mt5_client.get_symbol_info(symbol)
            if symbol_info is None:
                return self._order_failed("Erro ao atualizar cotação")
            
            price = symbol_info['ask'] if order_type == 'BUY' else symbol_info['bid']
            
            # Monta request
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": mt5_order_type,
                "price": price,
                "sl": stop_loss,
                "tp": take_profit,
                "deviation": self.deviation,
                "magic": self.magic_number,
                "comment": comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": filling_mode
            }
            
            logger.info(
                f"Tentativa {attempt}/{self.max_retries} - "
                f"Enviando ordem ao broker..."
            )
            
            # Envia ordem
            result = mt5.order_send(request)
            
            if result is None:
                error = mt5.last_error()
                logger.error(f"Erro ao enviar ordem: {error}")
                
                if attempt < self.max_retries:
                    await asyncio.sleep(0.5)
                    continue
                else:
                    return self._order_failed(f"MT5 Error: {error}")
            
            # Processa resultado
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(
                    f"✓ ORDEM EXECUTADA - "
                    f"Ticket: {result.order}, "
                    f"Volume: {result.volume}, "
                    f"Preço: {result.price}"
                )
                
                return {
                    'success': True,
                    'ticket': result.order,
                    'volume': result.volume,
                    'price': result.price,
                    'sl': stop_loss,
                    'tp': take_profit,
                    'symbol': symbol,
                    'type': order_type,
                    'comment': result.comment,
                    'retcode': result.retcode
                }
            
            # Trata erros específicos
            elif result.retcode == 10004:  # TRADE_RETCODE_REQUOTE
                logger.warning(
                    f"⚠ REQUOTE (10004) - Preço mudou. "
                    f"Novo preço: {result.ask if order_type == 'BUY' else result.bid}"
                )
                
                if attempt < self.max_retries:
                    await asyncio.sleep(0.2)  # Pequeno delay antes de retry
                    continue
                else:
                    return self._order_failed(
                        f"Requote persistente após {self.max_retries} tentativas"
                    )
            
            elif result.retcode == 10013:  # TRADE_RETCODE_INVALID_REQUEST
                logger.error(
                    f"✗ ORDEM INVÁLIDA (10013) - "
                    f"Possível problema com filling_mode ou parâmetros"
                )
                
                # Tenta com filling mode alternativo se primeira tentativa
                if attempt == 1:
                    logger.info("Tentando filling mode alternativo...")
                    filling_mode = self._get_alternative_filling_mode(filling_mode)
                    await asyncio.sleep(0.5)
                    continue
                else:
                    return self._order_failed(
                        f"Ordem rejeitada (10013): {result.comment}"
                    )
            
            elif result.retcode == 10006:  # TRADE_RETCODE_REJECT
                logger.error(f"✗ ORDEM REJEITADA (10006): {result.comment}")
                return self._order_failed(f"Rejeitada pelo broker: {result.comment}")
            
            elif result.retcode == 10014:  # TRADE_RETCODE_INVALID_VOLUME
                logger.error(f"✗ VOLUME INVÁLIDO (10014): {volume}")
                return self._order_failed(f"Volume inválido: {volume}")
            
            elif result.retcode == 10015:  # TRADE_RETCODE_INVALID_PRICE
                logger.error(f"✗ PREÇO INVÁLIDO (10015): {price}")
                return self._order_failed(f"Preço inválido: {price}")
            
            elif result.retcode == 10016:  # TRADE_RETCODE_INVALID_STOPS
                logger.error(
                    f"✗ STOPS INVÁLIDOS (10016) - "
                    f"SL: {stop_loss}, TP: {take_profit}"
                )
                return self._order_failed(
                    f"Stops inválidos - SL: {stop_loss}, TP: {take_profit}"
                )
            
            else:
                logger.error(
                    f"✗ ERRO DESCONHECIDO ({result.retcode}): {result.comment}"
                )
                
                if attempt < self.max_retries:
                    await asyncio.sleep(1.0)
                    continue
                else:
                    return self._order_failed(
                        f"Erro {result.retcode}: {result.comment}"
                    )
        
        # Se chegou aqui, esgotou todas as tentativas
        return self._order_failed("Máximo de tentativas excedido")
    
    async def close_position(
        self,
        ticket: int,
        comment: str = "Close by AI"
    ) -> Dict[str, Any]:
        """
        Fecha posição aberta.
        
        Args:
            ticket: Ticket da posição
            comment: Comentário de fechamento
            
        Returns:
            Dicionário com resultado
        """
        logger.info(f"Fechando posição {ticket}...")
        
        # Obtém informações da posição
        position = mt5.positions_get(ticket=ticket)
        
        if position is None or len(position) == 0:
            return self._order_failed(f"Posição {ticket} não encontrada")
        
        position = position[0]
        
        # Determina tipo de ordem de fechamento (oposto à posição)
        if position.type == mt5.POSITION_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price_type = 'bid'
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price_type = 'ask'
        
        # Obtém preço atual
        symbol_info = await self.mt5_client.get_symbol_info(position.symbol)
        if symbol_info is None:
            return self._order_failed("Erro ao obter cotação para fechamento")
        
        price = symbol_info[price_type]
        
        # Monta request de fechamento
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": position.volume,
            "type": order_type,
            "position": ticket,
            "price": price,
            "deviation": self.deviation,
            "magic": self.magic_number,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._get_filling_mode(symbol_info['filling_mode'])
        }
        
        # Envia ordem de fechamento
        result = mt5.order_send(request)
        
        if result is None:
            error = mt5.last_error()
            return self._order_failed(f"Erro ao fechar: {error}")
        
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"✓ Posição {ticket} fechada com sucesso")
            
            return {
                'success': True,
                'ticket': ticket,
                'close_price': result.price,
                'profit': position.profit,
                'comment': result.comment
            }
        else:
            return self._order_failed(
                f"Falha ao fechar (retcode {result.retcode}): {result.comment}"
            )
    
    def _get_filling_mode(self, filling_mode_flags: int) -> int:
        """
        Determina filling mode apropriado baseado nas flags do símbolo.
        
        Args:
            filling_mode_flags: Flags de filling_mode do símbolo
            
        Returns:
            Constante MT5 de filling mode
        """
        # Verifica cada modo disponível na ordem de preferência
        
        # FOK (Fill or Kill) - Preferido para execução imediata completa
        if filling_mode_flags & 1:  # SYMBOL_FILLING_FOK
            return mt5.ORDER_FILLING_FOK
        
        # IOC (Immediate or Cancel) - Permite execução parcial
        if filling_mode_flags & 2:  # SYMBOL_FILLING_IOC
            return mt5.ORDER_FILLING_IOC
        
        # RETURN - Modo padrão para market orders
        if filling_mode_flags & 4:  # SYMBOL_FILLING_RETURN
            return mt5.ORDER_FILLING_RETURN
        
        # Fallback para RETURN (mais comum)
        logger.warning(
            f"Filling mode não reconhecido: {filling_mode_flags}. Usando RETURN."
        )
        return mt5.ORDER_FILLING_RETURN
    
    def _get_alternative_filling_mode(self, current_mode: int) -> int:
        """
        Retorna modo de filling alternativo.
        
        Args:
            current_mode: Modo atual
            
        Returns:
            Modo alternativo
        """
        if current_mode == mt5.ORDER_FILLING_FOK:
            return mt5.ORDER_FILLING_IOC
        elif current_mode == mt5.ORDER_FILLING_IOC:
            return mt5.ORDER_FILLING_RETURN
        else:
            return mt5.ORDER_FILLING_FOK
    
    def _order_failed(self, reason: str) -> Dict[str, Any]:
        """
        Retorna estrutura de ordem falhada.
        
        Args:
            reason: Motivo da falha
            
        Returns:
            Dicionário com informação de falha
        """
        return {
            'success': False,
            'error': reason,
            'timestamp': datetime.now().isoformat()
        }
    
    async def modify_position(
        self,
        ticket: int,
        new_sl: Optional[float] = None,
        new_tp: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Modifica SL/TP de posição existente.
        
        Args:
            ticket: Ticket da posição
            new_sl: Novo stop loss (None para manter)
            new_tp: Novo take profit (None para manter)
            
        Returns:
            Dicionário com resultado
        """
        position = mt5.positions_get(ticket=ticket)
        
        if position is None or len(position) == 0:
            return self._order_failed(f"Posição {ticket} não encontrada")
        
        position = position[0]
        
        # Usa valores atuais se não fornecidos novos
        sl = new_sl if new_sl is not None else position.sl
        tp = new_tp if new_tp is not None else position.tp
        
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": position.symbol,
            "position": ticket,
            "sl": sl,
            "tp": tp
        }
        
        result = mt5.order_send(request)
        
        if result is None:
            error = mt5.last_error()
            return self._order_failed(f"Erro ao modificar: {error}")
        
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"✓ Posição {ticket} modificada - SL: {sl}, TP: {tp}")
            return {'success': True, 'ticket': ticket, 'sl': sl, 'tp': tp}
        else:
            return self._order_failed(
                f"Falha ao modificar (retcode {result.retcode}): {result.comment}"
            )
