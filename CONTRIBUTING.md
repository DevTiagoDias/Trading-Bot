# Guia de Desenvolvimento e Boas Práticas

## 🏗️ Arquitetura

### Princípios SOLID

O projeto segue os princípios SOLID:

1. **Single Responsibility**: Cada classe tem uma única responsabilidade
2. **Open/Closed**: Extensível sem modificar código existente (via herança)
3. **Liskov Substitution**: Estratégias podem ser substituídas sem quebrar o código
4. **Interface Segregation**: Interfaces mínimas e específicas
5. **Dependency Inversion**: Dependências via abstrações (BaseStrategy)

### Padrões de Projeto Utilizados

- **Singleton**: `MT5Client`, `Config` (única instância)
- **Strategy Pattern**: Sistema de estratégias plugáveis
- **Template Method**: `BaseStrategy` define o template
- **Factory**: Criação de sinais através de `TradeSignal`

## 📝 Convenções de Código

### Estilo

- Seguir **PEP 8**
- Type hints em todas as funções públicas
- Docstrings em formato Google Style

### Exemplo de Docstring

```python
def calculate_lot_size(self, signal: TradeSignal) -> float:
    """
    Calculate position size based on risk parameters.
    
    Args:
        signal: Trade signal with entry and stop loss
        
    Returns:
        Calculated lot size in standard lots
        
    Raises:
        ValueError: If signal parameters are invalid
    """
    pass
```

### Nomenclatura

- Classes: `PascalCase` (ex: `RiskManager`)
- Funções/métodos: `snake_case` (ex: `calculate_lot_size`)
- Constantes: `UPPER_CASE` (ex: `MAX_POSITIONS`)
- Privadas: `_prefixo` (ex: `_validate_config`)

## 🧪 Testes

### Estrutura de Testes

```python
import unittest
from unittest.mock import Mock, patch

class TestRiskManager(unittest.TestCase):
    
    def setUp(self):
        """Setup test fixtures."""
        self.risk_manager = RiskManager()
    
    def tearDown(self):
        """Cleanup after tests."""
        pass
    
    def test_validate_signal_success(self):
        """Test successful validation."""
        # Arrange
        signal = create_test_signal()
        
        # Act
        is_valid, reason = self.risk_manager.validate_signal(signal)
        
        # Assert
        self.assertTrue(is_valid)
```

### Executar Testes

```bash
python -m unittest discover tests/
```

## 🔍 Logging

### Níveis de Log

- **DEBUG**: Informações detalhadas de debug
- **INFO**: Eventos normais (trades, conexões)
- **WARNING**: Situações não críticas (requotes, spreads altos)
- **ERROR**: Erros recuperáveis
- **CRITICAL**: Erros fatais

### Exemplo de Uso

```python
from core.logger import get_logger

logger = get_logger(__name__)

# Log de trade
TradingLogger.log_trade(
    action="BUY",
    symbol="EURUSD",
    lot=0.10,
    price=1.08450,
    sl=1.08350,
    tp=1.08650,
    reason="ATR Trend",
    order_id=12345
)

# Log de erro
logger.error(f"Failed to execute order: {error_msg}", exc_info=True)
```

## 🎯 Adicionando Nova Estratégia

### Passo 1: Criar Classe

```python
# strategies/my_strategy.py

from strategies.base import BaseStrategy, TradeSignal, SignalType
import pandas as pd

class MyStrategy(BaseStrategy):
    
    def __init__(self):
        super().__init__("My Strategy Name")
        # Seus parâmetros aqui
        self.parameter1 = 10
        self.parameter2 = 20
    
    def generate_signal(self, symbol: str, dataframe: pd.DataFrame) -> Optional[TradeSignal]:
        """
        Implementar lógica de geração de sinal.
        """
        # Validar dados suficientes
        if len(dataframe) < self.parameter2:
            return None
        
        # Sua lógica aqui
        latest = dataframe.iloc[-1]
        
        # Exemplo: Retornar sinal de compra
        return TradeSignal(
            symbol=symbol,
            signal_type=SignalType.BUY,
            price=latest['close'],
            stop_loss=latest['close'] - 0.001,
            take_profit=latest['close'] + 0.002,
            reason="Sua lógica"
        )
    
    def on_tick(self, symbol: str, tick_data: Dict) -> Optional[TradeSignal]:
        """
        Processar tick (opcional).
        """
        return None
```

