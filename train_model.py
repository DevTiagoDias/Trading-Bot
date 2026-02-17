"""
Script de Treinamento do Meta-Modelo.

Este script treina o classificador RandomForest usado no meta-labeling
com dados históricos de um símbolo específico.

Uso:
    python train_model.py
"""

import asyncio
import json
import sys
from pathlib import Path

# Adiciona diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent))

from core import configure_logging_from_config, get_logger, MT5Client
from data import FeatureEngine
from strategies import MetaLabeler

logger = get_logger(__name__)


async def train_meta_model(
    symbol: str = "EURUSD",
    timeframe: str = "H1",
    lookback: int = 5000,
    side: int = 1
) -> None:
    """
    Treina o meta-modelo com dados históricos.
    
    Args:
        symbol: Símbolo para treinamento
        timeframe: Timeframe dos dados
        lookback: Número de barras históricas
        side: 1 para compra, -1 para venda
    """
    logger.info("=" * 80)
    logger.info("Iniciando Treinamento do Meta-Modelo")
    logger.info("=" * 80)
    
    # Carrega configurações
    with open("config/settings.json", 'r') as f:
        config = json.load(f)
    
    # Inicializa MT5
    mt5_config = config['mt5']
    client = MT5Client(
        login=mt5_config['login'],
        password=mt5_config['password'],
        server=mt5_config['server'],
        timeout=mt5_config['timeout']
    )
    
    try:
        # Conecta
        await client.connect()
        
        logger.info(f"Obtendo {lookback} barras de {symbol} {timeframe}...")
        
        # Obtém dados históricos
        df = await client.get_rates(symbol, timeframe, lookback)
        
        if df is None or len(df) == 0:
            logger.error("Falha ao obter dados históricos")
            return
        
        logger.info(f"✓ {len(df)} barras obtidas")
        
        # Calcula features
        logger.info("Calculando indicadores técnicos...")
        strategy_config = config['strategy']
        
        engine = FeatureEngine(
            ema_period=strategy_config['ema_period'],
            rsi_period=strategy_config['rsi_period'],
            atr_period=strategy_config['atr_period']
        )
        
        df = engine.calculate_indicators(df)
        df = engine.create_ml_features(df)
        
        logger.info(f"✓ Features calculadas: {len(df.columns)} colunas")
        
        # Treina modelo
        logger.info(f"Treinando meta-modelo (side={side})...")
        
        ml_config = config['ml']
        risk_config = config['risk']
        
        labeler = MetaLabeler(
            n_estimators=ml_config['n_estimators'],
            max_depth=ml_config['max_depth'],
            min_samples_split=ml_config['min_samples_split'],
            random_state=ml_config['random_state'],
            model_path=ml_config['model_path']
        )
        
        metrics = labeler.train(
            df=df,
            side=side,
            sl_mult=risk_config['stop_loss_atr_multiplier'],
            tp_mult=risk_config['take_profit_atr_multiplier']
        )
        
        if metrics['success']:
            logger.info("=" * 80)
            logger.info("✓✓✓ TREINAMENTO CONCLUÍDO COM SUCESSO ✓✓✓")
            logger.info("=" * 80)
            logger.info(f"Amostras: {metrics['n_samples']}")
            logger.info(f"Features: {metrics['n_features']}")
            logger.info(f"Acurácia Treino: {metrics['train_accuracy']:.2%}")
            logger.info(f"Acurácia Teste: {metrics['test_accuracy']:.2%}")
            logger.info("")
            logger.info("Top 5 Features Mais Importantes:")
            
            # Ordena features por importância
            importance = metrics['feature_importance']
            sorted_features = sorted(
                importance.items(),
                key=lambda x: x[1],
                reverse=True
            )
            
            for i, (feature, imp) in enumerate(sorted_features[:5], 1):
                logger.info(f"  {i}. {feature}: {imp:.4f}")
            
            logger.info("=" * 80)
        else:
            logger.error(f"✗ Treinamento falhou: {metrics.get('error')}")
    
    except Exception as e:
        logger.error(f"Erro durante treinamento: {e}", exc_info=True)
    
    finally:
        # Desconecta
        await client.disconnect()


async def main():
    """
    Função principal.
    """
    # Configura logging
    configure_logging_from_config("config/settings.json")
    
    # Menu de opções
    print("\n" + "=" * 60)
    print("TREINAMENTO DO META-MODELO")
    print("=" * 60)
    print("\nOpções:")
    print("1. Treinar para sinais de COMPRA")
    print("2. Treinar para sinais de VENDA")
    print("3. Treinar ambos (recomendado)")
    print("0. Sair")
    print("\n" + "=" * 60)
    
    choice = input("\nEscolha uma opção: ").strip()
    
    if choice == "0":
        print("Saindo...")
        return
    
    symbol = input("Símbolo [EURUSD]: ").strip() or "EURUSD"
    timeframe = input("Timeframe [H1]: ").strip() or "H1"
    lookback = int(input("Barras históricas [5000]: ").strip() or "5000")
    
    if choice == "1":
        await train_meta_model(symbol, timeframe, lookback, side=1)
    elif choice == "2":
        await train_meta_model(symbol, timeframe, lookback, side=-1)
    elif choice == "3":
        logger.info("Treinando modelo para COMPRA...")
        await train_meta_model(symbol, timeframe, lookback, side=1)
        
        logger.info("\nTreinando modelo para VENDA...")
        await train_meta_model(symbol, timeframe, lookback, side=-1)
    else:
        print("Opção inválida!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nInterrompido pelo usuário")
    except Exception as e:
        print(f"\n\nErro: {e}")
