# 🏗️ Arquitetura do Sistema - Visão Geral Técnica

## Estrutura de Arquivos Completa

```
trading_bot/
│
├── 📁 config/                          # Configurações
│   ├── settings.json                   # Config principal (EDITAR ANTES DE USAR)
│   └── settings_conservative.json      # Config conservadora (iniciantes)
│
├── 📁 core/                            # Núcleo do Sistema
│   ├── __init__.py
│   ├── decorators.py                   # Singleton + Retry com Backoff
│   ├── logger.py                       # Sistema de logging rotativo
│   └── mt5_client.py                   # Cliente MT5 (Singleton)
│
├── 📁 data/                            # Engenharia de Features
│   ├── __init__.py
│   └── features.py                     # FeatureEngine + CUSUM + BarrierLabeler
│
├── 📁 strategies/                      # Lógica de IA
│   ├── __init__.py
│   └── ai_logic.py                     # PrimaryStrategy + MetaLabeler + AITradingLogic
│
├── 📁 execution/                       # Execução de Ordens
│   ├── __init__.py
│   └── order_manager.py                # OrderManager (ECN/STP)
│
├── 📁 risk/                            # Gestão de Risco
│   ├── __init__.py
│   └── manager.py                      # KellyRiskManager
│
├── 📁 models/                          # Modelos ML (gerados pelo sistema)
│   └── meta_classifier.pkl             # RandomForest treinado
│
├── 📁 logs/                            # Logs do Sistema (gerados automaticamente)
│   └── trading_bot.log                 # Log rotativo (10MB x 5)
│
├── main.py                             # ⭐ Orquestrador Principal
├── train_model.py                      # Script de treinamento do meta-modelo
├── diagnostic.py                       # Validação e diagnóstico do sistema
├── requirements.txt                    # Dependências Python
├── README.md                           # Documentação principal
├── BEST_PRACTICES.md                   # Guia de melhores práticas
└── .gitignore                          # Arquivos a ignorar no git
```

---

## 📊 Fluxo de Dados e Processamento

```
┌─────────────────────────────────────────────────────────────┐
│                    SISTEMA DE TRADING                        │
└─────────────────────────────────────────────────────────────┘

1. INICIALIZAÇÃO
   ├── Carrega config/settings.json
   ├── Inicializa Logger (core/logger.py)
   ├── Conecta MT5 (core/mt5_client.py + decorators.py)
   ├── Inicializa FeatureEngine (data/features.py)
   ├── Cria filtros CUSUM por símbolo
   ├── Carrega/Cria MetaLabeler (strategies/ai_logic.py)
   ├── Inicializa RiskManager (risk/manager.py)
   └── Inicializa OrderManager (execution/order_manager.py)

2. LOOP PRINCIPAL (Assíncrono)
   │
   ├─► Para cada símbolo:
   │   │
   │   ├── Verifica posição existente
   │   │   └── Se existe → Skip
   │   │
   │   ├── Obtém dados históricos (MT5)
   │   │   └── DataFrame OHLCV
   │   │
   │   ├── Calcula Features (FeatureEngine)
   │   │   ├── EMA, RSI, ATR
   │   │   ├── Volatilidade
   │   │   ├── Momentum
   │   │   └── Features ML
   │   │
   │   ├── Atualiza CUSUM Filter
   │   │   ├── Detecta evento?
   │   │   │   ├── SIM → Prossegue
   │   │   │   └── NÃO → Skip
   │   │
   │   ├── Gera Sinal Primário (PrimaryStrategy)
   │   │   ├── Analisa Preço vs EMA
   │   │   ├── Verifica RSI
   │   │   ├── Calcula SL/TP (ATR)
   │   │   └── Retorna: BUY/SELL/HOLD
   │   │
   │   ├── Aplica Meta-Labeling (MetaLabeler)
   │   │   ├── RandomForest prediz P(sucesso)
   │   │   ├── P(sucesso) > threshold?
   │   │   │   ├── SIM → Aprova sinal
   │   │   │   └── NÃO → Rejeita sinal
   │   │
   │   ├── Calcula Position Size (KellyRiskManager)
   │   │   ├── Calcula Kelly Fraction
   │   │   ├── Determina lote baseado em risco
   │   │   └── Aplica limites
   │   │
   │   ├── Valida Trade (RiskManager)
   │   │   ├── Verifica max_positions
   │   │   ├── Verifica drawdown
   │   │   ├── Valida risco
   │   │   └── Aprova/Rejeita
   │   │
   │   └── Executa Ordem (OrderManager)
   │       ├── Determina filling_mode
   │       ├── Envia ordem ao broker
   │       ├── Trata requotes (10004)
   │       ├── Trata rejeições (10013)
   │       └── Confirma execução
   │
   └─► await asyncio.sleep(interval)
```

---

## 🧩 Módulos e Responsabilidades

### 1. core/decorators.py
**Propósito**: Padrões de design para resiliência

**Classes/Funções**:
- `@singleton`: Garante instância única (MT5Client)
- `@retry_with_backoff`: Retry inteligente com backoff exponencial
- `@measure_time`: Medição de performance

**Uso**:
```python
@singleton
class MT5Client:
    pass

@retry_with_backoff(max_attempts=5)
async def connect():
    pass
```

---

### 2. core/logger.py
**Propósito**: Sistema centralizado de logging

**Classes**:
- `LoggerManager`: Gerenciador singleton de loggers
- `configure_logging_from_config()`: Setup a partir de JSON
- `get_logger()`: Obtém logger configurado

