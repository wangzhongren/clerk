// 核心 JS 逻辑
let currentTaskId = null;
let isProcessing = false;
let currentAssistantMessageContainer = null; // 存储整个助手消息容器
let currentStreamingText = ''; // 用于累积 LLM token
let hasFinalResponse = false; // 标记是否已收到最终响应
const MAX_CONVERSATION_TURNS = 50; // 最大对话轮数

// 从 localStorage 加载对话历史
let conversationHistory = loadConversationHistory();

document.addEventListener('DOMContentLoaded', () => {
    bindNavEvents();
    loadSkills();
    loadTasks();
    loadConfig();
    loadTaskHistoryToSettings(); // 加载任务历史到配置页面
    
    // 初始化页面时显示保存的对话历史
    renderSavedConversation();
    
    // 加载 Token 用量
    loadTokenUsage();
    
    // 确保初始状态干净
    currentAssistantMessageContainer = null;
    currentStreamingText = '';
    hasFinalResponse = false;
});

function bindNavEvents() {
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', function() {
            document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
            this.classList.add('active');
            
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            const tabId = this.getAttribute('data-tab');
            document.getElementById(tabId).classList.add('active');
            document.getElementById('page-title').textContent = this.textContent.trim();
            
            // 切换到不同页面时刷新对应数据
            if (tabId === 'settings') {
                loadTaskHistoryToSettings();
            } else if (tabId === 'tasks') {
                loadTaskList();
            }
        });
    });
    
    const submitTaskBtn = document.getElementById('submit-task');
    const userInput = document.getElementById('user-input');
    const aiConfigForm = document.getElementById('ai-config-form');
    const feishuConfigForm = document.getElementById('feishu-config-form');
    
    if (submitTaskBtn) {
        submitTaskBtn.addEventListener('click', submitTask);
    }
    if (userInput) {
        userInput.addEventListener('keypress', e => { if (e.key === 'Enter') submitTask(); });
    }
    if (aiConfigForm) {
        aiConfigForm.addEventListener('submit', saveAIConfig);
    }
    if (feishuConfigForm) {
        feishuConfigForm.addEventListener('submit', saveFeishuConfig);
    }
}

// 从 localStorage 加载对话历史（带数据校验）
function loadConversationHistory() {
    try {
        const saved = localStorage.getItem('clerk_conversation_history');
        if (!saved) return [];
        const parsed = JSON.parse(saved);
        if (!Array.isArray(parsed)) return [];
        // 验证每条消息格式
        return parsed.filter(msg => 
            typeof msg === 'object' && 
            (msg.sender === 'user' || msg.sender === 'assistant') && 
            typeof msg.message === 'string'
        );
    } catch (e) {
        console.warn('Failed to load conversation history from localStorage:', e);
        return [];
    }
}

// 保存对话历史到 localStorage
function saveConversationHistory() {
    try {
        const trimmedHistory = conversationHistory.slice(-MAX_CONVERSATION_TURNS);
        localStorage.setItem('clerk_conversation_history', JSON.stringify(trimmedHistory));
    } catch (e) {
        console.warn('Failed to save conversation history to localStorage:', e);
    }
}

// 渲染保存的对话历史
function renderSavedConversation() {
    const container = document.getElementById('conversation-history');
    if (!container) return;
    
    container.innerHTML = '';
    
    conversationHistory.forEach(msg => {
        // 历史消息直接渲染，不触发流式状态
        const div = document.createElement('div');
        div.className = `message-container ${msg.sender}`;
        const avatar = msg.sender === 'user' ? '我' : 'C';
        // 安全处理 message 内容
        const safeMessage = msg.message || '';
        div.innerHTML = `<div class="message-avatar">${avatar}</div><div class="message-content">${marked.parse(safeMessage)}</div>`;
        container.appendChild(div);
    });
    
    scrollToBottom();
}

