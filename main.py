"""
Orquestrador Principal do Sistema de Trading Institucional.

Melhorias Sênior nesta versão:
- Anti-Starvation: Gestão otimizada do Event Loop para priorizar o Telegram.
- Redução de Latência: Micro-pausas assíncronas para processamento paralelo real.
"""

# --- FILTRO DE AVISOS (CRÍTICO PARA LIMPEZA DO TERMINAL) ---
import warnings
import os

os.environ["PYTHONWARNINGS"] = "ignore"
warnings.filterwarnings("ignore", message=".*sklearn.utils.parallel.delayed.*")
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")
# -----------------------------------------------------------

import asyncio
import json
import signal
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
import time # Adicionado para medição precisa

from core import configure_logging_from_config, get_logger, MT5Client, measure_time, TelegramBot
from data.features import FeatureEngine, CUSUMFilter
from strategies.ai_logic import PrimaryStrategy, MetaLabeler, AITradingLogic
from risk.manager import KellyRiskManager
from execution.order_manager import OrderManager
from train_model import train_meta_model

logger = get_logger(__name__)


class TradingBot:
    def __init__(self, config_path: str = "config/settings.json"):
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        self.running = False
        self.telegram_task: Optional[asyncio.Task] = None
        
        self.mt5_client: Optional[MT5Client] = None
        self.feature_engine: Optional[FeatureEngine] = None
        self.cusum_filters: Dict[str, CUSUMFilter] = {}
        self.primary_strategy: Optional[PrimaryStrategy] = None
        self.meta_labeler: Optional[MetaLabeler] = None
        self.ai_logic: Optional[AITradingLogic] = None
        self.risk_manager: Optional[KellyRiskManager] = None
        self.order_manager: Optional[OrderManager] = None
        self.telegram: Optional[TelegramBot] = None
        
        self.symbols: List[str] = []
        self.active_positions: Dict[str, Any] = {}
        self.last_retrain_check = datetime.now()
        
        logger.info("=" * 80)
        logger.info("   TRADING BOT INSTITUCIONAL - INICIALIZANDO   ")
        logger.info("=" * 80)
    
    def load_config(self) -> None:
        try:
            if not os.path.exists(self.config_path):
                raise FileNotFoundError(f"Arquivo de configuração não encontrado: {self.config_path}")
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            logger.info("Configurações carregadas.")
        except Exception as e:
            logger.critical(f"Erro ao carregar configurações: {e}")
            raise
    
    async def setup(self) -> None:
        logger.info("Iniciando setup dos componentes...")
        configure_logging_from_config(self.config_path)
        self.load_config()
        
        tg_config = self.config.get('telegram', {'enabled': False})
        self.telegram = TelegramBot(
            token=tg_config.get('token', ''),
            chat_id=tg_config.get('chat_id', ''),
            enabled=tg_config.get('enabled', False)
        )
        
        mt5_config = self.config['mt5']
        self.mt5_client = MT5Client(
            login=mt5_config['login'],
            password=mt5_config['password'],
            server=mt5_config['server'],
            timeout=mt5_config['timeout'],
            path=mt5_config.get('path', '')
        )
        
        if not await self.mt5_client.connect():
            raise ConnectionError("Falha crítica ao conectar com MetaTrader 5")
        
        st_config = self.config['strategy']
        self.feature_engine = FeatureEngine(
            ema_period=st_config['ema_period'],
            rsi_period=st_config['rsi_period'],
            atr_period=st_config['atr_period']
        )
        
        self.symbols = self.config['trading']['symbols']
        for symbol in self.symbols:
            self.cusum_filters[symbol] = CUSUMFilter(
                threshold=st_config['cusum_threshold'],
                drift=st_config['cusum_drift']
            )
        
        r_config = self.config['risk']
        self.primary_strategy = PrimaryStrategy(
            ema_period=st_config['ema_period'],
            rsi_period=st_config['rsi_period'],
            rsi_overbought=st_config['rsi_overbought'],
            rsi_oversold=st_config['rsi_oversold'],
            sl_atr_mult=r_config['stop_loss_atr_multiplier'],
            tp_atr_mult=r_config['take_profit_atr_multiplier']
        )
        
        ml_config = self.config['ml']
        self.meta_labeler = MetaLabeler(
            n_estimators=ml_config['n_estimators'],
            max_depth=ml_config['max_depth'],
            min_samples_split=ml_config['min_samples_split'],
            random_state=ml_config['random_state'],
            model_path=ml_config['model_path']
        )
        
        self.ai_logic = AITradingLogic(
            feature_engine=self.feature_engine,
            primary_strategy=self.primary_strategy,
            meta_labeler=self.meta_labeler,
            meta_threshold=st_config['meta_model_threshold']
        )
        
        self.risk_manager = KellyRiskManager(
            kelly_fraction=r_config['kelly_fraction'],
            max_risk_per_trade=r_config['max_risk_per_trade'],
            estimated_win_rate=r_config['estimated_win_rate'],
            min_kelly_exposure=r_config['min_kelly_exposure'],
            max_kelly_exposure=r_config['max_kelly_exposure']
        )
        
        trading_config = self.config['trading']
        self.order_manager = OrderManager(
            mt5_client=self.mt5_client,
            magic_number=trading_config['magic_number'],
            deviation=trading_config['deviation'],
            max_retries=3
        )
        
        account_info = await self.mt5_client.get_account_info()
        if account_info:
            logger.info(f"Conectado à conta. Saldo: {account_info['balance']}")
            await self.telegram.send_startup_message(balance=account_info['balance'])
            
        logger.info("✓ Setup concluído.")
    
    async def check_and_retrain_model(self):
        try:
            interval_hours = self.config['ml'].get('retrain_interval_hours', 168)
            last_training = self.meta_labeler.last_training_date
            
            should_retrain = False
            if last_training is None:
                should_retrain = True
            else:
                elapsed_time = datetime.now() - last_training
                if elapsed_time.total_seconds() > (interval_hours * 3600):
                    should_retrain = True
            
            if should_retrain:
                logger.info("Iniciando Retreinamento Automático...")
                if self.telegram:
                    await self.telegram.send_message("⚙️ <b>Manutenção:</b> Treinando IA...")
                
                train_symbol = self.symbols[0] if self.symbols else "EURUSD"
                
                result = await train_meta_model(symbol=train_symbol, side=3, silent=True)
                
                if result['success']:
                    self.meta_labeler.reload()
                    if self.telegram:
                        await self.telegram.send_message(f"✅ <b>IA Atualizada!</b>\nAcurácia: {result['acc']:.1%}")
        except Exception as e:
            logger.error(f"Erro retreinamento: {e}")

    @measure_time
    async def process_symbol(self, symbol: str) -> None:
        try:
            # Yield to event loop at start
            await asyncio.sleep(0.001)
            
            existing_positions = await self.mt5_client.get_positions(symbol)
            if existing_positions:
                return
            
            timeframe = self.config['trading']['timeframe']
            lookback = self.config['strategy']['lookback_bars']
            
            df = await self.mt5_client.get_rates(symbol, timeframe, lookback)
            if df is None or len(df) < self.config['strategy']['min_data_points']:
                return
            
            df['log_return'] = df['close'].pct_change().fillna(0)
            last_return = df['log_return'].iloc[-1]
            last_timestamp = df.index[-1]
            
            event_detected, direction = self.cusum_filters[symbol].update(last_return, last_timestamp)
            if not event_detected:
                return
            
            logger.info(f"{symbol}: ⚡ EVENTO CUSUM ({direction})")
            
            # --- CORREÇÃO DE STARVATION (THREAD SEPARADA) ---
            # A IA bloqueava o bot. Agora ela roda em background,
            # deixando o Telegram 100% responsivo para o comando /fechar
            loop = asyncio.get_running_loop()
            signal_data = await loop.run_in_executor(None, self.ai_logic.analyze, df)
            
            if signal_data['action'] == 'HOLD' or not signal_data.get('meta_approved', False):
                return
            
            logger.info(f"{symbol}: ✓ SINAL APROVADO! Prob: {signal_data['meta_probability']:.2%}")
            
            account_info = await self.mt5_client.get_account_info()
            symbol_info = await self.mt5_client.get_symbol_info(symbol)
            if not account_info or not symbol_info: return
            
            payoff_ratio = self.risk_manager.calculate_payoff_ratio(
                signal_data['entry_price'], signal_data['sl'], signal_data['tp']
            )
            position_size = self.risk_manager.calculate_position_size(
                account_info['balance'], signal_data['entry_price'], signal_data['sl'],
                symbol_info, signal_data['meta_probability'], payoff_ratio
            )
            
            if not position_size['valid']: return
            
            all_positions = await self.mt5_client.get_positions()
            risk_validation = self.risk_manager.validate_trade(
                account_info['balance'], account_info['equity'], len(all_positions),
                self.config['trading']['max_positions'], position_size['risk_amount']
            )
            
            if not risk_validation['approved']: return
            
            logger.info(f"{symbol}: Executando {signal_data['action']}...")
            order_result = await self.order_manager.send_market_order(
                symbol=symbol,
                order_type=signal_data['action'],
                volume=position_size['volume'],
                stop_loss=signal_data['sl'],
                take_profit=signal_data['tp'],
                comment=f"AI-{signal_data['meta_probability']:.0%}"
            )
            
            if order_result['success']:
                logger.info(f"✓ ORDEM EXECUTADA! Ticket: {order_result['ticket']}")
                if self.telegram:
                    await self.telegram.send_trade_alert(
                        symbol, signal_data['action'], order_result['price'], position_size['volume'],
                        signal_data['sl'], signal_data['tp'], signal_data['meta_probability'],
                        order_result['ticket'], account_info['balance'], account_info['equity']
                    )
            else:
                logger.error(f"{symbol}: FALHA NA EXECUÇÃO: {order_result.get('error')}")
        
        except Exception as e:
            logger.error(f"Erro em {symbol}: {e}")

    async def trading_loop(self) -> None:
        loop_interval = self.config['system']['loop_interval']
        logger.info(f"LOOP DE TRADING INICIADO - {loop_interval}s")
        
        iteration_count = 0
        while self.running:
            try:
                iteration_count += 1
                
                if not await self.mt5_client.ensure_connected():
                    await asyncio.sleep(5.0)
                    continue

                if (datetime.now() - self.last_retrain_check).total_seconds() > 60:
                    await self.check_and_retrain_model()
                    self.last_retrain_check = datetime.now()
                
                for symbol in self.symbols:
                    await self.process_symbol(symbol)
                    # YIELD CRÍTICO: Permite que o Telegram processe mensagens IMEDIATAMENTE entre cada moeda.
                    await asyncio.sleep(0.05) 
                
                await asyncio.sleep(loop_interval)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erro loop: {e}")
                await asyncio.sleep(5.0)

    async def run(self):
        await self.setup()
        self.running = True
        
        if self.telegram and self.telegram.enabled:
            logger.info("Iniciando serviço Telegram...")
            self.telegram_task = asyncio.create_task(self.telegram.start(self.mt5_client))
        
        await self.trading_loop()

    async def shutdown(self):
        logger.info("Iniciando shutdown...")
        self.running = False
        if self.telegram: self.telegram.stop()
        if self.telegram_task: self.telegram_task.cancel()
        if self.mt5_client: await self.mt5_client.disconnect()
        logger.info("Shutdown concluído")

async def main():
    bot = TradingBot()
    def stop_signal_handler(sig, frame):
        asyncio.create_task(bot.shutdown())
        
    signal.signal(signal.SIGINT, stop_signal_handler)
    signal.signal(signal.SIGTERM, stop_signal_handler)
    await bot.run()

if __name__ == "__main__":
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        pass