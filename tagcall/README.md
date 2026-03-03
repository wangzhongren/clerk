# TagCall —— 基于 `<function-call>` 标签的轻量级大模型工具调用框架

**TagCall** 是一个简单、灵活、无依赖的大模型函数调用（Function Calling）解决方案。它通过在模型输出中插入标准 XML 风格标签（如 `<function-call>add(a=1, b=2)</function-call>`），实现本地函数的安全调用，适用于任何支持文本生成的大模型（OpenAI、Ollama、Llama.cpp、vLLM 等）。

无需复杂 Schema 定义，无需 JSON 模式约束，只需装饰器注册 + 标准提示词，即可让任意大模型“调用你的代码”。

---

## ✨ 特性

- **零依赖解析**：使用 `BeautifulSoup` 安全解析 `<function-call>` 标签（可选，也可自行替换）
- **自动函数签名提取**：无需手动写参数，自动从源码或 `inspect.signature` 生成 `func(a, b)` 形式
- **类型安全参数解析**：支持字符串（双引号）、整数、浮点数、布尔值、`None`
- **可拼接系统提示**：提供纯净的 `get_system_prompt()`，便于集成到任意角色设定中
- **兼容所有大模型 API**：OpenAI SDK、Ollama、自定义后端均可使用
- **流式友好**：先流式输出，再完整解析，不影响用户体验

---

## 📦 安装

将 `tagcall/` 目录放入你的 Python 项目中，确保可导入：

```bash
your_project/
├── tagcall/
│   ├── __init__.py
│   ├── core.py
│   ├── decorator.py
│   └── prompt.py
└── your_agent.py
```

依赖（仅解析 HTML 标签时需要）：
```bash
pip install beautifulsoup4
```

> 💡 若你希望完全移除 `bs4` 依赖，可自行替换 `parse_function_calls` 中的解析逻辑（例如用正则）。

---

## 🚀 快速开始

### 1. 注册工具函数

```python
from tagcall import function_call

@function_call(prompt="获取当前时间")
def get_time():
    import time
    return time.strftime("%H:%M:%S")

@function_call(prompt="计算两个数的和")
def add(a: int, b: int):
    return a + b
```

### 2. 获取系统提示词（用于注入模型）

```python
from tagcall import get_system_prompt

system_prompt = get_system_prompt()
# 输出示例：
# 可用工具函数：
# get_time() - 获取当前时间
# add(a, b) - 计算两个数的和
#
# 调用规则：
# - 若需调用，请在回答中插入 <function-call> 标签...
```

### 3. 调用大模型（以 OpenAI SDK 为例）

```python
from openai import OpenAI
from tagcall import parse_function_calls, global_registry

client = OpenAI()  # 或配置 Ollama base_url

response = client.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "现在几点？"}
    ]
)

llm_output = response.choices[0].message.content
```

### 4. 解析并执行函数调用

```python
calls = parse_function_calls(llm_output)
for call in calls:
    result = global_registry.execute_function(
        call['name'],
        *call['args'],
        **call['kwargs']
    )
    print(f"{call['name']} → {result}")
```

---

## 🧪 示例项目

查看完整示例：
- [`test_tagcall_agent_with_openai.py`](../test_tagcall_agent_with_openai.py)：支持 OpenAI / Ollama（兼容 API）+ 流式输出
- [`test_tagcall_agent.py`](../test_tagcall_agent.py)：纯本地模拟测试

---

## 📝 提示词设计说明

`get_system_prompt()` 返回的内容**不含角色定义**，仅为工具描述片段，便于拼接：

```python
my_role = "你是公司内部效率助手，语气简洁。"
full_prompt = f"{my_role}\n\n{get_system_prompt()}"
```

模型将被引导输出如下格式：
```text
<function-call>get_time()</function-call>
```
或
```text
<function-call>add(a=3, b=5)</function-call>
```

---

## 🔒 安全性

- 函数必须显式注册才能被调用，防止任意代码执行；
- 参数解析严格限制为基本类型，不支持表达式求值；
- 标签解析基于 HTML/XML 安全解析器，避免注入风险。

---

## 🤝 贡献与扩展

- 替换 `parse_function_calls` 实现（如使用正则）以移除 `bs4` 依赖；
- 扩展 `_parse_value` 支持更多类型（如列表、字典）；
- 添加异步执行支持（当前为同步）。

---

## 📜 License

MIT License — 自由用于个人及商业项目。