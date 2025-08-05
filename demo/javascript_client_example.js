/**
 * JavaScript客户端示例 - 按照设计文档规范实现
 * 
 * 展示如何在浏览器环境中使用 /api/v1/chat/stream 接口进行确认交互
 */

class StandardChatStreamClient {
    /**
     * 初始化客户端
     * @param {string} baseUrl - API服务器地址
     */
    constructor(baseUrl = 'http://localhost:8000') {
        this.baseUrl = baseUrl;
    }

    /**
     * 发送任务并处理确认流程
     * @param {string} task - 要执行的任务
     * @param {string} sessionId - 会话ID
     * @returns {Promise<boolean>} 是否成功完成
     */
    async sendTaskWithConfirmation(task, sessionId) {
        console.log(`发送任务: ${task}`);
        console.log(`会话ID: ${sessionId}`);

        try {
            const response = await fetch(`${this.baseUrl}/api/v1/chat/stream`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: task,
                    session_id: sessionId
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            return await this.processStreamResponse(response, sessionId);

        } catch (error) {
            console.error(`任务执行失败: ${error.message}`);
            return false;
        }
    }

    /**
     * 处理流式响应
     * @param {Response} response - Fetch响应对象
     * @param {string} sessionId - 会话ID
     * @returns {Promise<boolean>} 处理结果
     */
    async processStreamResponse(response, sessionId) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        try {
            while (true) {
                const { done, value } = await reader.read();
                
                if (done) {
                    break;
                }

                const chunk = decoder.decode(value, { stream: true });
                const lines = chunk.split('\n');

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const chunkData = JSON.parse(line.substring(6));
                            const chunkType = chunkData.chunk_type || 'content';

                            console.log(`收到chunk: ${chunkType}`);

                            if (chunkType === 'confirmation_request') {
                                // 处理确认请求
                                const confirmed = await this.handleConfirmationRequest(chunkData, sessionId);
                                if (!confirmed) {
                                    return false;
                                }

                            } else if (chunkType === 'confirmation_received') {
                                console.log(`✅ ${chunkData.chunk}`);

                            } else if (chunkType === 'task_replanned') {
                                console.log(`🔄 ${chunkData.chunk}`);

                            } else if (chunkType === 'error') {
                                console.error(`❌ ${chunkData.chunk}`);
                                return false;

                            } else if (chunkType === 'completion') {
                                console.log('🎉 任务完成!');
                                return true;

                            } else {
                                // 其他类型的chunk
                                const content = chunkData.chunk || '';
                                if (content.trim()) {
                                    console.log(`[${chunkType}] ${content}`);
                                }
                            }

                            // 检查是否完成
                            if (chunkData.finished) {
                                break;
                            }

                        } catch (parseError) {
                            console.warn(`解析chunk失败: ${parseError.message} - ${line}`);
                        }
                    }
                }
            }

            return true;

        } finally {
            reader.releaseLock();
        }
    }

    /**
     * 处理确认请求
     * @param {Object} chunkData - 确认请求数据
     * @param {string} sessionId - 会话ID
     * @returns {Promise<boolean>} 是否成功处理
     */
    async handleConfirmationRequest(chunkData, sessionId) {
        const confirmationData = chunkData.confirmation_data || {};
        const tasks = confirmationData.tasks || [];

        console.log('🔔 收到确认请求:');
        console.log(`   会话: ${sessionId}`);
        console.log(`   任务数量: ${tasks.length}`);
        console.log(`   风险级别: ${confirmationData.risk_level || 'unknown'}`);
        console.log(`   超时时间: ${confirmationData.timeout_seconds || 300}秒`);

        // 显示任务列表
        console.log('   任务详情:');
        tasks.forEach(task => {
            console.log(`     ${task.index || '?'}. ${task.description || '未知任务'}`);
            console.log(`        工具: ${task.tool || 'unknown'}`);
        });

        // 在浏览器环境中显示确认对话框
        return await this.showConfirmationDialog(confirmationData, sessionId);
    }

    /**
     * 显示确认对话框 (浏览器环境)
     * @param {Object} confirmationData - 确认数据
     * @param {string} sessionId - 会话ID
     * @returns {Promise<boolean>} 用户选择结果
     */
    async showConfirmationDialog(confirmationData, sessionId) {
        const tasks = confirmationData.tasks || [];
        
        // 构建任务描述
        const taskList = tasks.map(task => 
            `${task.index || '?'}. ${task.description || '未知任务'}`
        ).join('\n');

        const message = `请确认执行以下任务:\n\n${taskList}\n\n请选择操作:`;

        // 简单的浏览器确认对话框
        const confirmed = confirm(`${message}\n\n点击"确定"执行，"取消"取消任务`);
        
        if (confirmed) {
            return await this.sendConfirmation(sessionId, 'confirm');
        } else {
            return await this.sendConfirmation(sessionId, 'cancel');
        }
    }

    /**
     * 显示高级确认对话框 (自定义UI)
     * @param {Object} confirmationData - 确认数据
     * @param {string} sessionId - 会话ID
     * @returns {Promise<boolean>} 用户选择结果
     */
    async showAdvancedConfirmationDialog(confirmationData, sessionId) {
        return new Promise((resolve) => {
            // 创建模态对话框
            const modal = document.createElement('div');
            modal.style.cssText = `
                position: fixed; top: 0; left: 0; width: 100%; height: 100%;
                background: rgba(0,0,0,0.5); display: flex; align-items: center;
                justify-content: center; z-index: 10000;
            `;

            const dialog = document.createElement('div');
            dialog.style.cssText = `
                background: white; padding: 20px; border-radius: 8px;
                max-width: 600px; max-height: 80vh; overflow-y: auto;
            `;

            const tasks = confirmationData.tasks || [];
            const taskList = tasks.map(task => 
                `<li><strong>${task.index || '?'}.</strong> ${task.description || '未知任务'} <em>(${task.tool || 'unknown'})</em></li>`
            ).join('');

            dialog.innerHTML = `
                <h3>🔔 任务确认</h3>
                <p><strong>会话:</strong> ${sessionId}</p>
                <p><strong>任务数量:</strong> ${tasks.length}</p>
                <p><strong>风险级别:</strong> ${confirmationData.risk_level || 'unknown'}</p>
                <p><strong>超时时间:</strong> ${confirmationData.timeout_seconds || 300}秒</p>
                
                <h4>任务详情:</h4>
                <ul>${taskList}</ul>
                
                <div style="margin-top: 20px;">
                    <button id="confirm-btn" style="margin-right: 10px; padding: 8px 16px; background: #28a745; color: white; border: none; border-radius: 4px;">✅ 确认执行</button>
                    <button id="modify-btn" style="margin-right: 10px; padding: 8px 16px; background: #ffc107; color: black; border: none; border-radius: 4px;">🔧 修改任务</button>
                    <button id="cancel-btn" style="padding: 8px 16px; background: #dc3545; color: white; border: none; border-radius: 4px;">❌ 取消执行</button>
                </div>
                
                <div id="modify-section" style="display: none; margin-top: 15px;">
                    <label for="modify-input">修改建议:</label>
                    <textarea id="modify-input" style="width: 100%; height: 60px; margin-top: 5px;"></textarea>
                    <button id="submit-modify" style="margin-top: 10px; padding: 8px 16px; background: #007bff; color: white; border: none; border-radius: 4px;">提交修改</button>
                </div>
            `;

            modal.appendChild(dialog);
            document.body.appendChild(modal);

            // 添加事件监听器
            const confirmBtn = dialog.querySelector('#confirm-btn');
            const modifyBtn = dialog.querySelector('#modify-btn');
            const cancelBtn = dialog.querySelector('#cancel-btn');
            const modifySection = dialog.querySelector('#modify-section');
            const submitModifyBtn = dialog.querySelector('#submit-modify');
            const modifyInput = dialog.querySelector('#modify-input');

            const cleanup = () => {
                document.body.removeChild(modal);
            };

            confirmBtn.addEventListener('click', async () => {
                cleanup();
                const success = await this.sendConfirmation(sessionId, 'confirm');
                resolve(success);
            });

            cancelBtn.addEventListener('click', async () => {
                cleanup();
                const success = await this.sendConfirmation(sessionId, 'cancel');
                resolve(success);
            });

            modifyBtn.addEventListener('click', () => {
                modifySection.style.display = 'block';
                modifyInput.focus();
            });

            submitModifyBtn.addEventListener('click', async () => {
                const userMessage = modifyInput.value.trim();
                cleanup();
                const success = await this.sendConfirmation(sessionId, 'modify', userMessage);
                resolve(success);
            });

            // ESC键取消
            const handleKeyPress = (event) => {
                if (event.key === 'Escape') {
                    cleanup();
                    this.sendConfirmation(sessionId, 'cancel').then(resolve);
                    document.removeEventListener('keydown', handleKeyPress);
                }
            };
            document.addEventListener('keydown', handleKeyPress);
        });
    }

    /**
     * 发送确认响应
     * @param {string} sessionId - 会话ID
     * @param {string} action - 确认动作 (confirm, modify, cancel)
     * @param {string} [userMessage] - 用户消息（修改建议等）
     * @returns {Promise<boolean>} 是否成功发送
     */
    async sendConfirmation(sessionId, action, userMessage = null) {
        // 按照设计文档格式构造确认消息
        let message = `CONFIRM_ACTION:${action}`;
        if (userMessage) {
            message += `:${userMessage}`;
        }

        console.log(`发送确认响应: ${message}`);

        try {
            const response = await fetch(`${this.baseUrl}/api/v1/chat/stream`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: message,
                    session_id: sessionId
                })
            });

            if (!response.ok) {
                console.error(`确认响应失败: ${response.status} - ${response.statusText}`);
                return false;
            }

            // 处理确认响应
            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            try {
                while (true) {
                    const { done, value } = await reader.read();
                    
                    if (done) break;

                    const chunk = decoder.decode(value, { stream: true });
                    const lines = chunk.split('\n');

                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const chunkData = JSON.parse(line.substring(6));
                                const chunkType = chunkData.chunk_type || 'content';

                                if (chunkType === 'confirmation_received') {
                                    console.log(`✅ 确认已接收: ${chunkData.chunk}`);
                                    return true;
                                } else if (chunkType === 'error') {
                                    console.error(`❌ 确认失败: ${chunkData.chunk}`);
                                    return false;
                                }

                            } catch (parseError) {
                                // 忽略解析错误
                                continue;
                            }
                        }
                    }
                }

                return true;

            } finally {
                reader.releaseLock();
            }

        } catch (error) {
            console.error(`发送确认响应失败: ${error.message}`);
            return false;
        }
    }
}

