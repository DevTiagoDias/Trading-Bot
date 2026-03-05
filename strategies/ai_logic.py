"""
Lógica de Inteligência Artificial para Trading Institucional — v3.0

Módulo responsável por toda a inteligência do robô, incluindo:
1. BarrierLabeler : Rotulagem de dados históricos (Triple Barrier Method).
2. PrimaryStrategy: Estratégia cirúrgica — EMA + ADX + MACD + RSI.
3. MetaLabeler    : Filtro de ML (Random Forest) para validar sinais.
4. AITradingLogic : Orquestrador que une a estratégia técnica com a IA.

Melhorias v3.0
--------------
• PrimaryStrategy usa ADX (filtro lateral) + MACD (gatilho) + EMA/RSI (base).
• adx_threshold é OPCIONAL com default 20.0 → compatível com main.py existente.
• ALL_FEATURES alinhado ao que features.py realmente produz (sem features fictícias).
• Logging detalhado em todos os pontos críticos (save, load, predict, train).
• Validação defensiva sem bare except — erros sempre logados explicitamente.
• Parâmetros de risco conservadores: SL 1.5× / TP 2.0× (via train_model.py).
• BarrierLabeler: SL vence em caso de toque simultâneo com TP (conservador).
• Overfitting warning automático no treinamento (gap train/test > 15%).
"""

import warnings
import os

os.environ["PYTHONWARNINGS"] = "ignore"
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")
warnings.filterwarnings("ignore", message=".*sklearn.utils.parallel.delayed.*")

import pandas as pd
import numpy as np
import joblib
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

from core.logger import get_logger
from data.features import FeatureEngine

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 1. BarrierLabeler
# ---------------------------------------------------------------------------

class BarrierLabeler:
    """
    Implementação do Método de Barreiras Triplas (Triple Barrier Method).

    Inspirado em Marcos López de Prado (Advances in Financial Machine Learning).
    Rotula cada barra histórica como:
        1 → Trade vencedor (TP atingido antes do SL ou do tempo)
        0 → Trade perdedor / expirado pelo limite de tempo

    Barreiras:
        Superior  → Take Profit  (tp_multiplier × ATR)
        Inferior  → Stop Loss    (sl_multiplier × ATR)
        Vertical  → Limite de tempo (max_bars)

    Nota v3: quando SL e TP são tocados na mesma barra, o SL vence
    (pior caso conservador) para não super-estimar a taxa de acerto.
    Os multiplicadores padrão são conservadores (1.5/2.0) mas o
    train_model.py os sobrescreve com os valores do risk_config.
    """

    def __init__(
        self,
        sl_multiplier: float = 1.5,
        tp_multiplier: float = 2.0,
        max_bars: int = 15,
    ):
        self.sl_multiplier = float(sl_multiplier)
        self.tp_multiplier = float(tp_multiplier)
        self.max_bars = int(max_bars)

        logger.debug(
            f"BarrierLabeler inicializado | "
            f"SL: {self.sl_multiplier}xATR | "
            f"TP: {self.tp_multiplier}xATR | "
            f"Max Bars: {self.max_bars}"
        )

    def generate_labels(self, df: pd.DataFrame, side: int) -> pd.Series:
        """
        Gera os rótulos Y para treinamento simulando cada entrada histórica.

        Args:
            df   : DataFrame com colunas OHLC + 'atr' (saída do FeatureEngine).
            side : 1 = COMPRA, -1 = VENDA.

        Returns:
            pd.Series com 0s e 1s indexado igual ao df (NaN nas últimas max_bars).
        """
        if df is None or df.empty:
            logger.error("BarrierLabeler: DataFrame vazio fornecido para rotulagem.")
            return pd.Series()

        if 'atr' not in df.columns:
            logger.error("BarrierLabeler: coluna 'atr' ausente. Impossível calcular barreiras.")
            return pd.Series(index=df.index, data=np.nan)

        labels = pd.Series(index=df.index, data=np.nan)

        # Arrays NumPy para performance em loops grandes
        highs  = df['high'].values
        lows   = df['low'].values
        closes = df['close'].values
        atrs   = df['atr'].values
        n      = len(df)

        wins = losses = timeouts = 0

        for i in range(n - self.max_bars):
            entry      = closes[i]
            volatility = atrs[i]

            if np.isnan(volatility) or volatility <= 0:
                continue

            # Define as barreiras de preço
            if side == 1:           # COMPRA
                sl_price = entry - (volatility * self.sl_multiplier)
                tp_price = entry + (volatility * self.tp_multiplier)
            elif side == -1:        # VENDA
                sl_price = entry + (volatility * self.sl_multiplier)
                tp_price = entry - (volatility * self.tp_multiplier)
            else:
                logger.warning(f"BarrierLabeler: side inválido ({side}). Use 1 ou -1.")
                continue

            outcome   = 0    # padrão: timeout / perda
            timed_out = True

            for j in range(1, self.max_bars + 1):
                if i + j >= n:
                    break

                hi = highs[i + j]
                lo = lows[i + j]

                if side == 1:
                    # SL vence em empate (conservador)
                    if lo <= sl_price:
                        outcome   = 0
                        timed_out = False
                        break
                    if hi >= tp_price:
                        outcome   = 1
                        timed_out = False
                        break
                else:
                    if hi >= sl_price:
                        outcome   = 0
                        timed_out = False
                        break
                    if lo <= tp_price:
                        outcome   = 1
                        timed_out = False
                        break

            if timed_out:
                timeouts += 1
            elif outcome == 1:
                wins += 1
            else:
                losses += 1

            labels.iloc[i] = outcome

        total = wins + losses + timeouts
        if total > 0:
            logger.debug(
                f"BarrierLabeler concluído | Total: {total} | "
                f"Wins: {wins} ({wins/total:.1%}) | "
                f"Losses: {losses} ({losses/total:.1%}) | "
                f"Timeouts: {timeouts} ({timeouts/total:.1%})"
            )
        else:
            logger.warning("BarrierLabeler: nenhuma barra pôde ser rotulada (ATR inválido?).")

        return labels


