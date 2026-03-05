"""
Cliente Telegram Assíncrono com Loop Dedicado e Comandos Interativos.
Inclui rotinas avançadas e dinâmicas de fechamento de ordens para MT5.
"""

import aiohttp
import asyncio
import MetaTrader5 as mt5
from typing import Optional, Dict, Any
from core.logger import get_logger

logger = get_logger(__name__)

class TelegramBot:
    """Cliente para interação via Telegram Bot API."""
    
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
        if not self.enabled: return
        self.running = True
        logger.info("Telegram: Iniciando serviço de escuta em background...")
        
        async with aiohttp.ClientSession() as session:
            while self.running:
                try:
                    payload = {"offset": self.last_update_id + 1, "timeout": 1, "allowed_updates": ["message"]}
                    try:
                        async with session.post(f"{self.base_url}/getUpdates", json=payload, timeout=5) as response:
                            if response.status == 200:
                                data = await response.json()
                                if data.get("ok"):
                                    for update in data.get("result", []):
                                        self.last_update_id = update["update_id"]
                                        if "message" in update:
                                            await self._handle_message(update["message"], mt5_client)
                    except asyncio.TimeoutError:
                        pass
                    except Exception as e:
                        logger.debug(f"Erro de conexão Telegram: {e}")
                        await asyncio.sleep(5)
                    await asyncio.sleep(0.5)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Erro crítico no Telegram: {e}")
                    await asyncio.sleep(5)

    def stop(self):
        self.running = False

    async def _handle_message(self, message: Dict, mt5_client: Any) -> None:
        sender_id = str(message.get("chat", {}).get("id", ""))
        text = message.get("text", "").strip().lower()
        
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
            await self.send_message("🔕 <b>Notificações Pausadas.</b>\nO robô continua operando silenciosamente.")
        elif text == "/retomar":
            self.alerts_muted = False
            await self.send_message("🔔 <b>Notificações Retomadas.</b>")
        elif text in ["/ajuda", "/start", "ajuda"]:
            await self.send_message(
                "🤖 <b>Painel de Controle:</b>\n\n"
                "💰 /saldo - Ver saldo e lucro\n"
                "📊 /status - Ver negociações abertas\n"
                "🛑 /fechar EURUSD - Encerrar negociação\n"
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
            profit = info['profit']
            emoji = "🟢" if profit >= 0 else "🔴"
            msg = f"💰 <b>Financeiro</b>\n💵 Saldo: <b>${info['balance']:,.2f}</b>\n📈 Equity: <b>${info['equity']:,.2f}</b>\n{emoji} Lucro Aberto: <b>${profit:,.2f}</b>"
            await self.send_message(msg)

    async def _reply_status(self, mt5_client: Any) -> None:
        if not await mt5_client.ensure_connected():
            await self.send_message("⚠️ MT5 Desconectado.")
            return
        positions = await mt5_client.get_positions()
        if not positions:
            await self.send_message("✅ <b>Sistema Online.</b>\nNenhuma negociação aberta.")
            return
        msg = f"📊 <b>Abertas ({len(positions)}):</b>\n\n"
        for pos in positions:
            is_dict = isinstance(pos, dict)
            sym = pos['symbol'] if is_dict else pos.symbol
            vol = pos['volume'] if is_dict else pos.volume
            prof = pos['profit'] if is_dict else pos.profit
            p_type = pos['type'] if is_dict else pos.type
            action = "COMPRA 🟢" if p_type == 0 else "VENDA 🔴"
            msg += f"🔸 <b>{sym}</b> | {action} | {vol} Lotes\n   Lucro Atual: ${prof:.2f}\n\n"
        await self.send_message(msg)

    async def _reply_fechar(self, mt5_client: Any, symbol: str) -> None:
        """Fechamento Dinâmico de Nível Sênior - Analisa as regras da corretora na hora."""
        if not await mt5_client.ensure_connected():
            await self.send_message("⚠️ MT5 Desconectado.")
            return

        positions = await mt5_client.get_positions(symbol)
        if not positions:
            await self.send_message(f"⚠️ Nenhuma negociação aberta para <b>{symbol}</b>.")
            return
            
        await self.send_message(f"⏳ Executando fechamento absoluto de <b>{symbol}</b>...")
        loop = asyncio.get_event_loop()
        
        # Verifica a política de preenchimento exigida pela corretora
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            await self.send_message(f"❌ Símbolo {symbol} não encontrado no MT5.")
            return

        filling_type = mt5.ORDER_FILLING_RETURN # Fallback padrão
        if symbol_info.filling_mode & mt5.SYMBOL_FILLING_FOK:
            filling_type = mt5.ORDER_FILLING_FOK
        elif symbol_info.filling_mode & mt5.SYMBOL_FILLING_IOC:
            filling_type = mt5.ORDER_FILLING_IOC

        for pos in positions:
            try:
                is_dict = isinstance(pos, dict)
                ticket = pos['ticket'] if is_dict else pos.ticket
                vol = pos['volume'] if is_dict else pos.volume
                p_type = pos['type'] if is_dict else pos.type
                prof = pos['profit'] if is_dict else pos.profit
                magic = pos.get('magic', 0) if is_dict else getattr(pos, 'magic', 0)
                
                # Ação Oposta para Fechar
                order_type = mt5.ORDER_TYPE_SELL if p_type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
                tick = mt5.symbol_info_tick(symbol)
                price = tick.bid if order_type == mt5.ORDER_TYPE_SELL else tick.ask
                
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": symbol,
                    "volume": float(vol),
                    "type": order_type,
                    "position": ticket,
                    "price": price,
                    "deviation": 50, # Tolerância alta de derrapagem para forçar saída
                    "magic": magic,
                    "comment": "Forced Close TG",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": filling_type
                }
                
                result = await loop.run_in_executor(None, mt5.order_send, request)

                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    emoji = "🟢" if prof >= 0 else "🔴"
                    await self.send_message(f"✅ <b>Ordem {ticket} Fechada!</b>\n{emoji} Resultado: ${prof:.2f}")
                else:
                    err = result.comment if result else "N/A"
                    code = result.retcode if result else "N/A"
                    await self.send_message(f"❌ <b>Falha na ordem {ticket}:</b>\nErro MT5 [{code}]: {err}")
                    
            except Exception as e:
                logger.error(f"Erro ao fechar {symbol}: {e}")
                await self.send_message(f"❌ Erro de sistema ao fechar {symbol}.")

    async def _reply_fechar_todas(self, mt5_client: Any) -> None:
        if not await mt5_client.ensure_connected(): return
        positions = await mt5_client.get_positions()
        if not positions:
            await self.send_message("⚠️ Nenhuma posição aberta.")
            return
            
        await self.send_message(f"🚨 Encerrando TODAS as {len(positions)} posições em aberto...")
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
        except Exception as e: return False

    async def send_trade_alert(self, symbol, action, price, volume, sl, tp, prob, ticket, balance, equity):
        if self.alerts_muted: return
        emoji = "🟢" if action == "BUY" else "🔴"
        msg = f"{emoji} <b>NOVA ORDEM: {symbol}</b>\n{action} | {volume} Lotes\nPreço: {price}\nTicket: <code>{ticket}</code>\n\n🎯 TP: {tp}\n🛑 SL: {sl}\n🤖 IA: {prob:.1%}\n──────────────\n💰 Saldo: ${balance:,.2f}"
        await self.send_message(msg)

    async def send_startup_message(self, balance: float):
        if self.enabled:
            await self.send_message(f"🚀 <b>Trading Bot Iniciado</b>\n💰 Saldo: ${balance:,.2f}\n👉 /ajuda para comandos")