// --- 工作台逻辑 ---
async function submitTask() {
    if (isProcessing) return;
    const inputEl = document.getElementById('user-input');
    const submitBtn = document.getElementById('submit-task');
    const text = inputEl.value.trim();
    if (!text) return;

    // 立即禁用输入框和按钮
    addMessageToHistory('user', text);
    inputEl.value = '';
    isProcessing = true;
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = '执行中...';
    }

    // 重置状态
    currentAssistantMessageContainer = null;
    currentStreamingText = '';
    hasFinalResponse = false;

    // 检查是否接近最大轮数限制
    let shouldSummarize = false;
    let enhancedInput = text;
    
    if (conversationHistory.length >= MAX_CONVERSATION_TURNS - 1) {
        shouldSummarize = true;
        enhancedInput = `【重要】当前对话已接近${MAX_CONVERSATION_TURNS}轮限制，请执行以下操作：
1. 总结当前任务的整体进展和已完成的工作
2. 分析当前遇到的问题或挑战（如果有）
3. 提出明确的下一步行动计划和未来方向
4. 给出具体的建议或结论

原始用户请求：${text}`;
    }

    // 1. 创建任务 (如果还没任务 ID)
    if (!currentTaskId) {
        try {
            const resp = await fetch('/api/tasks', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({description: text})
            });
            const data = await resp.json();
            if (data.task_id) currentTaskId = data.task_id;
            else throw new Error(data.error);
        } catch (e) {
            addMessageToHistory('assistant', '❌ 创建任务失败：' + e.message);
            resetInputState(); return;
        }
    }

    // 2. 构建完整的对话历史（整段对话）
    // 注意：conversationHistory 已经包含了最新的用户消息，无需再传 input
    const history = conversationHistory.map(msg => ({
        role: msg.sender === 'user' ? 'user' : 'assistant',
        content: msg.message
    }));

    // 3. 执行任务 (流式)
    try {
        const response = await fetch('/api/execute', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                task_id: currentTaskId, 
                history: history
                // 不再传递 input 参数，后端从 history 最后一条获取
            })
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = JSON.parse(line.slice(6));
                    if (data.type === 'llm_token') {
                        // 累积 LLM token，稍后统一渲染
                        currentStreamingText += data.content;
                        renderCurrentStreamingText();
                    } else if (data.type === 'function_result') {
                        // 函数调用结果，创建独立块（不保存到历史）
                        flushCurrentStreamingText(); // 先刷新累积的 LLM 文本
                        addAssistantMessagePart('function', `执行 ${data.function} 的结果: ${data.result}`);
                    } else if (data.type === 'function_error') {
                        // 函数调用错误，创建独立块（不保存到历史）
                        flushCurrentStreamingText(); // 先刷新累积的 LLM 文本
                        addAssistantMessagePart('error', `执行 ${data.function} 时出错: ${data.error}`);
                    } else if (data.type === 'observation') {
                        // 观察结果，创建独立块（不保存到历史）
                        flushCurrentStreamingText(); // 先刷新累积的 LLM 文本
                        addAssistantMessagePart('observation', `Observation: ${data.content}`);
                    } else if (data.type === 'final_response') {
                        // 最终响应，刷新累积文本并添加最终响应
                        flushCurrentStreamingText();
                        addAssistantMessagePart('final', data.content);
                        hasFinalResponse = true;
                        // 只有最终响应才保存到历史记录
                        conversationHistory.push({ sender: 'assistant', message: data.content });
                        checkAndCleanupHistory();
                        saveConversationHistory();
                    } else if (data.type === 'iteration_start') {
                        // 迭代开始，可以显示迭代信息（不保存到历史）
                        flushCurrentStreamingText(); // 先刷新累积的 LLM 文本
                        addAssistantMessagePart('info', `--- 迭代 ${data.iteration} ---`);
                    }
                }
            }
        }
        
        // 如果没有收到 final_response，将累积的文本作为最终响应
        if (!hasFinalResponse && currentStreamingText) {
            flushCurrentStreamingText();
            const finalContent = currentStreamingText;
            addAssistantMessagePart('final', finalContent);
            // 保存到历史记录
            conversationHistory.push({ sender: 'assistant', message: finalContent });
            checkAndCleanupHistory();
            saveConversationHistory();
        }
        
    } catch (e) {
        addMessageToHistory('assistant', '❌ 执行错误：' + e.message);
    } finally {
        resetInputState();
        loadTasks();
        loadTokenUsage(); // 任务完成后自动刷新 Token 用量
    }
}

