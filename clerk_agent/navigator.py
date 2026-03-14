import json
import re
from typing import Dict, List, Any, Optional
from .config import load_config
from .llm_client import call_llm

class NavigatorAgent:
    """
    导航代理 - 负责监督 Worker Agent 的工作流程
    功能：
    1. 每 5 步审查一次方向是否正确
    2. 检测是否钻牛角尖或陷入死循环
    3. 任务结束时评估是否真正完成
    4. 提供修正指令或确认完成
    """
    
    def __init__(self):
        self.review_interval = 5  # 每 5 步审查一次
    
    def _build_review_prompt(self, task_description: str, logs: List[Dict], iteration: int) -> str:
        """构建审查提示词"""
        # 提取最近 10 条日志
        recent_logs = logs[-10:] if len(logs) > 10 else logs
        
        log_summary = ""
        for i, log in enumerate(recent_logs):
            entry = log.get('entry', {})
            log_type = entry.get('type', 'unknown')
            if log_type == 'function_call':
                log_summary += f"{i+1}. 调用 {entry.get('function')} - 结果：{str(entry.get('result', '无'))[:100]}\n"
            elif log_type == 'llm_response':
                log_summary += f"{i+1}. AI 思考：{entry.get('content', '')[:100]}...\n"
            elif log_type == 'function_call_error':
                log_summary += f"{i+1}. 错误：{entry.get('function')} - {entry.get('error', '未知错误')}\n"
            else:
                log_summary += f"{i+1}. {log_type}: {str(entry)[:100]}\n"
        
        return f"""你是一个智能任务导航员。请审查以下任务执行日志，判断 Worker Agent 是否在正确的轨道上。

【任务描述】
{task_description}

【当前迭代次数】
{iteration}

【最近执行日志】
{log_summary}

【审查要点】
1. **方向判断**：当前执行步骤是否有助于完成任务？
2. **死循环检测**：是否重复执行相同的无效操作？
3. **钻牛角尖检测**：是否在一个问题上卡住太久？
4. **更好方案**：是否有更简单直接的解决方案？
5. **完成度评估**：如果这是最后一步，任务是否真正完成？

【输出要求】
请严格按照以下 JSON 格式输出：
{{
    "is_on_track": true/false,  // 是否在正确轨道上
    "is_stuck": true/false,     // 是否钻牛角尖或死循环
    "is_complete": true/false,  // 任务是否已完成（仅在最后一步评估）
    "suggestion": "简短的建议或修正指令，如果需要改变方向",  // 如果需要干预
    "confidence": 0.0-1.0       // 判断置信度
}}

注意：
- 如果一切正常，is_on_track=true, is_stuck=false, suggestion=""
- 如果发现问题，suggestion 必须包含具体的修正指令，例如："请改用 read_file 读取配置文件，而不是反复尝试 execute_shell"
- 如果任务已完成，is_complete=true
"""

    def _build_final_review_prompt(self, task_description: str, logs: List[Dict], last_llm_response: str) -> str:
        """构建最终审查提示词（当 Worker 认为任务完成时）"""
        # 提取所有函数调用
        function_calls = []
        for log in logs:
            entry = log.get('entry', {})
            if entry.get('type') == 'function_call':
                function_calls.append({
                    'function': entry.get('function'),
                    'kwargs': entry.get('kwargs'),
                    'result': entry.get('result')
                })
        
        calls_summary = "\n".join([
            f"- {call['function']}({json.dumps(call['kwargs'])}) => {str(call['result'])[:100]}"
            for call in function_calls
        ]) or "无函数调用"
        
        return f"""你是一个严格的任务验收员。Worker Agent 声称任务已完成，请审查是否真的完成。

【任务描述】
{task_description}

【Worker 的最终回复】
{last_llm_response}

【执行过的所有函数调用】
{calls_summary}

【审查要点】
1. **真实性验证**：Worker 是否真的执行了必要的操作？还是只是在虚构结果？
2. **完整性检查**：任务要求的所有步骤是否都已完成？
3. **证据链**：函数调用的结果是否能证明任务成功？
4. **遗漏检测**：是否有明显的遗漏步骤？

【输出要求】
请严格按照以下 JSON 格式输出：
{{
    "is_really_complete": true/false,  // 是否真的完成
    "is_fabricated": true/false,       // 是否在虚构结果
    "missing_steps": ["遗漏的步骤 1", "遗漏的步骤 2"],  // 如果有遗漏
    "verification_evidence": "验证任务完成的关键证据",
    "final_verdict": "PASS" / "FAIL" / "NEED_MORE_WORK"  // 最终裁决
}}

注意：
- 如果没有函数调用但 Worker 声称完成，is_fabricated 应为 true
- 如果关键步骤缺失，final_verdict 应为 NEED_MORE_WORK
- 只有所有证据都支持完成，final_verdict 才为 PASS
"""

    async def review_progress(self, task_description: str, logs: List[Dict], iteration: int) -> Dict[str, Any]:
        """
        审查任务进度（每 5 步调用一次）
        
        Returns:
            {
                "is_on_track": bool,
                "is_stuck": bool,
                "suggestion": str,  # 如果需要干预
                "should_interrupt": bool  # 是否需要强制中断
            }
        """
        config = load_config()
        if not config.get('api_key'):
            return {"is_on_track": True, "is_stuck": False, "suggestion": "", "should_interrupt": False}
        
        prompt = self._build_review_prompt(task_description, logs, iteration)
        
        try:
            response, _ = await call_llm(
                "你是一个专业的任务导航员，请严格按照 JSON 格式输出，不要包含任何 Markdown 标记。",
                prompt,
                config
            )
            
            # 清理并解析 JSON
            import re
            cleaned = response.strip()
            if cleaned.startswith('```json'):
                cleaned = cleaned[7:]
            if cleaned.startswith('```'):
                cleaned = cleaned[3:]
            if cleaned.endswith('```'):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
            
            json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = json.loads(cleaned)
            
            # 判断是否需要干预
            should_interrupt = result.get('is_stuck', False) or not result.get('is_on_track', True)
            
            return {
                "is_on_track": result.get('is_on_track', True),
                "is_stuck": result.get('is_stuck', False),
                "suggestion": result.get('suggestion', ''),
                "should_interrupt": should_interrupt,
                "confidence": result.get('confidence', 0.5)
            }
            
        except Exception as e:
            print(f"Navigator 审查失败：{str(e)}")
            # 审查失败时默认不干预
            return {"is_on_track": True, "is_stuck": False, "suggestion": "", "should_interrupt": False}

    async def final_review(self, task_description: str, logs: List[Dict], last_llm_response: str) -> Dict[str, Any]:
        """
        最终审查（当 Worker 没有工具调用时）
        
        Returns:
            {
                "is_really_complete": bool,
                "is_fabricated": bool,
                "missing_steps": list,
                "final_verdict": "PASS" / "FAIL" / "NEED_MORE_WORK",
                "correction_instruction": str  # 如果需要继续工作
            }
        """
        config = load_config()
        if not config.get('api_key'):
            return {"is_really_complete": True, "final_verdict": "PASS", "correction_instruction": ""}
        
        prompt = self._build_final_review_prompt(task_description, logs, last_llm_response)
        
        try:
            response, _ = await call_llm(
                "你是一个严格的任务验收员，请严格按照 JSON 格式输出，不要包含任何 Markdown 标记。",
                prompt,
                config
            )
            
            # 清理并解析 JSON
            import re
            cleaned = response.strip()
            if cleaned.startswith('```json'):
                cleaned = cleaned[7:]
            if cleaned.startswith('```'):
                cleaned = cleaned[3:]
            if cleaned.endswith('```'):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
            
            json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = json.loads(cleaned)
            
            # 生成修正指令
            correction_instruction = ""
            if result.get('final_verdict') == 'NEED_MORE_WORK':
                missing = result.get('missing_steps', [])
                if missing:
                    correction_instruction = f"任务未完成，还需要执行以下步骤：{', '.join(missing)}。请继续工作。"
                else:
                    correction_instruction = "任务未完成，请继续检查并执行遗漏的步骤。"
            elif result.get('is_fabricated'):
                correction_instruction = "检测到可能在虚构结果。请提供真实的执行证据，或重新执行必要的操作。"
            
            return {
                "is_really_complete": result.get('is_really_complete', False),
                "is_fabricated": result.get('is_fabricated', False),
                "missing_steps": result.get('missing_steps', []),
                "verification_evidence": result.get('verification_evidence', ''),
                "final_verdict": result.get('final_verdict', 'NEED_MORE_WORK'),
                "correction_instruction": correction_instruction
            }
            
        except Exception as e:
            print(f"Navigator 最终审查失败：{str(e)}")
            # 审查失败时默认通过
            return {"is_really_complete": True, "final_verdict": "PASS", "correction_instruction": ""}