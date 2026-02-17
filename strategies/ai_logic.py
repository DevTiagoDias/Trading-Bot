"""
Lógica de Inteligência Artificial para Trading.

Implementa:
- Modelo Primário: Seguidor de tendência com EMA e RSI
- Meta-Modelo: RandomForest para filtro de qualidade de sinais
- Sistema de treinamento e predição
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, Any, Tuple
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
import joblib
from pathlib import Path
from datetime import datetime

from core.logger import get_logger
from data.features import FeatureEngine, BarrierLabeler

logger = get_logger(__name__)


class PrimaryStrategy:
    """
    Estratégia Primária: Seguidor de Tendência.
    
    Gera sinais de compra/venda baseados em:
    - Posição do preço em relação à EMA200
    - RSI para confirmação de momentum
    - Barreiras dinâmicas baseadas em ATR
    """
    
    def __init__(
        self,
        ema_period: int = 200,
        rsi_period: int = 14,
        rsi_overbought: float = 70,
        rsi_oversold: float = 30,
        sl_atr_mult: float = 2.0,
        tp_atr_mult: float = 3.0
    ):
        """
        Inicializa estratégia primária.
        
        Args:
            ema_period: Período da EMA
            rsi_period: Período do RSI
            rsi_overbought: Nível de sobrecompra do RSI
            rsi_oversold: Nível de sobrevenda do RSI
            sl_atr_mult: Multiplicador ATR para Stop Loss
            tp_atr_mult: Multiplicador ATR para Take Profit
        """
        self.ema_period = ema_period
        self.rsi_period = rsi_period
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold
        self.sl_atr_mult = sl_atr_mult
        self.tp_atr_mult = tp_atr_mult
        
        logger.info(
            f"PrimaryStrategy inicializada - "
            f"EMA: {ema_period}, RSI: {rsi_period}, "
            f"SL_mult: {sl_atr_mult}, TP_mult: {tp_atr_mult}"
        )
    
    def generate_signal(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Gera sinal de trading baseado em análise técnica.
        
        Args:
            df: DataFrame com indicadores calculados
            
        Returns:
            Dicionário com sinal e parâmetros de risco
            {
                'action': 'BUY'/'SELL'/'HOLD',
                'side': 1/-1/0,
                'confidence': float,
                'entry_price': float,
                'sl': float,
                'tp': float,
                'atr': float
            }
        """
        if df is None or len(df) == 0:
            return self._no_signal()
        
        # Pega última barra completa (não a atual que pode estar em formação)
        if len(df) < 2:
            return self._no_signal()
        
        current = df.iloc[-1]
        
        # Valida dados necessários
        if pd.isna(current['ema']) or pd.isna(current['rsi']) or pd.isna(current['atr']):
            logger.debug("Indicadores insuficientes para gerar sinal")
            return self._no_signal()
        
        close = current['close']
        ema = current['ema']
        rsi = current['rsi']
        atr = current['atr']
        
        # Lógica de Sinal de COMPRA
        if close > ema and rsi < self.rsi_overbought and rsi > 50:
            # Tendência de alta confirmada
            sl = close - (self.sl_atr_mult * atr)
            tp = close + (self.tp_atr_mult * atr)
            
            # Calcula confiança baseada na força do sinal
            distance_from_ema = (close - ema) / atr
            rsi_strength = (rsi - 50) / 50  # Normalizado
            confidence = min(0.5 + (distance_from_ema * 0.2) + (rsi_strength * 0.3), 1.0)
            
            return {
                'action': 'BUY',
                'side': 1,
                'confidence': confidence,
                'entry_price': close,
                'sl': sl,
                'tp': tp,
                'atr': atr,
                'ema': ema,
                'rsi': rsi
            }
        
        # Lógica de Sinal de VENDA
        elif close < ema and rsi > self.rsi_oversold and rsi < 50:
            # Tendência de baixa confirmada
            sl = close + (self.sl_atr_mult * atr)
            tp = close - (self.tp_atr_mult * atr)
            
            # Calcula confiança
            distance_from_ema = (ema - close) / atr
            rsi_strength = (50 - rsi) / 50
            confidence = min(0.5 + (distance_from_ema * 0.2) + (rsi_strength * 0.3), 1.0)
            
            return {
                'action': 'SELL',
                'side': -1,
                'confidence': confidence,
                'entry_price': close,
                'sl': sl,
                'tp': tp,
                'atr': atr,
                'ema': ema,
                'rsi': rsi
            }
        
        return self._no_signal()
    
    def _no_signal(self) -> Dict[str, Any]:
        """
        Retorna estrutura de 'sem sinal'.
        """
        return {
            'action': 'HOLD',
            'side': 0,
            'confidence': 0.0,
            'entry_price': 0.0,
            'sl': 0.0,
            'tp': 0.0,
            'atr': 0.0,
            'ema': 0.0,
            'rsi': 0.0
        }


