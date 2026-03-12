"""
Cliente Telegram Assíncrono com Fechamento Forçado (Bulletproof).
Resolve o problema de ordens travadas ignorando restrições de Magic Number 
e aumentando o Deviation com múltiplas tentativas de preenchimento.
"""

import aiohttp
import asyncio
import MetaTrader5 as mt5
from typing import Optional, Dict, Any
from core.logger import get_logger

logger = get_logger(__name__)

class TelegramBot:
    """
    Cliente para interação via Telegram Bot API.
    Executa polling em thread/task separada e permite fechar operações via chat de forma agressiva.
    """
    def __init__(self, token: str, chat_id: str, enabled: bool = True):
        self.token = token
        self.chat_id = str(chat_id)
        self.enabled = enabled
        self.running = False
        self.alerts_muted = False
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.last_update_id = 0
        
        if enabled and token and chat_id:
            logger.info(f"TelegramBot configurado para Chat ID: {chat_id}")
        else:
            self.enabled = False
            logger.info("TelegramBot desativado")

    async def start(self, mt5_client: Any) -> None:
        """Inicia o loop de verificação de mensagens em background."""
        if not self.enabled: return
        self.running = True
        logger.info("Telegram: Iniciando serviço de escuta em background...")
        
        async with aiohttp.ClientSession() as session:
            while self.running:
                try:
                    payload = {"offset": self.last_update_id + 1, "timeout": 2, "allowed_updates": ["message"]}
                    async with session.post(f"{self.base_url}/getUpdates", json=payload, timeout=5) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data.get("ok"):
                                for update in data.get("result", []):
                                    self.last_update_id = update["update_id"]
                                    if "message" in update:
                                        await self._handle_message(update["message"], mt5_client)
                except asyncio.TimeoutError:
                    pass # Normal para long polling
                except Exception as e:
                    logger.debug(f"Erro de conexão Telegram: {e}")
                    await asyncio.sleep(2)
                
                await asyncio.sleep(0.1) # Micro-pausa para manter a responsividade alta

    def stop(self):
        """Para o loop do Telegram."""
        self.running = False

    async def _handle_message(self, message: Dict, mt5_client: Any) -> None:
        """Processa comandos recebidos pelo chat."""
        sender_id = str(message.get("chat", {}).get("id", ""))
        text = message.get("text", "").strip().lower()
        
        # Ignora mensagens de outras pessoas (Segurança máxima)
        if sender_id != self.chat_id: return 

        if text == "/saldo":
            await self._reply_balance(mt5_client)
        elif text == "/status":
            await self._reply_status(mt5_client)
        elif text.startswith("/fechar "):
            parts = text.split(" ")
            if len(parts) >= 2:
                await self._reply_fechar(mt5_client, parts[1].upper())
            else:
                await self.send_message("⚠️ Formato inválido. Use: /fechar EURUSD")
        elif text == "/fechar_todas":
            await self._reply_fechar_todas(mt5_client)
        elif text == "/parar":
            self.alerts_muted = True
            await self.send_message("🔕 <b>Alertas Pausados.</b>\nO robô continua operando silenciosamente.")
        elif text == "/retomar":
            self.alerts_muted = False
            await self.send_message("🔔 <b>Alertas Retomados.</b>")
        elif text in ["/ajuda", "/start"]:
            await self.send_message(
                "🤖 <b>Painel de Controle:</b>\n\n"
                "💰 /saldo - Ver saldo e lucro\n"
                "📊 /status - Ver negociações abertas\n"
                "🛑 /fechar EURUSD - Encerrar negociação à força\n"
                "💥 /fechar_todas - Fechar TODAS as posições\n"
                "🔕 /parar - Mutar alertas\n"
                "🔔 /retomar - Desmutar alertas"
            )

    async def _reply_balance(self, mt5_client: Any) -> None:
        if not await mt5_client.ensure_connected(): 
            await self.send_message("⚠️ MT5 Desconectado.")
            return
        info = await mt5_client.get_account_info()
        if info:
            emoji = "🟢" if info['profit'] >= 0 else "🔴"
            await self.send_message(
                f"💰 <b>Financeiro</b>\n"
                f"💵 Saldo: <b>${info['balance']:,.2f}</b>\n"
                f"📈 Equity: <b>${info['equity']:,.2f}</b>\n"
                f"{emoji} Lucro Aberto: <b>${info['profit']:,.2f}</b>"
            )

    async def _reply_status(self, mt5_client: Any) -> None:
        if not await mt5_client.ensure_connected(): 
            await self.send_message("⚠️ MT5 Desconectado.")
            return
        positions = await mt5_client.get_positions()
        if not positions:
            await self.send_message("✅ Nenhuma negociação aberta no momento.")
            return
        msg = f"📊 <b>Abertas ({len(positions)}):</b>\n\n"
        for pos in positions:
            sym = pos['symbol'] if isinstance(pos, dict) else pos.symbol
            vol = pos['volume'] if isinstance(pos, dict) else pos.volume
            prof = pos['profit'] if isinstance(pos, dict) else pos.profit
            p_type = pos['type'] if isinstance(pos, dict) else pos.type
            action = "COMPRA 🟢" if p_type == 0 else "VENDA 🔴"
            msg += f"🔸 <b>{sym}</b> | {action} | Lote {vol}\n   Lucro: ${prof:.2f}\n\n"
        await self.send_message(msg)

    async def _reply_fechar(self, mt5_client: Any, symbol: str) -> None:
        """Fechamento Forçado - Tenta múltiplas vezes ignorando restrições de corretora."""
        if not await mt5_client.ensure_connected(): 
            await self.send_message("⚠️ MT5 Desconectado.")
            return

        positions = await mt5_client.get_positions(symbol)
        if not positions:
            await self.send_message(f"⚠️ Nenhuma negociação aberta para <b>{symbol}</b>.")
            return
            
        await self.send_message(f"⏳ Fechamento forçado de <b>{symbol}</b> iniciado...")
        loop = asyncio.get_event_loop()
        
        # Estratégia Sênior: Tentar todos os modos de preenchimento possíveis
        filling_types = [mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN]

        for pos in positions:
            try:
                ticket = int(pos['ticket'] if isinstance(pos, dict) else pos.ticket)
                vol = float(pos['volume'] if isinstance(pos, dict) else pos.volume)
                p_type = int(pos['type'] if isinstance(pos, dict) else pos.type)
                prof = pos['profit'] if isinstance(pos, dict) else pos.profit
                
                order_type = mt5.ORDER_TYPE_SELL if p_type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
                
                success = False
                final_result = None
                
                # TENTA FECHAR ATÉ 3 VEZES COM MÉTODOS DIFERENTES
                for filling in filling_types:
                    tick = mt5.symbol_info_tick(symbol)
                    if not tick: continue
                    
                    price = tick.bid if order_type == mt5.ORDER_TYPE_SELL else tick.ask
                    
                    request = {
                        "action": mt5.TRADE_ACTION_DEAL,
                        "symbol": symbol,
                        "volume": vol,
                        "type": order_type,
                        "position": ticket,
                        "price": price,
                        "deviation": 200, # ALTA TOLERÂNCIA - Sai a qualquer preço disponível!
                        "type_time": mt5.ORDER_TIME_GTC,
                        "type_filling": filling
                    }
                    
                    result = await loop.run_in_executor(None, mt5.order_send, request)
                    final_result = result
                    
                    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                        success = True
                        break # Se conseguiu fechar, sai do loop de tentativas
                        
                    await asyncio.sleep(0.5) # Pausa pequena antes de tentar forçar outra vez com modo diferente
                
                # Avalia o resultado final após as tentativas
                if success:
                    emoji = "🟢" if prof >= 0 else "🔴"
                    await self.send_message(f"✅ <b>{symbol} Fechado à força!</b>\n{emoji} Resultado: ${prof:.2f}")
                    logger.info(f"Telegram: Ordem {ticket} de {symbol} encerrada com sucesso à força.")
                else:
                    err = final_result.comment if final_result else "Desconhecido"
                    code = final_result.retcode if final_result else "N/A"
                    await self.send_message(
                        f"❌ <b>Falha ao fechar {symbol}:</b>\n\n"
                        f"<b>Código:</b> {code}\n"
                        f"<b>Motivo:</b> {err}\n\n"
                        f"<i>A corretora recusou a saída repetidas vezes. Feche manualmente no MT5!</i>"
                    )
                    
            except Exception as e:
                logger.error(f"Erro no fechamento agressivo de {symbol}: {e}")
                await self.send_message(f"❌ Erro sistémico ao fechar {symbol}.")

    async def _reply_fechar_todas(self, mt5_client: Any) -> None:
        if not await mt5_client.ensure_connected(): return
        positions = await mt5_client.get_positions()
        if not positions:
            await self.send_message("⚠️ Nenhuma posição aberta no momento.")
            return
            
        await self.send_message(f"🚨 <b>PÂNICO:</b> Encerrando TODAS as {len(positions)} posições em aberto...")
        for pos in positions:
            sym = pos['symbol'] if isinstance(pos, dict) else pos.symbol
            await self._reply_fechar(mt5_client, sym)
            await asyncio.sleep(0.5)

    async def send_message(self, message: str) -> bool:
        if not self.enabled: return False
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/sendMessage", json={"chat_id": self.chat_id, "text": message, "parse_mode": "HTML"}) as resp:
                    return resp.status == 200
        except Exception as e: 
            logger.error(f"Falha ao enviar para Telegram: {e}")
            return False

    async def send_trade_alert(self, symbol, action, price, volume, sl, tp, prob, ticket, balance, equity):
        if self.alerts_muted: return
        emoji = "🟢" if action == "BUY" else "🔴"
        msg = (
            f"{emoji} <b>NOVA ORDEM: {symbol}</b>\n\n"
            f"<b>Ação:</b> {action}\n"
            f"<b>Lote:</b> {volume}\n"
            f"<b>Preço:</b> {price}\n"
            f"<b>Ticket:</b> <code>{ticket}</code>\n\n"
            f"🎯 <b>Alvo (TP):</b> {tp}\n"
            f"🛑 <b>Risco (SL):</b> {sl}\n"
            f"🤖 <b>Confiança IA:</b> {prob:.1%}\n"
            f"──────────────\n"
            f"💰 Saldo Conta: ${balance:,.2f}"
        )
        await self.send_message(msg)

    async def send_startup_message(self, balance: float):
        if self.enabled:
            await self.send_message(f"🚀 <b>Trading Bot Iniciado</b>\n💰 Saldo Inicial: ${balance:,.2f}\n👉 Digite /ajuda para ver os comandos.")