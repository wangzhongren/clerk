import json
import asyncio
import os
from flask import render_template, request, jsonify, Response, stream_with_context
from .config import load_config, save_config
from .llm_client import call_llm_stream, call_llm
from .agents import TaskAgent, SkillAgent, WorkerAgent
from tagcall import function_call, get_system_prompt, parse_function_calls, global_registry

# 初始化代理
task_agent = TaskAgent()
skill_agent = SkillAgent()
worker_agent = WorkerAgent(task_agent, skill_agent)

def register_routes(app):
    """注册所有路由"""
    
    @app.route('/')
    def index():
        """主页面"""
        return render_template('index.html')

    @app.route('/api/skills')
    def get_skills():
        """获取所有技能列表"""
        try:
            skills = skill_agent.list_skills()
            return jsonify({"skills": skills})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/skills/<skill_name>')
    def get_skill_content(skill_name):
        """获取指定技能的详细内容"""
        try:
            content = skill_agent.read_skill(skill_name)
            return jsonify({"content": content})
        except FileNotFoundError:
            return jsonify({"error": f"技能 {skill_name} 不存在"}), 404
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/skills', methods=['POST'])
    def save_skill():
        """保存或更新技能"""
        try:
            data = request.json
            skill_name = data.get('name')
            content = data.get('content')
            
            if not skill_name or not content:
                return jsonify({"error": "缺少技能名称或内容"}), 400
            
            skill_agent.save_skill(skill_name, content)
            return jsonify({"message": f"技能 {skill_name} 保存成功"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/skills/<skill_name>', methods=['DELETE'])
    def delete_skill(skill_name):
        """删除技能"""
        try:
            skill_agent.delete_skill(skill_name)
            return jsonify({"message": f"技能 {skill_name} 删除成功"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/tasks')
    def get_tasks():
        """获取任务索引列表"""
        try:
            from pathlib import Path
            import os
            current_dir = Path(os.getcwd())
            
            tasks_file = current_dir / 'tasks.md'
            if not tasks_file.exists():
                return jsonify({"tasks": []})
            
            with open(tasks_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 简单解析 Markdown 表格
            tasks = []
            lines = content.split('\n')
            in_table = False
            for line in lines:
                if line.strip().startswith('| 任务 ID |'):
                    in_table = True
                    continue
                if in_table and line.strip().startswith('| ') and not line.strip().startswith('|--------|'):
                    parts = [part.strip() for part in line.strip('| \n').split('|')]
                    if len(parts) >= 4:
                        tasks.append({
                            "id": parts[0],
                            "created_at": parts[1],
                            "description": parts[2],
                            "status": parts[3]
                        })
            
            return jsonify({"tasks": tasks})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/tasks/<task_id>')
    def get_task_detail(task_id):
        """获取任务详细信息"""
        try:
            from pathlib import Path
            import os
            current_dir = Path(os.getcwd())
            
            task_file = current_dir / 'tasks' / f"{task_id}.json"
            if not task_file.exists():
                return jsonify({"error": f"任务 {task_id} 不存在"}), 404
            
            with open(task_file, 'r', encoding='utf-8') as f:
                task_data = json.load(f)
            
            return jsonify(task_data)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/tasks', methods=['POST'])
    def create_task():
        """创建新任务"""
        try:
            data = request.json
            description = data.get('description')
            
            if not description:
                return jsonify({"error": "缺少任务描述"}), 400
            
            task_id = task_agent.create_task(description)
            return jsonify({"task_id": task_id, "message": "任务创建成功"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/config')
    def get_config():
        """获取配置信息"""
        try:
            config = load_config()
            # 不返回敏感的 API key
            safe_config = config.copy()
            safe_config.pop('api_key', None)
            return jsonify(safe_config)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/config', methods=['POST'])
    def update_config():
        """更新配置信息"""
        try:
            data = request.json
            # 保留现有的 API key 如果没有提供新的
            current_config = load_config()
            if 'api_key' not in data and 'api_key' in current_config:
                data['api_key'] = current_config['api_key']
            
            save_config(data)
            return jsonify({"message": "配置更新成功"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/execute', methods=['POST'])
    def execute_task():
        """执行任务（ReAct 循环 + 流式传输）"""
        try:
            data = request.json
            task_id = data.get('task_id')
            history = data.get("history", [])
            
            if not task_id or not history:
                return jsonify({"error": "缺少任务 ID 或对话历史"}), 400
            
            # 从 history 最后一条获取用户输入（不再依赖单独的 input 参数）
            if not history or history[-1].get('role') != 'user':
                return jsonify({"error": "对话历史最后一条必须是用户消息"}), 400
            
            user_input = history[-1].get('content')
            
            task_agent.log_to_task(task_id, {"type": "user_input", "content": user_input})
            
            config = load_config()
            if not config.get('api_key'):
                return jsonify({"error": "未配置 API Key，请先在设置中配置"}), 400
            
            system_prompt = worker_agent.get_system_prompt(get_system_prompt()); 
            
            new_history = history[:-1] # 先拿掉最后一条用户新问题
            current_query = history[-1] # 存好当前用户新问题

            # 伪造一个“标准示范”
            fake_shot = [
                {
                    "role": "user", 
                    "content": "（系统行为同步）请确认你当前的执行协议。"
                },
                {
    "role": "assistant",
    "content":f"""收到。我已切换至 **ReAct+D+T (自适应维护)** 协议。

**我的执行逻辑如下：**

1. **Route (路由)**：分析任务领域，检索 `{os.getcwd()}/skills/` 目录下是否有匹配的存量技能书f。
2. **Thought (规划)**：
   - **优先复用**：若存在存量技能，我将优先规划调用该技能以实现热启动。
   - **工具强制**：无论历史记录如何简化，我必须通过 `<function-call>` 执行任务，严禁直接输出答案。
3. **Action (动作)**：发起 `<function-call>...</function-call>`。
4. **Observe (反馈与判别)**：
   - **效能评估**：基于 Stdout 事实。若存量技能运行成功且结果符合预期，则继续逻辑推进。
   - **触发重构**：若反馈显示脚本报错、API 结构变更或数据失效，我将立即判定该技能“已过时”。
5. **Distill (进化与覆盖)**：
   - **动态探索**：在判定技能失效后，我将立即启动原子工具重新探索成功路径。
   - **技能更新**：**【核心】** 只要新路径探索成功，我必须立即重新整理并生成新的脚本，覆写旧有的 `{os.getcwd()}/skills/` 文件，确保技能库始终处于可用状态。

**状态确认**：已就绪。我将信任并优先使用已有技能，但在发现其失效时，我会通过重新探索来自动完成技能书的更新迭代。"""
}
            ]

            # 重新组合：系统提示 + 历史 + 伪造示范 + 当前问题
            conversation_history = [
                {"role": "system", "content": system_prompt},
            ] + new_history + fake_shot + [current_query]
            max_iterations = 100
            iteration = 0
            
            # 内部 async 生成器逻辑
            async def _async_generate():
                nonlocal iteration, conversation_history
                while iteration < max_iterations:
                    iteration += 1
                    yield f"data: {json.dumps({'type': 'iteration_start', 'iteration': iteration})}\n\n"
                    
                    stream = await call_llm_stream(conversation_history, config)
                    llm_response = ""
                    async for chunk in stream:
                        if  chunk.choices.__len__() > 0 and chunk.choices[0].delta.content is not None:
                            content = chunk.choices[0].delta.content
                            llm_response += content
                            yield f"data: {json.dumps({'type': 'llm_token', 'content': content})}\n\n"
                    
                    task_agent.log_to_task(task_id, {
                        "type": "llm_response", "content": llm_response, "iteration": iteration
                    })
                    
                    function_calls = parse_function_calls(llm_response)
                    
                    # 检查是否解析失败
                    if len(function_calls) == 1 and 'error' in function_calls[0]:
                        error_msg = function_calls[0]['error']
                        # 将错误信息作为观察结果反馈给 AI
                        # 你的工具调用格式有误（错误：{error_info}）。请检查 _body_fields 和 CDATA 的对应关系，并重新输出该工具调用块
                        observation = f"你的工具调用格式有误（错误：:{error_msg}),请检查 _body_fields 和 CDATA 的对应关系，并重新输出该工具调用块"
                        yield f"data: {json.dumps({'type': 'function_error', 'function': 'parse_error', 'error': error_msg})}\n\n"
                        
                        # 添加到对话历史，让 AI 重新生成
                        conversation_history.append({"role": "assistant", "content": llm_response})
                        conversation_history.append({"role": "system", "content": f"Observation: {observation}"})
                        yield f"data: {json.dumps({'type': 'observation', 'content': observation})}\n\n"
                        continue
                    
                    if not function_calls:
                        yield f"data: {json.dumps({'type': 'final_response', 'content': llm_response})}\n\n"
                        task_agent.complete_task(task_id, "")
                        break
                    
                    observation = ""
                    for call in function_calls:
                        try:
                            result = global_registry.execute_function(
                                call['name'], *[], **call['kwargs']
                            )
                            log_entry = {
                                "type": "function_call", "function": call['name'],
                                "args": [], "kwargs": call['kwargs'],
                                "result": result, "iteration": iteration
                            }
                            task_agent.log_to_task(task_id, log_entry)
                            observation += f"执行 {call['name']} 的结果：{result}\n"
                            yield f"data: {json.dumps({'type': 'function_result', 'function': call['name'], 'result': str(result)})}\n\n"
                        except Exception as e:
                            if call.__contains__("name"):
                                task_agent.log_to_task(task_id, {
                                    "type": "function_call_error", "function": call['name'],
                                    "error": str(e), "iteration": iteration
                                })
                                observation += f"执行 {call['name']} 时出错：{str(e)}\n"
                                yield f"data: {json.dumps({'type': 'function_error', 'function': call['name'], 'error': str(e)})}\n\n"
                            else:
                                task_agent.log_to_task(task_id, {
                                    "type": "function_call_error", "function": "name为空",
                                    "error": str(e), "iteration": iteration
                                })
                                if call.__contains__("name"):
                                    observation += f"执行 {call['name']} 时出错：{str(e)}\n"
                                    yield f"data: {json.dumps({'type': 'function_error', 'function': call['name'], 'error': str(e)})}\n\n"
                                else:
                                    observation += f"执行时出错：{str(e)}\n"
                                    yield f"data: {json.dumps({'type': 'function_error', 'function': None, 'error': str(e)})}\n\n"

                    conversation_history.append({"role": "assistant", "content": llm_response})
                    conversation_history.append({"role": "system", "content": f"Observation: {observation.strip()}"})
                    yield f"data: {json.dumps({'type': 'observation', 'content': observation.strip()})}\n\n"
                
                if iteration >= max_iterations:
                    final_msg = "任务执行超时，已达到最大迭代次数。"
                    yield f"data: {json.dumps({'type': 'final_response', 'content': final_msg})}\n\n"
                    task_agent.complete_task(task_id, final_msg)
                yield f"data: {json.dumps({'type': 'task_complete'})}\n\n"
            
            # 同步包装器：把 async generator 转为同步 generator
            def _sync_generate():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    async_gen = _async_generate()
                    while True:
                        try:
                            yield loop.run_until_complete(async_gen.__anext__())
                        except StopAsyncIteration:
                            break
                finally:
                    loop.close()
            
            # 返回时用 stream_with_context 包装同步 generator
            return Response(
                stream_with_context(_sync_generate()),
                mimetype='text/event-stream'
            )
            
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/save_script_as_skill', methods=['POST'])
    def save_script_as_skill():
        """将生成的脚本保存为技能"""
        try:
            from pathlib import Path
            import os
            current_dir = Path(os.getcwd())
            
            data = request.json
            script_content = data.get('script_content')
            skill_name = data.get('skill_name')
            skill_description = data.get('skill_description', '')
            
            if not script_content or not skill_name:
                return jsonify({"error": "缺少脚本内容或技能名称"}), 400
            
            # 1. 保存脚本到 scripts 目录
            scripts_dir = current_dir / "scripts"
            scripts_dir.mkdir(exist_ok=True)
            script_file = scripts_dir / f"{skill_name}.py"
            
            with open(script_file, 'w', encoding='utf-8') as f:
                f.write(script_content)
            
            # 2. 创建技能描述 Markdown
            skill_md_content = f"""# {skill_name}

{skill_description}

## 使用方法
```python
# 调用此技能来执行相关操作
```

## 脚本位置
`./scripts/{skill_name}.py`
"""
            
            # 3. 保存技能到 skills 目录
            skill_agent.save_skill(skill_name, skill_md_content)
            
            return jsonify({"message": f"脚本已保存为技能 '{skill_name}'"})
            
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/summarize', methods=['POST'])
    async def summarize_conversation():
        """总结对话历史，每 50 轮调用一次"""
        try:
            data = request.json
            task_id = data.get('task_id')
            conversation_history = data.get('conversation_history', [])
            
            if not task_id:
                return jsonify({"error": "缺少任务 ID"}), 400
            
            # 构建总结提示
            history_text = "\n".join([
                f"{'用户' if msg['sender'] == 'user' else '助手'}: {msg['message']}"
                for msg in conversation_history
            ])
            
            summary_prompt = f"""你是一个办公自动化助手，需要对以下对话历史进行总结。
请按照以下格式输出 Markdown：

## 当前任务状态
[简要描述当前任务的进展和状态]

## 下一步计划
[建议下一步应该做什么]

对话历史：
{history_text}
"""
            
            # 加载配置
            config = load_config()
            if not config.get('api_key'):
                return jsonify({"error": "未配置 API Key，请先在设置中配置"}), 400
            
            # 调用 LLM 进行总结
            summary = await call_llm("你是一个专业的办公自动化助手，请根据要求总结对话。", summary_prompt, config)
            
            # 记录总结到任务日志
            task_agent.log_to_task(task_id, {
                "type": "summary",
                "content": summary
            })
            
            return jsonify({"summary": summary})
            
        except Exception as e:
            return jsonify({"error": str(e)}), 500