from typing import Union, List
from .core import global_registry



def get_system_prompt(toolbox: Union[str, List[str]] = "default") -> str:
    """
    生成可拼接的函数调用提示片段，支持单个或多个工具箱
    
    Args:
        toolbox: 工具箱名称，可以是单个字符串（如 "default"）或多个名称列表（如 ["default", "file_tools"]）
    
    Returns:
        包含所有指定工具箱中可用工具函数及调用规则的提示文本
    """
    if isinstance(toolbox, str):
        toolboxes = [toolbox]
    else:
        toolboxes = toolbox
    
    all_descriptions = []
    for tb in toolboxes:
        desc = global_registry.get_prompt_descriptions(agent=tb)
        if desc.strip():  # 避免空描述
            all_descriptions.append(desc)
    
    functions_desc = "\n".join(all_descriptions) if all_descriptions else "无可用工具函数"
    
    return (
    f"## 🛠 工具库 (Available Tools)\n"
    f"你可以通过以下函数与系统交互：\n"
    f"{functions_desc}\n\n"
    
    f"## 📝 交互与调用协议 (Interaction Protocol)\n"
    f"1. **单次调用原则** (最高优先级): \n"
    f"   - 每次回复**只能包含一个** `<function-call>` 标签。\n"
    f"   - 严禁在同一回复中调用多个函数。\n"
    f"   - 如果需要执行多个步骤，必须分多次回复，每次调用一个函数，等待系统返回结果后再继续。\n"
    f"   - *正确示例*: \n"
    f"     ```\n"
    f"     <function-call>write_file(filepath=\"test.py\", content=\"print('hello')\")</function-call>\n"
    f"     ```\n"
    f"   - *错误示例*: \n"
    f"     ```\n"
    f"     <function-call>func1()</function-call>\n"
    f"     <function-call>func2()</function-call>\n"
    f"     ```\n"
    f"2. **调用格式**: 必须将函数调用包裹在 `<function-call>` 标签内。\n"
    f"   - *正确示例*: `<function-call>func_name(arg1=\"value\", arg2=123)</function-call>`\n"
    f"3. **多行字符串规范**: \n"
    f"   - 如果参数包含多行文本、换行符或复杂结构，**必须**使用三引号 `\"\"\"` 包裹。\n"
    f"   - *正确示例*: `write_file(filepath=\"test.py\", content=\"\"\"print('hello')\nprint('world')\"\"\")`\n"
    f"   - *错误示例*: `write_file(filepath=\"test.py\", content=\"print('hello')\nprint('world')\")` (严禁出现)\n"
    f"4. **语法约束**: \n"
    f"   - **字符串**: 单行字符串使用双引号 (e.g., `\"path/to/file\"`)。\n"
    f"   - **布尔值/数字**: 直接书写 (e.g., `True`, `0.5`)。\n"
    f"   - **禁止**: 标签内严禁出现 Python 注释 `#` 或多余的换行符（三引号内除外）。\n"
    f"5. **错误处理**: 如果函数返回报错 (stderr)，请分析原因并尝试修正代码重新调用。\n"
)