"""
Utilitário de Configuração
Carrega e valida configurações do sistema
"""

import json
import os
from typing import Dict, Any, Optional
from pathlib import Path


class ConfigurationError(Exception):
    """Erro de configuração"""
    pass


class ConfigLoader:
    """Carregador de configurações"""

    def __init__(self, config_path: str = "config/settings.json"):
        """
        Args:
            config_path: Caminho do arquivo de configuração
        """
        self.config_path = config_path
        self.config: Optional[Dict[str, Any]] = None

    def load(self) -> Dict[str, Any]:
        """
        Carrega configurações do arquivo
        
        Returns:
            Dicionário com configurações
            
        Raises:
            ConfigurationError: Se erro ao carregar
        """
        if not os.path.exists(self.config_path):
            raise ConfigurationError(f"Arquivo de configuração não encontrado: {self.config_path}")

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            
            self._validate_config()
            
            return self.config
            
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"Erro ao parsear JSON: {str(e)}")
        except Exception as e:
            raise ConfigurationError(f"Erro ao carregar configuração: {str(e)}")

    def _validate_config(self) -> None:
        """Valida configurações obrigatórias"""
        required_sections = ['mt5', 'trading', 'risk', 'strategy']
        
        for section in required_sections:
            if section not in self.config:
                raise ConfigurationError(f"Seção obrigatória ausente: {section}")

        # Valida MT5
        mt5_config = self.config['mt5']
        required_mt5 = ['login', 'password', 'server']
        for field in required_mt5:
            if field not in mt5_config:
                raise ConfigurationError(f"Campo MT5 obrigatório ausente: {field}")

        # Valida Trading
        trading_config = self.config['trading']
        if 'symbols' not in trading_config or len(trading_config['symbols']) == 0:
            raise ConfigurationError("Lista de símbolos vazia")

    def get(self, section: str, key: str, default: Any = None) -> Any:
        """
        Obtém valor de configuração
        
        Args:
            section: Seção da configuração
            key: Chave
            default: Valor padrão
            
        Returns:
            Valor da configuração
        """
        if self.config is None:
            raise ConfigurationError("Configuração não carregada")

        return self.config.get(section, {}).get(key, default)

    def get_section(self, section: str) -> Dict[str, Any]:
        """
        Obtém seção inteira de configuração
        
        Args:
            section: Nome da seção
            
        Returns:
            Dicionário com configurações da seção
        """
        if self.config is None:
            raise ConfigurationError("Configuração não carregada")

        if section not in self.config:
            raise ConfigurationError(f"Seção não encontrada: {section}")

        return self.config[section]

    def save(self, config_path: Optional[str] = None) -> None:
        """
        Salva configurações
        
        Args:
            config_path: Caminho alternativo (opcional)
        """
        if self.config is None:
            raise ConfigurationError("Nenhuma configuração para salvar")

        path = config_path or self.config_path
        
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            raise ConfigurationError(f"Erro ao salvar configuração: {str(e)}")


def load_config(config_path: str = "config/settings.json") -> Dict[str, Any]:
    """
    Função helper para carregar configuração
    
    Args:
        config_path: Caminho do arquivo
        
    Returns:
        Dicionário com configurações
    """
    loader = ConfigLoader(config_path)
    return loader.load()