function resetInputState() {
    isProcessing = false;
    const submitBtn = document.getElementById('submit-task');
    if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = '执行';
    }
    currentAssistantMessageContainer = null;
    currentStreamingText = '';
    hasFinalResponse = false;
}

// 渲染当前累积的 LLM 流式文本（临时显示）
function renderCurrentStreamingText() {
    if (!currentAssistantMessageContainer) {
        // 创建助手消息容器
        const container = document.getElementById('conversation-history');
        if (!container) return;
        currentAssistantMessageContainer = document.createElement('div');
        currentAssistantMessageContainer.className = 'message-container assistant';
        currentAssistantMessageContainer.innerHTML = `<div class="message-avatar">C</div><div class="message-content"></div>`;
        container.appendChild(currentAssistantMessageContainer);
    }
    
    const contentDiv = currentAssistantMessageContainer.querySelector('.message-content');
    // 找到或创建 LLM 流式文本的 div
    let llmDiv = contentDiv.querySelector('.message-part-llm-temp');
    if (!llmDiv) {
        llmDiv = document.createElement('div');
        llmDiv.className = 'message-part message-part-llm-temp';
        llmDiv.style.fontSize = '12px';
        llmDiv.style.lineHeight = '1.4';
        llmDiv.style.color = '#666';
        llmDiv.style.marginBottom = '8px';
        llmDiv.style.padding = '6px 10px';
        llmDiv.style.backgroundColor = '#f9f9f9';
        llmDiv.style.borderLeft = '2px solid #ddd';
        contentDiv.appendChild(llmDiv);
    }
    
    // 更新 LLM 流式文本内容
    llmDiv.innerHTML = marked.parse(currentStreamingText);
    scrollToBottom();
}

// 刷新累积的 LLM 文本，将其转换为永久块
function flushCurrentStreamingText() {
    if (!currentStreamingText.trim()) return;
    
    if (!currentAssistantMessageContainer) {
        // 如果还没有容器，先创建
        const container = document.getElementById('conversation-history');
        if (!container) return;
        currentAssistantMessageContainer = document.createElement('div');
        currentAssistantMessageContainer.className = 'message-container assistant';
        currentAssistantMessageContainer.innerHTML = `<div class="message-avatar">C</div><div class="message-content"></div>`;
        container.appendChild(currentAssistantMessageContainer);
    }
    
    const contentDiv = currentAssistantMessageContainer.querySelector('.message-content');
    // 移除临时的 LLM div
    const tempLlmDiv = contentDiv.querySelector('.message-part-llm-temp');
    if (tempLlmDiv) {
        tempLlmDiv.remove();
    }
    
    // 创建永久的 LLM 块
    const llmDiv = document.createElement('div');
    llmDiv.className = 'message-part message-part-llm';
    llmDiv.style.fontSize = '12px';
    llmDiv.style.lineHeight = '1.4';
    llmDiv.style.color = '#666';
    llmDiv.style.marginBottom = '8px';
    llmDiv.style.padding = '6px 10px';
    llmDiv.style.backgroundColor = '#f9f9f9';
    llmDiv.style.borderLeft = '2px solid #ddd';
    llmDiv.innerHTML = marked.parse(currentStreamingText);
    contentDiv.appendChild(llmDiv);
    
    // 重置累积文本
    currentStreamingText = '';
    scrollToBottom();
}