### Passo 2: Registrar no main.py

```python
from strategies.my_strategy import MyStrategy

# No __init__ do TradingBot
self.strategy = MyStrategy()
```

## 🛡️ Tratamento de Erros

### Hierarquia de Exceções

```python
try:
    result = mt5.order_send(request)
except MT5ConnectionError:
    # Erro de conexão - tentar reconectar
    self.mt5_client.reconnect()
except ValueError as e:
    # Parâmetros inválidos
    logger.error(f"Invalid parameters: {e}")
except Exception as e:
    # Erro genérico
    logger.error(f"Unexpected error: {e}", exc_info=True)
finally:
    # Limpeza sempre executada
    cleanup_resources()
```

## 📊 Performance

### Otimizações Implementadas

1. **Buffer Circular**: Limita memória a últimos 1000 candles
2. **Cálculo Incremental**: Indicadores só recalculados para dados novos
3. **Caching**: Informações de símbolos cacheadas
4. **Batch Processing**: Múltiplos símbolos processados em lote

### Profiling

```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# Código a ser medido
bot.start()

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)  # Top 20 funções
```

## 🔐 Segurança

### Credenciais

- **NUNCA** commitar `settings.json` com credenciais reais
- Use variáveis de ambiente para produção
- Mantenha arquivos sensíveis no `.gitignore`

### Exemplo com Environment Variables

```python
import os
from dotenv import load_dotenv

load_dotenv()

config = {
    "mt5": {
        "login": int(os.getenv("MT5_LOGIN")),
        "password": os.getenv("MT5_PASSWORD"),
        "server": os.getenv("MT5_SERVER")
    }
}
```

## 📦 Deploy

### Checklist de Deploy

- [ ] Testado em conta DEMO por 1+ semana
- [ ] Logs revisados para erros
- [ ] Notificações Telegram funcionando
- [ ] Parâmetros de risco conservadores
- [ ] Backup da configuração
- [ ] Monitoramento ativo configurado

### Ambiente de Produção

```bash
# 1. Clonar repositório
git clone <repo>

# 2. Criar ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 3. Instalar dependências
pip install -r requirements.txt

# 4. Configurar settings.json

# 5. Testar conexão
python setup_check.py

# 6. Executar
python main.py
```

## 📈 Monitoramento

### Métricas Importantes

- Drawdown diário
- Taxa de acerto (win rate)
- Profit factor
- Sharpe ratio
- Número de requotes
- Tempo de execução médio

### Dashboard Recomendado

Integre com ferramentas como:
- Grafana + InfluxDB
- Custom dashboard web
- Planilha Google Sheets via API

## 🐛 Debug

### Aumentar Verbosidade

```python
# config/settings.json
{
  "logging": {
    "level": "DEBUG"  # Mude de INFO para DEBUG
  }
}
```

### Modo Dry Run

Implemente um modo de teste sem executar trades reais:

```python
class OrderManager:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
    
    def execute_order(self, signal, lot_size):
        if self.dry_run:
            logger.info(f"[DRY RUN] Would execute: {signal}")
            return OrderResult.SUCCESS, None, "Dry run"
        
        # Execução real
        return self._real_execute(signal, lot_size)
```

## 📞 Suporte

- Issues no GitHub
- Documentação MT5: https://www.mql5.com/en/docs
- Comunidade: https://www.mql5.com/en/forum