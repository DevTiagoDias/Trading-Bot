# 📂 Arquitetura Completa de Pastas - Trading Bot

## 🌳 Estrutura em Árvore

```
trading_bot/                                    # Raiz do projeto
│
├── 📁 config/                                  # ⚙️ Configurações
│   ├── settings.json                           # Config PRINCIPAL (edite suas credenciais aqui)
│   └── settings_conservative.json              # Config conservadora para iniciantes
│
├── 📁 core/                                    # 🔧 Núcleo do Sistema
│   ├── __init__.py                             # ✨ API pública: MT5Client, get_logger, decorators
│   ├── decorators.py                           # Singleton + Retry + Backoff Exponencial
│   ├── logger.py                               # Sistema de logging rotativo
│   └── mt5_client.py                           # Cliente MT5 com reconexão automática
│
├── 📁 data/                                    # 📊 Engenharia de Features
│   ├── __init__.py                             # ✨ API pública: FeatureEngine, CUSUMFilter, BarrierLabeler
│   └── features.py                             # Features + Filtro CUSUM + Triple-Barrier Labeling
│
├── 📁 strategies/                              # 🤖 Inteligência Artificial
│   ├── __init__.py                             # ✨ API pública: PrimaryStrategy, MetaLabeler, AITradingLogic
│   └── ai_logic.py                             # Estratégia Primária + Meta-Labeling (RandomForest)
│
├── 📁 execution/                               # 💼 Execução de Ordens
│   ├── __init__.py                             # ✨ API pública: OrderManager
│   └── order_manager.py                        # Gestor ECN/STP (trata erros 10004, 10013, etc.)
│
├── 📁 risk/                                    # 🛡️ Gestão de Risco
│   ├── __init__.py                             # ✨ API pública: KellyRiskManager
│   └── manager.py                              # Critério de Kelly + Dimensionamento de Posição
│
├── 📁 models/                                  # 🧠 Modelos de Machine Learning
│   └── meta_classifier.pkl                     # RandomForest treinado (gerado por train_model.py)
│
├── 📁 logs/                                    # 📝 Logs do Sistema
│   └── trading_bot.log                         # Log rotativo principal (10MB x 5 backups)
│
├── 📄 main.py                                  # ⭐ ORQUESTRADOR PRINCIPAL - Execute este!
├── 📄 train_model.py                           # 🎓 Script de treinamento do meta-modelo
├── 📄 diagnostic.py                            # 🔍 Validação e diagnóstico do sistema
│
├── 📄 requirements.txt                         # 📦 Dependências Python
├── 📄 .gitignore                               # 🚫 Arquivos ignorados pelo Git
│
└── 📚 Documentação/
    ├── README.md                               # 📖 Manual completo do sistema
    ├── QUICKSTART.md                           # ⚡ Guia de início rápido (5 minutos)
    ├── ARCHITECTURE.md                         # 🏗️ Visão técnica da arquitetura
    └── BEST_PRACTICES.md                       # ✅ Melhores práticas de produção
```

---

## 📊 Estatísticas do Projeto

```
Total de Módulos Python:      13 arquivos
Total de Linhas de Código:    ~3.500 linhas
Documentação:                 4 arquivos .md
Arquivos de Config:           2 arquivos JSON
```

---

## 🗂️ Detalhamento por Pasta

### 📁 `config/` - Configurações
```
config/
├── settings.json                    # 🔴 EDITAR: Login, senha, servidor MT5
└── settings_conservative.json       # 🟢 USAR: Para iniciantes (risco baixo)
```

**O que configurar:**
- Credenciais MT5 (`login`, `password`, `server`)
- Símbolos para operar (`symbols`)
- Parâmetros de risco (`kelly_fraction`, `max_risk_per_trade`)
- Threshold do meta-modelo (`meta_model_threshold`)

---