// 添加助手消息的不同部分
function addAssistantMessagePart(type, content) {
    const container = document.getElementById('conversation-history');
    if (!container) return;
    
    // 如果还没有助手消息容器，创建一个新的
    if (!currentAssistantMessageContainer) {
        currentAssistantMessageContainer = document.createElement('div');
        currentAssistantMessageContainer.className = 'message-container assistant';
        currentAssistantMessageContainer.innerHTML = `<div class="message-avatar">C</div><div class="message-content"></div>`;
        container.appendChild(currentAssistantMessageContainer);
    }
    
    const contentDiv = currentAssistantMessageContainer.querySelector('.message-content');
    
    // 根据类型创建不同的 div
    const partDiv = document.createElement('div');
    partDiv.className = `message-part message-part-${type}`;
    
    // 设置样式
    if (type === 'final') {
        // 最终响应使用正常字体
        partDiv.style.fontSize = '14px';
        partDiv.style.lineHeight = '1.6';
        partDiv.style.marginBottom = '12px';
        partDiv.innerHTML = marked.parse(content);
    } else {
        // 其他类型使用小字体
        partDiv.style.fontSize = '12px';
        partDiv.style.lineHeight = '1.4';
        partDiv.style.marginBottom = '8px';
        partDiv.style.padding = '6px 10px';
        
        if (type === 'error') {
            partDiv.style.color = '#d32f2f';
            partDiv.style.backgroundColor = '#ffebee';
            partDiv.style.borderLeft = '2px solid #f44336';
        } else if (type === 'function') {
            partDiv.style.color = '#1976d2';
            partDiv.style.backgroundColor = '#e3f2fd';
            partDiv.style.borderLeft = '2px solid #2196f3';
        } else if (type === 'observation') {
            partDiv.style.color = '#388e3c';
            partDiv.style.backgroundColor = '#e8f5e8';
            partDiv.style.borderLeft = '2px solid #4caf50';
        } else if (type === 'info') {
            partDiv.style.color = '#7b1fa2';
            partDiv.style.backgroundColor = '#f3e5f5';
            partDiv.style.borderLeft = '2px solid #9c27b0';
            partDiv.style.fontWeight = 'bold';
        } else if (type === 'llm') {
            partDiv.style.color = '#666';
            partDiv.style.backgroundColor = '#f9f9f9';
            partDiv.style.borderLeft = '2px solid #ddd';
        }
        
        if (type === 'llm') {
            partDiv.innerHTML = marked.parse(content);
        } else {
            partDiv.textContent = content;
        }
    }
    
    contentDiv.appendChild(partDiv);
    scrollToBottom();
}

function scrollToBottom() {
    const container = document.getElementById('conversation-history');
    if (container) {
        requestAnimationFrame(() => {
            container.scrollTo({
                top: container.scrollHeight,
                behavior: 'smooth'
            });
        });
    }
}

function addMessageToHistory(sender, message, isStreaming = false) {
    const container = document.getElementById('conversation-history');
    if (!container) return;
    
    if (sender === 'user') {
        const div = document.createElement('div');
        div.className = 'message-container user';
        div.innerHTML = `<div class="message-avatar">我</div><div class="message-content">${marked.parse(message)}</div>`;
        container.appendChild(div);
        
        // 添加到历史记录
        conversationHistory.push({ sender: 'user', message: message });
        checkAndCleanupHistory();
        saveConversationHistory();
        
        currentAssistantMessageContainer = null;
        currentStreamingText = '';
        hasFinalResponse = false;
    } else {
        // 对于非流式的完整消息（如错误消息），直接创建完整消息
        const div = document.createElement('div');
        div.className = 'message-container assistant';
        div.innerHTML = `<div class="message-avatar">C</div><div class="message-content">${marked.parse(message)}</div>`;
        container.appendChild(div);
        
        // 添加到历史记录（错误消息等特殊情况）
        conversationHistory.push({ sender: 'assistant', message: message });
        checkAndCleanupHistory();
        saveConversationHistory();
        
        currentAssistantMessageContainer = null;
        currentStreamingText = '';
        hasFinalResponse = false;
    }
    scrollToBottom();
}

// 检查并清理对话历史
function checkAndCleanupHistory() {
    const needsCleanup = localStorage.getItem('clerk_needs_cleanup') === 'true';
    
    if (needsCleanup && conversationHistory.length > 0) {
        const keepCount = Math.max(0, MAX_CONVERSATION_TURNS - 2);
        conversationHistory = conversationHistory.slice(-keepCount);
        localStorage.removeItem('clerk_needs_cleanup');
        saveConversationHistory();
    }
    else if (conversationHistory.length > MAX_CONVERSATION_TURNS) {
        conversationHistory = conversationHistory.slice(-(MAX_CONVERSATION_TURNS));
        saveConversationHistory();
    }
}