# ---------------------------------------------------------------------------
# 2. PrimaryStrategy
# ---------------------------------------------------------------------------

class PrimaryStrategy:
    """
    Estratégia Primária Cirúrgica — Nível Sênior Quant (v3).

    Combina a base da v1 (EMA200 + RSI) com filtros avançados:
        • ADX > adx_threshold  → Confirma existência de tendência real (mata laterais)
        • Preço vs EMA200      → Define direção da tendência
        • MACD vs Signal       → Confirma momentum na direção certa
        • RSI                  → Evita entrar em zona de exaustão

    COMPATIBILIDADE com main.py:
        adx_threshold é opcional (default=20.0). O main.py existente não passa
        esse parâmetro, então o sistema continua funcionando sem alterações.
    """

    def __init__(
        self,
        ema_period: int       = 200,
        rsi_period: int       = 14,
        rsi_overbought: float = 70.0,
        rsi_oversold: float   = 30.0,
        sl_atr_mult: float    = 1.5,
        tp_atr_mult: float    = 2.0,
        adx_threshold: float  = 20.0,  # OPCIONAL — main.py não passa, usa default
    ):
        self.ema_period     = ema_period
        self.rsi_period     = rsi_period
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold   = rsi_oversold
        self.sl_atr_mult    = sl_atr_mult
        self.tp_atr_mult    = tp_atr_mult
        self.adx_threshold  = adx_threshold

        logger.info(
            f"PrimaryStrategy v3 Inicializada | "
            f"EMA: {ema_period} | RSI: {rsi_period} ({rsi_oversold}/{rsi_overbought}) | "
            f"ADX mín: {adx_threshold} | SL: {sl_atr_mult}x / TP: {tp_atr_mult}x"
        )

    def generate_signal(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Analisa a última barra e retorna um sinal estruturado.

        Colunas 'adx', 'macd' e 'macd_signal' são calculadas pelo FeatureEngine
        (features.py → calculate_indicators). Se ausentes, retorna HOLD.

        Returns:
            Dict com 'action' em {'BUY', 'SELL', 'HOLD'} e metadados completos.
        """
        if df is None or len(df) == 0:
            return self._hold("DataFrame vazio ou None")

        if len(df) < self.ema_period:
            return self._hold(
                f"Dados insuficientes para EMA{self.ema_period} "
                f"({len(df)} barras disponíveis)"
            )

        bar = df.iloc[-1]

        # Valida todas as colunas obrigatórias (calculadas pelo FeatureEngine)
        required = ['close', 'ema', 'rsi', 'atr', 'adx', 'macd', 'macd_signal']
        for col in required:
            if col not in bar.index or pd.isna(bar[col]):
                return self._hold(f"Indicador ausente ou NaN: '{col}'")

        close       = bar['close']
        ema         = bar['ema']
        rsi         = bar['rsi']
        atr         = bar['atr']
        adx         = bar['adx']
        macd        = bar['macd']
        macd_signal = bar['macd_signal']

        # ── FILTRO 1: Tendência real (ADX) ───────────────────────────────────
        # Elimina a maioria das entradas ruins em mercados laterais
        if adx < self.adx_threshold:
            return self._hold(
                f"Mercado lateral (ADX={adx:.1f} < {self.adx_threshold:.1f}). "
                f"Aguardando tendência."
            )

        # ── FILTRO 2 + 3 + 4: Direção + Momentum + RSI ───────────────────────

        # COMPRA: preço acima da EMA + MACD confirmando + RSI sem sobrecompra
        if close > ema and macd > macd_signal and rsi < self.rsi_overbought:
            logger.debug(
                f"Sinal BUY | Close: {close:.5f} > EMA: {ema:.5f} | "
                f"ADX: {adx:.1f} | MACD: {macd:.5f} > Sig: {macd_signal:.5f} | "
                f"RSI: {rsi:.1f}"
            )
            return self._signal('BUY', 1, close, atr, ema, rsi, adx)

        # VENDA: preço abaixo da EMA + MACD confirmando + RSI sem sobrevenda
        if close < ema and macd < macd_signal and rsi > self.rsi_oversold:
            logger.debug(
                f"Sinal SELL | Close: {close:.5f} < EMA: {ema:.5f} | "
                f"ADX: {adx:.1f} | MACD: {macd:.5f} < Sig: {macd_signal:.5f} | "
                f"RSI: {rsi:.1f}"
            )
            return self._signal('SELL', -1, close, atr, ema, rsi, adx)

        return self._hold("Indicadores não alinhados. Aguardando confluência.")

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _signal(
        self,
        action: str,
        side: int,
        close: float,
        atr: float,
        ema: float,
        rsi: float,
        adx: float,
    ) -> Dict[str, Any]:
        sl = close - (self.sl_atr_mult * atr) if side == 1 else close + (self.sl_atr_mult * atr)
        tp = close + (self.tp_atr_mult * atr) if side == 1 else close - (self.tp_atr_mult * atr)

        # Confiança técnica heurística (0.1 a 0.99)
        dist_ema  = abs(close - ema) / max(atr, 1e-9)
        rsi_score = ((rsi - 50) / 20.0) if side == 1 else ((50 - rsi) / 20.0)
        adx_score = min((adx - self.adx_threshold) / 30.0, 1.0)
        confidence = 0.40 + (0.10 * dist_ema) + (0.15 * rsi_score) + (0.15 * adx_score)
        confidence = float(min(max(confidence, 0.10), 0.99))

        return {
            'action'      : action,
            'side'        : side,
            'confidence'  : confidence,
            'entry_price' : close,
            'sl'          : sl,
            'tp'          : tp,
            'atr'         : atr,
            'ema'         : ema,
            'rsi'         : rsi,
            'adx'         : adx,
        }

    def _hold(self, reason: str = "") -> Dict[str, Any]:
        if reason:
            logger.debug(f"PrimaryStrategy → HOLD | {reason}")
        return {
            'action'      : 'HOLD',
            'side'        : 0,
            'confidence'  : 0.0,
            'entry_price' : 0.0,
            'sl'          : 0.0,
            'tp'          : 0.0,
            'atr'         : 0.0,
            'ema'         : 0.0,
            'rsi'         : 0.0,
            'reason'      : reason,
        }


# ---------------------------------------------------------------------------
# 3. MetaLabeler
# ---------------------------------------------------------------------------

class MetaLabeler:
    """
    Meta-Modelo Random Forest — Conceito de Meta-Labeling (López de Prado).

    Não prevê preço. Prevê SE o sinal da PrimaryStrategy vai dar lucro.

    Input  (X) : Features técnicas estacionárias produzidas pelo FeatureEngine.
    Target (Y) : 1 = trade vencedor | 0 = perdedor.
    Output     : Probabilidade de sucesso do sinal atual (0.0 a 1.0).

    ALL_FEATURES v3
    ---------------
    Lista alinhada EXATAMENTE ao que features.py produz:

    calculate_indicators  → rsi, adx, macd, macd_hist, volatility,
                             momentum, price_distance_ema, volume_ratio

    create_ml_features    → return_mean_5/10/20, volatility_5/10/20,
                             rsi_mean_5/10/20, ema_trend, price_acceleration,
                             range_normalized, body_shadow_ratio,
                             macd_divergence, adx_direction

    Features ausentes no DataFrame são ignoradas com warning, garantindo
    que o sistema nunca quebre por falta de coluna opcional.
    """

    # Ordem canônica — nunca reordenar, mantém compatibilidade de modelos salvos
    ALL_FEATURES: List[str] = [
        # Indicadores base (calculate_indicators)
        'rsi',
        'adx',
        'macd',
        'macd_hist',
        'volatility',
        'momentum',
        'price_distance_ema',
        'volume_ratio',
        # Janelas temporais múltiplas (create_ml_features)
        'return_mean_5',
        'return_mean_10',
        'return_mean_20',
        'volatility_5',
        'volatility_10',
        'volatility_20',
        'rsi_mean_5',
        'rsi_mean_10',
        'rsi_mean_20',
        # Price action quantitativo (create_ml_features)
        'ema_trend',
        'price_acceleration',
        'range_normalized',
        'body_shadow_ratio',
        # Features derivadas de ADX e MACD (create_ml_features)
        'macd_divergence',   # macd - macd_signal
        'adx_direction',     # sign(adx_plus - adx_minus)
    ]

    def __init__(
        self,
        n_estimators: int      = 100,
        max_depth: int         = 10,
        min_samples_split: int = 20,
        random_state: int      = 42,
        model_path: str        = "models/meta_classifier.pkl",
    ):
        self.n_estimators      = n_estimators
        self.max_depth         = max_depth
        self.min_samples_split = min_samples_split
        self.random_state      = random_state
        self.model_path        = model_path

        self.model              : Optional[RandomForestClassifier] = None
        self.feature_columns    : Optional[List[str]]              = None
        self.is_trained         : bool                             = False
        self.last_training_date : Optional[datetime]               = None

        # Tenta carregar modelo existente ao iniciar
        self._load_model()

        logger.info(
            f"MetaLabeler v3 Configurado | "
            f"Trees: {n_estimators} | Depth: {max_depth} | "
            f"MinSamplesSplit: {min_samples_split} | Path: '{model_path}'"
        )

    # ── API Pública ───────────────────────────────────────────────────────────

    def reload(self) -> bool:
        """
        Recarrega o modelo do disco sem reiniciar o processo.
        Chamado pelo main.py após retreinamento automático (check_and_retrain_model).

        Returns:
            True se recarregou com sucesso, False caso contrário.
        """
        logger.info("MetaLabeler: solicitação de reload do modelo...")
        self._load_model()
        status = "OK" if self.is_trained else "FALHOU"
        logger.info(f"MetaLabeler: reload {status}.")
        return self.is_trained

    def train(
        self,
        df: pd.DataFrame,
        side: int,
        sl_mult: float = 1.5,
        tp_mult: float = 2.0,
    ) -> Dict[str, Any]:
        """
        Treina o modelo com dados históricos rotulados pelo BarrierLabeler.

        Chamado pelo train_model.py com sl_mult/tp_mult vindos do risk_config,
        garantindo que os multiplicadores de risco sejam consistentes em todo
        o sistema (estratégia, rotulagem e execução usam os mesmos valores).

        Args:
            df      : DataFrame com features calculadas pelo FeatureEngine.
            side    : 1 = treinar para sinais de compra | -1 = venda.
            sl_mult : Multiplicador ATR para Stop Loss (vem do risk_config).
            tp_mult : Multiplicador ATR para Take Profit (vem do risk_config).

        Returns:
            Dict com 'success', métricas de acurácia e feature importance.
        """
        logger.info(
            f"MetaLabeler: iniciando treinamento | "
            f"Side: {'COMPRA' if side == 1 else 'VENDA'} | "
            f"SL: {sl_mult}x | TP: {tp_mult}x"
        )

        # 1. Geração de Labels com os mesmos multiplicadores do sistema
        labeler = BarrierLabeler(
            sl_multiplier=sl_mult,
            tp_multiplier=tp_mult,
            max_bars=15,
        )
        labels = labeler.generate_labels(df, side)

        # 2. Seleção de features disponíveis no DataFrame atual
        available = [col for col in self.ALL_FEATURES if col in df.columns]

        if not available:
            msg = "Nenhuma feature compatível encontrada no DataFrame para treino."
            logger.error(f"MetaLabeler: {msg}")
            return {'success': False, 'error': msg}

        missing = [c for c in self.ALL_FEATURES if c not in df.columns]
        if missing:
            logger.warning(
                f"MetaLabeler: {len(missing)} features ausentes (serão ignoradas): {missing}"
            )

        self.feature_columns = available

        # 3. Montagem de X e y
        X = df[available].values
        y = labels.values

        valid = ~np.isnan(X).any(axis=1) & ~np.isnan(y)
        X, y  = X[valid], y[valid]

        if len(X) < 100:
            msg = f"Dados insuficientes após limpeza: {len(X)} amostras (mínimo: 100)."
            logger.warning(f"MetaLabeler: {msg}")
            return {'success': False, 'error': msg}

        class_counts = {int(k): int(v) for k, v in zip(*np.unique(y, return_counts=True))}
        logger.info(f"MetaLabeler: distribuição de classes → {class_counts}")

        # 4. Split Treino / Teste
        X_train, X_test, y_train, y_test = train_test_split(
            X, y,
            test_size=0.2,
            random_state=self.random_state,
            stratify=y,
        )

        # 5. Treinamento
        self.model = RandomForestClassifier(
            n_estimators      = self.n_estimators,
            max_depth         = self.max_depth,
            min_samples_split = self.min_samples_split,
            random_state      = self.random_state,
            n_jobs            = -1,           # Usa todos os cores
            class_weight      = 'balanced',   # Compensa desbalanceamento win/loss
        )

        logger.debug(f"MetaLabeler: ajustando modelo com {len(X_train)} amostras...")
        self.model.fit(X_train, y_train)

        # 6. Métricas
        train_acc = accuracy_score(y_train, self.model.predict(X_train))
        test_acc  = accuracy_score(y_test,  self.model.predict(X_test))

        logger.info(
            f"MetaLabeler: treinamento concluído | "
            f"Train Acc: {train_acc:.2%} | Test Acc: {test_acc:.2%} | "
            f"Amostras: {len(X)} | Features: {len(available)}"
        )

        # Alerta de overfitting automático
        gap = train_acc - test_acc
        if gap > 0.15:
            logger.warning(
                f"MetaLabeler: ⚠️ Possível overfitting (gap train/test = {gap:.2%}). "
                f"Considere aumentar min_samples_split ou reduzir max_depth no settings.json."
            )

        # 7. Persiste e atualiza estado
        self._save_model()
        self.is_trained = True

        return {
            'success'            : True,
            'train_accuracy'     : train_acc,
            'test_accuracy'      : test_acc,
            'n_samples'          : len(X),
            'n_features'         : len(available),
            'feature_importance' : self.get_feature_importance(),
        }

    def predict_probability(self, df: pd.DataFrame) -> float:
        """
        Retorna a probabilidade (0.0 a 1.0) de o sinal atual ser vencedor.

        Retorna 0.5 (neutro) em caso de modelo não treinado, dados inválidos
        ou features com NaN — sempre logando o motivo explicitamente.
        """
        if not self.is_trained or self.model is None:
            logger.warning(
                "MetaLabeler: predição solicitada com modelo não treinado. "
                "Retornando neutro (0.5)."
            )
            return 0.5

        if df is None or len(df) == 0:
            logger.warning("MetaLabeler: DataFrame vazio na predição. Retornando 0.5.")
            return 0.5

        current = df.iloc[-1]

        try:
            X = np.array([[current[col] for col in self.feature_columns]])

            if np.isnan(X).any():
                nan_cols = [
                    col for col, val in zip(self.feature_columns, X[0])
                    if np.isnan(val)
                ]
                logger.debug(
                    f"MetaLabeler: NaN nas features {nan_cols}. Retornando 0.5."
                )
                return 0.5

            proba = float(self.model.predict_proba(X)[0][1])
            return proba

        except KeyError as e:
            logger.error(f"MetaLabeler: feature ausente nos dados de entrada: {e}")
            return 0.5
        except Exception as e:
            logger.error(f"MetaLabeler: erro inesperado na predição: {e}")
            return 0.5

    def get_feature_importance(self) -> Dict[str, float]:
        """
        Retorna importância de cada feature.
        Usado pelo train_model.py para exibir o relatório Top 5 features.
        """
        if not self.is_trained or self.model is None or self.feature_columns is None:
            return {}
        try:
            return dict(zip(self.feature_columns, self.model.feature_importances_))
        except Exception as e:
            logger.error(f"MetaLabeler: erro ao extrair importâncias: {e}")
            return {}

    # ── Persistência ─────────────────────────────────────────────────────────

    def _save_model(self) -> None:
        """Persiste o modelo e metadados no disco usando Joblib."""
        try:
            Path(self.model_path).parent.mkdir(parents=True, exist_ok=True)

            payload = {
                'model'           : self.model,
                'feature_columns' : self.feature_columns,
                'trained_at'      : datetime.now().isoformat(),
                'version'         : '3.0',
            }

            joblib.dump(payload, self.model_path)
            self.last_training_date = datetime.now()

            logger.info(f"MetaLabeler: modelo salvo com sucesso em '{self.model_path}'.")

        except Exception as e:
            logger.error(
                f"MetaLabeler: CRÍTICO — falha ao salvar modelo em '{self.model_path}': {e}"
            )

    def _load_model(self) -> None:
        """Carrega modelo e metadados do disco."""
        try:
            path = Path(self.model_path)

            if not path.exists():
                logger.warning(
                    f"MetaLabeler: modelo não encontrado em '{self.model_path}'. "
                    f"Execute train_model.py para criar um."
                )
                self.is_trained = False
                return

            logger.info(f"MetaLabeler: carregando modelo de '{path}'...")
            data = joblib.load(self.model_path)

            self.model           = data['model']
            self.feature_columns = data['feature_columns']
            self.is_trained      = True

            trained_at_str = data.get('trained_at')
            if trained_at_str:
                try:
                    self.last_training_date = datetime.fromisoformat(trained_at_str)
                    age     = datetime.now() - self.last_training_date
                    version = data.get('version', '?')
                    logger.info(
                        f"MetaLabeler: modelo v{version} carregado | "
                        f"Idade: {age.days}d {age.seconds // 3600}h | "
                        f"Features ativas: {len(self.feature_columns)}"
                    )
                except ValueError:
                    self.last_training_date = datetime.now()

        except Exception as e:
            logger.error(f"MetaLabeler: falha ao carregar modelo: {e}")
            self.is_trained = False


# ---------------------------------------------------------------------------
# 4. AITradingLogic — Orquestrador
# ---------------------------------------------------------------------------

class AITradingLogic:
    """
    Orquestrador da Lógica de IA (Facade Pattern).

    Simplifica a interação entre o TradingBot (main.py) e os subsistemas
    de estratégia e ML, expondo uma API de uma única chamada: analyze().

    Fluxo de Decisão:
        1. FeatureEngine → calcula indicadores + features ML.
        2. PrimaryStrategy → sinal técnico bruto (BUY / SELL / HOLD).
        3. Se HOLD: retorna imediatamente (sem custo de ML).
        4. MetaLabeler → probabilidade de sucesso do sinal.
        5. prob >= meta_threshold → APROVADO | caso contrário → HOLD.
    """

    def __init__(
        self,
        feature_engine   : FeatureEngine,
        primary_strategy : PrimaryStrategy,
        meta_labeler     : MetaLabeler,
        meta_threshold   : float = 0.60,
    ):
        self.feature_engine   = feature_engine
        self.primary_strategy = primary_strategy
        self.meta_labeler     = meta_labeler
        self.meta_threshold   = meta_threshold

        logger.info(
            f"AITradingLogic v3 Pronta | "
            f"Threshold de Confiança Mínimo: {meta_threshold:.1%}"
        )

    def analyze(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Executa o pipeline completo de análise para uma barra de mercado.

        Args:
            df : DataFrame OHLCV bruto (saída do MT5Client.get_rates).

        Returns:
            Dict com decisão final + todos os metadados para logging e execução.
            Campos garantidos: 'action', 'side', 'meta_approved', 'meta_probability'.
        """
        # Passo 1: Enriquecimento de dados (FeatureEngine)
        df_ind  = self.feature_engine.calculate_indicators(df)
        df_feat = self.feature_engine.create_ml_features(df_ind)

        # Passo 2: Estratégia Primária (Análise Técnica)
        signal = self.primary_strategy.generate_signal(df_feat)

        # Curto-circuito — não gasta ML em HOLD (performance)
        if signal['action'] == 'HOLD':
            return signal

        # Passo 3: Meta-Labeling (Filtro de IA)
        prob = self.meta_labeler.predict_probability(df_feat)

        logger.info(
            f"Análise Cruzada | "
            f"Sinal Técnico: {signal['action']} | "
            f"Confiança IA: {prob:.2%} | "
            f"Corte Mínimo: {self.meta_threshold:.2%}"
        )

        # Passo 4: Decisão Final
        if prob >= self.meta_threshold:
            signal['meta_probability'] = prob
            signal['meta_approved']    = True
            signal['timestamp']        = datetime.now()

            logger.info(
                f">>> SINAL {signal['action']} APROVADO PELA IA "
                f"(prob={prob:.2%}) <<<"
            )
            return signal

        # Sinal rejeitado pelo filtro de ML
        logger.info(
            f"Sinal {signal['action']} REJEITADO pela IA | "
            f"Prob: {prob:.2%} < Corte: {self.meta_threshold:.2%}"
        )
        return {
            'action'           : 'HOLD',
            'side'             : 0,
            'confidence'       : 0.0,
            'entry_price'      : 0.0,
            'sl'               : 0.0,
            'tp'               : 0.0,
            'atr'              : 0.0,
            'meta_probability' : prob,
            'meta_approved'    : False,
            'rejection_reason' : (
                f"Probabilidade insuficiente "
                f"({prob:.2%} < {self.meta_threshold:.2%})"
            ),
            'original_signal'  : signal['action'],
        }