### 📁 `core/` - Infraestrutura Fundamental
```
core/
├── __init__.py                      # Exporta: MT5Client, get_logger, singleton, retry_with_backoff
├── decorators.py                    # Padrões: @singleton, @retry_with_backoff
├── logger.py                        # Logging: Console + Arquivo rotativo
└── mt5_client.py                    # MT5: Conexão, dados, posições
```

**Responsabilidades:**
- Conexão única ao MT5 (Singleton)
- Reconexão automática em falhas (Retry + Backoff)
- Sistema de logging unificado
- Abstração completa da API MetaTrader5

---

### 📁 `data/` - Engenharia Quantitativa
```
data/
├── __init__.py                      # Exporta: FeatureEngine, CUSUMFilter, BarrierLabeler
└── features.py                      # Features, CUSUM, Triple-Barrier
```

**Responsabilidades:**
- Calcular indicadores técnicos (EMA, RSI, ATR)
- Filtro CUSUM para detecção de regime shifts
- Criar features para Machine Learning
- Gerar labels baseados em barreiras triplas

---

### 📁 `strategies/` - Inteligência Artificial
```
strategies/
├── __init__.py                      # Exporta: PrimaryStrategy, MetaLabeler, AITradingLogic
└── ai_logic.py                      # Estratégia + Meta-Labeling
```

**Responsabilidades:**
- **PrimaryStrategy**: Gerar sinais direcionais (BUY/SELL)
- **MetaLabeler**: RandomForest para prever P(sucesso)
- **AITradingLogic**: Orquestrar primária + meta
- Treinamento e predição do modelo ML

---

### 📁 `execution/` - Execução de Ordens
```
execution/
├── __init__.py                      # Exporta: OrderManager
└── order_manager.py                 # Envio e gestão de ordens ECN
```

**Responsabilidades:**
- Enviar ordens de mercado ao broker
- Mapeamento automático de `filling_mode` (FOK/IOC/RETURN)
- Tratamento de requotes (Erro 10004)
- Tratamento de rejeições (Erro 10013, 10006, etc.)
- Fechar e modificar posições

---

### 📁 `risk/` - Gestão de Risco
```
risk/
├── __init__.py                      # Exporta: KellyRiskManager
└── manager.py                       # Kelly + Dimensionamento de Posição
```

**Responsabilidades:**
- Calcular fração de Kelly baseado em win rate
- Determinar tamanho de lote científico
- Validar trades (max positions, drawdown, etc.)
- Calcular payoff ratio (TP/SL)

---

### 📁 `models/` - Machine Learning
```
models/
└── meta_classifier.pkl              # RandomForest treinado (gerado automaticamente)
```

**Gerado por:** `train_model.py`

**Conteúdo:**
- Modelo RandomForest serializado
- Features utilizadas no treinamento
- Timestamp do treinamento

---

### 📁 `logs/` - Auditoria
```
logs/
└── trading_bot.log                  # Log rotativo (10MB por arquivo, 5 backups)
```

**Gerado por:** Sistema de logging do robô

**Conteúdo:**
- Todas as operações do sistema
- Sinais gerados e executados
- Erros e avisos
- Métricas de performance

---

## 📝 Scripts Principais

### ⭐ `main.py` - ORQUESTRADOR
```python
# Execute este para iniciar o robô
python main.py
```

**Fluxo:**
1. Carrega configurações
2. Conecta ao MT5
3. Inicializa todos os componentes
4. Loop assíncrono de trading
5. Processa símbolos → Detecta eventos → Executa ordens

---

### 🎓 `train_model.py` - Treinamento ML
```python
# Execute antes da primeira vez
python train_model.py
```

**Fluxo:**
1. Conecta ao MT5
2. Baixa dados históricos
3. Calcula features
4. Treina RandomForest
5. Salva modelo em `models/meta_classifier.pkl`

---

### 🔍 `diagnostic.py` - Validação
```python
# Execute para validar instalação
python diagnostic.py
```

**Verifica:**
- ✅ Dependências instaladas
- ✅ Configuração válida
- ✅ Conexão MT5 funcionando
- ✅ Símbolos disponíveis
- ✅ Estrutura de pastas correta

