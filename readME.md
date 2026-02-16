# 🤖 Trading Bot MT5/Python - Professional

Sistema completo de trading algorítmico para MetaTrader 5, desenvolvido com arquitetura modular, orientação a objetos e foco em gestão de risco profissional.

## 📋 Características Principais

### ✅ Arquitetura Profissional
- **Modular**: Código organizado em módulos claros e independentes
- **Orientado a Objetos**: Uso de classes, herança e composição
- **Type Hinting**: Tipagem estática em todas as funções
- **Production-Ready**: Pronto para ambiente de produção

### 🛡️ Gestão de Risco Avançada
- **Cálculo Dinâmico de Posição**: Baseado em risco monetário e ATR
- **Circuit Breaker**: Bloqueio automático ao atingir drawdown diário
- **Validação Pré-Execução**: Todas as ordens validadas antes de envio
- **Tick Value Real-Time**: Suporta pares cruzados e índices corretamente

### 🔄 Conectividade Robusta
- **Padrão Singleton**: Uma única conexão MT5
- **Retry Logic Inteligente**: Reconexão automática em falhas transientes
- **Tratamento de Erros**: Códigos de erro MT5 tratados individualmente
- **Requote Handling**: Retentativa automática com novo preço

### 📊 Pipeline de Dados Eficiente
- **Buffer Circular**: Rolling window de 1000 candles
- **Indicadores Técnicos**: Integração com pandas_ta
- **Atualização Incremental**: Evita recálculo desnecessário

### 📈 Motor de Estratégia Extensível
- **Classe Base Abstrata**: Interface padronizada para estratégias
- **Estratégia Exemplo**: ATR Trend Follower implementada
- **Fácil Extensão**: Adicione novas estratégias facilmente

### 📝 Sistema de Logging Profissional
- **Rotativo**: Logs com rotação automática
- **Níveis Distintos**: INFO, WARNING, ERROR com contexto
- **Logs Especializados**: Trade logs, signal logs, risk logs

## 🏗️ Estrutura do Projeto

```
trading_bot/
├── config/
│   └── settings.json          # Configurações centralizadas
├── core/
│   ├── logger.py             # Sistema de logging
│   └── mt5_interface.py      # Interface MT5 (Singleton + Retry)
├── data/
│   └── data_feed.py          # Market data handler (Buffer Circular)
├── strategies/
│   ├── base.py               # Classe abstrata base
│   └── atr_trend_follower.py # Estratégia ATR Trend Follower
├── execution/
│   └── order_manager.py      # Gestor de ordens
├── risk/
│   └── risk_manager.py       # Gestor de risco (CRÍTICO)
├── utils/
│   └── config.py             # Utilitário de configuração
├── main.py                   # Orquestrador principal
└── requirements.txt          # Dependências
```

## 🚀 Instalação

### 1. Pré-requisitos
- Python 3.8 ou superior
- MetaTrader 5 instalado
- Conta demo ou real no MT5

### 2. Instalar Dependências

```bash
pip install -r requirements.txt
```

### 3. Configurar settings.json

Edite `config/settings.json` com suas credenciais:

```json
{
  "mt5": {
    "login": 12345678,
    "password": "sua_senha",
    "server": "MetaQuotes-Demo"
  }
}
```

## ⚙️ Configuração

### Parâmetros de Risco (Críticos)

```json
{
  "risk": {
    "risk_percent_per_trade": 1.0,      // Risco por operação (% do saldo)
    "max_daily_drawdown_percent": 3.0,  // Drawdown máximo diário
    "max_position_size": 1.0,           // Tamanho máximo (lotes)
    "min_position_size": 0.01,          // Tamanho mínimo (lotes)
    "use_dynamic_sizing": true          // Ajuste baseado em volatilidade
  }
}
```

### Parâmetros da Estratégia

```json
{
  "strategy": {
    "atr_trend_follower": {
      "ema_period": 200,              // Período da EMA
      "rsi_period": 14,               // Período do RSI
      "rsi_oversold": 30,             // Nível de sobrevenda
      "rsi_overbought": 70,           // Nível de sobrecompra
      "atr_period": 14,               // Período do ATR
      "atr_multiplier_stop": 2.0,     // Multiplicador ATR para stop
      "atr_multiplier_target": 3.0    // Multiplicador ATR para target
    }
  }
}
```

## 🎯 Uso

### Modo Normal

```bash
python main.py
```

### Com Configuração Customizada

```python
from main import TradingBot

bot = TradingBot(config_path="minha_config.json")
bot.initialize()
bot.run()
```

## 📊 Lógica da Estratégia ATR Trend Follower

### Condições de Compra (BUY)
```
✓ Preço > EMA(200)  [Tendência de alta]
✓ RSI < 30          [Pullback/sobrevenda]
→ Stop Loss: Preço - (2.0 × ATR)
→ Take Profit: Preço + (3.0 × ATR)
```

