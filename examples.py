"""
Exemplo de Uso Avançado do Trading Bot
Demonstra funcionalidades adicionais e customizações
"""

from main import TradingBot
from core.mt5_interface import MT5Client
from risk.risk_manager import RiskManager
import time


def exemplo_basico():
    """Exemplo de uso básico do bot"""
    print("=== EXEMPLO BÁSICO ===\n")
    
    # Cria e inicializa bot
    bot = TradingBot(config_path="config/settings.json")
    
    if bot.initialize():
        print("✓ Bot inicializado com sucesso!")
        
        # Executa por 1 hora
        print("Executando por 1 hora...")
        start_time = time.time()
        
        try:
            while time.time() - start_time < 3600:  # 1 hora
                bot._process_symbol("EURUSD")
                time.sleep(60)
        except KeyboardInterrupt:
            print("\nInterrompido pelo usuário")
        finally:
            bot.shutdown()


def exemplo_monitoramento():
    """Exemplo de monitoramento de métricas"""
    print("=== EXEMPLO MONITORAMENTO ===\n")
    
    bot = TradingBot()
    if not bot.initialize():
        return
    
    try:
        # Obtém métricas de risco a cada minuto
        for _ in range(10):
            metrics = bot.risk_manager.get_risk_metrics()
            
            print("\n--- Métricas de Risco ---")
            print(f"Saldo: ${metrics['balance']:,.2f}")
            print(f"Equity: ${metrics['equity']:,.2f}")
            print(f"P&L Diário: ${metrics['daily_pnl']:,.2f} ({metrics['daily_pnl_percent']:.2f}%)")
            print(f"Posições: {metrics['num_positions']}/{metrics['max_positions']}")
            print(f"Circuit Breaker: {'ATIVO ⚠️' if metrics['circuit_breaker_active'] else 'Inativo ✓'}")
            
            time.sleep(60)
            
    except KeyboardInterrupt:
        print("\nInterrompido")
    finally:
        bot.shutdown()


def exemplo_fechar_tudo():
    """Exemplo de fechamento emergencial de posições"""
    print("=== EXEMPLO FECHAMENTO DE EMERGÊNCIA ===\n")
    
    bot = TradingBot()
    if not bot.initialize():
        return
    
    try:
        # Fecha todas as posições
        print("Fechando todas as posições...")
        result = bot.order_manager.close_all_positions()
        
        print(f"✓ Fechadas: {result['closed']}")
        print(f"✗ Falharam: {result['failed']}")
        print(f"Total: {result['total']}")
        
    finally:
        bot.shutdown()


def exemplo_teste_conexao():
    """Exemplo de teste de conexão"""
    print("=== TESTE DE CONEXÃO ===\n")
    
    from utils.config import load_config
    
    config = load_config("config/settings.json")
    mt5_config = config['mt5']
    
    client = MT5Client()
    
    try:
        print("Tentando conectar ao MT5...")
        if client.connect(
            login=mt5_config['login'],
            password=mt5_config['password'],
            server=mt5_config['server']
        ):
            print("✓ Conexão estabelecida!")
            
            # Obtém informações da conta
            account_info = client.get_account_info()
            if account_info:
                print(f"\nConta: {account_info['login']}")
                print(f"Servidor: {account_info['server']}")
                print(f"Saldo: ${account_info['balance']:,.2f}")
                print(f"Equity: ${account_info['equity']:,.2f}")
                print(f"Margem Livre: ${account_info['margin_free']:,.2f}")
            
            # Obtém informações do terminal
            terminal_info = client.get_terminal_info()
            if terminal_info:
                print(f"\nTerminal: {terminal_info['name']}")
                print(f"Empresa: {terminal_info['company']}")
                print(f"AlgoTrading: {'HABILITADO ✓' if terminal_info['trade_allowed'] else 'DESABILITADO ✗'}")
        else:
            print("✗ Falha na conexão")
    
    finally:
        client.disconnect()


