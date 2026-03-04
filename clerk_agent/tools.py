import os
import json
import subprocess
import re
from pathlib import Path
from typing import Dict, Any, List

def _is_dangerous_command(command: str) -> bool:
    """检查命令是否包含危险操作"""
    config_path = Path(__file__).parent / "config.yaml"
    dangerous_commands = []
    if config_path.exists():
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        dangerous_commands = config.get('dangerous_commands', [])
    
    command_lower = command.lower()
    for dangerous in dangerous_commands:
        if dangerous.lower() in command_lower:
            return True
    return False

def read_file(filepath: str) -> str:
    """
    读取文件内容（整个文件系统均可访问）
    
    Args:
        filepath: 文件的绝对路径或相对路径
        
    Returns:
        文件内容字符串
    """
    full_path = Path(filepath).resolve()
    
    if not full_path.exists():
        raise FileNotFoundError(f"文件 {filepath} 不存在")
    
    with open(full_path, 'r', encoding='utf-8') as f:
        return f.read()

def write_file(filepath: str, content: str) -> str:
    """
    写入文件内容（整个文件系统均可访问）
    
    Args:
        filepath: 文件的绝对路径或相对路径
        content: 要写入的内容
        
    Returns:
        操作结果描述
    """
    full_path = Path(filepath).resolve()
    
    # 创建父目录
    full_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return f"文件 {filepath} 写入成功"

def execute_shell(command: str) -> Dict[str, Any]:
    """
    执行 Shell 命令，并确保在独立的 Python 虚拟环境中运行
    """
    if _is_dangerous_command(command):
        return {
            "stdout": "",
            "stderr": f"危险命令被拦截: {command}。请在 WebUI 中手动授权执行。",
            "returncode": -1,
            "requires_approval": True
        }

    # 1. 确保虚拟环境存在
    venv_path = os.path.join(os.getcwd(), "scripts", "task_env")
    if not os.path.exists(venv_path):
        subprocess.run(["python", "-m", "venv", venv_path])
        
    # 2. 获取当前环境变量并注入虚拟环境路径
    # 这一步是关键：让 Shell 优先识别虚拟环境的 bin/Scripts 目录
    env = os.environ.copy()
    venv_bin = os.path.join(venv_path, "bin") if os.name != 'nt' else os.path.join(venv_path, "Scripts")
    env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
    env["VIRTUAL_ENV"] = venv_path  # 某些工具需要此变量来识别 venv

    try:
        result = subprocess.run(
            command,
            shell=True,
            env=env,            # 【核心修改】传入修改后的环境变量
            encoding='utf-8',
            capture_output=True,
            text=True,
            timeout=300          # 遵守 300 秒超时限制
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": "命令执行超时 (300 秒)",
            "returncode": -1
        }