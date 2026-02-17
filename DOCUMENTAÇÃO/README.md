# 🤖 Sistema de Trading Institucional com IA

Sistema avançado de trading algorítmico com Machine Learning, integrado ao MetaTrader 5.

## 🎯 Características Principais

### Arquitetura Quantitativa
- **Filtro CUSUM**: Detecção de mudanças estruturais no mercado
- **Meta-Labeling**: RandomForest para auditoria de qualidade de sinais
- **Critério de Kelly Fracionário**: Dimensionamento científico de posição
- **Barreiras Triplas**: Gestão dinâmica de Stop Loss e Take Profit

### Infraestrutura Institucional
- **Arquitetura Assíncrona**: Zero bloqueios, máxima eficiência
- **Padrão Singleton**: Conexão única e gerenciada ao MT5
- **Retry com Backoff Exponencial**: Reconexão automática inteligente
- **Logging Rotativo**: Auditoria completa de operações
- **Tipagem Estática**: Código robusto e manutenível

### Execução ECN/STP
- **Mapeamento Automático de Filling Mode**: Resolve ERR_INVALID_REQUEST (10013)
- **Tratamento de Requotes**: Retry inteligente em ERR_REQUOTE (10004)
- **Validação Multi-Camada**: Risco, liquidez, exposição

## 📁 Estrutura do Projeto

```
trading_bot/
├── config/
│   └── settings.json           # Configurações centralizadas
├── core/
│   ├── decorators.py           # Singleton e Retry
│   ├── logger.py               # Sistema de logging
│   └── mt5_client.py           # Cliente MT5
├── data/
│   └── features.py             # Engenharia de features e CUSUM
├── strategies/
│   └── ai_logic.py             # Estratégia primária e meta-labeling
├── execution/
│   └── order_manager.py        # Gestor de ordens ECN
├── risk/
│   └── manager.py              # Gestão de risco Kelly
├── models/                     # Modelos ML treinados
├── logs/                       # Logs rotativos
├── main.py                     # Orquestrador principal
└── requirements.txt            # Dependências
```

## 🚀 Instalação

### Pré-requisitos
- Python 3.8+
- MetaTrader 5 instalado e configurado
- Conta de trading (demo ou real)

### Passos

1. **Clone ou copie o projeto**
```bash
cd trading_bot
```

2. **Crie ambiente virtual** (recomendado)
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows
```

3. **Instale dependências**
```bash
pip install -r requirements.txt
```

4. **Configure suas credenciais**

Edite `config/settings.json`:

```json
{
  "mt5": {
    "login": SEU_LOGIN,
    "password": "SUA_SENHA",
    "server": "SEU_SERVIDOR"
  }
}
```

## ⚙️ Configuração

### Arquivo `config/settings.json`

#### Credenciais MT5
```json
"mt5": {
  "login": 123456789,
  "password": "SuaSenha",
  "server": "MetaQuotes-Demo",
  "timeout": 60000
}
```

#### Parâmetros de Trading
```json
"trading": {
  "symbols": ["EURUSD", "GBPUSD", "USDJPY"],
  "timeframe": "H1",
  "max_positions": 3,
  "magic_number": 987654321
}
```

#### Gestão de Risco
```json
"risk": {
  "kelly_fraction": 0.25,          // 25% do Kelly completo
  "max_risk_per_trade": 0.02,      // 2% do capital por trade
  "estimated_win_rate": 0.55,      // 55% de acerto estimado
  "stop_loss_atr_multiplier": 2.0, // SL = 2 x ATR
  "take_profit_atr_multiplier": 3.0 // TP = 3 x ATR
}
```

#### Estratégia e IA
```json
"strategy": {
  "ema_period": 200,
  "rsi_period": 14,
  "cusum_threshold": 0.02,         // Sensibilidade do CUSUM
  "meta_model_threshold": 0.60,    // 60% de probabilidade mínima
  "lookback_bars": 1000
}
```

## 🎮 Uso

### Execução Básica
```bash
python main.py
```

### Treinamento Inicial do Meta-Modelo

O meta-modelo pode ser treinado antes da primeira execução:

```python
from data.features import FeatureEngine
from strategies.ai_logic import MetaLabeler
from core.mt5_client import MT5Client
import asyncio

async def train_model():
    # Conecta ao MT5
    client = MT5Client(login=..., password=..., server=...)
    await client.connect()
    
    # Obtém dados históricos
    df = await client.get_rates("EURUSD", "H1", 5000)
    
    # Cria features
    engine = FeatureEngine()
    df = engine.calculate_indicators(df)
    df = engine.create_ml_features(df)
    
    # Treina modelo
    labeler = MetaLabeler()
    metrics = labeler.train(df, side=1)  # 1 para compra, -1 para venda
    
    print(f"Acurácia: {metrics['test_accuracy']:.2%}")

