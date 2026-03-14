# Clerk Agent 

![Version](https://img.shields.io/badge/version-5.0.0-blue)
![License](https://img.shields.io/badge/license-apache--2.0-red)
![Protocol](https://img.shields.io/badge/protocol-ReAct%2BD%2BT-orange)
![Navigator](https://img.shields.io/badge/navigator-Enabled-purple)

**Clerk Agent** 是一个基于 **ReAct+D+T（自适应维护）协议** 的企业级办公自动化智能体框架。它通过明确的**工具/技能分层架构**和**导航代理监督机制**，将通用 AI 能力转化为可沉淀、可复用、可审计的自动化资产。

> 🎯 **核心理念**：AI 负责执行，人类负责决策，导航员负责监督。优秀的 AI Code 工程不是让 AI 猜你想要什么，而是通过结构化的声明，让 AI 无法做错。

---

## 🌟 核心特性

### 🔧 工具与技能明确分层

| 层级 | 定义 | 特点 | 示例 |
|------|------|------|------|
| **工具层 (Tools)** | 原子操作能力（肢体） | 低频变更、稳定可靠 | `read_file`, `modify_file`, `execute_shell` |
| **技能层 (Skills)** | 工具组合 + 业务逻辑（招式） | 高频迭代、业务驱动 | `维护系统任务创建`, `微博热搜爬取` |

### 🧭 导航代理监督机制 (v5.0 新增)

| 功能 | 说明 | 触发条件 |
|------|------|----------|
| **定期方向审查** | 每 5 步审查任务方向是否正确 | 迭代次数 % 5 == 0 |
| **死循环检测** | 识别重复无效操作 | 日志模式分析 |
| **钻牛角尖检测** | 发现卡住太久的问题 | 时间/步骤阈值 |
| **最终任务验收** | 严格验证任务是否真正完成 | Worker 停止调用工具 |
| **自动修正指令** | 发现问题时注入修正指令 | 审查未通过 |

### 📚 技能沉淀机制

- ✅ **持久化存储**：技能以 `.md` 手册 + `.py` 脚本形式固化到本地
- ✅ **树状分类管理**：按领域分类（维护系统/文件操作/数据爬取等）
- ✅ **跨会话复用**：技能库支持热启动，秒级响应重复任务
- ✅ **自动进化**：技能失效时自动重新探索并覆盖更新
- ✅ **AI 自动总结**：任务成功后 AI 自动生成技能名称、描述和文档

---

## 📦 技术架构

```
office-skills-agent/
├── clerk_agent/
│   ├── app.py                  # Flask API 服务 + 工具注册
│   ├── agents.py               # ReAct+D+T 核心逻辑
│   ├── navigator.py            # 🧭 导航代理（v5.0 新增）
│   ├── routes.py               # API 路由（含导航集成）
│   ├── tools.py                # 原子工具层
│   ├── llm_client.py           # LLM 调用封装
│   ├── config.py               # 配置管理
│   └── webui/
│       ├── index.html          # Web 界面
│       └── main.js             # 前端逻辑（含导航事件处理）
├── skills/                     # 📚 技能库（树状分类）
│   ├── 导航代理监督机制使用手册.md
│   ├── 维护系统操作技能手册.md
│   ├── 城市天气查询与五日预报.md
│   ├── 微博热搜榜单获取与导出.md
│   └── ...
├── tasks/                      # 任务历史记录
│   ├── T247.json
│   └── ...
├── config/
│   ├── local_config.json       # 本地配置持久化
│   └── token_usage.json        # Token 用量统计
└── README.md                   # 本文档
```

---

## 🚀 快速开始

### 环境要求

- Python 3.8+
- macOS / Windows / Linux

### 安装依赖

```bash
pip install flask flask-cors openai pyyaml
```

### 配置 API 密钥

编辑 `config/local_config.json`：

```json
{
  "api_key": "your-api-key-here",
  "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "model": "qwen3-max",
  "workspace": "/Users/wangzhongren/code/Clery/office-skills-agent/",
  "user_preference": {
    "skill_naming": "中文",
    "file_format": "[功能描述] 工具技能书.md"
  }
}
```

### 启动服务

```bash
cd /Users/wangzhongren/code/Clery/office-skills-agent
source venv/bin/activate  # 如果有虚拟环境
python -m clerk_agent.app
```

服务启动后，访问 `http://localhost:5002` 使用 Web 界面。

---

## 🧠 使用指南

### 1. Web 界面操作

1. 打开浏览器访问 `http://localhost:5002`
2. 在对话框输入任务描述（如"查询合肥今天天气"）
3. 点击"执行"按钮
4. 实时查看：
   - AI 思考过程
   - 工具调用记录
   - 🧭 导航员审查日志（每 5 步）
   - 🔍 最终验收结果

### 2. 任务执行流程

```
用户输入任务
    ↓
Worker Agent 开始执行
    ↓
[每 5 步] 🧭 导航员审查方向
    ├─ 方向正确 → 继续执行
    └─ 发现问题 → 注入修正指令
    ↓
Worker 声称完成
    ↓
🔍 导航员最终验收
    ├─ PASS → 任务结束
    ├─ FAIL → 要求重新执行
    └─ NEED_MORE_WORK → 继续工作
    ↓
[可选] 📝 总结成技能
    └─ AI 自动生成技能文档
```

### 3. 技能调用示例

```
# 调用已有技能（热启动）
执行 "城市天气查询与五日预报" 技能

# AI 自动检索技能树 → 加载脚本 → 执行 → 返回结果
```

### 4. 技能沉淀

任务成功后，点击"📝 总结成技能"按钮：
- AI 自动生成技能名称
- AI 自动生成技能描述
- AI 自动生成技能文档（.md）
- AI 自动生成执行脚本（.py）
- 自动归类到技能树对应节点

---

## 🔧 原子工具列表

| 工具名 | 功能 | 特性 |
|--------|------|------|
| `read_file` | 读取文件内容 | 智能编码检测 (utf-8/gbk/latin-1) |
| `write_file` | 写入文件内容 | 自动创建目录 |
| `modify_file` | 修改文件内容 | 支持 replace/insert/delete/append，换行符保护 |
| `execute_shell_sync` | 同步执行 Shell 命令 | 30 秒超时，即时返回结果 |
| `execute_shell` | 异步执行 Shell 命令 | 后台运行，返回日志路径 |
| `update_self_profile` | 更新 Clerk 自身配置 | 持久化到 self.md |
| `update_user_profile` | 更新用户画像 | 持久化到 user.md |
| `get_token_usage` | 获取 Token 用量 | 显示累计用量和最近记录 |

---

## 🧭 导航代理详解

### 工作原理

导航代理（Navigator Agent）是一个独立的监督模块，实时监控 Worker Agent 的执行过程：

1. **定期审查**：每 5 步分析最近 10 条日志，判断方向是否正确
2. **死循环检测**：识别重复失败的相同操作
3. **最终验收**：验证函数调用结果是否支持任务完成声明

### 前端日志显示

在 Web 界面中，导航事件以特殊样式显示：

| 事件类型 | 显示效果 | 颜色 |
|----------|----------|------|
| `navigator_review` | 🧭 导航员正在审查任务方向... (第 X 步) | 紫色 |
| `navigator_result` | ✅/⚠️ 审查结果：摘要 (置信度：X%) | 淡紫 |
| `navigator_correction` | ⚠️ 导航员干预：修正指令 | 红色 |
| `navigator_final_review` | 🔍 导航员正在进行最终验收... | 紫色 |
| `navigator_final_result` | ✅/❌/⚠️ 验收结果：原因 | 绿色/红色 |
| `navigator_rejection` | ❌ 验收未通过：原因 | 红色 |

### 配置说明

- **审查间隔**：默认每 5 步，可在 `clerk_agent/navigator.py` 中修改 `review_interval`
- **自动启用**：集成在 `/api/execute` 接口中，无需额外配置
- **失败降级**：导航审查失败时默认不干预，保证任务继续

---

## 📊 Token 用量监控

### 查看当前用量

在 Web 界面点击右上角"📊 Token 用量"按钮，或调用 API：

```bash
curl http://localhost:5002/api/token/usage
```

### 功能特性

- ✅ **自动累计**：每次 API 调用后自动更新用量
- ✅ **历史记录**：保留最近 100 条用量记录
- ✅ **分类统计**：分别统计输入 (prompt) 和输出 (completion) token
- ✅ **重置功能**：支持手动重置统计数据

---

## 📚 技能库管理

### 技能目录结构

```
skills/
├── 导航代理监督机制使用手册.md
├── 维护系统操作技能手册.md
├── 城市天气查询与五日预报.md
├── 微博热搜榜单获取与导出.md
├── 抖音热榜获取与导出.md
├── 数据库 API 转 MCP 封装工具技能书.md
├── 用户临时文件安全清理.md
├── 获取下载文件夹中最大的 10 个文件.md
└── ...
```

### 技能生命周期

1. **探索**：新任务首次执行，AI 使用原子工具探索成功路径
2. **沉淀**：成功后 AI 自动生成 `.md` 手册和 `.py` 脚本
3. **归类**：按领域分类存入技能树对应节点
4. **复用**：后续任务优先检索技能库，热启动执行
5. **进化**：技能失效时自动重新探索并覆盖更新

---

## 🔒 安全机制

| 机制 | 说明 |
|------|------|
| **感知边界** | 严禁脑补实时或本地数据，必须动用工具 |
| **动作中断** | 发起 `<function-call>` 后立即停止，等待物理反馈 |
| **树状检索** | 按"领域→子类→技能"路径寻址，严禁全量扫描 |
| **导航监督** | 每 5 步审查方向，防止钻牛角尖 |
| **最终验收** | 严格验证任务完成，防止虚构结果 |
| **危险命令拦截** | 配置文件定义黑名单，自动拦截高危操作 |
| **超时保护** | Shell 命令 30 秒超时，防止挂起 |
| **编码兼容** | 智能检测文件编码，避免乱码 |

---

## 📊 Clerk vs 通用 AI 对比

| 维度 | Clerk Agent | 通用 AI |
|------|-------------|---------|
| **工具/技能分层** | ✅ 明确分离 | ❌ 混合 |
| **技能持久化** | ✅ 本地文件固化 | ❌ 会话记忆 |
| **跨会话复用** | ✅ 热启动 | ❌ 重新描述 |
| **导航监督** | ✅ 每 5 步审查 + 最终验收 | ❌ 无 |
| **自动进化** | ✅ 失效覆盖更新 | ❌ 无 |
| **防虚构机制** | ✅ 最终验收验证 | ❌ 无 |
| **企业审计** | ✅ 脚本可审查 | ❌ 黑盒 |

> **定位**：Clerk 不是替代通用 AI，而是在其之上构建企业级自动化层。

---

## 🛠️ 开发扩展

### 添加新工具

在 `clerk_agent/tools.py` 中添加函数，在 `clerk_agent/app.py` 中注册：

```python
# tools.py
def new_tool(param1: str, param2: int) -> str:
    """新工具功能描述"""
    return implementation(param1, param2)

# app.py
@function_call(prompt="工具功能描述", name="new_tool")
def new_tool_wrapper(param1: str, param2: int):
    return new_tool(param1, param2)
```

### 创建新技能

1. 执行新任务，让 AI 探索成功路径
2. 任务成功后，点击"📝 总结成技能"
3. AI 自动生成 `.md` 手册和 `.py` 脚本
4. 自动归类到 `skills/` 目录对应节点

### 自定义导航策略

修改 `clerk_agent/navigator.py` 中的审查逻辑：

```python
class NavigatorAgent:
    def __init__(self):
        self.review_interval = 5  # 修改审查间隔
```

---

## 📄 相关文档

| 文档 | 路径 | 说明 |
|------|------|------|
| **导航代理手册** | `skills/导航代理监督机制使用手册.md` | 导航机制详解 |
| **技能手册** | `skills/*/` | 各领域的技能文档 |
| **任务记录** | `tasks/*.json` | 历史任务执行日志 |

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！请确保：
- 新增技能需包含 `.md` 手册和 `.py` 脚本
- 更新相关文档
- 通过导航代理验收测试

---

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。

---

> **边界 AI 达模型 v5.0** - 让 AI 无法做错，让技能持续进化，让导航员全程监督。

**项目位置**: `/Users/wangzhongren/code/Clery/office-skills-agent/`  
**技能目录**: `/Users/wangzhongren/code/Clery/office-skills-agent/skills/`  
**启动命令**: `python -m clerk_agent.app`  
**访问地址**: `http://localhost:5002`
