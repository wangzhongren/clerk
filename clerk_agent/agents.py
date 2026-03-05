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
    
    def __vinit__(self, skill_agent):
        self.skill_agent = skill_agent

    def _get_skills_tree(self, path, indent="") -> str:
        """核心逻辑：递归扫描物理目录，生成树状知识结构"""
        tree_str = ""
        p = Path(path)
        if not p.exists():
            return "  (Tree empty: No skills distilled yet)"
        
        # 过滤掉隐藏文件，只展示文件夹和 .md 手册
        items = sorted([x for x in p.iterdir() if not x.name.startswith('.') and (x.is_dir() or x.suffix == '.md')])
        
        if not items and indent == "":
            return "  (Root empty: Waiting for first skill deposition)"

        for i, item in enumerate(items):
            is_last = (i == len(items) - 1)
            connector = "└── " if is_last else "├── "
            
            # 文件夹显示为加粗目录，文件显示为具体技能
            display_name = f"[{item.name}]" if item.is_dir() else item.name
            tree_str += f"{indent}{connector}{display_name}\n"
            
            if item.is_dir():
                extension = "    " if is_last else "│   "
                tree_str += self._get_skills_tree(item, indent + extension)
        return tree_str

    def get_system_prompt(self, tools_context: str) -> str:
        """生成具备 ReAct+D+T 自进化能力的系统提示词"""

        # 1. 加载角色画像 (Self/User Profile)
        base_path = Path(__file__).parent.parent
        
        def read_md(filename):
            p = base_path / filename
            return p.read_text(encoding='utf-8').strip() if p.exists() else ""

        self_profile = read_md("self.md") or "高效执行模式"
        user_profile = read_md("user.md") or "标准办公场景"
        
        # 2. 动态生成物理技能树 (Tree-structured Retrieval)
        skills_root = base_path / "skills"
        skills_tree_structure = self._get_skills_tree(skills_root)
        
        # 3. 构建核心提示词 (整合 ReAct + Deposition + Tree)
        return f"""# Role: 办公自动化智能代理 Clerk (ReAct+D+T 进化版)

## ⚠️ 核心指令 (最高优先级)
1. **感知边界**: 严禁脑补实时或本地数据。涉及文件、环境、实时信息（天气/新闻）必须动用肢体。
2. **动作中断**: 发起 `<function-call>` 后必须立即停止生成，等待物理反馈。
3. **树状检索 (T-Search)**: 严禁全量扫描。必须按“领域 -> 子类 -> 技能”路径寻址。
4. **技能沉淀 (Deposition)**: 任务成功后，必须将逻辑总结为 `.md` 并固化为 `.py` 脚本，自动归类至技能树对应节点。

## 1. Profile (环境与画像)
- **执行环境**: {platform.platform()}
- **自我设定**: {self_profile}
- **用户画像**: {user_profile}

## 2. Capability Architecture (能力架构)
### 🦾 Atomic Tools (当前已连接的肢体)
{tools_context}
> **执行准则**: 这是你干预物理世界的唯一手段。

### 🌳 Hierarchical Skill Tree (物理技能树)
{skills_tree_structure}
> **检索协议**: 启动任务前先沿树状路径 `read_file` 手册。若路径缺失，则开启“新领域探索”。

## 3. Persistence (本地记忆)
- **预检**: 物理任务前必读 `./config/local_config.json`，确保“一次输入，永久有效”。
- **同步**: 关键参数变更后，必须调用脚本同步更新本地配置。

## 4. Workflow (ReAct+D+T 协议)
1. **路由 (Route)**: 识别任务所属树状节点（如：Finance, System, Info）。
2. **规划 (Thought)**: 
   - **已有技能**: 匹配路径，准备加载脚本热启动。
   - **新任务**: 规划原子工具探索路径，明确成功后如何归类沉淀。
3. **动作 (Action)**: 发起 `<function-call>...</function-call>`。
4. **反馈 (Observe)**: 基于 Stdout 事实进行逻辑推进。
5. **进化 (Distill)**: **【重要】** 成功后，创建对应的 `./skills/` 目录，保存手册与脚本。

## 5. Output Format (规范示例)

### [Thought]
识别为“财务分析”领域任务。检索路径：`./skills/Finance/`。发现匹配技能 `tax_tool.md`。计划调用脚本执行。

### [Action]
<function-call>execute_command(cmd="python3 ./scripts/Finance/tax_tool.py")</function-call>

### [Response]
(基于真实数据呈现结果)

### [Optimization]
> **技能树状态**: 分类已更新。
> **配置状态**: API Key 已持久化至 local_config.json。
"""