asyncio.run(train_model())
```

### Monitoramento em Tempo Real

O sistema gera logs em:
- **Console**: Saída em tempo real
- **Arquivo**: `logs/trading_bot.log` (rotativo, 10MB x 5 arquivos)

## 🔬 Fluxo de Operação

### 1. Aquisição de Dados
```
MT5 → DataFrame OHLCV → Indicadores (EMA, RSI, ATR)
```

### 2. Filtro CUSUM
```
Retornos → CUSUM → Evento Detectado? → Prossegue
```

### 3. Análise Primária
```
Preço vs EMA + RSI → Sinal Direcional + Barreiras (SL/TP)
```

### 4. Meta-Labeling
```
Features → RandomForest → P(Sucesso) > 60%? → Aprovado
```

### 5. Gestão de Risco
```
Kelly Fracionário → Tamanho de Lote → Validação Multi-Camada
```

### 6. Execução
```
Ordem → Filling Mode → Retry em Requote → Confirmação
```

## 📊 Métricas e KPIs

### Logs de Trade
```
2025-02-17 14:30:15 | INFO | EURUSD: ⚡ EVENTO CUSUM DETECTADO - Direção: UP
2025-02-17 14:30:15 | INFO | EURUSD: ✓ SINAL APROVADO - Ação: BUY, Probabilidade: 67.3%
2025-02-17 14:30:16 | INFO | Position Sizing - Volume: 0.15 lots, Actual Risk: 150.00 (2.0%)
2025-02-17 14:30:17 | INFO | EURUSD: ✓✓✓ ORDEM EXECUTADA COM SUCESSO ✓✓✓
```

### Análise de Performance
- Taxa de acerto do meta-modelo
- Drawdown máximo
- Sharpe Ratio (calcular externamente)
- Profit Factor (calcular externamente)

## 🛡️ Gestão de Erros

### Tratamento Automático
- **ERR_REQUOTE (10004)**: Retry com preço atualizado
- **ERR_INVALID_REQUEST (10013)**: Tenta filling mode alternativo
- **Desconexão**: Reconexão com backoff exponencial
- **Dados insuficientes**: Skip do símbolo na iteração

### Validações Pré-Trade
- ✅ Número máximo de posições
- ✅ Drawdown máximo (20%)
- ✅ Risco por trade (2% máx)
- ✅ Equity positivo
- ✅ Probabilidade meta-modelo (60% mín)

## 🔧 Customização

### Adicionar Novo Indicador

Em `data/features.py`:
```python
def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
    # ... código existente ...
    
    # Novo indicador
    df['meu_indicador'] = ta.minha_funcao(df['close'])
    
    return df
```

### Modificar Lógica de Sinal

Em `strategies/ai_logic.py`:
```python
class PrimaryStrategy:
    def generate_signal(self, df: pd.DataFrame) -> Dict[str, Any]:
        # Adapte a lógica conforme sua estratégia
        pass
```

### Ajustar Parâmetros de Risco

Diretamente em `config/settings.json` - **sem necessidade de recompilar**.

## 🎓 Conceitos Teóricos

### Filtro CUSUM
Detecta mudanças persistentes no processo gerador de dados (regime shift).

**Referência**: López de Prado, M. (2018). *Advances in Financial Machine Learning*.

### Meta-Labeling
Ao invés de prever direção, prevê a **probabilidade de sucesso** de um sinal.

**Vantagem**: Reduz falsos positivos em 40-60%.

### Critério de Kelly
Determina fração ótima do capital a arriscar:

```
f* = (p × b - q) / b

Onde:
p = probabilidade de ganho
q = 1 - p
b = payoff ratio (ganho/perda)
```

**Implementação**: Kelly Fracionário (25%) para reduzir volatilidade.

## ⚠️ Avisos Importantes

### Backtesting
Este código é para **trading ao vivo**. Para backtesting, adapte:
- Use dados históricos completos
- Simule execução sem enviar ordens reais
- Calcule métricas de performance

### Disclaimers
- ⚠️ Trading envolve risco de perda de capital
- ⚠️ Teste sempre em **conta demo** antes de usar real
- ⚠️ Este código é para fins **educacionais**
- ⚠️ Não há garantia de lucro
- ⚠️ Use por sua conta e risco

### Configurações Recomendadas para Início
```json
{
  "risk": {
    "kelly_fraction": 0.1,      // Conservador (10% do Kelly)
    "max_risk_per_trade": 0.01  // 1% por trade
  },
  "trading": {
    "max_positions": 1          // Uma posição por vez
  }
}
```

## 📚 Dependências

- **MetaTrader5**: Integração com plataforma
- **pandas**: Manipulação de dados
- **numpy**: Computação numérica
- **pandas-ta**: Indicadores técnicos
- **scikit-learn**: Machine Learning
- **joblib**: Persistência de modelos

## 🤝 Contribuições

Para melhorias:
1. Adicione testes unitários
2. Implemente mais estratégias
3. Otimize hiperparâmetros do RandomForest
4. Adicione mais filtros (Kalman, Wavelets)

## 📞 Suporte

Para dúvidas técnicas:
- Revise os logs em `logs/trading_bot.log`
- Verifique conexão MT5
- Valide permissões de trading na conta
- Confirme que símbolos estão ativos no Market Watch

## 📄 Licença

Este código é fornecido "como está" para fins educacionais.

---

**Desenvolvido com rigor institucional para trading quantitativo profissional.**
