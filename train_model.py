"""
Script de Treinamento do Meta-Modelo.

Este script treina o classificador RandomForest usado no meta-labeling
com dados históricos de um símbolo específico.

Uso Manual:
    python train_model.py
    
Uso Automático:
    Importado pelo main.py para retreinamento periódico.
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
    side: int = 3, # 3 = Ambos (Padrão)
    silent: bool = False
) -> dict:
    """
    Treina o meta-modelo com dados históricos.
    
    Args:
        symbol: Símbolo para treinamento
        timeframe: Timeframe dos dados
        lookback: Número de barras históricas
        side: 1 (Compra), -1 (Venda), 3 (Ambos)
        silent: Se True, suprime logs excessivos (para modo automático)
        
    Returns:
        Dicionário com estatísticas do treinamento: {'success': bool, 'acc': float}
    """
    if not silent:
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
    
    metrics_summary = {'success': False, 'acc': 0.0}
    
    try:
        # Conecta
        await client.connect()
        
        if not silent:
            logger.info(f"Obtendo {lookback} barras de {symbol} {timeframe}...")
        
        # Obtém dados históricos
        df = await client.get_rates(symbol, timeframe, lookback)
        
        if df is None or len(df) == 0:
            logger.error("Falha ao obter dados históricos")
            return metrics_summary
        
        if not silent:
            logger.info(f"✓ {len(df)} barras obtidas")
        
        # Calcula features
        if not silent:
            logger.info("Calculando indicadores técnicos...")
            
        strategy_config = config['strategy']
        
        engine = FeatureEngine(
            ema_period=strategy_config['ema_period'],
            rsi_period=strategy_config['rsi_period'],
            atr_period=strategy_config['atr_period']
        )
        
        df = engine.calculate_indicators(df)
        df = engine.create_ml_features(df)
        
        if not silent:
            logger.info(f"✓ Features calculadas: {len(df.columns)} colunas")
        
        # Configurações de Treino
        ml_config = config['ml']
        risk_config = config['risk']
        
        labeler = MetaLabeler(
            n_estimators=ml_config['n_estimators'],
            max_depth=ml_config['max_depth'],
            min_samples_split=ml_config['min_samples_split'],
            random_state=ml_config['random_state'],
            model_path=ml_config['model_path']
        )
        
        # Define quais lados treinar
        sides_to_train = []
        if side == 1:
            sides_to_train = [1]
        elif side == -1:
            sides_to_train = [-1]
        else:
            sides_to_train = [1, -1] # Ambos
            
        final_acc = 0
        success_count = 0
        
        for s in sides_to_train:
            side_name = "COMPRA" if s == 1 else "VENDA"
            if not silent:
                logger.info(f"Treinando meta-modelo para {side_name}...")
            
            metrics = labeler.train(
                df=df,
                side=s,
                sl_mult=risk_config['stop_loss_atr_multiplier'],
                tp_mult=risk_config['take_profit_atr_multiplier']
            )
            
            if metrics['success']:
                success_count += 1
                final_acc = metrics['test_accuracy'] # Guarda a última acurácia
                
                if not silent:
                    # Relatório Detalhado Completo (Restaurado)
                    logger.info(f"Amostras: {metrics['n_samples']}")
                    logger.info(f"Features: {metrics['n_features']}")
                    logger.info(f"Acurácia Treino: {metrics['train_accuracy']:.2%}")
                    logger.info(f"Acurácia Teste: {metrics['test_accuracy']:.2%}")
                    
                    # Exibe Feature Importance
                    importances = metrics['feature_importance']
                    sorted_features = sorted(importances.items(), key=lambda x: x[1], reverse=True)[:5]
                    
                    logger.info("Top 5 Features Mais Importantes:")
                    for i, (feat, score) in enumerate(sorted_features, 1):
                        logger.info(f"   {i}. {feat}: {score:.4f}")
                    logger.info("-" * 40)
        
        # Considera sucesso se treinou pelo menos um lado com êxito
        if success_count > 0:
            metrics_summary['success'] = True
            metrics_summary['acc'] = final_acc
            
            if not silent:
                logger.info("=" * 80)
                logger.info("✓✓✓ TREINAMENTO CONCLUÍDO COM SUCESSO ✓✓✓")
                logger.info("=" * 80)
        else:
            logger.error("Falha no treinamento de todos os lados selecionados")
    
    except Exception as e:
        logger.error(f"Erro durante treinamento: {e}", exc_info=True)
    
    finally:
        # Desconecta apenas se foi chamado diretamente, não pelo singleton em loop
        # Mas como usamos singleton, disconnect não atrapalha se reconectar depois
        if not silent:
            await client.disconnect()
            
    return metrics_summary


async def main():
    """
    Função principal para execução manual interativa.
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
    
    side_map = {"1": 1, "2": -1, "3": 3}
    
    if choice in side_map:
        await train_meta_model(
            symbol=symbol, 
            timeframe=timeframe, 
            lookback=lookback, 
            side=side_map[choice],
            silent=False
        )
    else:
        print("Opção inválida!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nInterrompido pelo usuário")
    except Exception as e:
        print(f"\n\nErro: {e}")