### Condições de Venda (SELL)
```
✓ Preço < EMA(200)  [Tendência de baixa]
✓ RSI > 70          [Pullback/sobrecompra]
→ Stop Loss: Preço + (2.0 × ATR)
→ Take Profit: Preço - (3.0 × ATR)
```

## 🛡️ Sistema de Gestão de Risco

### Cálculo de Posição

```
Lotes = (Saldo × Risco%) / (Distância_SL_Pontos × Valor_do_Ponto)
```

**Exemplo:**
- Saldo: $10,000
- Risco: 1% = $100
- Stop Loss: 50 pontos
- Valor do Ponto: $1
- **Resultado: 2.0 lotes**

### Circuit Breaker

Quando o drawdown diário atinge **3%**:
- ❌ Todas as novas operações são BLOQUEADAS
- ⚠️ Sistema entra em modo de proteção
- ✅ Reativa automaticamente no próximo dia

## 📝 Logs

Os logs são salvos em `logs/` com rotação automática:

```
logs/
├── trading_bot_20241216.log
├── trading_bot_20241216.log.1
└── trading_bot_20241216.log.2
```

### Tipos de Log

- **TRADE**: Ordens executadas
- **SIGNAL**: Sinais gerados
- **RISK**: Eventos de gestão de risco
- **ERROR**: Erros e exceções

## 🔧 Tratamento de Erros MT5

### Erros Tratados Automaticamente

| Código | Erro | Ação |
|--------|------|------|
| 10004 | Requote | Retenta com novo preço |
| 10030 | Fill inválido | Tenta tipo alternativo |
| -10005 | Connection lost | Reconecta automaticamente |

### Erros Que Bloqueiam Execução

| Código | Erro | Resultado |
|--------|------|-----------|
| 10018 | Mercado fechado | Aguarda abertura |
| 10019 | Sem saldo | Bloqueia trading |
| 10017 | Trading desabilitado | Alerta usuário |

## 🔌 Extensibilidade

### Criar Nova Estratégia

```python
from strategies.base import BaseStrategy, TradingSignal, SignalType

class MinhaEstrategia(BaseStrategy):
    def __init__(self, parameters):
        super().__init__("Minha Estratégia", parameters)
    
    def initialize(self) -> bool:
        # Lógica de inicialização
        return True
    
    def generate_signal(self, data, symbol) -> Optional[TradingSignal]:
        # Lógica da estratégia
        if condicao_compra:
            return TradingSignal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                price=preco,
                stop_loss=sl,
                take_profit=tp
            )
        return None
    
    def on_tick(self, symbol, bid, ask):
        return None
    
    def should_close_position(self, symbol, entry_price, current_price, position_type):
        return False
```

## ⚠️ Avisos Importantes

### ⚡ NUNCA em Produção Sem Teste

1. **Sempre teste em conta DEMO primeiro**
2. **Ajuste os parâmetros de risco para seu perfil**
3. **Monitore os primeiros dias de operação**
4. **Tenha um plano de contingência**

### 🔐 Segurança

- **Não compartilhe** seu `settings.json` com credenciais
- **Use senhas fortes** na conta MT5
- **Monitore** as operações regularmente
- **Backup** dos logs e configurações

## 📚 Documentação Adicional

### Ordem de Execução

1. **Carrega configuração** → `config/settings.json`
2. **Conecta ao MT5** → `MT5Client.connect()`
3. **Inicializa buffers** → `MarketDataHandler.initialize_buffers()`
4. **Setup estratégia** → `ATRTrendFollower.initialize()`
5. **Inicia loop** → `TradingBot.run()`

### Loop Principal

```
Loop Infinito (a cada 60s):
├── Verifica reset diário
├── Verifica conexão MT5
├── Atualiza dados de mercado
├── Para cada símbolo:
│   ├── Calcula indicadores
│   ├── Gera sinal
│   ├── Valida risco
│   ├── Calcula tamanho
│   └── Executa ordem
└── Log status a cada 5min
```

## 🤝 Contribuindo

Para adicionar funcionalidades:
1. Mantenha a estrutura modular
2. Use type hinting
3. Documente com docstrings
4. Teste em ambiente demo

## 📄 Licença

Este código é fornecido como exemplo educacional. Use por sua conta e risco.

## ⚖️ Disclaimer

**TRADING ENVOLVE RISCO DE PERDA FINANCEIRA**

- Este software é fornecido "como está"
- Não há garantia de lucros
- Pode resultar em perdas significativas
- Teste extensivamente antes de usar capital real
- O autor não se responsabiliza por perdas

---

**Desenvolvido com foco em segurança, modularidade e gestão profissional de risco.**
