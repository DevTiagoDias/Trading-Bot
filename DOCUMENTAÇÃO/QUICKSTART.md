# ⚡ Guia de Início Rápido (5 minutos)

## 🎯 Objetivo
Colocar o robô em funcionamento em conta DEMO o mais rápido possível.

---

## Passo 1: Pré-requisitos (2 min)

### Instale o Python 3.8+
```bash
python --version  # Deve mostrar 3.8 ou superior
```

### Instale o MetaTrader 5
- Download: https://www.metatrader5.com/
- Configure uma conta DEMO
- Anote: Login, Senha, Servidor

---

## Passo 2: Instalação (1 min)

### Clone/Extraia o projeto
```bash
cd trading_bot
```

### Crie ambiente virtual (recomendado)
```bash
# Linux/Mac
python -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

### Instale dependências
```bash
pip install -r requirements.txt
```

---

## Passo 3: Configuração (1 min)

### Edite `config/settings.json`

**MÍNIMO OBRIGATÓRIO**:
```json
{
  "mt5": {
    "login": SEU_LOGIN_AQUI,           // ← Altere
    "password": "SUA_SENHA_AQUI",       // ← Altere
    "server": "SEU_SERVIDOR_AQUI"       // ← Altere (ex: "MetaQuotes-Demo")
  }
}
```

**Para iniciantes**, use a configuração conservadora:
```bash
# Linux/Mac
cp config/settings_conservative.json config/settings.json

# Windows
copy config\settings_conservative.json config\settings.json
```
Depois edite apenas as credenciais MT5.

---

## Passo 4: Validação (30 seg)

Execute o diagnóstico:
```bash
python diagnostic.py
```

**Deve mostrar**:
```
✓ MetaTrader5
✓ pandas
✓ Conexão estabelecida com sucesso
✓ EURUSD
...
✓✓✓ SISTEMA PRONTO PARA OPERAR ✓✓✓
```

Se houver erros, resolva-os antes de prosseguir.

---

## Passo 5: Primeiro Treino do Meta-Modelo (30 seg)

```bash
python train_model.py
```

Escolha:
- Opção: **3** (treinar ambos)
- Símbolo: **EURUSD** (ou deixe em branco)
- Timeframe: **H1** (ou deixe em branco)
- Barras: **5000** (ou deixe em branco)

Aguarde o treinamento (1-2 minutos).

**Output esperado**:
```
✓✓✓ TREINAMENTO CONCLUÍDO COM SUCESSO ✓✓✓
Acurácia Teste: 54.23%
```

---

## Passo 6: Executar o Robô (10 seg)

```bash
python main.py
```

**Logs esperados**:
```
2025-02-17 14:30:00 | INFO | Sistema de Logging Inicializado
2025-02-17 14:30:01 | INFO | ✓ Conexão MT5 Estabelecida com Sucesso
2025-02-17 14:30:02 | INFO | Iniciando Loop de Trading
2025-02-17 14:30:02 | INFO | --- Iteração 1 ---
```

---

## 🎮 Controle do Robô

### Parar o robô
```
Ctrl + C
```

### Ver logs em tempo real (outro terminal)
```bash
# Linux/Mac
tail -f logs/trading_bot.log

# Windows
Get-Content logs\trading_bot.log -Wait
```

### Reiniciar após mudanças
1. Pare (Ctrl+C)
2. Edite configuração
3. Execute novamente

---

## 📊 Primeiras Operações

### O que esperar:
1. **Iterações constantes** a cada 0.5-1s
2. **"Nenhum evento CUSUM detectado"** na maioria das vezes (normal!)
3. Quando CUSUM detecta evento:
   - Gera sinal primário
   - Meta-modelo analisa
   - Se aprovado → Executa ordem

### Primeira ordem executada:
```
EURUSD: ⚡ EVENTO CUSUM DETECTADO - Direção: UP
EURUSD: ✓ SINAL APROVADO - Ação: BUY, Probabilidade: 67.3%
Position Sizing - Volume: 0.15 lots, Risk: 150.00 (2.0%)
EURUSD: ✓✓✓ ORDEM EXECUTADA COM SUCESSO ✓✓✓
```

Verifique no MetaTrader 5 → Guia "Trade" → Posições

---

## ⚠️ Checklist de Segurança

Antes de executar:

- [ ] ✅ Está usando conta **DEMO**
- [ ] ✅ `max_risk_per_trade` ≤ 0.02 (2%)
- [ ] ✅ `max_positions` = 1 ou 2 (começar pequeno)
- [ ] ✅ Diagnostic passou todos os testes
- [ ] ✅ Meta-modelo treinado (accuracy > 50%)
- [ ] ⚠️ **NÃO use em conta REAL sem 1 semana de testes em DEMO**

---

## 🐛 Troubleshooting Rápido

### Erro: "Falha ao inicializar MT5"
- ✅ MetaTrader 5 está instalado?
- ✅ Terminal MT5 está aberto?
- ✅ Credenciais corretas em `config/settings.json`?

### Erro: "Símbolo não disponível"
- ✅ Símbolo está no Market Watch do MT5?
- ✅ Nome do símbolo está correto? (EURUSD, não EUR/USD)

### Erro: "Ordem rejeitada (10013)"
- ✅ Conta tem permissão para trading automatizado?
- ✅ Opções → Expert Advisors → "Allow automated trading" marcado?

### Nenhum sinal gerado
- ✅ **Normal!** CUSUM filtra muito. Aguarde eventos.
- ✅ Diminua `cusum_threshold` para mais sinais (ex: 0.015)
- ✅ Aumente número de símbolos em `config/settings.json`

---

## 📚 Próximos Passos

Após primeira execução bem-sucedida:

1. **Monitore 24h** em conta demo
2. **Ajuste parâmetros** se necessário
3. **Leia README.md** completo
4. **Leia BEST_PRACTICES.md** antes de real
5. **Retreine modelo** semanalmente

---

## 💬 Suporte

**Logs não fazem sentido?**
→ Leia ARCHITECTURE.md para entender o fluxo

**Quer customizar?**
→ Leia código-fonte (bem documentado!)

**Dúvidas de configuração?**
→ README.md tem explicações detalhadas

---

## 🎉 Parabéns!

Se chegou até aqui, você tem um robô de trading institucional funcionando!

**Lembre-se**:
- 🎯 Teste SEMPRE em demo primeiro
- 📊 Monitore performance
- 🔧 Ajuste parâmetros baseado em dados
- 📚 Continue aprendendo

**Bons trades! 🚀**
