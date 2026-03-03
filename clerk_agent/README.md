# 🎩 Clerk Agent 3.0 系统设计文档 (多代理协作版)

## 1. 项目概述

**Clerk** 是一个垂直于办公自动化领域的轻量化智能体。它不依赖大型框架，核心理念是**“全 Markdown/JSON 状态管理”**与**“原子化 Python 工具执行”**。

Clerk 致力于为普通办公人员提供透明、可干预的自动化流程。

---

## 2. 核心架构哲学

* **状态即文件**：所有记忆、配置和任务日志均存储为本地文件（Markdown/JSON），所见即所得。
* **按需加载 (Lazy Loading)**：仅在需要具体技能时才读取技能文件内容，最大化 LLM 的 Token 效率。
* **多代理协奏 (Multi-Agent Orchestration)**：将配置管理、技能管理、任务管理拆分为专门的代理模块。
* **技能沉淀复用**：自动生成的脚本可保存为技能，避免重复开发相同功能。
* **动态自我进化**：支持实时更新自我设定和用户画像，实现个性化服务。

---

## 3. 存储架构与目录结构

| 组件 | 存储方式 | 职责 |
| --- | --- | --- |
| **`config.yaml`** | 文件 | 存储 `API_KEY`, `BASE_URL`, `METADATA` 等敏感配置。 |
| **`user.md`** | 文件 | 存储用户画像、常用偏好、个人信息（姓名、邮箱等）。 |
| **`self.md`** | 文件 | Clerk 自身设定、工作空间根目录、当前环境信息。 |
| **`tasks.md`** | 文件 | **任务索引表**：记录历史任务 ID、时间、状态 (Pending/Success/Failed)。 |
| **`/tasks/*.json`** | 文件夹 | **任务详情**：每个文件对应一个任务 ID，存储详细 prompt、生成的代码、执行日志。 |
| **`/skills/*.md`** | 文件夹 | **技能库**：存放 `.md` 格式的技能说明文档，包含逻辑描述和代码模板。 |
| **`/scripts/*.py`** | 文件夹 | **脚本库**：存放从对话中提取并保存的 Python 脚本，可直接作为技能调用。 |
| **`/workspace`** | 文件夹 | **文件沙盒**：所有办公文件读写操作仅限此目录。 |

---

## 4. 代理分工设计 (Agent Specialization)

### 4.1 🧠 Worker Agent (核心执行代理)

* **职责**：接收任务，进行 ReAct 思考，生成 Python 代码，调用工具。
* **工具箱**：
  - `read_file`, `write_file`, `execute_shell`
  - **`update_self_profile`**：更新自我设定 (`self.md`)
  - **`update_user_profile`**：更新用户画像 (`user.md`)
* **协作**：在需要技能时调用 Skill Agent，在需要记录任务详情时调用 Task Agent。
* **流式输出**：支持 SSE 流式传输，实时显示 LLM 推理过程和工具调用结果。

### 4.2 🛠️ Skill Agent (技能管理器)

* **职责**：维护 `/skills/` 文件夹和 `/scripts/` 文件夹。
* **核心逻辑**：
  * **列出技能**：启动时扫描并将所有文件名列表装载进 LLM 的 Prompt 中，以便 LLM 自主决策。
  * **按需读取**：LLM 决策使用特定技能后，读取该文件的内容。
  * **技能维护**：通过 WebUI 执行技能的增、删、改操作。
  * **脚本保存**：将对话中生成的 Python 脚本自动保存为可复用的技能。

### 4.3 📂 Task Agent (任务管理器)

* **职责**：维护 `tasks.md` 和 `/tasks/` 目录。
* **能力**：
  * `create_task(description)`：生成唯一 ID，初始化 `tasks.md` 条目，创建 `/tasks/ID.json`。
  * `log_to_task(id, log_entry)`：将 Worker Agent 的操作日志即时追加到 `tasks/ID.json`。
  * `complete_task(id, result)`：标记任务完成状态。

---

