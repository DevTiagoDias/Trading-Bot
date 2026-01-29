#!/usr/bin/env python3
"""
Setup and verification script for Trading Bot.
Checks dependencies, configuration, and MT5 connection.
"""

import sys
import os
from pathlib import Path


def check_python_version():
    """Check if Python version is adequate."""
    print("Checking Python version...")
    version = sys.version_info
    
    if version.major < 3 or (version.major == 3 and version.minor < 9):
        print(f"❌ Python 3.9+ required. Current: {version.major}.{version.minor}")
        return False
    
    print(f"✓ Python {version.major}.{version.minor}.{version.micro}")
    return True


def check_dependencies():
    """Check if all required packages are installed."""
    print("\nChecking dependencies...")
    
    required_packages = {
        'MetaTrader5': 'MetaTrader5',
        'pandas': 'pandas',
        'pandas_ta': 'pandas-ta',
        'requests': 'requests'
    }
    
    all_installed = True
    
    for package, pip_name in required_packages.items():
        try:
            __import__(package)
            print(f"✓ {pip_name}")
        except ImportError:
            print(f"❌ {pip_name} not installed")
            all_installed = False
    
    if not all_installed:
        print("\nInstall missing packages with:")
        print("pip install -r requirements.txt")
        return False
    
    return True


def check_configuration():
    """Check if configuration file exists and is valid."""
    print("\nChecking configuration...")
    
    config_path = Path(__file__).parent / 'config' / 'settings.json'
    
    if not config_path.exists():
        print(f"❌ Configuration file not found: {config_path}")
        return False
    
    try:
        import json
        with open(config_path, 'r') as f:
            config_data = json.load(f)
        
        # Check required sections
        required_sections = ['mt5', 'trading', 'risk', 'strategy']
        
        for section in required_sections:
            if section not in config_data:
                print(f"❌ Missing configuration section: {section}")
                return False
        
        # Check MT5 credentials
        if config_data['mt5']['login'] == 12345678:
            print("⚠️  Warning: Using default MT5 login. Please update settings.json")
        
        print("✓ Configuration file valid")
        return True
        
    except json.JSONDecodeError:
        print("❌ Invalid JSON in configuration file")
        return False
    except Exception as e:
        print(f"❌ Error reading configuration: {e}")
        return False


def check_mt5_installation():
    """Check if MT5 is properly installed."""
    print("\nChecking MetaTrader 5...")
    
    try:
        import MetaTrader5 as mt5
        
        if not mt5.initialize():
            error = mt5.last_error()
            print(f"⚠️  Could not initialize MT5: {error}")
            print("   Make sure MT5 is installed and running")
            return False
        
        terminal_info = mt5.terminal_info()
        if terminal_info:
            print(f"✓ MT5 Terminal: {terminal_info.company}")
            print(f"  Version: {terminal_info.build}")
            
            if not terminal_info.trade_allowed:
                print("⚠️  Warning: Algorithmic trading is disabled in MT5")
                print("   Enable it in Tools → Options → Expert Advisors")
        
        mt5.shutdown()
        return True
        
    except Exception as e:
        print(f"❌ Error checking MT5: {e}")
        return False


def create_directories():
    """Create required directories."""
    print("\nCreating directories...")
    
    directories = ['logs', 'tests']
    
    for directory in directories:
        dir_path = Path(__file__).parent / directory
        dir_path.mkdir(exist_ok=True)
        print(f"✓ {directory}/")
    
    return True


def main():
    """Run all checks."""
    print("=" * 60)
    print("Trading Bot Setup Verification")
    print("=" * 60)
    
    checks = [
        ("Python Version", check_python_version),
        ("Dependencies", check_dependencies),
        ("Configuration", check_configuration),
        ("MT5 Installation", check_mt5_installation),
        ("Directories", create_directories)
    ]
    
    all_passed = True
    
    for check_name, check_func in checks:
        try:
            if not check_func():
                all_passed = False
        except Exception as e:
            print(f"❌ {check_name} check failed: {e}")
            all_passed = False
    
    print("\n" + "=" * 60)
    
    if all_passed:
        print("✅ All checks passed! You can now run the bot:")
        print("   python main.py")
    else:
        print("❌ Some checks failed. Please fix the issues above.")
        return 1
    
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())