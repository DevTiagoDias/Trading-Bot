# 🤖 Robô de Trading Profissional MT5/Python - Visão Geral

## 📋 Resumo Executivo

Sistema completo de trading algorítmico para MetaTrader 5, desenvolvido com arquitetura enterprise-grade, seguindo as melhores práticas de engenharia de software.

## ✨ Características Principais

### 🏗️ Arquitetura
- **Modular**: Separação clara em camadas (dados, estratégia, execução, risco)
- **Extensível**: Fácil adicionar novas estratégias via herança
- **Manutenível**: Código limpo, documentado e testável
- **Production-Ready**: Tratamento robusto de erros e logging profissional

### 🛡️ Segurança e Gestão de Risco
- **Circuit Breaker**: Parada automática em drawdown excessivo (3%)
- **Cálculo Dinâmico de Lotes**: Baseado em % de risco e ATR
- **Validação Pré-Trade**: Margem, spread, posições simultâneas
- **Trailing Stops**: Stops dinâmicos baseados em ATR

### 🔌 Conectividade
- **Padrão Singleton**: Única instância de conexão MT5
- **Retry Inteligente**: Reconexão automática em falhas transientes
- **Error Handling**: Tratamento específico para cada código de erro MT5
- **Filling Type Detection**: Seleção automática (FOK/IOC/RETURN)

### 📊 Pipeline de Dados
- **Buffer Circular**: Gerenciamento eficiente de memória (1000 candles)
- **Indicadores Técnicos**: Integração com pandas_ta (RSI, EMA, ATR)
- **Atualização Incremental**: Recálculo apenas de dados novos
- **Multi-Símbolo**: Suporte simultâneo a múltiplos pares

### 📈 Estratégia Implementada
**ATR Trend Follower**:
- Compra em pullbacks de tendências de alta (RSI < 30, Preço > EMA200)
- Venda em pullbacks de tendências de baixa (RSI > 70, Preço < EMA200)
- Trailing stops dinâmicos (2.0 × ATR)

## 📁 Estrutura de Arquivos

```
trading_bot/
├── config/
│   ├── __init__.py          # Carregador de configurações (Singleton)
│   └── settings.json        # Configurações centralizadas
│
├── core/
│   ├── __init__.py
│   ├── logger.py            # Sistema de logging com rotação
│   └── mt5_interface.py     # Cliente MT5 (Singleton + Retry)
│
├── data/
│   ├── __init__.py
│   └── data_feed.py         # Handler de dados (Buffer Circular)
│
├── strategies/
│   ├── __init__.py
│   ├── base.py              # Classe abstrata BaseStrategy
│   └── atr_trend_follower.py # Estratégia concreta
│
├── execution/
│   ├── __init__.py
│   └── order_manager.py     # Execução de ordens
│
├── risk/
│   ├── __init__.py
│   └── risk_manager.py      # Gestão de risco + Circuit Breaker
│
├── utils/
│   ├── __init__.py
│   └── notifications.py     # Notificações Telegram
│
├── examples/
│   └── multi_strategy_example.py # Exemplo multi-estratégia
│
├── tests/
│   └── test_risk_manager.py # Testes unitários
│
├── main.py                  # Orquestrador principal
├── setup_check.py          # Script de verificação
├── requirements.txt        # Dependências
├── README.md              # Documentação principal
├── CONTRIBUTING.md        # Guia de desenvolvimento
└── .gitignore             # Ignorar arquivos sensíveis
```

## 🎯 Componentes Detalhados

### 1. Config (`config/`)
- Carregamento centralizado de configurações
- Validação de parâmetros críticos
- Padrão Singleton para acesso global

### 2. Core (`core/`)
- **MT5Interface**: Conexão com retry inteligente
- **Logger**: Sistema de logging rotativo (arquivo + console)
- Decoradores para retry e error handling

### 3. Data (`data/`)
- **MarketDataHandler**: Buffer circular de 1000 candles
- Atualização incremental de indicadores
- Suporte a múltiplos timeframes e símbolos

### 4. Strategies (`strategies/`)
- **BaseStrategy**: Classe abstrata com Template Method
- **ATRTrendFollower**: Implementação concreta
- Extensível via herança

### 5. Execution (`execution/`)
- **OrderManager**: Execução com filling type automático
- Retry em requotes (até 3 tentativas)
- Modificação de posições (SL/TP)

### 6. Risk (`risk/`)
- **RiskManager**: Guardião de todas as operações
- Cálculo de lote: `Lote = (Saldo × Risco%) / (SL_Pontos × Tick_Value)`
- Circuit Breaker: Bloqueia trades em DD > 3%

### 7. Utils (`utils/`)
- **TelegramNotifier**: Alertas em tempo real
- Notificações de trades, erros e circuit breaker

## 🚀 Como Usar

### Instalação Rápida

```bash
# 1. Clonar/extrair o projeto
cd trading_bot

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Configurar settings.json
# Editar: login, password, server, símbolos

# 4. Verificar setup
python setup_check.py

# 5. Executar
python main.py
```

### Configuração Mínima

```json
{
  "mt5": {
    "login": 12345678,
    "password": "sua_senha",
    "server": "MetaQuotes-Demo"
  },
  "trading": {
    "symbols": ["EURUSD", "GBPUSD"],
    "timeframe": "M15"
  },
  "risk": {
    "risk_per_trade_percent": 1.0,
    "max_daily_drawdown_percent": 3.0
  }
}
```

