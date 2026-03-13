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
    
    # def get_system_prompt(functions_desc):
      # 注意：这里的 {{ 和 }} 在 f-string 渲染后会变成单层的 { 和 }
    return f"""
# 🛠️ 自动化工具调用协议 (Tool-Use Protocol)

你必须严格遵守以下 XML 格式进行工具调用。

### 1. 可用工具定义 (Functions)
{functions_desc}

### 2. 强制性输出格式
所有调用必须包裹在 `<function-call>` 内，采用 "字段声明-数据块对应" 模式：

<function-call>
  <工具名 _body_fields="参数1,参数2">
    <![CDATA[ 参数1的值 ]]>
    <![CDATA[ 参数2的值 ]]>
  </工具名>
</function-call>

### 3. 严格约束
- **顺序一致**：CDATA 块数量必须与 _body_fields 声明的参数数量严格对等。
- **禁止裸露文本**：所有参数值必须完全置于 CDATA 块内。
- **本地化意识**：涉及配置保存时，请根据 [2026-02-26] 约定优先使用本地路径。

### 4. 正确示例 (JSON 写入)
<function-call>
  <write_file _body_fields="filepath,content">
    <![CDATA[./config.json]]>
    <![CDATA[ {{ "theme": "dark", "version": 1.0 }} ]]>
  </write_file>
</function-call>
"""