import os
import sys
import json
import asyncio
from pathlib import Path
from flask import Flask, render_template
from flask_cors import CORS

# 获取当前目录
current_dir = Path(os.getcwd())
print(current_dir)

# 导入必要的模块
from tagcall import function_call, get_system_prompt, global_registry
from clerk_agent.agents import TaskAgent, SkillAgent, WorkerAgent
from clerk_agent.tools import execute_shell_sync, read_file, write_file, execute_shell, modify_file
from clerk_agent.routes import register_routes
from clerk_agent.config import load_config

# 注册工具函数到 TagCall（只注册一次）
def register_tools():
    """注册工具函数到全局注册表"""
    if 'read_file' not in global_registry.get_all_functions():
        @function_call(prompt="读取文件内容", name="read_file")
        def read_file_tool(filepath: str):
            return read_file(filepath)

    if 'write_file' not in global_registry.get_all_functions():
        @function_call(prompt="写入内容到文件", name="write_file")
        def write_file_tool(filepath: str, content: str):
            return write_file(filepath, content)

    if 'modify_file' not in global_registry.get_all_functions():
        @function_call(prompt="""【文件修改工具】支持替换、插入、删除、追加等操作。
    1. **操作类型**：
       - "replace": 替换文本 (需要 old_text, new_text 参数)
       - "insert": 插入文本 (需要 position, content 参数，position  "start"/"end")可为行号或
       - "delete": 删除文本 (需要 target 参数，可为行号范围或文本内容)
       - "append": 追加文本 (需要 content 参数)
    2. **使用场景**：修改配置文件、更新代码、调整文档内容等
    3. **注意**：操作前建议先用 read_file 查看原内容""", name="modify_file")
        def modify_file_tool(filepath: str, operation: str, old_text:str="",new_text:str="",position:str="",content:str="",target:str="",add_newline:bool=True):
            # 构建关键字参数字典，只传递非空值
            kwargs = {}
            if old_text:
                kwargs['old_text'] = old_text
            if new_text:
                kwargs['new_text'] = new_text
            if position:
                kwargs['position'] = position
            if content:
                kwargs['content'] = content
            if target:
                kwargs['target'] = target
            # add_newline 参数需要特殊处理，因为它是 bool 类型
            if 'add_newline' in locals():
                kwargs['add_newline'] = add_newline
            return modify_file(filepath, operation, **kwargs)

    if 'execute_shell' not in global_registry.get_all_functions():
        @function_call(prompt="""【异步后台启动器】用于长耗时任务。
    1. **使用场景**：启动服务、安装大型包、跑模型、耗时超过 30 秒的脚本。
    2. **行为预期**：调用后会立即返回"已启动"和日志路径。不要等待结果返回，应直接告知用户任务已后台运行。
    3. **查看进度**：稍后可使用 `read_file` 读取返回的 `log_path` 来确认任务状态。
    4. **注意**：Windows 下无需手动加 start /B，工具底层已处理。""")
        def execute_shell_tool(command: str):
            return execute_shell(command)

    # --- 同步工具注册 ---
    if 'execute_shell_sync' not in global_registry.get_all_functions():
        @function_call(prompt="""【同步即时查询】用于短时间 (30s 内) 必须获取结果的任务。
    1. **使用场景**：`ls/dir` 看文件、`git status`、`pip list`、读取配置、检查进程等。
    2. **行为预期**：主进程会等待命令完成并直接返回 stdout 输出。
    3. **禁忌**：严禁执行会阻塞或长耗时的命令，否则会导致机器人卡死并触发超时强制中断。""")
        def execute_shell_sync_tool(command: str):
            return execute_shell_sync(command)
        
    # 新增：更新自我设定
    if 'update_self_profile' not in global_registry.get_all_functions():
        @function_call(prompt="更新 Clerk 自身的设定和工作空间信息", name="update_self_profile")
        def update_self_profile_tool(content: str):
            return update_self_profile(content)
    
    # 新增：更新用户画像
    if 'update_user_profile' not in global_registry.get_all_functions():
        @function_call(prompt="更新用户画像、偏好设置和个人信息", name="update_user_profile")
        def update_user_profile_tool(content: str):
            return update_user_profile(content)

    

def update_self_profile(content: str) -> str:
    """更新 self.md 文件"""
    self_file = current_dir / "self.md"
    with open(self_file, 'w', encoding='utf-8') as f:
        f.write(content)
    return f"自我设定已更新并保存到 {self_file}"

def update_user_profile(content: str) -> str:
    """更新 user.md 文件"""
    user_file = current_dir / "user.md"
    with open(user_file, 'w', encoding='utf-8') as f:
        f.write(content)
    return f"用户画像已更新并保存到 {user_file}"

# 创建 Flask
app = Flask(__name__, 
    static_folder=str(current_dir / 'webui'),
    static_url_path='',  # 将静态路径映射到根目录
    template_folder=str(current_dir / 'webui')
)
CORS(app)

# 注册工具
register_tools()

# 注册路由
register_routes(app)

def main():
    """启动 Flask WebUI"""
    print("🚀 Clerk Agent 3.0 WebUI 启动中...")
    print("=" * 50)
    print("🔧 已注册的工具函数:")
    for func_name in global_registry.get_all_functions().keys():
        print(f"   - {func_name}")
    
    print("\n📁 技能库状态:")
    skill_agent = SkillAgent()
    skills = skill_agent.list_skills()
    if skills:
        for skill in skills:
            print(f"   - {skill}")
    else:
        print("   (暂无技能)")
    
    print("\n🌐 WebUI 服务启动:")
    print("   访问地址：http://localhost:5002")
    print("   按 Ctrl+C 停止服务")
    
    # 启动 Flask 应用
    app.run(host='0.0.0.0', port=5002, debug=False)

if __name__ == "__main__":
    main()