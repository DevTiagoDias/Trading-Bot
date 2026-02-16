"""
Trading Bot Main - Orquestrador Principal
Coordena todos os componentes do sistema de trading
"""

import time
import signal
import sys
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

# Imports dos módulos do sistema
from core.logger import TradingLogger, logger_instance
from core.mt5_interface import MT5Client
from data.data_feed import MarketDataHandler
from strategies.atr_trend_follower import ATRTrendFollower
from execution.order_manager import OrderManager
from risk.risk_manager import RiskManager
from utils.config import load_config


class TradingBot:
    """
    Bot de Trading Principal
    Coordena todos os componentes
    """

    def __init__(self, config_path: str = "config/settings.json"):
        """
        Args:
            config_path: Caminho do arquivo de configuração
        """
        self.config_path = config_path
        self.config: Optional[Dict[str, Any]] = None
        self.running = False
        
        # Componentes
        self.logger = None
        self.mt5_client: Optional[MT5Client] = None
        self.data_handler: Optional[MarketDataHandler] = None
        self.strategy: Optional[ATRTrendFollower] = None
        self.order_manager: Optional[OrderManager] = None
        self.risk_manager: Optional[RiskManager] = None
        
        # Controle
        self.last_update = datetime.now()
        self.last_daily_reset = datetime.now().date()
        
        # Setup signal handlers para shutdown gracioso
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def initialize(self) -> bool:
        """
        Inicializa todos os componentes
        
        Returns:
            True se inicialização bem sucedida
        """
        print("=" * 80)
        print("INICIALIZANDO TRADING BOT")
        print("=" * 80)
        
        try:
            # 1. Carrega configuração
            print("Carregando configuração...")
            self.config = load_config(self.config_path)
            print("✓ Configuração carregada")
            
            # 2. Setup Logger
            print("Configurando sistema de logging...")
            log_config = self.config.get('logging', {})
            logger_instance.setup(
                log_level=log_config.get('level', 'INFO'),
                log_to_file=log_config.get('log_to_file', True),
                log_dir=log_config.get('log_dir', 'logs'),
                max_bytes=log_config.get('max_bytes', 10485760),
                backup_count=log_config.get('backup_count', 5)
            )
            self.logger = logger_instance.get_logger()
            print("✓ Logger configurado")
            
            # 3. Conecta ao MT5
            self.logger.info("Conectando ao MetaTrader 5...")
            mt5_config = self.config['mt5']
            self.mt5_client = MT5Client()
            
            if not self.mt5_client.connect(
                login=mt5_config['login'],
                password=mt5_config['password'],
                server=mt5_config['server'],
                path=mt5_config.get('path', ''),
                timeout=mt5_config.get('timeout', 60000)
            ):
                self.logger.error("Falha na conexão com MT5")
                return False
            
            # 4. Inicializa Data Handler
            self.logger.info("Inicializando Market Data Handler...")
            trading_config = self.config['trading']
            self.data_handler = MarketDataHandler(
                symbols=trading_config['symbols'],
                timeframe=trading_config.get('timeframe', 'M15'),
                buffer_size=1000
            )
            
            if not self.data_handler.initialize_buffers():
                self.logger.error("Falha ao inicializar buffers de dados")
                return False
            
            # 5. Inicializa Estratégia
            self.logger.info("Inicializando Estratégia...")
            strategy_config = self.config['strategy']['atr_trend_follower']
            self.strategy = ATRTrendFollower(parameters=strategy_config)
            
            if not self.strategy.initialize():
                self.logger.error("Falha ao inicializar estratégia")
                return False
            
            # 6. Inicializa Order Manager
            self.logger.info("Inicializando Order Manager...")
            self.order_manager = OrderManager(
                magic_number=trading_config.get('magic_number', 123456),
                deviation=20
            )
            
            # 7. Inicializa Risk Manager
            self.logger.info("Inicializando Risk Manager...")
            risk_config = self.config['risk']
            self.risk_manager = RiskManager(
                risk_percent_per_trade=risk_config.get('risk_percent_per_trade', 1.0),
                max_daily_drawdown_percent=risk_config.get('max_daily_drawdown_percent', 3.0),
                max_position_size=risk_config.get('max_position_size', 1.0),
                min_position_size=risk_config.get('min_position_size', 0.01),
                max_positions=trading_config.get('max_positions', 3),
                use_dynamic_sizing=risk_config.get('use_dynamic_sizing', True)
            )
            
            if not self.risk_manager.initialize():
                self.logger.error("Falha ao inicializar Risk Manager")
                return False
            
            self.logger.info("=" * 80)
            self.logger.info("SISTEMA INICIALIZADO COM SUCESSO!")
            self.logger.info("=" * 80)
            
            return True
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Erro na inicialização: {str(e)}", exc_info=True)
            else:
                print(f"ERRO: {str(e)}")
            return False

    def run(self) -> None:
        """Loop principal do bot"""
        if not self.config.get('trading', {}).get('enable_trading', True):
            self.logger.warning("Trading está DESABILITADO na configuração!")
            return

        self.running = True
        self.logger.info("Iniciando loop principal de trading...")
        
        update_interval = 60  # Atualiza a cada 60 segundos
        
        try:
            while self.running:
                try:
                    # Verifica reset diário
                    self._check_daily_reset()
                    
                    # Verifica conexão
                    if not self.mt5_client.check_connection():
                        self.logger.error("Conexão perdida, tentando reconectar...")
                        if not self.mt5_client.reconnect():
                            self.logger.error("Falha na reconexão, aguardando...")
                            time.sleep(30)
                            continue
                    
                    # Atualiza dados de mercado
                    self.data_handler.update_data()
                    
                    # Processa cada símbolo
                    for symbol in self.config['trading']['symbols']:
                        self._process_symbol(symbol)
                    
                    # Log status de risco periodicamente
                    if (datetime.now() - self.last_update).seconds >= 300:  # A cada 5 min
                        self.risk_manager.log_risk_status()
                        self.last_update = datetime.now()
                    
                    # Aguarda próximo ciclo
                    time.sleep(update_interval)
                    
                except KeyboardInterrupt:
                    self.logger.info("Interrupção pelo usuário...")
                    break
                except Exception as e:
                    self.logger.error(f"Erro no loop principal: {str(e)}", exc_info=True)
                    time.sleep(30)
                    
        finally:
            self.shutdown()

    def _process_symbol(self, symbol: str) -> None:
        """
        Processa um símbolo
        
        Args:
            symbol: Símbolo a processar
        """
        try:
            # Obtém dados com indicadores
            required_indicators = self.strategy.get_required_indicators()
            data = self.data_handler.calculate_indicators(symbol, required_indicators)
            
            if data is None or len(data) < 50:
                self.logger.debug(f"Dados insuficientes para {symbol}")
                return
            
            # Gera sinal
            signal = self.strategy.generate_signal(data, symbol)
            
            if signal is None:
                return
            
            # Valida sinal com Risk Manager
            is_valid, reason = self.risk_manager.validate_signal(signal)
            
            if not is_valid:
                self.logger.warning(f"Sinal rejeitado para {symbol}: {reason}")
                logger_instance.log_risk_event("SIGNAL_REJECTED", f"{symbol} - {reason}")
                return
            
            # Calcula tamanho da posição
            volume = self.risk_manager.calculate_position_size(symbol, signal)
            
            if volume is None:
                self.logger.error(f"Falha ao calcular tamanho de posição para {symbol}")
                return
            
            # Log do sinal
            logger_instance.log_signal(symbol, signal.signal_type.value, signal.reason)
            
            # Executa ordem
            self.logger.info(f"Executando sinal: {signal}")
            result = self.order_manager.execute_signal(
                signal=signal,
                volume=volume,
                comment=f"Bot_{signal.signal_type.value}"
            )
            
            if result.success:
                logger_instance.log_trade(
                    action=signal.signal_type.value,
                    symbol=symbol,
                    volume=volume,
                    price=result.price,
                    sl=signal.stop_loss or 0,
                    tp=signal.take_profit or 0,
                    ticket=result.ticket
                )
                self.logger.info(f"✓ Ordem executada: Ticket {result.ticket}")
            else:
                self.logger.error(f"✗ Falha na execução: {result.comment}")
                
        except Exception as e:
            self.logger.error(f"Erro ao processar {symbol}: {str(e)}", exc_info=True)

    def _check_daily_reset(self) -> None:
        """Verifica e executa reset diário se necessário"""
        today = datetime.now().date()
        
        if today > self.last_daily_reset:
            self.logger.info("Novo dia detectado, executando reset diário...")
            self.risk_manager.reset_daily_metrics()
            self.last_daily_reset = today

    def close_all_positions(self) -> None:
        """Fecha todas as posições abertas"""
        self.logger.info("Fechando todas as posições...")
        result = self.order_manager.close_all_positions()
        self.logger.info(f"Posições fechadas: {result}")

    def shutdown(self) -> None:
        """Encerra o sistema graciosamente"""
        self.logger.info("=" * 80)
        self.logger.info("ENCERRANDO TRADING BOT")
        self.logger.info("=" * 80)
        
        self.running = False
        
        # Opcionalmente fecha todas as posições
        # self.close_all_positions()
        
        # Desconecta do MT5
        if self.mt5_client:
            self.mt5_client.disconnect()
        
        self.logger.info("Sistema encerrado")
        self.logger.info("=" * 80)

    def _signal_handler(self, signum, frame):
        """Handler para sinais de sistema"""
        self.logger.info(f"Sinal {signum} recebido, encerrando...")
        self.running = False


def main():
    """Função principal"""
    print("""
    ╔════════════════════════════════════════════╗
    ║   TRADING BOT MT5/PYTHON - PROFESSIONAL   ║
    ║         Sistema de Trading Algorítmico     ║
    ╚════════════════════════════════════════════╝
    """)
    
    # Cria e inicializa bot
    bot = TradingBot(config_path="config/settings.json")
    
    if not bot.initialize():
        print("✗ Falha na inicialização do sistema")
        sys.exit(1)
    
    print("\n✓ Sistema pronto. Iniciando trading...\n")
    
    # Inicia loop principal
    try:
        bot.run()
    except KeyboardInterrupt:
        print("\n\nInterrompido pelo usuário")
    except Exception as e:
        print(f"\n✗ Erro fatal: {str(e)}")
        if bot.logger:
            bot.logger.error("Erro fatal", exc_info=True)
    finally:
        bot.shutdown()


if __name__ == "__main__":
    main()