// --- 技能中心逻辑 ---
async function loadSkills() {
    const listEl = document.getElementById('skills-list');
    if (!listEl) return;
    try {
        const resp = await fetch('/api/skills');
        const data = await resp.json();
        listEl.innerHTML = '';
        if (data.skills.length === 0) listEl.innerHTML = '暂无技能。';
        
        data.skills.forEach(skill => {
            const card = document.createElement('div');
            card.className = 'skill-card';
            card.innerHTML = `
                <div class="skill-info"><h3>${skill}</h3></div>
                <div class="skill-actions">
                    <button class="btn-outline" onclick="editSkill('${skill}')">编辑</button>
                </div>
            `;
            listEl.appendChild(card);
        });
    } catch (e) { listEl.innerHTML = '加载失败：' + e.message; }
}

async function editSkill(name) {
    try {
        const resp = await fetch(`/api/skills/${name}`);
        const data = await resp.json();
        openSkillModal(name, data.content);
    } catch (e) { alert('加载失败：' + e.message); }
}

async function saveSkill() {
    const name = document.getElementById('skill-name').value.trim();
    const content = document.getElementById('skill-content').value.trim();
    if (!name || !content) return alert('请填写名称和内容');
    
    try {
        const resp = await fetch('/api/skills', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name, content})
        });
        alert('保存成功');
        closeSkillModal();
        loadSkills();
    } catch (e) { alert('保存失败：' + e.message); }
}

async function deleteSkill() {
    const name = document.getElementById('skill-name').value.trim();
    if (!confirm(`确定删除技能 ${name} 吗？`)) return;
    try {
        await fetch(`/api/skills/${name}`, {method: 'DELETE'});
        closeSkillModal();
        loadSkills();
    } catch (e) { alert('删除失败：' + e.message); }
}