class MetaLabeler:
    """
    Meta-Modelo para classificação de qualidade de sinais.
    
    Atua como auditor de risco, prevendo a probabilidade de sucesso
    de cada sinal gerado pela estratégia primária.
    
    Utiliza RandomForest para aprender padrões históricos de sucesso/fracasso.
    """
    
    def __init__(
        self,
        n_estimators: int = 100,
        max_depth: int = 10,
        min_samples_split: int = 20,
        random_state: int = 42,
        model_path: str = "models/meta_classifier.pkl"
    ):
        """
        Inicializa meta-labeler.
        
        Args:
            n_estimators: Número de árvores no RandomForest
            max_depth: Profundidade máxima das árvores
            min_samples_split: Mínimo de amostras para split
            random_state: Seed para reprodutibilidade
            model_path: Caminho para salvar/carregar modelo
        """
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_split = min_samples_split
        self.random_state = random_state
        self.model_path = model_path
        
        self.model: Optional[RandomForestClassifier] = None
        self.feature_columns: Optional[list] = None
        self.is_trained = False
        
        # Tenta carregar modelo existente
        self._load_model()
        
        logger.info(
            f"MetaLabeler inicializado - "
            f"Trees: {n_estimators}, Depth: {max_depth}"
        )
    
    def train(
        self,
        df: pd.DataFrame,
        side: int,
        sl_mult: float = 2.0,
        tp_mult: float = 3.0
    ) -> Dict[str, Any]:
        """
        Treina o meta-modelo com dados históricos.
        
        Args:
            df: DataFrame com features e preços
            side: Direção dos trades (1 para compra, -1 para venda)
            sl_mult: Multiplicador do ATR para Stop Loss
            tp_mult: Multiplicador do ATR para Take Profit
            
        Returns:
            Dicionário com métricas de treinamento
        """
        logger.info(f"Iniciando treinamento do meta-modelo (side={side})...")
        
        # Gera labels usando Triple-Barrier Method
        labeler = BarrierLabeler(
            sl_multiplier=sl_mult,
            tp_multiplier=tp_mult,
            max_bars=10
        )
        
        labels = labeler.generate_labels(df, side)
        
        # Seleciona features para ML
        feature_cols = [
            'rsi', 'volatility', 'momentum', 'price_distance_ema',
            'volume_ratio', 'return_mean_5', 'return_mean_10', 'return_mean_20',
            'volatility_5', 'volatility_10', 'volatility_20',
            'rsi_mean_5', 'rsi_mean_10', 'rsi_mean_20',
            'ema_trend', 'price_acceleration', 'range_normalized', 'body_shadow_ratio'
        ]
        
        # Filtra features disponíveis
        available_features = [col for col in feature_cols if col in df.columns]
        
        if not available_features:
            logger.error("Nenhuma feature disponível para treinamento")
            return {'success': False, 'error': 'No features available'}
        
        self.feature_columns = available_features
        
        # Prepara dados
        X = df[available_features].values
        y = labels
        
        # Remove amostras com NaN
        valid_indices = ~np.isnan(X).any(axis=1) & ~np.isnan(y)
        X = X[valid_indices]
        y = y[valid_indices]
        
        if len(X) < 100:
            logger.warning(f"Dados insuficientes para treinamento: {len(X)} amostras")
            return {'success': False, 'error': 'Insufficient data'}
        
        # Split treino/teste
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=self.random_state, stratify=y
        )
        
        # Treina modelo
        self.model = RandomForestClassifier(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            min_samples_split=self.min_samples_split,
            random_state=self.random_state,
            n_jobs=-1
        )
        
        self.model.fit(X_train, y_train)
        
        # Avalia modelo
        y_pred_train = self.model.predict(X_train)
        y_pred_test = self.model.predict(X_test)
        
        train_acc = accuracy_score(y_train, y_pred_train)
        test_acc = accuracy_score(y_test, y_pred_test)
        
        logger.info(f"Treinamento concluído - Train Acc: {train_acc:.3f}, Test Acc: {test_acc:.3f}")
        
        # Salva modelo
        self._save_model()
        
        self.is_trained = True
        
        return {
            'success': True,
            'train_accuracy': train_acc,
            'test_accuracy': test_acc,
            'n_samples': len(X),
            'n_features': len(available_features),
            'feature_importance': dict(zip(available_features, self.model.feature_importances_))
        }
    
    def predict_probability(self, df: pd.DataFrame) -> float:
        """
        Prediz probabilidade de sucesso do sinal atual.
        
        Args:
            df: DataFrame com features calculadas
            
        Returns:
            Probabilidade de sucesso (0-1)
        """
        if not self.is_trained or self.model is None:
            logger.warning("Meta-modelo não treinado. Retornando probabilidade neutra.")
            return 0.5
        
        if df is None or len(df) == 0:
            return 0.5
        
        # Pega última barra
        current = df.iloc[-1]
        
        # Extrai features
        try:
            X = np.array([[current[col] for col in self.feature_columns]])
            
            # Verifica NaN
            if np.isnan(X).any():
                logger.debug("Features contêm NaN, retornando probabilidade neutra")
                return 0.5
            
            # Prediz probabilidade
            proba = self.model.predict_proba(X)[0][1]  # Probabilidade da classe 1
            
            return float(proba)
            
        except Exception as e:
            logger.error(f"Erro ao predizer probabilidade: {e}")
            return 0.5
    
    def _save_model(self) -> None:
        """
        Salva modelo treinado em disco.
        """
        try:
            Path(self.model_path).parent.mkdir(parents=True, exist_ok=True)
            
            model_data = {
                'model': self.model,
                'feature_columns': self.feature_columns,
                'trained_at': datetime.now().isoformat()
            }
            
            joblib.dump(model_data, self.model_path)
            logger.info(f"Modelo salvo em {self.model_path}")
            
        except Exception as e:
            logger.error(f"Erro ao salvar modelo: {e}")
    
    def _load_model(self) -> None:
        """
        Carrega modelo previamente treinado.
        """
        try:
            if Path(self.model_path).exists():
                model_data = joblib.load(self.model_path)
                
                self.model = model_data['model']
                self.feature_columns = model_data['feature_columns']
                self.is_trained = True
                
                logger.info(f"Modelo carregado de {self.model_path}")
                logger.info(f"Treinado em: {model_data.get('trained_at', 'Unknown')}")
            else:
                logger.info("Nenhum modelo salvo encontrado. Treinamento necessário.")
                
        except Exception as e:
            logger.warning(f"Erro ao carregar modelo: {e}")


