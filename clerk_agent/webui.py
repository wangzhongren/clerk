import os
import sys
from pathlib import Path

# 添加当前目录到 Python 路径
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

# 尝试导入必要的模块
try:
    from tagcall import function_call, get_system_prompt, parse_function_calls, global_registry
    from clerk_agent.agents import TaskAgent, SkillAgent, WorkerAgent
    from clerk_agent.tools import read_file, write_file, execute_shell
except ImportError as e:
    print(f"❌ 导入错误: {e}")
    print("请确保 tagcall 目录与 clerk_agent 目录在同一级别")
    sys.exit(1)

# 注册工具函数到 TagCall
@function_call(prompt="读取工作空间内的文件内容", name="read_file")
def read_file_tool(filepath: str):
    return read_file(filepath)

@function_call(prompt="写入内容到工作空间内的文件", name="write_file")
def write_file_tool(filepath: str, content: str):
    return write_file(filepath, content)

@function_call(prompt="执行 Shell 命令（危险命令会被拦截）", name="execute_shell")
def execute_shell_tool(command: str):
    return execute_shell(command)

# 初始化代理
task_agent = TaskAgent()
skill_agent = SkillAgent()
worker_agent = WorkerAgent(task_agent, skill_agent)

def main():
    """启动 WebUI（简化版，实际项目中会使用 FastAPI/Flask）"""
    print("🚀 Clerk Agent 3.0 WebUI (简化版)")
    print("=" * 50)
    print("🔧 已注册的工具函数:")
    for func_name in global_registry.get_all_functions().keys():
        print(f"   - {func_name}")
    
    print("\n📁 技能库状态:")
    skills = skill_agent.list_skills()
    if skills:
        for skill in skills:
            print(f"   - {skill}")
    else:
        print("   (暂无技能)")
    
    print("\n📋 任务管理器已就绪")
    print("💡 提示: 实际 WebUI 应使用 FastAPI + Vue.js 实现完整界面")
    print("   当前文件仅用于验证系统集成")

if __name__ == "__main__":
    main()