function openSkillModal(name='', content='') {
    document.getElementById('skill-name').value = name;
    document.getElementById('skill-content').value = content;
    const deleteBtn = document.getElementById('delete-skill-btn');
    if (deleteBtn) {
        deleteBtn.style.display = name ? 'inline-block' : 'none';
    }
    document.getElementById('skillModal').style.display = 'flex';
}
function closeSkillModal() { 
    const modal = document.getElementById('skillModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

// --- 任务历史逻辑 ---
let currentViewTaskId = null; // 当前查看的任务 ID

// 加载任务到独立的任务列表页面（调用新 API，后端已按时间倒序）
async function loadTaskList() {
    const container = document.getElementById('task-list-container');
    if (!container) return;
    try {
        const resp = await fetch('/api/tasks/list');
        const data = await resp.json();
        container.innerHTML = '';
        
        // 后端返回格式：{ "tasks": [...] }，无需检查 success 字段
        if (!data.tasks || !Array.isArray(data.tasks) || data.tasks.length === 0) {
            container.innerHTML = '<div style="padding:40px; text-align:center; color:#888;">暂无任务历史</div>';
            return;
        }

        // 后端已按时间倒序排列，直接使用
        data.tasks.forEach(task => {
            const item = document.createElement('div');
            item.className = 'task-history-item';
            
            // 安全获取字段值，兼容多种字段名
            const taskName = task.name || task.description || '未命名任务';
            const taskStatus = task.status || 'Unknown';
            const taskId = task.id || task.task_id || 'unknown';
            const taskTime = task.created_at || task.createdAt || task.timestamp || '未知时间';
            
            let badgeClass = taskStatus === 'Success' ? 'badge-success' : (taskStatus === 'Failed' ? 'badge-danger' : 'badge-warning');
            
            item.innerHTML = `
                <div class="task-history-info">
                    <div class="task-history-title">${taskName}</div>
                    <div class="task-history-meta">ID: ${taskId} | ${taskTime}</div>
                </div>
                <div class="task-history-status">
                    <span class="badge ${badgeClass}">${taskStatus}</span>
                </div>
            `;
            item.onclick = () => viewTaskDetail(taskId);
            container.appendChild(item);
        });
    } catch (e) { 
        container.innerHTML = '<div style="padding:40px; text-align:center; color:#d32f2f;">加载失败：' + e.message + '</div>'; 
    }
}

async function loadTasks() {
    const tbody = document.getElementById('tasks-table-body');
    if (!tbody) return;
    try {
        const resp = await fetch('/api/tasks');
        const data = await resp.json();
        tbody.innerHTML = '';
        if (data.tasks.length === 0) tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;">暂无任务</td></tr>';

        data.tasks.forEach(task => {
            const row = document.createElement('tr');
            let badgeClass = task.status === 'Success' ? 'badge-success' : (task.status === 'Failed' ? 'badge-danger' : 'badge-warning');
            row.innerHTML = `
                <td>${task.id}</td>
                <td>${task.created_at}</td>
                <td>${task.description}</td>
                <td><span class="badge ${badgeClass}">${task.status}</span></td>
                <td><button class="btn-outline" onclick="viewTaskDetail('${task.id}')">详情</button></td>
            `;
            tbody.appendChild(row);
        });
    } catch (e) { tbody.innerHTML = '<tr><td colspan="5">加载失败</td></tr>'; }
}

// 加载任务历史到配置页面
async function loadTaskHistoryToSettings() {
    const listEl = document.getElementById('task-history-list');
    if (!listEl) return;
    try {
        const resp = await fetch('/api/tasks');
        const data = await resp.json();
        listEl.innerHTML = '';
        if (data.tasks.length === 0) {
            listEl.innerHTML = '<div style="padding:20px; text-align:center; color:#888;">暂无任务历史</div>';
            return;
        }

        // 只显示最近 10 个任务
        const recentTasks = data.tasks.slice(0, 10);
        recentTasks.forEach(task => {
            const item = document.createElement('div');
            item.className = 'task-history-item';
            let badgeClass = task.status === 'Success' ? 'badge-success' : (task.status === 'Failed' ? 'badge-danger' : 'badge-warning');
            item.innerHTML = `
                <div class="task-history-info">
                    <div class="task-history-title">${task.description}</div>
                    <div class="task-history-meta">ID: ${task.id} | ${task.created_at}</div>
                </div>
                <div class="task-history-status">
                    <span class="badge ${badgeClass}">${task.status}</span>
                </div>
            `;
            item.onclick = () => viewTaskDetail(task.id);
            listEl.appendChild(item);
        });
    } catch (e) { 
        listEl.innerHTML = '<div style="padding:20px; text-align:center; color:#d32f2f;">加载失败</div>'; 
    }
}

async function viewTaskDetail(taskId) {
    currentViewTaskId = taskId; // 保存当前任务 ID
    const contentEl = document.getElementById('task-detail-content');
    const titleEl = document.getElementById('task-detail-title');
    const modalEl = document.getElementById('taskDetailModal');
    if (!contentEl || !titleEl || !modalEl) return;
    
    contentEl.innerHTML = '加载中...';
    titleEl.textContent = `任务详情 - ${taskId}`;
    modalEl.style.display = 'flex';

    try {
        // 优先尝试新接口，兼容旧接口
        let task;
        try {
            const resp = await fetch(`/api/tasks/${taskId}`);
            task = await resp.json();
        } catch (e) {
            // 如果新接口失败，尝试从任务列表查找
            const listResp = await fetch('/api/tasks/list');
            const listData = await listResp.json();
            // 新 API 返回格式：{ "tasks": [...] }，无 success 字段
            if (listData.tasks && Array.isArray(listData.tasks)) {
                task = listData.tasks.find(t => (t.id || t.task_id) === taskId) || {};
            } else {
                throw new Error('任务不存在');
            }
        }
        
        // 安全获取字段值，兼容多种字段名
        const description = task.description || task.name || '未命名任务';
        const status = task.status || 'Unknown';
        const result = task.result || task.output || '无';
        const createdAt = task.created_at || task.createdAt || task.timestamp || '未知时间';
        const logs = task.logs || task.log || task.logs || [];
        
        let logsHtml = '<pre style="background:#f4f4f4; padding:10px; border-radius:4px; overflow-x:auto; max-height:400px; overflow-y:auto;">';
        if(logs && logs.length > 0) {
            logs.forEach(log => {
                const timestamp = log.timestamp || log.time || 'unknown';
                const entry = log.entry || log.content || log;
                logsHtml += `[${timestamp}] ${JSON.stringify(entry, null, 2)}\n`;
            });
        } else {
            logsHtml += '暂无日志';
        }
        logsHtml += '</pre>';

        contentEl.innerHTML = `
            <p><strong>描述:</strong> ${description}</p>
            <p><strong>状态:</strong> <span class="badge ${status === 'Success' ? 'badge-success' : (status === 'Failed' ? 'badge-danger' : 'badge-warning')}">${status}</span></p>
            <p><strong>开始时间:</strong> ${createdAt}</p>
            <p><strong>结果:</strong> ${result}</p>
            <p><strong>日志:</strong></p>
            ${logsHtml}
        `;
        
        // 根据任务状态控制"总结成技能"按钮的显示（仅成功任务显示）
        const summarizeBtn = document.querySelector('#taskDetailModal button[onclick="openSummarizeModal()"]');
        if (summarizeBtn) {
            summarizeBtn.style.display = (status === 'Success') ? 'inline-block' : 'none';
        }
    } catch (e) { 
        contentEl.innerHTML = '<div style="padding:40px; text-align:center; color:#d32f2f;">加载详情失败：' + e.message + '</div>'; 
    }
}
function closeTaskDetailModal() { 
    const modal = document.getElementById('taskDetailModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

// --- 总结为技能功能 ---
function openSummarizeModal() {
    if (!currentViewTaskId) {
        alert('请先选择一个任务');
        return;
    }
    document.getElementById('summarize-skill-name').value = '';
    document.getElementById('summarize-skill-desc').value = '';
    document.getElementById('summarize-skill-content').value = '技能内容将在保存时自动生成';
    document.getElementById('summarizeModal').style.display = 'flex';
}

function closeSummarizeModal() {
    const modal = document.getElementById('summarizeModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

async function confirmSummarizeSkill() {
    const skillName = document.getElementById('summarize-skill-name').value.trim();
    const skillDesc = document.getElementById('summarize-skill-desc').value.trim();
    
    if (!skillName || !skillDesc) {
        alert('请填写技能名称和描述');
        return;
    }
    
    if (!currentViewTaskId) {
        alert('任务 ID 丢失，请重新打开任务详情');
        return;
    }
    
    try {
        const resp = await fetch('/api/tasks/summarize', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                task_id: currentViewTaskId,
                skill_name: skillName,
                skill_description: skillDesc
            })
        });
        
        const data = await resp.json();
        if (data.error) {
            alert('总结失败：' + data.error);
        } else {
            alert(data.message);
            closeSummarizeModal();
            closeTaskDetailModal();
            loadSkills(); // 刷新技能列表
            loadTokenUsage(); // 总结任务为技能后自动刷新 Token 用量
        }
    } catch (e) {
        alert('总结失败：' + e.message);
    }
}

// --- 配置逻辑 ---
async function loadConfig() {
    try {
        const resp = await fetch('/api/config');
        const config = await resp.json();
        // AI 配置
        const apiKeyEl = document.getElementById('api-key');
        const baseUrlEl = document.getElementById('base-url');
        const modelEl = document.getElementById('model');
        if (apiKeyEl) apiKeyEl.value = config.api_key || '';
        if (baseUrlEl) baseUrlEl.value = config.base_url || '';
        if (modelEl) modelEl.value = config.model || '';
        // 飞书配置
        const appIdEl = document.getElementById('feishu-app-id');
        const appSecretEl = document.getElementById('feishu-app-secret');
        const encryptKeyEl = document.getElementById('feishu-encrypt-key');
        const socketEnabledEl = document.getElementById('feishu-socket-enabled');
        if (appIdEl) appIdEl.value = config.feishu_app_id || '';
        if (appSecretEl) appSecretEl.value = config.feishu_app_secret || '';
        if (encryptKeyEl) encryptKeyEl.value = config.feishu_encrypt_key || '';
        if (socketEnabledEl) socketEnabledEl.checked = config.feishu_socket_enabled || false;
    } catch (e) { console.error('加载配置失败'); }
}

async function saveAIConfig(e) {
    e.preventDefault();
    const apiKeyEl = document.getElementById('api-key');
    const baseUrlEl = document.getElementById('base-url');
    const modelEl = document.getElementById('model');
    const config = {
        api_key: apiKeyEl ? apiKeyEl.value : '',
        base_url: baseUrlEl ? baseUrlEl.value : '',
        model: modelEl ? modelEl.value : ''
    };
    try {
        await fetch('/api/config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(config)
        });
        alert('AI 配置已保存');
    } catch (e) { alert('保存失败：' + e.message); }
}

async function saveFeishuConfig(e) {
    e.preventDefault();
    const appIdEl = document.getElementById('feishu-app-id');
    const appSecretEl = document.getElementById('feishu-app-secret');
    const encryptKeyEl = document.getElementById('feishu-encrypt-key');
    const socketEnabledEl = document.getElementById('feishu-socket-enabled');
    const config = {
        feishu_app_id: appIdEl ? appIdEl.value : '',
        feishu_app_secret: appSecretEl ? appSecretEl.value : '',
        feishu_encrypt_key: encryptKeyEl ? encryptKeyEl.value : '',
        feishu_socket_enabled: socketEnabledEl ? socketEnabledEl.checked : false
    };
    try {
        await fetch('/api/config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(config)
        });
        alert('飞书配置已保存');
        // 显示状态
        const statusEl = document.getElementById('feishu-status');
        if (statusEl) {
            if (config.feishu_socket_enabled) {
                statusEl.textContent = '✅ 飞书 Socket Mode 已启用，请重启服务以生效';
                statusEl.style.color = '#28a745';
            } else {
                statusEl.textContent = '⚠️ 飞书 Socket Mode 已禁用';
                statusEl.style.color = '#666';
            }
        }
    } catch (e) { 
        alert('保存失败：' + e.message);
        const statusEl = document.getElementById('feishu-status');
        if (statusEl) {
            statusEl.textContent = '❌ 保存失败';
            statusEl.style.color = '#dc3545';
        }
    }
}

// 页面即将卸载时，保存未完成的流式文本
window.addEventListener('beforeunload', () => {
    if (currentStreamingText && !hasFinalResponse) {
        // 强制保存未完成的流式文本
        conversationHistory.push({ sender: 'assistant', message: currentStreamingText });
        try {
            const trimmedHistory = conversationHistory.slice(-MAX_CONVERSATION_TURNS);
            localStorage.setItem('clerk_conversation_history', JSON.stringify(trimmedHistory));
        } catch (e) {
            console.warn('Failed to save unfinished streaming text:', e);
        }
    }
});// --- Token 用量管理 ---

// 加载并显示 Token 用量
async function loadTokenUsage() {
    try {
        const resp = await fetch('/api/token-usage');
        const data = await resp.json();
        
        // 更新显示
        const promptEl = document.getElementById('token-prompt');
        const completionEl = document.getElementById('token-completion');
        const totalEl = document.getElementById('token-total');
        const sessionsEl = document.getElementById('token-sessions');
        
        if (promptEl) promptEl.textContent = (data.prompt_tokens || 0).toLocaleString();
        if (completionEl) completionEl.textContent = (data.completion_tokens || 0).toLocaleString();
        if (totalEl) totalEl.textContent = (data.total_tokens || 0).toLocaleString();
        if (sessionsEl) sessionsEl.textContent = (data.session_count || 0).toLocaleString();
    } catch (e) {
        console.warn('加载 Token 用量失败:', e);
    }
}

// 重置 Token 用量
async function resetTokenUsage() {
    if (!confirm('确定要重置 Token 用量统计吗？此操作不可恢复。')) return;
    
    try {
        const resp = await fetch('/api/token-usage/reset', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        });
        const data = await resp.json();
        alert(data.message || 'Token 用量已重置');
        loadTokenUsage();
    } catch (e) {
        alert('重置失败：' + e.message);
    }
}

// 注意：DOMContentLoaded 已在文件开头定义，loadTokenUsage() 已在那里调用