## 5. 核心运行数据流

1. **启动与配置**：系统初始化，读取 `config.yaml` 连接 LLM。
2. **创建任务**：用户提出需求，**Task Agent** 创建记录。
3. **智能决策**：**Worker Agent** 根据系统 Prompt 中的可用技能列表决定使用哪一个，通过 **Skill Agent** 按需加载该技能的详细 MD 文档。
4. **ReAct 循环**：
   - **Thought**：LLM 分析当前状态并决定下一步行动
   - **Action**：生成 Python 代码 → 存入 `/temp_scripts`
   - **Observation**：执行 Shell 命令 → 获取 stdout/stderr
   - **Repeat**：基于观察结果继续推理，直到获得最终答案
5. **实时日志**：Worker 将每一步操作和结果传递给 **Task Agent**，实时更新 `/tasks/ID.json`。
6. **技能沉淀**：用户可将生成的 Python 脚本保存为技能，存储到 `/scripts/` 和 `/skills/` 目录。
7. **自我进化**：LLM 可调用 `update_self_profile` 和 `update_user_profile` 工具，动态调整自身行为和用户偏好。
8. **任务完成**：Task Agent 更新状态，WebUI 提示用户。

---

## 6. WebUI 界面规划

### 6.1 组件化架构
WebUI 采用组件化设计，主要包含以下独立组件：
- **Sidebar**：导航菜单（工作台、技能中心、任务历史、配置）
- **Header**：页面标题动态切换
- **Workbench**：聊天对话界面 + 输入框
- **Skills**：技能列表展示和管理
- **Tasks**：任务历史表格展示
- **Settings**：系统配置表单
- **Modals**：各种模态框（技能编辑、任务详情、脚本保存）

### 6.2 功能特性
* **工作台 (Workbench)**：
  - 聊天式对话界面，支持 Markdown 渲染
  - 左右分栏布局（聊天 70% : 日志 30%）
  - 流式输出显示 LLM 推理过程
  - 自动生成的 Python 代码可一键保存为技能
  
* **技能中心 (Skills)**：
  - 列表展示 `/skills/` 下的技能
  - 支持新增、编辑、删除技能
  - 技能描述使用 Markdown 格式
  
* **任务历史 (Tasks)**：
  - 侧边栏展示 `tasks.md` 索引
  - 点击可查看 `tasks/ID.json` 的详细日志
  - 显示任务状态（成功/失败/进行中）
  
* **配置 (Settings)**：
  - 修改 `config.yaml`
  - 支持 API Key、Base URL、Model 配置

* **脚本保存功能**：
  - 自动检测对话中的 Python 代码块
  - 在代码消息末尾添加 "保存为技能" 按钮
  - 保存后同时创建脚本文件和技能描述

---

## 7. 安全与限制 (Custom Instructions)

1. **路径隔离**：所有文件操作强制锁定在 `workspace` 目录。
2. **高危操作拦截**：`execute_shell` 检测到 `rm -rf`, `send_email` 等命令时，必须暂停并等待用户点击“允许”。
3. **流式安全**：SSE 流式传输使用标准 JSON 格式，防止 XSS 攻击。
4. **技能验证**：保存的脚本经过基本语法验证，确保可执行性。
5. **配置保护**：`config.yaml` 中的敏感信息（如 API Key）不会在前端显示。

---

## 8. 新增工具函数

### 8.1 `update_self_profile(content: str)`
- **功能**：更新 `self.md` 文件，修改 Clerk 的自我设定
- **使用场景**：当用户要求调整工作空间、环境信息或行为模式时
- **返回值**：操作结果描述

### 8.2 `update_user_profile(content: str)`
- **功能**：更新 `user.md` 文件，修改用户画像和偏好
- **使用场景**：当用户提供了新的个人信息、工作偏好或上下文信息时
- **返回值**：操作结果描述

这两个工具函数使 Clerk Agent 具备了**动态自我进化**的能力，能够根据对话上下文不断优化自身的服务体验。