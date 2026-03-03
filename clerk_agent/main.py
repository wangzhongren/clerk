import os
import sys
from pathlib import Path

# 确保 tagcall 在路径中
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

# 创建必要的目录
dirs_to_create = ['workspace', 'skills', 'tasks', 'temp_scripts']
for dir_name in dirs_to_create:
    dir_path = current_dir / dir_name
    dir_path.mkdir(exist_ok=True)

print("✅ Clerk Agent 3.0 初始化完成")
print(f"📁 工作目录: {current_dir}")
print("📋 可用命令:")
print("   python -m clerk_agent.webui     # 启动 WebUI")
print("   python -m clerk_agent.cli       # 启动命令行界面")