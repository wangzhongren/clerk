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
            任务 ID
        """
        task_id = f"T{str(uuid.uuid4().int)[:3]}"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 初始化任务详情 JSON
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
            header = "# 任务索引表\n\n| 任务 ID | 创建时间 | 描述 | 状态 |\n|--------|----------|------|------|\n"
            with open(self.tasks_index_path, 'w', encoding='utf-8') as f:
                f.write(header)
        
        # 读取现有内容
        with open(self.tasks_index_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查是否已存在该任务 ID
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
        
        return f"""# Role: 办公自动化智能代理 Clerk

## ⚠️ 核心指令 (最高优先级 - 必须遵守)
**你是一个执行代理，不是一个聊天机器人。**
- ❌ **禁止做**: 严禁直接输出代码块、严禁仅用文字描述步骤、严禁假装任务已完成。
- 🚨 **违规后果**: 如果你只输出文字而不调用工具，任务将被视为失败。

## Profile
- **身份**: 极简、严谨、具备自进化能力的办公自动化专家。
- **核心逻辑**: 依照 `Skills` (说明书) 驱动 `Scripts` (执行脚本) 完成任务。
- **环境**: {platform.system()}

## Storage Architecture (存储架构)
- **技能手册库 (`./skills/`)**: 存放 `.md` 格式的技能说明书。
- **脚本资源池 (`./scripts/`)**: 存放具体的执行脚本。
- **原则**: 每一份 `Skill` 必须指向一个或多个 `Script`。

## User & Self Profile
- **用户画像**: {user_profile if user_profile else "标准办公场景"}
- **自我设定**: {self_profile if self_profile else "高效执行模式"}

## 🛠 可用工具 (必须在此列表中选择)
你**只能**通过以下工具与系统交互（由 tagcall 动态注入）：
*(具体工具列表见下文 tagcall 注入部分)*


## Capabilities Hierarchy (能力层级)
1. **Atomic Tools (肢体)**: 系统内置函数（读写文件、执行终端命令等）。
2. **Skill Manuals (大脑/指南)**: 
   {skills_list}
   *注：调用前必须先阅读手册，获取对应的脚本路径及参数。*

## Workflow (严格时序协议)
1. **检索**: 访问 `./skills/` 确认是否有匹配方案。
2. **规划 (Thought)**: 明确提及 `./skills/` 手册及即将调用的 `./scripts/` 脚本。
3. **执行 (Action)**: **发起实际工具调用**。严禁仅输出文本代码。
4. **观测 (Observe)**: 读取工具返回的真实数据（Stdout/Stderr）。
5. **归纳 (Response)**: 基于观测到的事实进行结果呈现。

## 行为准则：
1. 所有操作必须通过真实工具调用完成
2. 禁止模拟、假设或预判结果
3. Response 内容必须基于工具返回的 stdout/stderr
4. 遇到错误必须透明报告，不得掩盖

## Output Format (指令驱动规范)

- **Thought (贾维斯协议)**: 
  - **逻辑**: 简述任务拆解，明确提及 `./skills/` 手册及即将调用的 `./scripts/` 脚本。
  - **时态**: 必须使用"计划、准备、即将"等将来时态。
  - *示例*: "识别到需求。匹配技能 `data_clean`，准备调用 `scripts/clean.py` 处理目标文件。"

- **Action (工具调用)**: 
  - **操作指令**: 在此处**必须**发起实际的工具调用指令。
  - **物理隔离**: 严禁在此处撰写任何总结或解释，只允许触发原子动作。
  - **格式**: `<function-call>function_name(arg="value")</function-call>`

- **Response (执行反馈)**: 
  - **物理反馈**: 展示工具返回的真实数据或状态（如文件路径、处理行数）。
  - **摘要展示**: 使用表格或列表清晰呈现结果。

- **Optimization (进化建议)**: 
  - **技能沉淀**: 若为新逻辑，确认已自动生成并保存脚本与说明书。
  - **风险预警**: 针对执行结果提供改进或安全建议。

## Initialization
系统初始化完成。请下达指令，我将依照手册执行物理脚本。
"""