import locale
import os
import json
import platform
import subprocess
import re
from pathlib import Path
import threading
from typing import Dict, Any, List
import os
import subprocess
import sys
import uuid
import time
from typing import Dict, Any, List
from pathlib import Path
import psutil

# 全局变量：存储当前对话历史（由 routes.py 在执行前更新）
_current_conversation_history: List[Dict[str, Any]] = []

def set_current_conversation_history(history: List[Dict[str, Any]]):
    """设置当前对话历史（由 routes.py 调用）"""
    global _current_conversation_history
    _current_conversation_history = history

def get_current_conversation_history() -> List[Dict[str, Any]]:
    """获取当前对话历史"""
    return _current_conversation_history.copy()

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
    
    # 智能检测编码
    encodings_to_try = ['utf-8', 'gbk', 'latin-1']
    content = None
    detected_encoding = 'utf-8'
    
    for enc in encodings_to_try:
        try:
            with open(full_path, 'r', encoding=enc) as f:
                content = f.read()
            detected_encoding = enc
            break
        except UnicodeDecodeError:
            continue
    
    if content is None:
        raise ValueError(f"无法读取文件编码，尝试了：{encodings_to_try}")
    
    return f"content: (编码：{detected_encoding})\n" + content

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

def modify_file(filepath: str, operation: str, **kwargs) -> str:
    """
    修改文件内容（支持替换、插入、删除等操作）
    
    Args:
        filepath: 文件的绝对路径或相对路径
        operation: 操作类型，可选值：
                   - "replace": 替换文本 (需要 old_text, new_text 参数)
                   - "insert": 插入文本 (需要 position, content 参数，position 可为行号或 "start"/"end")
                   - "delete": 删除文本 (需要 target 参数，可为行号范围或文本内容)
                   - "append": 追加文本 (需要 content 参数)
        **kwargs: 操作相关的参数
                  - add_newline: bool, 是否在插入/追加内容后添加换行符 (默认 True)
        
    Returns:
        操作结果描述
    """
    full_path = Path(filepath).resolve()
    
    if not full_path.exists():
        raise FileNotFoundError(f"文件 {filepath} 不存在")
    
    # 智能检测编码
    encodings_to_try = ['utf-8', 'gbk', 'latin-1']
    content = None
    detected_encoding = 'utf-8'
    
    for enc in encodings_to_try:
        try:
            with open(full_path, 'r', encoding=enc) as f:
                content = f.read()
            detected_encoding = enc
            break
        except UnicodeDecodeError:
            continue
    
    if content is None:
        raise ValueError(f"无法读取文件编码，尝试了：{encodings_to_try}")
    
    original_content = content
    modified = False
    new_content = original_content
    
    if operation == "replace":
        old_text = kwargs.get('old_text', '')
        new_text = kwargs.get('new_text', '')
        if not old_text:
            raise ValueError("replace 操作需要 old_text 参数")
        
        # 直接字符串替换，保持原始换行符格式
        new_content = original_content.replace(old_text, new_text)
        if new_content != original_content:
            modified = True
        else:
            return f"未找到要替换的文本：{old_text}"
    
    elif operation == "insert":
        position = kwargs.get('position', 'end')
        insert_content = kwargs.get('content', '')
        add_newline = kwargs.get('add_newline', True)  # 新增参数，默认添加换行符
        
        if not insert_content:
            raise ValueError("insert 操作需要 content 参数")
        
        lines = original_content.splitlines(keepends=True)
        
        if position == "start":
            prefix = insert_content + ('\n' if add_newline else '')
            lines.insert(0, prefix)
            modified = True
        elif position == "end":
            prefix = insert_content + ('\n' if add_newline else '')
            lines.append(prefix)
            modified = True
        elif isinstance(position, int) or (isinstance(position, str) and position.isdigit()):
            # 行号插入（从 1 开始），支持字符串转整数
            pos_int = int(position) if isinstance(position, str) else position
            if 1 <= pos_int <= len(lines) + 1:
                prefix = insert_content + ('\n' if add_newline else '')
                lines.insert(pos_int - 1, prefix)
                modified = True
            else:
                raise ValueError(f"行号 {pos_int} 超出范围 (1-{len(lines)+1})")
        else:
            raise ValueError(f"无效的 position 参数：{position}")
        
        new_content = ''.join(lines)
    
    elif operation == "delete":
        target = kwargs.get('target', '')
        if not target:
            raise ValueError("delete 操作需要 target 参数")
        
        lines = original_content.splitlines(keepends=True)
        
        # 检查是否为行号范围（如 "1-5" 或 "3"）
        if re.match(r'^\d+(-\d+)?$', str(target)):
            if '-' in str(target):
                start, end = map(int, target.split('-'))
                del lines[start-1:end]
            else:
                line_num = int(target)
                if 1 <= line_num <= len(lines):
                    del lines[line_num-1]
            modified = True
        else:
            # 删除包含特定文本的行
            new_lines = [line for line in lines if target not in line]
            if len(new_lines) < len(lines):
                lines = new_lines
                modified = True
            else:
                return f"未找到包含文本 '{target}' 的行"
        
        new_content = ''.join(lines)
    
    elif operation == "append":
        append_content = kwargs.get('content', '')
        add_newline = kwargs.get('add_newline', True)
        
        if not append_content:
            raise ValueError("append 操作需要 content 参数")
        
        # 检查原文件末尾是否有换行符，如果没有则先添加一个，确保追加内容在新行
        if original_content and not original_content.endswith('\n'):
            new_content = original_content + '\n'
        else:
            new_content = original_content
        
        # 追加内容
        new_content += append_content + ('\n' if add_newline else '')
        modified = True
    
    else:
        raise ValueError(f"不支持的操作类型：{operation}。支持：replace, insert, delete, append")
    
    # 写入修改后的内容（保持原编码）
    if modified:
        with open(full_path, 'w', encoding=detected_encoding) as f:
            f.write(new_content)
        return f"文件 {filepath} 修改成功（操作：{operation}，编码：{detected_encoding}）"
    else:
        return f"文件 {filepath} 无需修改"


