import locale
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

import os
import subprocess
import sys
import uuid
import locale
import time
from typing import Dict, Any

def execute_shell(command: str) -> Dict[str, Any]:
    """
    跨平台异步执行 Shell 命令，不阻塞主任务，并将输出重定向至本地日志。
    """
    # 1. 安全检查 (假设你已有该函数实现)
    # if _is_dangerous_command(command):
    #     return {"stdout": "", "stderr": "危险命令被拦截", "returncode": -1}

    # 2. 虚拟环境准备
    venv_path = os.path.join(os.getcwd(), "scripts", "task_env")
    if not os.path.exists(venv_path):
        subprocess.run([sys.executable, "-m", "venv", venv_path], check=False)
        
    env = os.environ.copy()
    venv_bin = os.path.join(venv_path, "bin") if os.name != 'nt' else os.path.join(venv_path, "Scripts")
    env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
    env["VIRTUAL_ENV"] = venv_path 
    env["PYTHONUNBUFFERED"] = "1"
    
    current_locale_encoding = locale.getpreferredencoding()

    # 3. 生成唯一的日志路径，用于存储后台输出
    log_id = str(uuid.uuid4())[:8]
    log_dir = os.path.join(os.getcwd(), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"task_{log_id}.log")

    try:
        # 打开日志文件准备写入
        # 使用 'a' 模式防止意外覆盖，buffering=1 实现行缓冲
        log_handle = open(log_file, "a", encoding=current_locale_encoding, errors='replace')

        # 4. 根据平台设置启动参数
        popen_kwargs = {
            "shell": True,
            "env": env,
            "stdout": log_handle,
            "stderr": subprocess.STDOUT, # 合并错误到输出
            "close_fds": True,
            "text": True
        }

        if os.name == 'nt':
            # Windows 核心：CREATE_NEW_PROCESS_GROUP 允许独立生存
            # DETACHED_PROCESS 确保没有黑窗口且不绑定父进程控制台
            # 解决 start /B 伪阻塞的关键
            popen_kwargs["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP | 
                0x00000008 # DETACHED_PROCESS 标志位
            )
        else:
            # Linux/macOS 核心：创建新会话/进程组，防止父进程退出时子进程被杀
            popen_kwargs["preexec_fn"] = os.setpgrp

        # 5. 启动进程 (非阻塞)
        process = subprocess.Popen(command, **popen_kwargs)

        # 这里做一个极短的检查（3），确认程序是否启动即崩溃
        time.sleep(5)
        ret_code = process.poll()

        if ret_code is not None and ret_code != 0:
            # 如果瞬时报错，读取日志返回错误
            log_handle.close()
            with open(log_file, "r", encoding=current_locale_encoding) as f:
                content = f.read()
            return {
                "stdout": content,
                "stderr": f"启动后立即退出，错误码: {ret_code}",
                "returncode": ret_code
            }

        # 6. 成功启动，立即返回
        return {
            "stdout": f"任务已在后台启动。\nPID: {process.pid}\n日志路径: {log_file}\n提示：请后续通过读取该日志文件查看执行进度。",
            "stderr": "",
            "returncode": 0,
            "log_path": log_file,
            "pid": process.pid
        }

    except Exception as e:
        return {
            "stdout": "",
            "stderr": f"后台启动失败: {str(e)}",
            "returncode": -1
        }

import os
import subprocess
import sys
import locale
from typing import Dict, Any

def execute_shell_sync(command: str, timeout: int = 30) -> Dict[str, Any]:
    """
    同步执行 Shell 命令，适用于能快速返回结果的操作（如查看目录、读取状态）。
    """
    # 环境配置逻辑（与异步版本保持一致）
    venv_path = os.path.join(os.getcwd(), "scripts", "task_env")
    if not os.path.exists(venv_path):
        subprocess.run([sys.executable, "-m", "venv", venv_path], check=False)
        
    env = os.environ.copy()
    venv_bin = os.path.join(venv_path, "bin") if os.name != 'nt' else os.path.join(venv_path, "Scripts")
    env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
    env["VIRTUAL_ENV"] = venv_path 
    env["PYTHONUNBUFFERED"] = "1"
    
    current_locale_encoding = locale.getpreferredencoding()

    try:
        # 同步执行核心逻辑
        result = subprocess.run(
            command,
            shell=True,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # 合并错误流
            text=True,
            encoding=current_locale_encoding,
            errors='replace',
            timeout=timeout  # 强制超时保护
        )
        
        return {
            "stdout": result.stdout if result.stdout else "",
            "returncode": result.returncode,
            "status": "completed"
        }
        
    except subprocess.TimeoutExpired as e:
        return {
            "stdout": e.stdout.decode(current_locale_encoding, 'replace') if e.stdout else "",
            "stderr": f"同步任务执行超时（限时 {timeout}s），请检查命令或改用异步工具执行。",
            "returncode": -1,
            "status": "timeout"
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": f"执行异常: {str(e)}",
            "returncode": -1,
            "status": "error"
        }