---

## 📚 Documentação

### `README.md`
- Manual completo do sistema
- Instalação, configuração, uso
- Explicações de cada módulo
- Métricas e KPIs

### `QUICKSTART.md`
- Início rápido em 5 minutos
- Checklist de segurança
- Troubleshooting comum

### `ARCHITECTURE.md`
- Visão técnica detalhada
- Fluxo de dados
- Decisões arquiteturais
- Padrões de design

### `BEST_PRACTICES.md`
- Checklist pré-produção
- Melhores práticas operacionais
- Sinais de alerta
- Otimizações avançadas

---

## 🎯 Imports Atualizados (Graças aos __init__.py!)

### ✅ NOVA FORMA (Limpa e Profissional):

```python
# main.py
from core import MT5Client, get_logger, configure_logging_from_config
from data import FeatureEngine, CUSUMFilter
from strategies import PrimaryStrategy, MetaLabeler, AITradingLogic
from risk import KellyRiskManager
from execution import OrderManager
```

### ❌ FORMA ANTIGA (Verbosa):

```python
# main.py
from core.mt5_client import MT5Client
from core.logger import get_logger, configure_logging_from_config
from data.features import FeatureEngine, CUSUMFilter
from strategies.ai_logic import PrimaryStrategy, MetaLabeler, AITradingLogic
from risk.manager import KellyRiskManager
from execution.order_manager import OrderManager
```

---

## 🚀 Fluxo de Uso Recomendado

```bash
# 1. Setup inicial
cd trading_bot
python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt

# 2. Configurar credenciais
nano config/settings.json  # Edite login, password, server

# 3. Validar sistema
python diagnostic.py

# 4. Treinar meta-modelo
python train_model.py

# 5. Executar robô
python main.py
```

---

## 📦 Arquivos Gerados em Runtime

Durante a execução, o sistema cria automaticamente:

```
trading_bot/
├── models/
│   └── meta_classifier.pkl          # ← Gerado após train_model.py
│
└── logs/
    ├── trading_bot.log               # ← Log atual
    ├── trading_bot.log.1             # ← Backup 1
    ├── trading_bot.log.2             # ← Backup 2
    ├── trading_bot.log.3             # ← Backup 3
    ├── trading_bot.log.4             # ← Backup 4
    └── trading_bot.log.5             # ← Backup 5 (mais antigo)
```

---

## 🔒 .gitignore (Não Versionar)

```gitignore
# Logs
logs/

# Modelos treinados
models/*.pkl

# Configurações sensíveis
config/settings.json

# Python cache
__pycache__/
*.pyc
```

**Mantenha no Git:**
- `config/settings_conservative.json` (template)
- Todo código-fonte
- Documentação
- `requirements.txt`

---

## 📈 Tamanho Aproximado por Componente

```
core/          → ~800 linhas   (Infraestrutura)
data/          → ~600 linhas   (Features + CUSUM)
strategies/    → ~700 linhas   (IA + Meta-Labeling)
execution/     → ~500 linhas   (Ordens ECN)
risk/          → ~400 linhas   (Kelly + Validação)
main.py        → ~400 linhas   (Orquestrador)
Scripts        → ~500 linhas   (train + diagnostic)
───────────────────────────────
TOTAL          → ~3.900 linhas
```

---

## ✨ Resumo Visual

```
🌳 trading_bot/
   ├── 📁 Core        (Infraestrutura base)
   ├── 📁 Data        (Features quantitativas)
   ├── 📁 Strategies  (Inteligência artificial)
   ├── 📁 Execution   (Ordens ao broker)
   ├── 📁 Risk        (Gestão científica de risco)
   ├── 📁 Models      (ML treinados)
   ├── 📁 Logs        (Auditoria)
   └── 📁 Config      (Parâmetros)
```

---

**Sistema completo, modular, profissional e pronto para produção!** 🚀
