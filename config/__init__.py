"""
Configuration loader module for Trading Bot.
Handles loading and validation of settings from JSON file.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict


class Config:
    """Singleton configuration loader with validation."""
    
    _instance = None
    _config: Dict[str, Any] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._config:
            self._load_config()
    
    def _load_config(self) -> None:
        """Load configuration from settings.json file."""
        config_path = Path(__file__).parent / "settings.json"
        
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            self._config = json.load(f)
        
        self._validate_config()
    
    def _validate_config(self) -> None:
        """Validate critical configuration parameters."""
        required_sections = ['mt5', 'trading', 'risk', 'strategy']
        
        for section in required_sections:
            if section not in self._config:
                raise ValueError(f"Missing required configuration section: {section}")
        
        # Validate risk parameters
        risk = self._config['risk']
        if not 0 < risk['risk_per_trade_percent'] <= 5:
            raise ValueError("risk_per_trade_percent must be between 0 and 5")
        
        if not 0 < risk['max_daily_drawdown_percent'] <= 10:
            raise ValueError("max_daily_drawdown_percent must be between 0 and 10")
        
        # Validate trading parameters
        trading = self._config['trading']
        if not trading['symbols']:
            raise ValueError("At least one symbol must be specified")
    
    def get(self, *keys: str, default: Any = None) -> Any:
        """
        Get configuration value by nested keys.
        
        Args:
            *keys: Nested keys to access (e.g., 'mt5', 'login')
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        value = self._config
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return default
            else:
                return default
        return value
    
    def get_all(self) -> Dict[str, Any]:
        """Get all configuration as dictionary."""
        return self._config.copy()
    
    def reload(self) -> None:
        """Reload configuration from file."""
        self._config.clear()
        self._load_config()


# Global config instance
config = Config()