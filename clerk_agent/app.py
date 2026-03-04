import os
import sys
import json
import yaml
import asyncio
from pathlib import Path
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import openai
import uuid
from flask import request, jsonify, Response, stream_with_context

import os

# 设置 HTTP 和 HTTPS 代理
os.environ['http_proxy'] = 'http://127.0.0.1:7897'
os.environ['https_proxy'] = 'http://127.0.0.1:7897'

# 获取当前目录
current_dir = Path(os.getcwd());
print(current_dir);

# 导入必要的模块
from tagcall import function_call, get_system_prompt, parse_function_calls, global_registry
from clerk_agent.agents import TaskAgent, SkillAgent, WorkerAgent
from clerk_agent.tools import read_file, write_file, execute_shell

# 注册工具函数到 TagCall（只注册一次）
def register_tools():
    """注册工具函数到全局注册表"""
    if 'read_file' not in global_registry.get_all_functions():
        @function_call(prompt="读取文件内容", name="read_file")
        def read_file_tool(filepath: str):
            return read_file(filepath)

    if 'write_file' not in global_registry.get_all_functions():
        @function_call(prompt="写入内容到文件，content 需要使用\"\"\"来传入多行", name="write_file")
        def write_file_tool(filepath: str, content: str):
            return write_file(filepath, content)

    if 'execute_shell' not in global_registry.get_all_functions():
        @function_call(prompt="执行 Shell 命令（危险命令会被拦截）,使用的是python的subprocess。", name="execute_shell")
        def execute_shell_tool(command: str):
            return execute_shell(command)
    
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

# 初始化代理
task_agent = TaskAgent()
skill_agent = SkillAgent()
worker_agent = WorkerAgent(task_agent, skill_agent)

# 注册工具
register_tools()

# 创建 Flask 应用
app = Flask(__name__, 
    static_folder=str(current_dir / 'webui'),
    static_url_path='',  # 将静态路径映射到根目录
    template_folder=str(current_dir / 'webui')
)
CORS(app)

def load_config():
    """加载配置文件"""
    config_path = current_dir / 'config.yaml'
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    return {}

def save_config(config_data):
    """保存配置文件"""
    config_path = current_dir / 'config.yaml'
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(config_data, f, allow_unicode=True, default_flow_style=False)

async def call_llm_stream(messages, config):
    """流式调用大模型 API"""
    try:
        client = openai.AsyncOpenAI(
            api_key=config.get('api_key'),
            base_url=config.get('base_url', 'https://api.openai.com/v1')
        )
        
        stream = await client.chat.completions.create(
            model=config.get('model', 'gpt-4o-mini'),
            messages=messages,
            temperature=0.7,
            max_tokens=2000,
            stream=True
        )
        return stream
    except Exception as e:
        raise Exception(f"LLM 调用失败：{str(e)}")

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
        
        system_prompt = worker_agent.get_system_prompt() + get_system_prompt()
        
        conversation_history = [
            {"role": "system", "content": system_prompt},
        ] + history
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
                    if chunk.choices[0].delta.content is not None:
                        content = chunk.choices[0].delta.content
                        llm_response += content
                        yield f"data: {json.dumps({'type': 'llm_token', 'content': content})}\n\n"
                
                task_agent.log_to_task(task_id, {
                    "type": "llm_response", "content": llm_response, "iteration": iteration
                })
                
                function_calls = parse_function_calls(llm_response)
                if not function_calls:
                    yield f"data: {json.dumps({'type': 'final_response', 'content': llm_response})}\n\n"
                    task_agent.complete_task(task_id, "")
                    break
                
                observation = ""
                for call in function_calls:
                    try:
                        result = global_registry.execute_function(
                            call['name'], *call['args'], **call['kwargs']
                        )
                        log_entry = {
                            "type": "function_call", "function": call['name'],
                            "args": call['args'], "kwargs": call['kwargs'],
                            "result": result, "iteration": iteration
                        }
                        task_agent.log_to_task(task_id, log_entry)
                        observation += f"执行 {call['name']} 的结果：{result}\n"
                        yield f"data: {json.dumps({'type': 'function_result', 'function': call['name'], 'result': str(result)})}\n\n"
                    except Exception as e:
                        task_agent.log_to_task(task_id, {
                            "type": "function_call_error", "function": call['name'],
                            "error": str(e), "iteration": iteration
                        })
                        observation += f"执行 {call['name']} 时出错：{str(e)}\n"
                        yield f"data: {json.dumps({'type': 'function_error', 'function': call['name'], 'error': str(e)})}\n\n"
                
                conversation_history.append({"role": "assistant", "content": llm_response})
                conversation_history.append({"role": "user", "content": f"Observation: {observation.strip()}"})
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


async def call_llm(system_prompt, user_message, config):
    """调用大模型 API"""
    try:
        client = openai.AsyncOpenAI(
            api_key=config.get('api_key'),
            base_url=config.get('base_url', 'https://api.openai.com/v1')
        )
        
        response = await client.chat.completions.create(
            model=config.get('model', 'gpt-4o-mini'),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7,
            max_tokens=2000
        )
        
        return response.choices[0].message.content
    except Exception as e:
        raise Exception(f"LLM 调用失败：{str(e)}")

def main():
    """启动 Flask WebUI"""
    print("🚀 Clerk Agent 3.0 WebUI 启动中...")
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
    
    print("\n🌐 WebUI 服务启动:")
    print("   访问地址：http://localhost:5000")
    print("   按 Ctrl+C 停止服务")
    
    # 启动 Flask 应用
    app.run(host='0.0.0.0', port=5000, debug=False)

if __name__ == "__main__":
    main()