## 📊 Fluxo de Execução

```
1. Inicialização
   ├── Conectar MT5
   ├── Carregar dados históricos
   ├── Calcular indicadores
   └── Iniciar risk manager

2. Loop Principal (a cada 5s)
   ├── Verificar conexão
   ├── Verificar circuit breaker
   ├── Atualizar dados de mercado
   │   └── Recalcular indicadores (incremental)
   ├── Para cada símbolo:
   │   ├── Verificar posição existente
   │   │   ├── Se existe: atualizar trailing stop
   │   │   └── Se não: gerar sinal
   │   ├── Validar sinal (RiskManager)
   │   ├── Calcular lote
   │   └── Executar ordem
   └── Log de status

3. Shutdown
   ├── Fechar posições (se configurado)
   ├── Desconectar MT5
   └── Enviar notificação
```

## 🎓 Padrões de Projeto Utilizados

1. **Singleton**
   - `MT5Client`: Uma única conexão
   - `Config`: Uma única instância de configuração

2. **Strategy Pattern**
   - `BaseStrategy`: Interface comum
   - Múltiplas implementações concretas

3. **Template Method**
   - `BaseStrategy.generate_signal()`: Template
   - Subclasses implementam lógica específica

4. **Decorator**
   - `@retry_on_connection_failure`: Retry automático

5. **Factory**
   - `TradeSignal`: Criação padronizada de sinais

## 🧪 Testes

### Executar Testes Unitários

```bash
python -m unittest discover tests/
```

### Teste em Ambiente Real

1. Configure conta **DEMO** no MT5
2. Ajuste `risk_per_trade_percent: 0.5` (conservador)
3. Execute por 1 semana
4. Analise logs em `logs/trading_bot.log`
5. Revise métricas de performance

## 📈 Métricas e Monitoramento

### Logs Gerados

```
2026-01-29 14:23:45 | INFO | Connected to MT5 | Balance: 10000.00
2026-01-29 14:25:12 | INFO | BUY EURUSD | Lot: 0.10 | Price: 1.08450
2026-01-29 14:30:45 | INFO | Position closed | Profit: $12.50
2026-01-29 15:01:03 | ERROR | CIRCUIT BREAKER | DD: 3.2%
```

### Notificações Telegram

- 🟢 Trade aberto (símbolo, lote, preço, SL, TP)
- ✅ Trade fechado (símbolo, lucro)
- 🚨 Circuit breaker ativado
- ⚠️ Erros críticos

## ⚙️ Personalização

### Criar Nova Estratégia

```python
from strategies.base import BaseStrategy, TradeSignal, SignalType

class MinhaEstrategia(BaseStrategy):
    def __init__(self):
        super().__init__("Nome da Estratégia")
    
    def generate_signal(self, symbol, dataframe):
        # Sua lógica aqui
        return TradeSignal(...)
    
    def on_tick(self, symbol, tick_data):
        # Processar ticks
        return None
```

### Modificar Parâmetros de Risco

```json
{
  "risk": {
    "risk_per_trade_percent": 0.5,     # Mais conservador
    "max_daily_drawdown_percent": 2.0, # Mais restritivo
    "max_positions": 2                  # Menos posições
  }
}
```

## 🛡️ Segurança

### ⚠️ Avisos Importantes

- **USE POR SUA CONTA E RISCO**
- Sempre teste em conta DEMO primeiro
- O desempenho passado não garante resultados futuros
- Nunca arrisque mais do que pode perder
- Monitore o bot regularmente
- Mantenha credenciais seguras (nunca commitar `settings.json`)

### Checklist de Segurança

- [ ] Testado em DEMO por 1+ semana
- [ ] Parâmetros de risco conservadores
- [ ] Circuit breaker funcionando
- [ ] Notificações ativas
- [ ] Logs sendo revisados diariamente
- [ ] Credenciais não versionadas

## 📚 Recursos Adicionais

### Documentação
- `README.md`: Guia de uso principal
- `CONTRIBUTING.md`: Guia de desenvolvimento
- Docstrings em cada módulo

### Exemplos
- `examples/multi_strategy_example.py`: Multi-estratégia
- `tests/test_risk_manager.py`: Testes unitários

### Scripts Auxiliares
- `setup_check.py`: Verificação de instalação
- `main.py`: Execução principal

## 🎯 Roadmap Futuro

Possíveis melhorias:

1. **Machine Learning**: Integração com modelos preditivos
2. **Backtesting**: Framework para testar estratégias em dados históricos
3. **Dashboard Web**: Interface gráfica para monitoramento
4. **Base de Dados**: Armazenamento de trades em SQLite/PostgreSQL
5. **Multi-Conta**: Suporte a múltiplas contas MT5
6. **Otimização de Parâmetros**: Grid search automático
7. **Análise de Sentimento**: Integração com news feeds

## 📞 Suporte

- **Logs**: `logs/trading_bot.log`
- **MT5 Docs**: https://www.mql5.com/en/docs
- **Issues**: Reporte bugs e sugestões

## 📄 Licença

Código fornecido "como está" para fins educacionais.

---

**Desenvolvido com:**
- ✅ Arquitetura limpa e modular
- ✅ Type hints e documentação completa
- ✅ Tratamento robusto de erros
- ✅ Logging profissional
- ✅ Gestão de risco avançada
- ✅ Extensibilidade via herança
- ✅ Testes unitários
- ✅ Production-ready