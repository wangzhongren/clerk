import os
import yaml
from pathlib import Path

# 获取当前目录
current_dir = Path(os.getcwd())

def load_config():
    """加载配置文件"""
    config_path = current_dir / 'config.yaml'
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    return {}

def save_config(config_data):
    """保存配置文件"""
    config_path = current_dir / 'config.yaml'
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(config_data, f, allow_unicode=True, default_flow_style=False)