# Clerk Agent 3.0 - 办公自动化智能体

![Clerk Agent](https://img.shields.io/badge/version-3.0.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Clerk Agent 是一个基于大语言模型的办公自动化智能体，能够理解自然语言指令、执行复杂任务、调用工具函数，并将成功经验沉淀为可复用的技能。通过 ReAct（推理+行动）机制，Clerk 能够自主规划、执行和验证任务，同时严格遵守安全约束。

## 🌟 核心特性

- **智能任务执行**：通过自然语言指令驱动，自动完成文件操作、Shell 命令执行、Python 脚本生成等办公任务
- **技能沉淀机制**：将成功执行的脚本自动注册为可复用技能，形成组织知识库
- **安全防护体系**：内置危险命令拦截机制，防止误操作导致系统损坏
- **完整任务追踪**：每个任务都有独立 ID 和详细日志，支持随时查看执行历史
- **个性化配置**：支持自定义 AI 模型、API 密钥和用户画像
- **Web UI 界面**：提供直观的 Web 界面，支持对话式交互和技能管理

## 📦 技术架构

```
clerk_agent/
├── app.py              # 主应用入口和 Flask API 服务
├── agents.py           # 任务代理、技能代理和工作代理核心逻辑
├── tools.py            # 工具函数实现（文件读写、Shell 执行）
├── webui/             # Web 用户界面
│   ├── index.html      # 主页面
│   └── main.js         # 前端交互逻辑
├── skills/            # 技能库目录（Markdown 格式）
├── scripts/           # 生成的 Python 脚本目录
├── tasks/             # 任务详情 JSON 文件目录
├── config.yaml        # 系统配置文件
├── self.md            # Clerk 自身设定文件
├── user.md            # 用户画像文件
└── tasks.md           # 任务索引表
```

## 🚀 快速开始

### 环境要求

- Python 3.8+
- pip 包管理器

### 安装依赖

```bash
pip install flask flask-cors openai pyyaml
```

### 配置 API 密钥

1. 复制 `config.yaml` 文件（如果不存在）
2. 编辑配置文件，填入您的 AI 服务 API 密钥：

```yaml
api_key: "your-api-key-here"
base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
model: "qwen3-max"
dangerous_commands:
  - "rm -rf /"
  - "format"
  - "mkfs"
  - "fdisk"
```

### 启动服务

```bash
python clerk_agent/app.py
```

服务启动后，访问 `http://localhost:5000` 即可使用 Web 界面。

## 🧠 使用指南

### 1. 智能工作台

在工作台中输入自然语言指令，例如：
- "帮我找出下载文件夹中最大的10个文件"
- "创建一个周报模板，包含项目进展、问题和下周计划"
- "分析当前目录下的所有 Python 文件，统计代码行数"

Clerk 会自动：
1. 分析任务需求
2. 规划执行步骤
3. 调用必要的工具函数
4. 执行并验证结果
5. 返回最终答案

### 2. 能力矩阵

在"能力矩阵"页面可以：
- 查看已注册的技能
- 编辑现有技能
- 创建新的技能

每个技能都是一个 Markdown 文件，包含技能描述、使用场景、参数说明和代码示例。

### 3. 核心配置

在"核心配置"页面可以：
- 设置 API 密钥
- 配置模型端点
- 更换 AI 模型

## 🔒 安全机制

Clerk Agent 内置多重安全保护：

1. **危险命令拦截**：配置文件中的 `dangerous_commands` 列表会自动拦截高危操作
2. **诚实原则**：所有执行结果都会如实报告，不会虚构成功状态
3. **路径规范**：所有生成的脚本都保存在 `./scripts/` 目录，避免污染其他位置
4. **超时保护**：Shell 命令执行有 30 秒超时限制，防止挂起

## 📝 文件说明

- **self.md**: Clerk 的自我设定文件，可自定义身份、能力和行为准则
- **user.md**: 用户画像文件，可记录用户偏好、工作习惯等信息
- **tasks.md**: 任务索引表，以 Markdown 表格形式展示所有任务
- **skills/**: 技能库目录，每个技能对应一个 `.md` 文件
- **scripts/**: 自动生成的 Python 脚本目录
- **tasks/**: 任务详情目录，每个任务对应一个 `.json` 文件

## 🛠️ 开发扩展

### 添加新工具函数

在 `app.py` 的 `register_tools()` 函数中添加新的工具注册：

```python
if 'new_tool' not in global_registry.get_all_functions():
    @function_call(prompt="工具功能描述", name="new_tool")
    def new_tool_function(param1: str, param2: int):
        return your_tool_implementation(param1, param2)
```

### 自定义技能模板

在 `skills/` 目录下创建新的 `.md` 文件，遵循以下格式：

```markdown
# 技能名称

## 技能描述
详细描述技能的功能和用途

## 使用场景
- 场景1
- 场景2

## 输入参数
- `param1`: 参数1说明
- `param2`: 参数2说明

## 输出格式
描述输出的内容和格式

## 代码模板
```python
# Python 代码示例
```

## 调用示例
```python
# 调用示例
```
```

## 📊 任务管理

每个任务都有完整的生命周期管理：

1. **创建**：通过 API 或 Web UI 创建新任务
2. **执行**：Clerk 执行 ReAct 循环，记录每一步操作
3. **完成**：任务成功或失败后标记状态
4. **追踪**：可通过任务 ID 查看完整执行日志

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！请确保：
- 遵循现有代码风格
- 添加必要的测试用例
- 更新相关文档

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。

---

> **注意**：请妥善保管您的 API 密钥，不要将其提交到公共代码仓库。生产环境中建议使用环境变量或密钥管理服务。