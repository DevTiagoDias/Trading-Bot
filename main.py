"""
Orquestrador Principal do Sistema de Trading Institucional.

Integra todos os componentes:
- Conexão MT5
- Análise de dados
- Estratégia primária
- Meta-labeling
- Gestão de risco
- Execução de ordens
- Notificações Telegram
- Retreinamento Automático

Fluxo de Execução:
1. Carrega configurações
2. Inicializa componentes
3. Conecta ao MT5
4. Loop assíncrono de trading (Paralelo ao Telegram)
"""

# --- FILTRO DE AVISOS (CRÍTICO PARA LIMPEZA DO TERMINAL) ---
import warnings
import os

# Define variável de ambiente para suprimir avisos em subprocessos do joblib
os.environ["PYTHONWARNINGS"] = "ignore"

# Silencia avisos específicos do scikit-learn/joblib sobre paralelismo.
warnings.filterwarnings("ignore", message=".*sklearn.utils.parallel.delayed.*")
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")
# -----------------------------------------------------------

import asyncio
import json
import signal
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

# Imports dos módulos do sistema
from core import configure_logging_from_config, get_logger, MT5Client, measure_time, TelegramBot
from data import FeatureEngine, CUSUMFilter
from strategies import PrimaryStrategy, MetaLabeler, AITradingLogic
from risk import KellyRiskManager
from execution import OrderManager
from train_model import train_meta_model  # Importa função de treino para o modo automático

logger = get_logger(__name__)


