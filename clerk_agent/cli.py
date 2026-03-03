import os
import sys
import json
from pathlib import Path

# 添加当前目录到 Python 路径
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

# 导入必要的模块
from tagcall import function_call, get_system_prompt, parse_function_calls, global_registry
from clerk_agent.agents import TaskAgent, SkillAgent, WorkerAgent
from clerk_agent.tools import read_file, write_file, execute_shell

# 注册工具函数（与 webui.py 保持一致）
@function_call(prompt="读取工作空间内的文件内容", name="read_file")
def read_file_tool(filepath: str):
    return read_file(filepath)

@function_call(prompt="写入内容到工作空间内的文件", name="write_file")
def write_file_tool(filepath: str, content: str):
    return write_file(filepath, content)

@function_call(prompt="执行 Shell 命令（危险命令会被拦截）", name="execute_shell")
def execute_shell_tool(command: str):
    return execute_shell(command)

def main():
    """命令行界面主函数"""
    print("🎩 Clerk Agent 3.0 CLI")
    print("=" * 40)
    
    # 初始化代理
    task_agent = TaskAgent()
    skill_agent = SkillAgent()
    worker_agent = WorkerAgent(task_agent, skill_agent)
    
    while True:
        try:
            user_input = input("\n👤 用户输入 (输入 'quit' 退出): ").strip()
            if user_input.lower() == 'quit':
                break
            
            if not user_input:
                continue
            
            # 创建新任务
            task_id = task_agent.create_task(user_input)
            print(f"📋 任务创建: {task_id}")
            
            # 获取系统提示词
            system_prompt = worker_agent.get_system_prompt()
            
            # 这里应该调用 LLM，但为了演示，我们模拟一个简单的响应
            print(f"\n🤖 模拟 LLM 响应...")
            
            # 模拟一个简单的文件操作任务
            if "创建" in user_input and "文件" in user_input:
                simulated_response = '<function-call>write_file("test.txt", "Hello Clerk Agent!")</function-call>'
            elif "读取" in user_input and "文件" in user_input:
                simulated_response = '<function-call>read_file("test.txt")</function-call>'
            else:
                simulated_response = "我理解了您的需求，但需要更多具体信息来执行操作。"
            
            print(f"💬 LLM 输出: {simulated_response}")
            
            # 解析并执行函数调用
            function_calls = parse_function_calls(simulated_response)
            if function_calls:
                for call in function_calls:
                    try:
                        result = global_registry.execute_function(
                            call['name'],
                            *call['args'],
                            **call['kwargs']
                        )
                        
                        # 记录到任务日志
                        log_entry = {
                            "action": "function_call",
                            "function": call['name'],
                            "args": call['args'],
                            "kwargs": call['kwargs'],
                            "result": result
                        }
                        task_agent.log_to_task(task_id, log_entry)
                        
                        print(f"✅ 执行结果: {result}")
                        
                    except Exception as e:
                        error_log = {
                            "action": "function_call_error",
                            "function": call['name'],
                            "error": str(e)
                        }
                        task_agent.log_to_task(task_id, error_log)
                        print(f"❌ 执行错误: {e}")
                
                # 完成任务
                task_agent.complete_task(task_id, "任务执行完成")
            else:
                # 直接回答
                task_agent.complete_task(task_id, simulated_response)
                print(f"💬 直接回答: {simulated_response}")
                
        except KeyboardInterrupt:
            print("\n👋 再见！")
            break
        except Exception as e:
            print(f"💥 系统错误: {e}")

if __name__ == "__main__":
    main()