def exemplo_calculo_risco():
    """Exemplo de cálculo de risco"""
    print("=== CÁLCULO DE RISCO ===\n")
    
    from strategies.base import TradingSignal, SignalType
    
    # Configura risk manager
    risk_manager = RiskManager(
        risk_percent_per_trade=1.0,
        max_daily_drawdown_percent=3.0,
        max_position_size=2.0,
        min_position_size=0.01
    )
    
    # Simula um sinal
    signal = TradingSignal(
        symbol="EURUSD",
        signal_type=SignalType.BUY,
        price=1.10000,
        stop_loss=1.09500,  # 50 pips
        take_profit=1.11000,  # 100 pips
        reason="Teste de cálculo"
    )
    
    # Calcula tamanho (com saldo simulado)
    volume = risk_manager.calculate_position_size(
        symbol="EURUSD",
        signal=signal,
        account_balance=10000.0  # $10,000
    )
    
    if volume:
        print(f"✓ Volume calculado: {volume:.2f} lotes")
        
        # Calcula risco e potencial
        risk_amount = 10000.0 * 0.01  # 1% de $10,000
        potential_profit = volume * 100 * 1.0  # 100 pips × $1/pip
        
        print(f"\nRisco: ${risk_amount:,.2f}")
        print(f"Potencial: ${potential_profit:,.2f}")
        print(f"Risk/Reward: 1:{potential_profit/risk_amount:.2f}")


def exemplo_backtest_simples():
    """Exemplo de backtest simples"""
    print("=== BACKTEST SIMPLES ===\n")
    
    from data.data_feed import MarketDataHandler
    from strategies.atr_trend_follower import ATRTrendFollower
    
    # Conecta ao MT5 primeiro
    from core.mt5_interface import MT5Client
    from utils.config import load_config
    
    config = load_config("config/settings.json")
    mt5_config = config['mt5']
    
    client = MT5Client()
    if not client.connect(
        login=mt5_config['login'],
        password=mt5_config['password'],
        server=mt5_config['server']
    ):
        print("Falha na conexão")
        return
    
    try:
        # Carrega dados históricos
        data_handler = MarketDataHandler(
            symbols=["EURUSD"],
            timeframe="H1",
            buffer_size=500
        )
        
        data_handler.initialize_buffers()
        
        # Inicializa estratégia
        strategy = ATRTrendFollower(parameters={
            'ema_period': 200,
            'rsi_period': 14,
            'rsi_oversold': 30,
            'rsi_overbought': 70,
            'atr_period': 14,
            'atr_multiplier_stop': 2.0,
            'atr_multiplier_target': 3.0
        })
        
        strategy.initialize()
        
        # Calcula indicadores
        data = data_handler.calculate_indicators(
            "EURUSD",
            strategy.get_required_indicators()
        )
        
        # Gera sinais para últimos 50 candles
        signals_count = 0
        buy_signals = 0
        sell_signals = 0
        
        for i in range(len(data) - 50, len(data)):
            subset = data.iloc[:i+1]
            signal = strategy.generate_signal(subset, "EURUSD")
            
            if signal:
                signals_count += 1
                if signal.signal_type == SignalType.BUY:
                    buy_signals += 1
                elif signal.signal_type == SignalType.SELL:
                    sell_signals += 1
                
                print(f"\n{data.index[i]}: {signal.signal_type.value}")
                print(f"  Preço: {signal.price:.5f}")
                print(f"  SL: {signal.stop_loss:.5f} | TP: {signal.take_profit:.5f}")
                print(f"  Razão: {signal.reason}")
        
        print(f"\n=== RESUMO ===")
        print(f"Total de sinais: {signals_count}")
        print(f"Sinais de COMPRA: {buy_signals}")
        print(f"Sinais de VENDA: {sell_signals}")
        
    finally:
        client.disconnect()


if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════╗
    ║   EXEMPLOS DE USO - TRADING BOT      ║
    ╚═══════════════════════════════════════╝
    
    Escolha um exemplo:
    1. Uso Básico
    2. Monitoramento de Métricas
    3. Fechamento de Emergência
    4. Teste de Conexão
    5. Cálculo de Risco
    6. Backtest Simples
    """)
    
    choice = input("Digite o número (1-6): ").strip()
    
    if choice == "1":
        exemplo_basico()
    elif choice == "2":
        exemplo_monitoramento()
    elif choice == "3":
        exemplo_fechar_tudo()
    elif choice == "4":
        exemplo_teste_conexao()
    elif choice == "5":
        exemplo_calculo_risco()
    elif choice == "6":
        exemplo_backtest_simples()
    else:
        print("Opção inválida")