class TradingBot:
    """
    Robô de Trading Institucional com IA.
    
    Orquestra todos os componentes do sistema de forma assíncrona
    com tratamento robusto de erros e reconexão automática.
    """
    
    def __init__(self, config_path: str = "config/settings.json"):
        """
        Inicializa o robô de trading.
        
        Args:
            config_path: Caminho para arquivo de configuração
        """
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        self.running = False
        
        # Tarefa de Background do Telegram
        self.telegram_task: Optional[asyncio.Task] = None
        
        # Componentes do sistema (inicializados em setup)
        self.mt5_client: Optional[MT5Client] = None
        self.feature_engine: Optional[FeatureEngine] = None
        self.cusum_filters: Dict[str, CUSUMFilter] = {}
        self.primary_strategy: Optional[PrimaryStrategy] = None
        self.meta_labeler: Optional[MetaLabeler] = None
        self.ai_logic: Optional[AITradingLogic] = None
        self.risk_manager: Optional[KellyRiskManager] = None
        self.order_manager: Optional[OrderManager] = None
        self.telegram: Optional[TelegramBot] = None
        
        # Estado do sistema
        self.symbols: list = []
        self.active_positions: Dict[str, Any] = {}
        self.last_retrain_check = datetime.now()
        
        logger.info("=" * 80)
        logger.info("TradingBot Inicializado")
        logger.info("=" * 80)
    
    def load_config(self) -> None:
        """
        Carrega configurações do arquivo JSON.
        """
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            
            logger.info(f"Configurações carregadas de {self.config_path}")
            
        except Exception as e:
            logger.error(f"Erro ao carregar configurações: {e}")
            raise
    
    async def setup(self) -> None:
        """
        Inicializa todos os componentes do sistema.
        """
        logger.info("Inicializando componentes do sistema...")
        
        # Configura logging
        configure_logging_from_config(self.config_path)
        
        # Carrega configurações
        self.load_config()
        
        # Inicializa Telegram
        tg_config = self.config.get('telegram', {'enabled': False})
        self.telegram = TelegramBot(
            token=tg_config.get('token', ''),
            chat_id=tg_config.get('chat_id', ''),
            enabled=tg_config.get('enabled', False)
        )
        
        # Inicializa MT5 Client
        mt5_config = self.config['mt5']
        self.mt5_client = MT5Client(
            login=mt5_config['login'],
            password=mt5_config['password'],
            server=mt5_config['server'],
            timeout=mt5_config['timeout'],
            path=mt5_config.get('path', '')
        )
        
        # Conecta ao MT5
        await self.mt5_client.connect()
        
        # Envia mensagem de início com saldo
        account_info = await self.mt5_client.get_account_info()
        if account_info:
            await self.telegram.send_startup_message(balance=account_info['balance'])
        
        # Inicializa Feature Engine
        strategy_config = self.config['strategy']
        self.feature_engine = FeatureEngine(
            ema_period=strategy_config['ema_period'],
            rsi_period=strategy_config['rsi_period'],
            atr_period=strategy_config['atr_period']
        )
        
        # Inicializa filtros CUSUM para cada símbolo
        self.symbols = self.config['trading']['symbols']
        for symbol in self.symbols:
            self.cusum_filters[symbol] = CUSUMFilter(
                threshold=strategy_config['cusum_threshold'],
                drift=strategy_config['cusum_drift']
            )
        
        # Inicializa Estratégia Primária
        risk_config = self.config['risk']
        self.primary_strategy = PrimaryStrategy(
            ema_period=strategy_config['ema_period'],
            rsi_period=strategy_config['rsi_period'],
            rsi_overbought=strategy_config['rsi_overbought'],
            rsi_oversold=strategy_config['rsi_oversold'],
            sl_atr_mult=risk_config['stop_loss_atr_multiplier'],
            tp_atr_mult=risk_config['take_profit_atr_multiplier']
        )
        
        # Inicializa Meta-Labeler
        ml_config = self.config['ml']
        self.meta_labeler = MetaLabeler(
            n_estimators=ml_config['n_estimators'],
            max_depth=ml_config['max_depth'],
            min_samples_split=ml_config['min_samples_split'],
            random_state=ml_config['random_state'],
            model_path=ml_config['model_path']
        )
        
        # Inicializa AI Logic
        self.ai_logic = AITradingLogic(
            feature_engine=self.feature_engine,
            primary_strategy=self.primary_strategy,
            meta_labeler=self.meta_labeler,
            meta_threshold=strategy_config['meta_model_threshold']
        )
        
        # Inicializa Risk Manager
        self.risk_manager = KellyRiskManager(
            kelly_fraction=risk_config['kelly_fraction'],
            max_risk_per_trade=risk_config['max_risk_per_trade'],
            estimated_win_rate=risk_config['estimated_win_rate'],
            min_kelly_exposure=risk_config['min_kelly_exposure'],
            max_kelly_exposure=risk_config['max_kelly_exposure']
        )
        
        # Inicializa Order Manager
        trading_config = self.config['trading']
        self.order_manager = OrderManager(
            mt5_client=self.mt5_client,
            magic_number=trading_config['magic_number'],
            deviation=trading_config['deviation'],
            max_retries=3
        )
        
        logger.info("✓ Todos os componentes inicializados com sucesso")
    
    async def check_and_retrain_model(self):
        """
        Verifica se precisa retreinar o modelo baseado no tempo decorrido.
        Se necessário, pausa o trading, treina e recarrega o modelo.
        """
        try:
            # Intervalo configurado (padrão 168h = 1 semana)
            interval_hours = self.config['ml'].get('retrain_interval_hours', 168)
            last_train = self.meta_labeler.last_training_date
            
            should_train = False
            
            # Se nunca foi treinado ou se passou do tempo
            if last_train is None:
                should_train = True
            else:
                elapsed = datetime.now() - last_train
                if elapsed.total_seconds() > (interval_hours * 3600):
                    should_train = True
            
            if should_train:
                logger.info("⏳ Modelo desatualizado. Iniciando retreinamento automático...")
                
                if self.telegram:
                    await self.telegram.send_message("⚙️ <b>Manutenção:</b> Retreinando Inteligência Artificial com dados recentes...")
                
                # Usa o primeiro símbolo da lista para treino (padrão)
                train_symbol = self.symbols[0] if self.symbols else "EURUSD"
                
                # Executa o treinamento em modo silencioso
                result = await train_meta_model(
                    symbol=train_symbol,
                    side=3, # Treina ambos os lados
                    silent=True
                )
                
                if result['success']:
                    # Recarrega o modelo novo na memória
                    self.meta_labeler.reload()
                    logger.info(f"✓ Modelo atualizado com sucesso. Nova acurácia: {result['acc']:.2%}")
                    
                    if self.telegram:
                        await self.telegram.send_message(
                            f"✅ <b>IA Atualizada!</b>\n"
                            f"Nova Acurácia: {result['acc']:.1%}\n"
                            f"Sistema pronto para operar."
                        )
                else:
                    logger.error("Falha no retreinamento automático")
                    if self.telegram:
                        await self.telegram.send_message("⚠️ <b>Erro:</b> Falha ao atualizar IA. Usando modelo anterior.")
                    
        except Exception as e:
            logger.error(f"Erro no processo de retreinamento: {e}", exc_info=True)

    @measure_time
    async def process_symbol(self, symbol: str) -> None:
        """
        Processa um símbolo: análise, geração de sinal e execução.
        
        Args:
            symbol: Nome do símbolo a processar
        """
        try:
            # Verifica se já existe posição aberta para este símbolo
            existing_positions = await self.mt5_client.get_positions(symbol)
            
            if existing_positions:
                logger.debug(f"{symbol}: Posição já aberta, pulando análise")
                return
            
            # Obtém dados históricos
            timeframe = self.config['trading']['timeframe']
            lookback = self.config['strategy']['lookback_bars']
            
            df = await self.mt5_client.get_rates(symbol, timeframe, lookback)
            
            if df is None or len(df) < self.config['strategy']['min_data_points']:
                logger.warning(f"{symbol}: Dados insuficientes")
                return
            
            # Calcula retorno logarítmico para CUSUM
            df['log_return'] = df['close'].pct_change().apply(lambda x: 0 if abs(x) < 1e-10 else x)
            last_return = df['log_return'].iloc[-1]
            
            # Atualiza filtro CUSUM
            cusum_filter = self.cusum_filters[symbol]
            event_detected, direction = cusum_filter.update(
                last_return,
                df.index[-1]
            )
            
            # Só prossegue se CUSUM detectou evento
            if not event_detected:
                logger.debug(f"{symbol}: Nenhum evento CUSUM detectado")
                return
            
            logger.info(f"{symbol}: ⚡ EVENTO CUSUM DETECTADO - Direção: {direction}")
            
            # Analisa com IA
            signal = self.ai_logic.analyze(df)
            
            if signal['action'] == 'HOLD':
                logger.info(f"{symbol}: Nenhum sinal de trading gerado")
                return
            
            # Valida com meta-modelo
            if not signal.get('meta_approved', False):
                prob = signal.get('meta_probability', 0.0)
                logger.info(f"{symbol}: Sinal rejeitado pelo meta-modelo (Probabilidade IA: {prob:.2%})")
                return
            
            # Sinal Aprovado (Restauração da demonstração de porcentagem requerida)
            logger.info(
                f"{symbol}: ✓ SINAL APROVADO - "
                f"Ação: {signal['action']}, "
                f"Probabilidade: {signal['meta_probability']:.2%}"
            )
            
            # Obtém informações da conta
            account_info = await self.mt5_client.get_account_info()
            if account_info is None:
                logger.error(f"{symbol}: Erro ao obter informações da conta")
                return
            
            # Obtém informações do símbolo
            symbol_info = await self.mt5_client.get_symbol_info(symbol)
            if symbol_info is None:
                logger.error(f"{symbol}: Erro ao obter informações do símbolo")
                return
            
            # Calcula payoff ratio
            payoff_ratio = self.risk_manager.calculate_payoff_ratio(
                entry_price=signal['entry_price'],
                stop_loss=signal['sl'],
                take_profit=signal['tp']
            )
            
            # Calcula tamanho da posição
            position_size = self.risk_manager.calculate_position_size(
                account_balance=account_info['balance'],
                entry_price=signal['entry_price'],
                stop_loss=signal['sl'],
                symbol_info=symbol_info,
                win_rate=signal['meta_probability'],
                payoff_ratio=payoff_ratio
            )
            
            if not position_size['valid']:
                logger.error(f"{symbol}: Tamanho de posição inválido")
                return
            
            # Valida trade
            all_positions = await self.mt5_client.get_positions()
            max_positions = self.config['trading']['max_positions']
            
            validation = self.risk_manager.validate_trade(
                account_balance=account_info['balance'],
                account_equity=account_info['equity'],
                existing_positions=len(all_positions),
                max_positions=max_positions,
                proposed_risk=position_size['risk_amount']
            )
            
            if not validation['approved']:
                logger.warning(f"{symbol}: Trade rejeitado pela validação de risco")
                return
            
            # Executa ordem
            logger.info(
                f"{symbol}: Executando {signal['action']} - "
                f"{position_size['volume']:.2f} lots"
            )
            
            order_result = await self.order_manager.send_market_order(
                symbol=symbol,
                order_type=signal['action'],
                volume=position_size['volume'],
                stop_loss=signal['sl'],
                take_profit=signal['tp'],
                comment=f"AI-{signal['meta_probability']:.0%}"
            )
            
            if order_result['success']:
                logger.info(
                    f"{symbol}: ✓✓✓ ORDEM EXECUTADA COM SUCESSO ✓✓✓"
                )
                logger.info(
                    f"Ticket: {order_result['ticket']}, "
                    f"Preço: {order_result['price']}, "
                    f"Risco: {position_size['risk_amount']:.2f} "
                    f"({position_size['risk_percentage']:.2f}%)"
                )
                
                # Armazena informação da posição
                self.active_positions[symbol] = {
                    'ticket': order_result['ticket'],
                    'opened_at': datetime.now(),
                    'signal': signal,
                    'position_size': position_size
                }
                
                # --- NOTIFICAÇÃO TELEGRAM ---
                if self.telegram:
                    # Obtém dados atualizados da conta para mostrar o saldo correto
                    updated_account = await self.mt5_client.get_account_info()
                    balance = updated_account['balance'] if updated_account else account_info['balance']
                    equity = updated_account['equity'] if updated_account else account_info['equity']

                    await self.telegram.send_trade_alert(
                        symbol=symbol,
                        action=signal['action'],
                        price=order_result['price'],
                        volume=position_size['volume'],
                        sl=signal['sl'],
                        tp=signal['tp'],
                        prob=signal['meta_probability'],
                        ticket=order_result['ticket'],
                        balance=balance,
                        equity=equity
                    )
                # -----------------------------

            else:
                logger.error(
                    f"{symbol}: ✗ FALHA NA EXECUÇÃO: {order_result.get('error')}"
                )
        
        except Exception as e:
            logger.error(f"{symbol}: Erro no processamento de {symbol}: {e}", exc_info=True)
    
    async def trading_loop(self) -> None:
        """
        Loop principal de trading assíncrono.
        
        Varre continuamente todos os símbolos configurados,
        processa sinais e executa operações.
        """
        loop_interval = self.config['system']['loop_interval']
        
        logger.info("=" * 80)
        logger.info("Iniciando Loop de Trading")
        logger.info(f"Símbolos: {', '.join(self.symbols)}")
        logger.info(f"Intervalo: {loop_interval}s")
        logger.info("=" * 80)
        
        iteration = 0
        
        while self.running:
            try:
                iteration += 1
                if iteration % 100 == 0:
                    logger.info(f"--- Iteração {iteration} ---")
                
                # Garante conexão
                if not await self.mt5_client.ensure_connected():
                    logger.error("Conexão perdida. Tentando reconectar...")
                    await asyncio.sleep(5.0)
                    continue
                
                # VERIFICAÇÃO DE RETREINAMENTO AUTOMÁTICO
                # Verifica a cada ~60 segundos para não sobrecarregar
                if (datetime.now() - self.last_retrain_check).total_seconds() > 60:
                    await self.check_and_retrain_model()
                    self.last_retrain_check = datetime.now()
                
                # Processa cada símbolo
                for symbol in self.symbols:
                    await self.process_symbol(symbol)
                
                # Aguarda antes da próxima iteração (NON-BLOCKING)
                await asyncio.sleep(loop_interval)
            
            except KeyboardInterrupt:
                logger.info("Interrupção do usuário detectada")
                break
            
            except Exception as e:
                logger.error(f"Erro no loop de trading: {e}", exc_info=True)
                await asyncio.sleep(5.0)  # Delay em caso de erro
        
        logger.info("Loop de trading finalizado")
    
    async def shutdown(self) -> None:
        """
        Desliga o sistema de forma segura.
        """
        logger.info("Iniciando shutdown...")
        
        self.running = False
        
        # Para o bot do Telegram
        if self.telegram:
            self.telegram.stop()
            
        if self.telegram_task:
            logger.info("Cancelando tarefa do Telegram...")
            self.telegram_task.cancel()
            try:
                await self.telegram_task
            except asyncio.CancelledError:
                pass
        
        # Desconecta do MT5
        if self.mt5_client:
            await self.mt5_client.disconnect()
        
        logger.info("Shutdown concluído")
    
    async def run(self) -> None:
        """
        Executa o robô de trading.
        """
        try:
            # Setup
            await self.setup()
            
            # Inicia Telegram em Background Task (Paralelo)
            if self.telegram and self.telegram.enabled:
                logger.info("Iniciando serviço Telegram em background...")
                self.telegram_task = asyncio.create_task(
                    self.telegram.start(self.mt5_client)
                )
            
            # Inicia loop de trading
            self.running = True
            await self.trading_loop()
        
        except Exception as e:
            logger.critical(f"Erro crítico: {e}", exc_info=True)
        
        finally:
            await self.shutdown()


async def main():
    """
    Função principal assíncrona.
    """
    # Cria instância do bot
    bot = TradingBot(config_path="config/settings.json")
    
    # Configura handlers de sinal para shutdown gracioso (Sem logger.info interno para o Windows)
    def signal_handler(signum, frame):
        asyncio.create_task(bot.shutdown())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Executa bot
    await bot.run()


if __name__ == "__main__":
    """
    Ponto de entrada do programa.
    """
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            
        # Executa loop assíncrono
        asyncio.run(main())
    
    except KeyboardInterrupt:
        print("\n\nPrograma interrompido pelo usuário")
    
    except Exception as e:
        print(f"\n\nErro fatal: {e}")
        sys.exit(1)