/**
 * 演示标准工作流程
 */
async function demonstrateStandardWorkflow() {
    console.log('🚀 JavaScript Chat Stream确认客户端演示');
    console.log('='.repeat(50));

    const client = new StandardChatStreamClient();

    // 检查服务器连接
    try {
        const healthResponse = await fetch(`${client.baseUrl}/health`);
        if (healthResponse.ok) {
            console.log('✅ 服务器连接正常');
        } else {
            console.warn(`⚠️  服务器状态异常: ${healthResponse.status}`);
        }
    } catch (error) {
        console.error(`❌ 无法连接到服务器: ${error.message}`);
        console.log('   请确保SimaCode API服务器正在运行:');
        console.log('   simacode serve --host 0.0.0.0 --port 8000');
        return;
    }

    // 测试任务
    const testTask = '创建一个React组件库项目的自动化构建和部署流程';
    const sessionId = `js-demo-${Date.now()}`;

    console.log(`\n🎯 执行任务: ${testTask}`);
    console.log(`📋 会话ID: ${sessionId}`);
    console.log('\n开始执行...\n');

    try {
        const success = await client.sendTaskWithConfirmation(testTask, sessionId);

        if (success) {
            console.log('\n🎉 任务执行成功完成!');
        } else {
            console.log('\n❌ 任务执行失败或被取消');
        }

    } catch (error) {
        console.error(`\n💥 执行过程中出现错误: ${error.message}`);
    }
}