def execute_shell(command: str) -> Dict[str, Any]:
    """跨平台异步执行 Shell 命令，不阻塞主任务，输出重定向至日志。"""
    # 虚拟环境与环境编码准备
    venv_path = os.path.join(os.getcwd(), "scripts", "task_env")
    if not os.path.exists(venv_path):
        subprocess.run([sys.executable, "-m", "venv", venv_path], check=False)
        
    env = os.environ.copy()
    venv_bin = os.path.join(venv_path, "bin") if os.name != 'nt' else os.path.join(venv_path, "Scripts")
    env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
    env["VIRTUAL_ENV"] = venv_path 
    env["PYTHONUNBUFFERED"] = "1"
    
    current_locale_encoding = locale.getpreferredencoding()

    # 生成唯一日志
    log_id = str(uuid.uuid4())[:8]
    log_dir = os.path.join(os.getcwd(), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"task_{log_id}.log")

    try:
        log_handle = open(log_file, "a", encoding=current_locale_encoding, errors='replace')
        popen_kwargs = {
            "shell": True,
            "env": env,
            "stdout": log_handle,
            "stderr": subprocess.STDOUT,
            "close_fds": True,
            "text": True,
            "encoding": current_locale_encoding
        }

        if os.name == 'nt':
            popen_kwargs["creationflags"] = (subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008)
        else:
            popen_kwargs["preexec_fn"] = os.setpgrp

        process = subprocess.Popen(command, **popen_kwargs)

        # 极短检查，确认是否启动即挂
        time.sleep(5) 
        ret_code = process.poll()

        if ret_code is not None and ret_code != 0:
            log_handle.close()
            with open(log_file, "r", encoding=current_locale_encoding) as f:
                content = f.read()
            return {"stdout": content, "stderr": f"启动失败，错误码：{ret_code}", "returncode": ret_code}

        return {
            "stdout": f"✅ 任务已后台启动。PID: {process.pid}\n日志：{log_file}\n提示：请稍后读取该日志查看进度。",
            "stderr": "",
            "returncode": 0,
            "log_path": log_file,
            "pid": process.pid
        }
    except Exception as e:
        return {"stdout": "", "stderr": f"后台启动失败：{str(e)}", "returncode": -1}



def kill_proc_tree(pid):
    try:
        parent = psutil.Process(pid)
        # 递归杀掉所有子进程（相当于 /T）
        for child in parent.children(recursive=True):
            child.kill()
        parent.kill() # 强制杀掉自己（相当于 /F）
    except psutil.NoSuchProcess:
        pass

def execute_shell_sync(command: str, timeout: int = 10) -> Dict[str, Any]:
    venv_path = os.path.join(os.getcwd(), "scripts", "task_env")
    env = os.environ.copy()
    venv_bin = os.path.join(venv_path, "bin") if os.name != 'nt' else os.path.join(venv_path, "Scripts")
    env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
    
    current_locale_encoding = locale.getpreferredencoding()
    is_windows = platform.system() == "Windows"
    
    # 准备启动参数
    extra_args = {}
    if is_windows:
        # Windows 开启新进程组，配合 psutil 效果更好
        extra_args["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        extra_args["start_new_session"] = True

    proc = subprocess.Popen(
        command,
        shell=True,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding=current_locale_encoding,
        errors='replace',
        **extra_args
    )

    try:
        # --- 核心改动：直接在这里等结果，自带超时处理 ---
        stdout_data, _ = proc.communicate(timeout=timeout)
        
        return {
            "stdout": stdout_data or "",
            "returncode": proc.returncode,
            "status": "completed"
        }

    except subprocess.TimeoutExpired:
        # 1. 强杀进程树
        kill_proc_tree(proc.pid)
        
        # 2. 尝试读取已经输出到管道的内容（非常重要，否则你会丢失超前的信息）
        # TimeoutExpired 异常对象里包含了已经读到的 stdout
        # 但如果是通过 communicate 触发的，我们需要手动从管道捞一把
        try:
            # 再次清理剩余管道数据，避免僵尸输出
            stdout_data, _ = proc.communicate(timeout=1) 
        except:
            stdout_data = "任务超时且无法获取剩余输出"

        return {
            "stdout": stdout_data or "",
            "stderr": f"❌ 同步任务执行超时（限时 {timeout}s）。已强制清理。",
            "returncode": -1,
            "status": "timeout"
        }
        
    except Exception as e:
        kill_proc_tree(proc.pid)
        return {"stdout": "", "stderr": f"执行异常：{str(e)}", "returncode": -1, "status": "error"}