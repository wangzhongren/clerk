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
    
    // 初始化页面时显示保存的对话历史
    renderSavedConversation();
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
        });
    });
    document.getElementById('submit-task').addEventListener('click', submitTask);
    document.getElementById('user-input').addEventListener('keypress', e => { if (e.key === 'Enter') submitTask(); });
    document.getElementById('config-form').addEventListener('submit', saveConfig);
}

// 从 localStorage 加载对话历史
function loadConversationHistory() {
    try {
        const saved = localStorage.getItem('clerk_conversation_history');
        return saved ? JSON.parse(saved) : [];
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
    container.innerHTML = '';
    
    conversationHistory.forEach(msg => {
        // 历史消息直接渲染，不触发流式状态
        const div = document.createElement('div');
        div.className = `message-container ${msg.sender}`;
        const avatar = msg.sender === 'user' ? '我' : 'C';
        div.innerHTML = `<div class="message-avatar">${avatar}</div><div class="message-content">${marked.parse(msg.message)}</div>`;
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
    submitBtn.disabled = true;
    submitBtn.textContent = '执行中...';

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
                        // 函数调用结果，创建独立块
                        flushCurrentStreamingText(); // 先刷新累积的 LLM 文本
                        addAssistantMessagePart('function', `执行 ${data.function} 的结果: ${data.result}`);
                    } else if (data.type === 'function_error') {
                        // 函数调用错误，创建独立块
                        flushCurrentStreamingText(); // 先刷新累积的 LLM 文本
                        addAssistantMessagePart('error', `执行 ${data.function} 时出错: ${data.error}`);
                    } else if (data.type === 'observation') {
                        // 观察结果，创建独立块
                        flushCurrentStreamingText(); // 先刷新累积的 LLM 文本
                        addAssistantMessagePart('observation', `Observation: ${data.content}`);
                    } else if (data.type === 'final_response') {
                        // 最终响应，刷新累积文本并添加最终响应
                        flushCurrentStreamingText();
                        addAssistantMessagePart('final', data.content);
                        hasFinalResponse = true;
                    } else if (data.type === 'iteration_start') {
                        // 迭代开始，可以显示迭代信息
                        flushCurrentStreamingText(); // 先刷新累积的 LLM 文本
                        addAssistantMessagePart('info', `--- 迭代 ${data.iteration} ---`);
                    }
                }
            }
        }
        
    } catch (e) {
        addMessageToHistory('assistant', '❌ 执行错误：' + e.message);
    } finally {
        // 确保最后的流式文本被保存
        if (!hasFinalResponse && currentStreamingText) {
            flushCurrentStreamingText();
            // 如果没有收到 final_response，将累积的文本作为最终响应
            conversationHistory.push({ sender: 'assistant', message: currentStreamingText });
            checkAndCleanupHistory();
            saveConversationHistory();
        }
        resetInputState();
        loadTasks();
    }
}

function resetInputState() {
    isProcessing = false;
    const submitBtn = document.getElementById('submit-task');
    submitBtn.disabled = false;
    submitBtn.textContent = '执行';
    currentAssistantMessageContainer = null;
    currentStreamingText = '';
    hasFinalResponse = false;
}

// 渲染当前累积的 LLM 流式文本（临时显示）
function renderCurrentStreamingText() {
    if (!currentAssistantMessageContainer) {
        // 创建助手消息容器
        const container = document.getElementById('conversation-history');
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
        
        // 将最终响应添加到历史记录
        conversationHistory.push({ sender: 'assistant', message: content });
        checkAndCleanupHistory();
        saveConversationHistory();
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
        
        // 添加到历史记录
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
    document.getElementById('delete-skill-btn').style.display = name ? 'inline-block' : 'none';
    document.getElementById('skillModal').style.display = 'flex';
}
function closeSkillModal() { document.getElementById('skillModal').style.display = 'none'; }

// --- 任务历史逻辑 ---
async function loadTasks() {
    const tbody = document.getElementById('tasks-table-body');
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

async function viewTaskDetail(taskId) {
    const contentEl = document.getElementById('task-detail-content');
    contentEl.innerHTML = '加载中...';
    document.getElementById('task-detail-title').textContent = `任务详情 - ${taskId}`;
    document.getElementById('taskDetailModal').style.display = 'flex';

    try {
        const resp = await fetch(`/api/tasks/${taskId}`);
        const task = await resp.json();
        
        let logsHtml = '<pre style="background:#f4f4f4; padding:10px; border-radius:4px; overflow-x:auto;">';
        if(task.logs && task.logs.length > 0) {
            task.logs.forEach(log => {
                logsHtml += `[${log.timestamp}] ${JSON.stringify(log.entry)}\n`;
            });
        } else {
            logsHtml += '暂无日志';
        }
        logsHtml += '</pre>';

        contentEl.innerHTML = `
            <p><strong>描述:</strong> ${task.description}</p>
            <p><strong>状态:</strong> ${task.status}</p>
            <p><strong>结果:</strong> ${task.result || '无'}</p>
            <p><strong>日志:</strong></p>
            ${logsHtml}
        `;
    } catch (e) { contentEl.innerHTML = '加载详情失败：' + e.message; }
}
function closeTaskDetailModal() { document.getElementById('taskDetailModal').style.display = 'none'; }

// --- 配置逻辑 ---
async function loadConfig() {
    try {
        const resp = await fetch('/api/config');
        const config = await resp.json();
        document.getElementById('api-key').value = config.api_key || '';
        document.getElementById('base-url').value = config.base_url || '';
        document.getElementById('model').value = config.model || '';
    } catch (e) { console.error('加载配置失败'); }
}

async function saveConfig(e) {
    e.preventDefault();
    const config = {
        api_key: document.getElementById('api-key').value,
        base_url: document.getElementById('base-url').value,
        model: document.getElementById('model').value
    };
    try {
        await fetch('/api/config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(config)
        });
        alert('配置已保存');
    } catch (e) { alert('保存失败：' + e.message); }
}