/**
 * 演示消息格式
 */
function demonstrateMessageFormats() {
    console.log('\n📨 标准消息格式演示');
    console.log('='.repeat(30));

    // 确认请求格式示例
    const confirmationRequestExample = {
        "chunk": "请确认执行以下3个任务:\n1. 创建React项目结构\n2. 配置Webpack构建\n3. 设置CI/CD流程",
        "session_id": "js-sess-123",
        "finished": false,
        "chunk_type": "confirmation_request",
        "confirmation_data": {
            "tasks": [
                {"index": 1, "description": "创建React项目结构", "tool": "file_write"},
                {"index": 2, "description": "配置Webpack构建", "tool": "file_write"},
                {"index": 3, "description": "设置CI/CD流程", "tool": "file_write"}
            ],
            "options": ["confirm", "modify", "cancel"],
            "timeout_seconds": 300,
            "confirmation_round": 1,
            "risk_level": "medium"
        },
        "requires_response": true,
        "stream_paused": true
    };

    console.log('📥 确认请求格式 (服务器 -> 客户端):');
    console.log(JSON.stringify(confirmationRequestExample, null, 2));

    // 确认响应格式示例
    const confirmationResponses = [
        {"message": "CONFIRM_ACTION:confirm", "session_id": "js-sess-123"},
        {"message": "CONFIRM_ACTION:modify:请添加TypeScript支持和单元测试配置", "session_id": "js-sess-123"},
        {"message": "CONFIRM_ACTION:cancel", "session_id": "js-sess-123"}
    ];

    console.log('\n📤 确认响应格式 (客户端 -> 服务器):');
    confirmationResponses.forEach((response, index) => {
        console.log(`   ${index + 1}. ${JSON.stringify(response)}`);
    });
}

// 在浏览器环境中使用
if (typeof window !== 'undefined') {
    // 导出到全局作用域
    window.StandardChatStreamClient = StandardChatStreamClient;
    window.demonstrateStandardWorkflow = demonstrateStandardWorkflow;
    window.demonstrateMessageFormats = demonstrateMessageFormats;
    
    console.log('✅ JavaScript客户端已加载');
    console.log('使用 demonstrateStandardWorkflow() 开始演示');
}

// 在Node.js环境中使用
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        StandardChatStreamClient,
        demonstrateStandardWorkflow,
        demonstrateMessageFormats
    };
}