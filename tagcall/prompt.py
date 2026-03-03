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
        f"可用工具函数：\n{functions_desc}\n\n"
        f"调用规则：\n"
        f"- 若需调用，请在回答中插入 <function-call> 标签，格式如：<function-call>func_name(arg1, arg2)</function-call>\n"
        f"- 字符串参数必须用双引号包裹（如 message=\"hello\"），数字、布尔值、None 直接书写\n"
        f"- 不要解释调用过程，不要输出额外说明\n"
        f"- 若无需调用函数，则直接回答问题"
    )