# Robô de Trading Profissional MT5/Python

Sistema completo de trading algorítmico para MetaTrader 5, desenvolvido com arquitetura modular e orientada a objetos.

## 🎯 Características

- **Arquitetura Modular**: Separação clara de responsabilidades (dados, estratégia, execução, risco)
- **Padrão Singleton**: Conexão única e gerenciada com MT5
- **Retry Inteligente**: Reconexão automática em falhas transientes
- **Gestão de Risco Avançada**: Cálculo dinâmico de lotes, circuit breaker, drawdown protection
- **Buffer Circular**: Gerenciamento eficiente de memória para dados históricos
- **Indicadores Técnicos**: Integração com pandas_ta (RSI, EMA, ATR)
- **Tratamento de Erros**: Handling granular de códigos MT5 (requote, invalid fill, etc.)
- **Trailing Stops**: Stops dinâmicos baseados em ATR
- **Logging Profissional**: Logs rotativos com níveis distintos
- **Notificações**: Alertas via Telegram

## 📁 Estrutura do Projeto

```
trading_bot/
├── config/
│   ├── __init__.py          # Carregador de configurações
│   └── settings.json        # Arquivo de configurações
├── core/
│   ├── __init__.py
│   ├── logger.py            # Sistema de logging
│   └── mt5_interface.py     # Interface MT5 com Singleton
├── data/
│   ├── __init__.py
│   └── data_feed.py         # Handler de dados de mercado
├── strategies/
│   ├── __init__.py
│   ├── base.py              # Classe abstrata base
│   └── atr_trend_follower.py # Estratégia concreta
├── execution/
│   ├── __init__.py
│   └── order_manager.py     # Gestor de ordens
├── risk/
│   ├── __init__.py
│   └── risk_manager.py      # Gestor de risco
├── utils/
│   ├── __init__.py
│   └── notifications.py     # Sistema de notificações
├── main.py                  # Orquestrador principal
└── requirements.txt
```

## 🚀 Instalação

### 1. Pré-requisitos

- Python 3.9 ou superior
- MetaTrader 5 instalado e configurado
- Conta demo ou real no MT5

### 2. Instalar Dependências

```bash
pip install -r requirements.txt
```

### 3. Configurar o Bot

Edite o arquivo `config/settings.json`:

```json
{
  "mt5": {
    "login": 12345678,          # Seu login MT5
    "password": "sua_senha",     # Sua senha
    "server": "MetaQuotes-Demo", # Servidor MT5
    "path": ""                   # Deixe vazio para auto-detect
  },
  "trading": {
    "symbols": ["EURUSD", "GBPUSD"],
    "timeframe": "M15",
    "max_positions": 3
  },
  "risk": {
    "risk_per_trade_percent": 1.0,    # Risco por trade
    "max_daily_drawdown_percent": 3.0 # Limite de DD diário
  }
}
```

### 4. Habilitar AlgoTrading no MT5

1. Abra o MetaTrader 5
2. Ferramentas → Opções → Expert Advisors
3. ✅ Ative "Permitir negociação algorítmica/automatizada"

## 🎮 Como Usar

### Executar o Bot

```bash
python main.py
```

### Parar o Bot

- Pressione `Ctrl+C` para shutdown gracioso
- O bot fechará todas as posições se `close_all_eod: true`

## 📊 Estratégia Implementada: ATR Trend Follower

### Lógica de Entrada

**Compra (BUY)**:
- Preço > EMA(200) → Tendência de alta
- RSI < 30 → Pullback (sobrevenda)
- Stop Loss: Preço - (2.0 × ATR)
- Take Profit: Preço + (4.0 × ATR)

**Venda (SELL)**:
- Preço < EMA(200) → Tendência de baixa
- RSI > 70 → Pullback (sobrecompra)
- Stop Loss: Preço + (2.0 × ATR)
- Take Profit: Preço - (4.0 × ATR)

### Saída

- **Trailing Stop**: 2.0 × ATR, ajustado dinamicamente
- Stop só sobe, nunca desce (para compras)

## 🛡️ Gestão de Risco

### Cálculo de Lote

```
Lote = (Saldo × Risco%) / (Distância_SL_Pontos × Valor_do_Tick)
```

### Circuit Breaker

- Ativa automaticamente se drawdown diário ≥ 3%
- Bloqueia novas operações até o próximo dia
- Envia alerta via Telegram

### Validações Pré-Trade

- ✓ Margem livre > 20%
- ✓ Spread < 20 pontos
- ✓ Máximo de 3 posições simultâneas
- ✓ Horário de trading (8h-22h)

## 📝 Logs

Os logs são salvos em `logs/trading_bot.log` com rotação automática:

```
2026-01-29 14:23:45 | INFO     | BUY EURUSD | Lot: 0.10 | Price: 1.08450
2026-01-29 14:25:12 | INFO     | Position closed | EURUSD | Profit: $12.50
2026-01-29 15:01:03 | ERROR    | CIRCUIT BREAKER | Drawdown: 3.2%
```

## 🔔 Notificações (Telegram)

### Configurar

1. Crie um bot no Telegram via [@BotFather](https://t.me/botfather)
2. Obtenha o token do bot
3. Obtenha seu chat_id via [@userinfobot](https://t.me/userinfobot)
4. Configure no `settings.json`:

```json
"notifications": {
  "telegram_enabled": true,
  "telegram_token": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
  "telegram_chat_id": "987654321"
}
```

## 🧪 Testes

Execute em conta **DEMO** primeiro:

1. Configure uma conta demo no MT5
2. Ajuste `risk_per_trade_percent: 0.5` para testes conservadores
3. Execute por 1 semana para validar
4. Analise os logs em `logs/`

## ⚠️ Avisos Importantes

- ⚠️ **USE POR SUA CONTA E RISCO**
- ⚠️ Sempre teste em conta DEMO primeiro
- ⚠️ O desempenho passado não garante resultados futuros
- ⚠️ Nunca arrisque mais do que pode perder
- ⚠️ Monitore o bot regularmente

## 🔧 Personalização

### Criar Nova Estratégia

1. Herde de `BaseStrategy` em `strategies/base.py`
2. Implemente `generate_signal()` e `on_tick()`
3. Registre no `main.py`

Exemplo:

```python
from strategies.base import BaseStrategy, TradeSignal, SignalType

class MinhaEstrategia(BaseStrategy):
    def __init__(self):
        super().__init__("Minha Estratégia")
    
    def generate_signal(self, symbol, dataframe):
        # Sua lógica aqui
        pass
    
    def on_tick(self, symbol, tick_data):
        # Processamento de tick
        pass
```

## 📞 Suporte

- Logs detalhados em `logs/trading_bot.log`
- Códigos de erro MT5: [Documentação Oficial](https://www.mql5.com/en/docs/constants/errorswarnings/enum_trade_return_codes)

## 📜 Licença

Este código é fornecido "como está" para fins educacionais. O autor não se responsabiliza por perdas financeiras.

---

**Desenvolvido com foco em:**
- Segurança do capital
- Robustez operacional
- Código limpo e manutenível
- Extensibilidade