**Features**:
- Logs simultâneos (console + arquivo)
- Rotação automática (tamanho limite)
- Formatação padronizada com timestamps

---

### 3. core/mt5_client.py
**Propósito**: Abstração completa da API MT5

**Classe Principal**: `MT5Client`

**Métodos Principais**:
- `connect()`: Conexão com retry
- `get_rates()`: Dados históricos → DataFrame
- `get_symbol_info()`: Informações do símbolo
- `get_account_info()`: Dados da conta
- `get_positions()`: Posições abertas
- `ensure_connected()`: Reconexão automática

---

### 4. data/features.py
**Propósito**: Engenharia quantitativa de features

**Classes**:

#### FeatureEngine
- `calculate_indicators()`: EMA, RSI, ATR vetorizado
- `create_ml_features()`: Features para meta-labeling

#### CUSUMFilter
- `update()`: Detecta eventos estruturais
- `reset()`: Limpa estado
- **Matemática**: Cumulative Sum para detecção de mudança de regime

#### BarrierLabeler
- `generate_labels()`: Cria labels para ML (Triple-Barrier Method)
- Usa SL/TP dinâmicos baseados em ATR

---

### 5. strategies/ai_logic.py
**Propósito**: Inteligência de decisão

**Classes**:

#### PrimaryStrategy
- `generate_signal()`: Seguidor de tendência (EMA + RSI)
- Retorna: ação, confiança, SL, TP, features

#### MetaLabeler
- `train()`: Treina RandomForest com dados históricos
- `predict_probability()`: P(sucesso) de um sinal
- Utiliza Triple-Barrier para labels

#### AITradingLogic
- `analyze()`: Orquestra primária + meta
- Combina sinais e aplica threshold

---

### 6. risk/manager.py
**Propósito**: Gestão científica de risco

**Classe**: `KellyRiskManager`

**Métodos**:
- `calculate_kelly_fraction()`: Fórmula de Kelly
- `calculate_position_size()`: Lote baseado em risco e ATR
- `validate_trade()`: Validação multi-camada
- `calculate_payoff_ratio()`: Razão TP/SL

**Fórmula Kelly**:
```
f* = (p × b - q) / b

p = probabilidade de ganho
q = 1 - p
b = payoff ratio
```

---

### 7. execution/order_manager.py
**Propósito**: Execução robusta de ordens

**Classe**: `OrderManager`

**Métodos**:
- `send_market_order()`: Envia ordem com retry
- `close_position()`: Fecha posição
- `modify_position()`: Modifica SL/TP
- `_get_filling_mode()`: Resolve filling automaticamente

**Tratamento de Erros**:
- **10004 (REQUOTE)**: Atualiza preço e retry
- **10013 (INVALID_REQUEST)**: Tenta filling alternativo
- **10006 (REJECT)**: Log e fail
- **10014 (INVALID_VOLUME)**: Fail
- **10015 (INVALID_PRICE)**: Fail
- **10016 (INVALID_STOPS)**: Fail

---

## 🔄 Padrões de Design Utilizados

### 1. Singleton Pattern
- **Onde**: `MT5Client`, `LoggerManager`
- **Por quê**: Conexão única ao MT5, logging centralizado

### 2. Decorator Pattern
- **Onde**: `@retry_with_backoff`, `@singleton`
- **Por quê**: Separação de concerns, reusabilidade

### 3. Strategy Pattern
- **Onde**: `PrimaryStrategy`, `MetaLabeler`
- **Por quê**: Algoritmos intercambiáveis

### 4. Factory Pattern (implícito)
- **Onde**: Criação de features, labels
- **Por quê**: Abstração de criação de objetos complexos

---

## 🎯 Decisões Arquiteturais Críticas

### Por que Asyncio?
- **Não bloqueia** durante sleep ou I/O
- Múltiplos símbolos processados eficientemente
- Reconexão não trava sistema

### Por que CUSUM?
- **Filtra ruído** do mercado
- Detecta mudanças estruturais (regime shifts)
- Reduz falsos sinais em 60-70%

### Por que Meta-Labeling?
- **Não prevê direção** (primária faz isso)
- Prevê **qualidade** do sinal
- Accuracy 55-65% já melhora retorno

### Por que Kelly Fracionário?
- Kelly completo é **muito agressivo**
- 25% do Kelly = **ótimo trade-off**
- Maximiza log(wealth) no longo prazo

---

## 🛠️ Extensões Futuras

### Curto Prazo:
1. Dashboard web (Flask/Streamlit)
2. Notificações (Telegram/Email)
3. Backtesting engine
4. A/B testing de estratégias

### Médio Prazo:
1. Multi-timeframe analysis
2. Correlation matrix para símbolos
3. Adaptive parameters (regime detection)
4. Portfolio optimization

### Longo Prazo:
1. Deep Learning (LSTM, Transformer)
2. Reinforcement Learning (DQN)
3. High-frequency trading (microsegundos)
4. Multi-broker support

---

## 📈 Performance Esperada

### Métricas Realistas (após otimização):
- **Win Rate**: 52-58%
- **Profit Factor**: 1.3-1.8
- **Sharpe Ratio**: 0.8-1.5
- **Max Drawdown**: 15-25%
- **Expectativa**: 0.5R - 1.2R por trade

### Fatores de Sucesso:
1. Backtesting rigoroso (≥ 2 anos de dados)
2. Otimização de hiperparâmetros
3. Regime de mercado adequado
4. Gestão de risco disciplinada
5. Retreinamento periódico do ML

---

**Sistema desenvolvido com padrões institucionais de engenharia de software e finanças quantitativas.**