class AITradingLogic:
    """
    Orquestrador da lógica de IA para trading.
    
    Combina estratégia primária e meta-labeling para gerar
    sinais de alta qualidade.
    """
    
    def __init__(
        self,
        feature_engine: FeatureEngine,
        primary_strategy: PrimaryStrategy,
        meta_labeler: MetaLabeler,
        meta_threshold: float = 0.60
    ):
        """
        Inicializa lógica de IA.
        
        Args:
            feature_engine: Motor de features
            primary_strategy: Estratégia primária
            meta_labeler: Meta-modelo
            meta_threshold: Threshold de probabilidade mínima
        """
        self.feature_engine = feature_engine
        self.primary_strategy = primary_strategy
        self.meta_labeler = meta_labeler
        self.meta_threshold = meta_threshold
        
        logger.info(f"AITradingLogic inicializada - Meta Threshold: {meta_threshold}")
    
    def analyze(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Analisa dados e gera sinal filtrado por meta-modelo.
        
        Args:
            df: DataFrame com OHLCV
            
        Returns:
            Dicionário com sinal e metadados
        """
        # Calcula indicadores
        df_with_indicators = self.feature_engine.calculate_indicators(df)
        
        # Cria features para ML
        df_with_features = self.feature_engine.create_ml_features(df_with_indicators)
        
        # Gera sinal primário
        primary_signal = self.primary_strategy.generate_signal(df_with_features)
        
        if primary_signal['action'] == 'HOLD':
            return primary_signal
        
        # Aplica meta-labeling
        success_probability = self.meta_labeler.predict_probability(df_with_features)
        
        logger.info(
            f"Sinal Primário: {primary_signal['action']} | "
            f"Probabilidade de Sucesso: {success_probability:.2%} | "
            f"Threshold: {self.meta_threshold:.2%}"
        )
        
        # Filtra sinal baseado em threshold
        if success_probability >= self.meta_threshold:
            primary_signal['meta_probability'] = success_probability
            primary_signal['meta_approved'] = True
            logger.info(f"✓ Sinal APROVADO pelo meta-modelo")
            return primary_signal
        else:
            logger.info(f"✗ Sinal REJEITADO pelo meta-modelo")
            return {
                'action': 'HOLD',
                'side': 0,
                'confidence': 0.0,
                'entry_price': 0.0,
                'sl': 0.0,
                'tp': 0.0,
                'atr': 0.0,
                'meta_probability': success_probability,
                'meta_approved': False,
                'rejection_reason': 'Low success probability'
            }
