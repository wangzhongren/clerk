import os
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
import platform
from .tools import read_file, write_file, execute_shell


class TaskAgent:
    """任务管理器 - 负责维护 tasks.md 和 /tasks/ 目录"""
    
    def __init__(self):
        self.tasks_index_path = Path(__file__).parent / "tasks.md"
        self.tasks_dir = Path(__file__).parent / "tasks"
        self.tasks_dir.mkdir(exist_ok=True)
    
    def create_task(self, description: str) -> str:
        """
        创建新任务
        
        Args:
            description: 任务描述
            
        Returns:
            任务ID
        """
        task_id = f"T{str(uuid.uuid4().int)[:3]}"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 初始化任务详情JSON
        task_detail = {
            "id": task_id,
            "description": description,
            "created_at": timestamp,
            "status": "Pending",
            "logs": [],
            "result": None
        }
        
        task_file = self.tasks_dir / f"{task_id}.json"
        with open(task_file, 'w', encoding='utf-8') as f:
            json.dump(task_detail, f, ensure_ascii=False, indent=2)
        
        # 更新任务索引表
        self._update_tasks_index(task_id, timestamp, description, "Pending")
        
        return task_id
    
    def _update_tasks_index(self, task_id: str, timestamp: str, description: str, status: str):
        """更新 tasks.md 索引文件"""
        if not self.tasks_index_path.exists():
            header = "# 任务索引表\n\n| 任务ID | 创建时间 | 描述 | 状态 |\n|--------|----------|------|------|\n"
            with open(self.tasks_index_path, 'w', encoding='utf-8') as f:
                f.write(header)
        
        # 读取现有内容
        with open(self.tasks_index_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查是否已存在该任务ID
        if f"| {task_id} |" in content:
            # 更新现有行
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if f"| {task_id} |" in line:
                    lines[i] = f"| {task_id} | {timestamp} | {description} | {status} |"
                    break
            content = '\n'.join(lines)
        else:
            # 添加新行
            new_line = f"| {task_id} | {timestamp} | {description} | {status} |"
            content = content.rstrip() + '\n' + new_line
        
        with open(self.tasks_index_path, 'w', encoding='utf-8') as f:
            f.write(content)
    
    def log_to_task(self, task_id: str, log_entry: Dict[str, Any]):
        """向任务日志追加条目"""
        task_file = self.tasks_dir / f"{task_id}.json"
        if not task_file.exists():
            raise FileNotFoundError(f"任务 {task_id} 不存在")
        
        with open(task_file, 'r', encoding='utf-8') as f:
            task_data = json.load(f)
        
        task_data["logs"].append({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "entry": log_entry
        })
        
        with open(task_file, 'w', encoding='utf-8') as f:
            json.dump(task_data, f, ensure_ascii=False, indent=2)
    
    def complete_task(self, task_id: str, result: Any, status: str = "Success"):
        """完成任务"""
        task_file = self.tasks_dir / f"{task_id}.json"
        if not task_file.exists():
            raise FileNotFoundError(f"任务 {task_id} 不存在")
        
        with open(task_file, 'r', encoding='utf-8') as f:
            task_data = json.load(f)
        
        task_data["status"] = status
        task_data["result"] = result
        task_data["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        with open(task_file, 'w', encoding='utf-8') as f:
            json.dump(task_data, f, ensure_ascii=False, indent=2)
        
        # 更新索引表
        self._update_tasks_index(
            task_id, 
            task_data["created_at"], 
            task_data["description"], 
            status
        )


class SkillAgent:
    """技能管理器 - 负责维护 /skills/ 目录"""
    
    def __init__(self):
        self.skills_dir = Path(__file__).parent.parent / "skills"
        self.skills_dir.mkdir(exist_ok=True)
    
    def list_skills(self) -> List[str]:
        """列出所有可用技能（返回文件名列表，不含扩展名）"""
        skills = []
        for skill_file in self.skills_dir.glob("*.md"):
            skills.append(skill_file.stem)
        return sorted(skills)
    
    def read_skill(self, skill_name: str) -> str:
        """读取指定技能的详细内容"""
        skill_file = self.skills_dir / f"{skill_name}.md"
        if not skill_file.exists():
            raise FileNotFoundError(f"技能 {skill_name} 不存在")
        
        with open(skill_file, 'r', encoding='utf-8') as f:
            return f.read()
    
    def save_skill(self, skill_name: str, content: str):
        """保存或更新技能"""
        skill_file = self.skills_dir / f"{skill_name}.md"
        with open(skill_file, 'w', encoding='utf-8') as f:
            f.write(content)
    
    def delete_skill(self, skill_name: str):
        """删除技能"""
        skill_file = self.skills_dir / f"{skill_name}.md"
        if skill_file.exists():
            skill_file.unlink()


class WorkerAgent:
    """核心执行代理 - 负责 ReAct 思考和工具调用"""
    
    def __init__(self, task_agent: TaskAgent, skill_agent: SkillAgent):
        self.task_agent = task_agent
        self.skill_agent = skill_agent
    
    def get_system_prompt(self) -> str:
        """生成 Worker Agent 的系统提示词"""
        # 读取 self.md 内容
        self_md_path = Path(__file__).parent.parent / "self.md"
        self_profile = ""
        if self_md_path.exists():
            with open(self_md_path, 'r', encoding='utf-8') as f:
                self_profile = f.read().strip()
        
        # 读取 user.md 内容  
        user_md_path = Path(__file__).parent.parent / "user.md"
        user_profile = ""
        if user_md_path.exists():
            with open(user_md_path, 'r', encoding='utf-8') as f:
                user_profile = f.read().strip()
        
        available_skills = self.skill_agent.list_skills()
        skills_list = "\n".join([f"- {skill}" for skill in available_skills]) if available_skills else "无可用技能"
        
        return f"""# Role: 办公自动化智能助手 Clerk

## Profile
- **身份**: 专业、高效、安全的办公自动化执行代理。
- **目标**: 准确理解用户意图，通过 Shell/Python 组合调用完成办公任务，并沉淀可复用技能。
- **环境**: {platform.system()}

## Self Profile (Clerk 自身设定)
{self_profile if self_profile else "暂无自我设定"}

## User Profile (用户画像)
{user_profile if user_profile else "暂无用户画像"}

## Constraints & Safety
1. **安全红线**: 严禁执行 destructive 命令 (如 `rm -rf /`, `format`, `del /f` 等)。涉及文件删除/修改需二次确认。
2. **诚实原则**: 执行结果必须如实报告，禁止虚构成功状态或输出内容。
3. **依赖管理**: 执行 Python 脚本前，必须检查并安装所需库 (通过 Shell `pip install`)。
4. **路径规范**: 所有生成的脚本必须保存至 `./scripts/` 目录，文件名需具备语义化 (如 `task_YYYYMMDD_description.py`)。

## Skills Context
当前可用技能列表：
{skills_list}
*注：若任务涉及复杂逻辑，优先检索上述技能；若无匹配，则新建脚本。*

## Workflow
1. **需求分析**: 拆解用户任务，判断是否需要调用现有技能或新建脚本。
2. **方案规划**: 
   - 若需新脚本：设计逻辑 -> 检查依赖 -> 规划文件路径。
   - 若需现有技能：调用 Skill Agent 获取详情。
3. **代码执行**:
   - 第一步：通过 Shell 工具将 Python 代码写入 `./scripts/` 本地文件。
   - 第二步：通过 Shell 工具执行该脚本 (确保环境激活)。
   - 第三步：捕获 stdout/stderr，判断执行状态。
4. **结果反馈**: 返回执行摘要、关键输出及潜在风险。
5. **技能沉淀**: 
   - 任务成功后，评估脚本的通用性。
   - 若具备复用价值，主动询问用户是否注册为新技能。
   - 若用户确认，生成 Markdown 文档 (文件名：`skill_语义化名称.md`)，内容包含：脚本路径、调用参数、功能描述、依赖项。
6. **日志记录**: 调用 Task Agent 记录本次操作日志。

## Output Format
- **思考过程**: 简要说明执行计划 (Thought)。
- **执行命令**: 明确展示使用的 Shell/Python 命令。
- **执行结果**: 清晰展示成功/失败状态及输出。
- **后续建议**: 针对结果的下一步操作建议或技能保存询问。

## Initialization
现在，请等待用户输入任务，并严格按照上述 Workflow 执行。
"""