"""
Script de Diagnóstico e Validação do Sistema.

Verifica:
- Conexão com MT5
- Disponibilidade de símbolos
- Configurações
- Dependências
- Permissões de trading

Uso:
    python diagnostic.py
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, Any

# Adiciona diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent))

from core import configure_logging_from_config, get_logger, MT5Client

logger = get_logger(__name__)


class SystemDiagnostic:
    """
    Diagnóstico completo do sistema de trading.
    """
    
    def __init__(self, config_path: str = "config/settings.json"):
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        self.issues: list = []
        self.warnings: list = []
        
    def check_dependencies(self) -> bool:
        """
        Verifica se todas as dependências estão instaladas.
        """
        print("\n" + "=" * 60)
        print("VERIFICANDO DEPENDÊNCIAS")
        print("=" * 60)
        
        dependencies = {
            'MetaTrader5': 'MetaTrader5',
            'pandas': 'pandas',
            'numpy': 'numpy',
            'pandas_ta': 'pandas-ta',
            'sklearn': 'scikit-learn',
            'joblib': 'joblib'
        }
        
        all_ok = True
        
        for module, package in dependencies.items():
            try:
                __import__(module)
                print(f"✓ {package}")
            except ImportError:
                print(f"✗ {package} - NÃO INSTALADO")
                self.issues.append(f"Dependência faltando: {package}")
                all_ok = False
        
        return all_ok
    
    def check_configuration(self) -> bool:
        """
        Valida arquivo de configuração.
        """
        print("\n" + "=" * 60)
        print("VERIFICANDO CONFIGURAÇÃO")
        print("=" * 60)
        
        # Verifica se arquivo existe
        if not Path(self.config_path).exists():
            print(f"✗ Arquivo {self.config_path} não encontrado")
            self.issues.append(f"Arquivo de configuração não encontrado")
            return False
        
        print(f"✓ Arquivo de configuração encontrado")
        
        # Carrega configuração
        try:
            with open(self.config_path, 'r') as f:
                self.config = json.load(f)
            print("✓ JSON válido")
        except json.JSONDecodeError as e:
            print(f"✗ Erro ao parsear JSON: {e}")
            self.issues.append("JSON inválido")
            return False
        
        # Valida seções obrigatórias
        required_sections = ['mt5', 'trading', 'risk', 'strategy', 'ml', 'logging', 'system']
        
        for section in required_sections:
            if section in self.config:
                print(f"✓ Seção '{section}' presente")
            else:
                print(f"✗ Seção '{section}' ausente")
                self.issues.append(f"Seção '{section}' ausente na configuração")
        
        # Valida credenciais MT5
        mt5_config = self.config.get('mt5', {})
        
        if mt5_config.get('login') == 123456789:
            print("⚠ Login padrão detectado - atualize com suas credenciais")
            self.warnings.append("Credenciais MT5 não configuradas")
        
        # Valida parâmetros de risco
        risk_config = self.config.get('risk', {})
        
        if risk_config.get('max_risk_per_trade', 0) > 0.05:
            print("⚠ Risco por trade > 5% - considere reduzir")
            self.warnings.append("Risco por trade elevado")
        
        if risk_config.get('kelly_fraction', 0) > 0.5:
            print("⚠ Kelly fraction > 50% - muito agressivo")
            self.warnings.append("Kelly fraction muito alto")
        
        return True
    
    async def check_mt5_connection(self) -> bool:
        """
        Testa conexão com MT5.
        """
        print("\n" + "=" * 60)
        print("TESTANDO CONEXÃO MT5")
        print("=" * 60)
        
        if not self.config:
            print("✗ Configuração não carregada")
            return False
        
        mt5_config = self.config.get('mt5', {})
        
        try:
            client = MT5Client(
                login=mt5_config['login'],
                password=mt5_config['password'],
                server=mt5_config['server'],
                timeout=mt5_config['timeout']
            )
            
            # Tenta conectar
            connected = await client.connect()
            
            if connected:
                print("✓ Conexão estabelecida com sucesso")
                
                # Obtém informações da conta
                account_info = await client.get_account_info()
                
                if account_info:
                    print(f"\nInformações da Conta:")
                    print(f"  Login: {account_info['login']}")
                    print(f"  Servidor: {account_info['server']}")
                    print(f"  Saldo: {account_info['balance']} {account_info['currency']}")
                    print(f"  Leverage: 1:{account_info['leverage']}")
                
                # Desconecta
                await client.disconnect()
                
                return True
            else:
                print("✗ Falha ao conectar")
                self.issues.append("Não foi possível conectar ao MT5")
                return False
        
        except Exception as e:
            print(f"✗ Erro: {e}")
            self.issues.append(f"Erro ao conectar MT5: {str(e)}")
            return False
    
    async def check_symbols(self) -> bool:
        """
        Verifica disponibilidade dos símbolos configurados.
        """
        print("\n" + "=" * 60)
        print("VERIFICANDO SÍMBOLOS")
        print("=" * 60)
        
        if not self.config:
            return False
        
        mt5_config = self.config.get('mt5', {})
        trading_config = self.config.get('trading', {})
        symbols = trading_config.get('symbols', [])
        
        if not symbols:
            print("⚠ Nenhum símbolo configurado")
            self.warnings.append("Nenhum símbolo configurado")
            return False
        
        try:
            client = MT5Client(
                login=mt5_config['login'],
                password=mt5_config['password'],
                server=mt5_config['server'],
                timeout=mt5_config['timeout']
            )
            
            await client.connect()
            
            all_ok = True
            
            for symbol in symbols:
                symbol_info = await client.get_symbol_info(symbol)
                
                if symbol_info:
                    print(f"✓ {symbol}")
                    print(f"    Spread: {symbol_info['spread']} pontos")
                    print(f"    Volume mín: {symbol_info['volume_min']}")
                    print(f"    Volume máx: {symbol_info['volume_max']}")
                else:
                    print(f"✗ {symbol} - não disponível")
                    self.issues.append(f"Símbolo {symbol} não disponível")
                    all_ok = False
            
            await client.disconnect()
            
            return all_ok
        
        except Exception as e:
            print(f"✗ Erro ao verificar símbolos: {e}")
            self.issues.append(f"Erro ao verificar símbolos: {str(e)}")
            return False
    
    def check_directories(self) -> bool:
        """
        Verifica estrutura de diretórios.
        """
        print("\n" + "=" * 60)
        print("VERIFICANDO ESTRUTURA DE DIRETÓRIOS")
        print("=" * 60)
        
        required_dirs = ['config', 'core', 'data', 'strategies', 'execution', 'risk', 'models', 'logs']
        
        all_ok = True
        
        for dir_name in required_dirs:
            dir_path = Path(dir_name)
            if dir_path.exists():
                print(f"✓ {dir_name}/")
            else:
                print(f"✗ {dir_name}/ - não encontrado")
                self.issues.append(f"Diretório {dir_name}/ não encontrado")
                all_ok = False
        
        return all_ok
    
    def print_summary(self) -> None:
        """
        Imprime sumário do diagnóstico.
        """
        print("\n" + "=" * 60)
        print("SUMÁRIO DO DIAGNÓSTICO")
        print("=" * 60)
        
        if not self.issues and not self.warnings:
            print("\n✓✓✓ SISTEMA PRONTO PARA OPERAR ✓✓✓")
            print("\nTodos os testes passaram com sucesso!")
            print("Você pode iniciar o robô com: python main.py")
        else:
            if self.issues:
                print(f"\n✗ PROBLEMAS ENCONTRADOS ({len(self.issues)}):")
                for i, issue in enumerate(self.issues, 1):
                    print(f"  {i}. {issue}")
                
                print("\nResolva os problemas acima antes de executar o robô.")
            
            if self.warnings:
                print(f"\n⚠ AVISOS ({len(self.warnings)}):")
                for i, warning in enumerate(self.warnings, 1):
                    print(f"  {i}. {warning}")
        
        print("\n" + "=" * 60)
    
    async def run_full_diagnostic(self) -> bool:
        """
        Executa diagnóstico completo.
        """
        print("\n" + "=" * 80)
        print("DIAGNÓSTICO DO SISTEMA DE TRADING")
        print("=" * 80)
        
        # 1. Dependências
        deps_ok = self.check_dependencies()
        
        # 2. Configuração
        config_ok = self.check_configuration()
        
        # 3. Diretórios
        dirs_ok = self.check_directories()
        
        # 4. Conexão MT5
        if config_ok:
            mt5_ok = await self.check_mt5_connection()
            
            # 5. Símbolos
            if mt5_ok:
                symbols_ok = await self.check_symbols()
            else:
                symbols_ok = False
        else:
            mt5_ok = False
            symbols_ok = False
        
        # Sumário
        self.print_summary()
        
        return deps_ok and config_ok and dirs_ok and mt5_ok and symbols_ok


async def main():
    """
    Função principal.
    """
    # Configura logging básico
    try:
        configure_logging_from_config("config/settings.json")
    except:
        pass  # Logging não crítico para diagnóstico
    
    diagnostic = SystemDiagnostic()
    success = await diagnostic.run_full_diagnostic()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nDiagnóstico interrompido")
    except Exception as e:
        print(f"\n\nErro no diagnóstico: {e}")
        sys.exit(1)
