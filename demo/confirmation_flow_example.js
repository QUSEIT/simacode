/**
 * SimaCode 确认流程完整示例 - JavaScript版本
 * 
 * 展示如何与 simacode serve API 进行完整的确认交互：
 * 1. 发送任务请求
 * 2. 接收确认请求
 * 3. 处理用户确认
 * 4. 发送确认响应
 * 5. 接收执行结果
 */

class SimaCodeConfirmationClient {
    constructor(baseUrl = 'http://localhost:8100') {
        this.baseUrl = baseUrl;
        this.currentSession = null;
    }

    /**
     * 生成唯一会话ID
     */
    generateSessionId() {
        return `demo-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    }

    /**
     * 发送任务并处理完整的确认流程
     * @param {string} task - 要执行的任务
     * @param {function} onConfirmationRequest - 确认请求回调函数
     * @returns {Promise<boolean>} - 是否成功完成
     */
    async executeTaskWithConfirmation(task, onConfirmationRequest) {
        this.currentSession = this.generateSessionId();
        
        console.log(`🚀 开始执行任务: ${task}`);
        console.log(`📋 会话ID: ${this.currentSession}`);

        try {
            // 发送初始任务请求
            const response = await fetch(`${this.baseUrl}/api/v1/chat/stream`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: task,
                    session_id: this.currentSession
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            if (!response.body) {
                throw new Error('Response body is null');
            }

            // 处理流式响应
            return await this.processStreamResponse(response, onConfirmationRequest);

        } catch (error) {
            console.error(`❌ 任务执行失败: ${error.message}`);
            return false;
        }
    }

    /**
     * 处理流式响应
     * @param {Response} response - Fetch响应对象
     * @param {function} onConfirmationRequest - 确认请求回调
     * @returns {Promise<boolean>} - 处理是否成功
     */
    async processStreamResponse(response, onConfirmationRequest) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        try {
            while (true) {
                const { done, value } = await reader.read();
                
                if (done) {
                    console.log('📡 流式响应结束');
                    break;
                }

                // 解码数据
                buffer += decoder.decode(value, { stream: true });
                
                // 处理完整的数据行
                const lines = buffer.split('\n');
                buffer = lines.pop() || ''; // 保留不完整的行

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const chunkData = JSON.parse(line.slice(6));
                            const result = await this.handleChunk(chunkData, onConfirmationRequest);
                            
                            // 如果返回false，说明需要终止
                            if (result === false) {
                                return false;
                            }
                            
                            // 如果任务完成
                            if (chunkData.chunk_type === 'completion' || chunkData.finished) {
                                console.log('🎉 任务执行完成!!!');
                                console.log(chunkData)
                                return true;
                            }
                            
                        } catch (parseError) {
                            console.warn(`⚠️ 解析chunk失败: ${parseError.message} - ${line}`);
                        }
                    }
                }
            }

            return true;

        } catch (error) {
            console.error(`❌ 流处理错误: ${error.message}`);
            return false;
        } finally {
            reader.releaseLock();
        }
    }

    /**
     * 处理单个chunk
     * @param {Object} chunkData - chunk数据
     * @param {function} onConfirmationRequest - 确认请求回调
     * @returns {Promise<boolean|null>} - 处理结果
     */
    async handleChunk(chunkData, onConfirmationRequest) {
        const { chunk_type, chunk, session_id, confirmation_data } = chunkData;

        console.log(`📨 收到chunk [${chunk_type}]: ${chunk}`);

        switch (chunk_type) {
            case 'confirmation_request':
                // 处理确认请求
                return await this.handleConfirmationRequest(chunkData, onConfirmationRequest);
                
            case 'confirmation_received':
                console.log(`✅ ${chunk}`);
                break;
                
            case 'task_replanned':
                console.log(`🔄 ${chunk}`);
                break;
                
            case 'error':
                console.error(`❌ ${chunk}`);
                return false;
                
            case 'completion':
                console.log('🎉 任务完成!');
                return true;
                
            default:
                // 其他类型的chunk（content, status, tool_output等）
                if (chunk && chunk.trim()) {
                    console.log(`[${chunk_type}] ${chunk}`);
                }
                break;
        }

        return null; // 继续处理
    }

    /**
     * 处理确认请求
     * @param {Object} chunkData - chunk数据
     * @param {function} onConfirmationRequest - 确认请求回调
     * @returns {Promise<boolean>} - 是否继续执行
     */
    async handleConfirmationRequest(chunkData, onConfirmationRequest) {
        const { confirmation_data, session_id } = chunkData;
        const { tasks, timeout_seconds, risk_level, confirmation_round } = confirmation_data;

        console.log('\n🔔 收到确认请求:');
        console.log(`   会话: ${session_id}`);
        console.log(`   任务数量: ${tasks.length}`);
        console.log(`   风险级别: ${risk_level}`);
        console.log(`   超时时间: ${timeout_seconds}秒`);
        console.log(`   确认轮次: ${confirmation_round}`);
        console.log('   任务详情:');
        
        tasks.forEach((task, index) => {
            console.log(`     ${index + 1}. ${task.description}`);
            console.log(`        工具: ${task.tool_name || task.tool || 'unknown'}`);
            console.log(`        类型: ${task.type || 'unknown'}`);
        });

        // 调用用户提供的确认回调
        let userChoice;
        try {
            userChoice = await onConfirmationRequest(confirmation_data);
        } catch (error) {
            console.error(`❌ 确认回调错误: ${error.message}`);
            userChoice = { action: 'cancel' };
        }

        // 发送确认响应  
        return await this.sendConfirmationResponse(session_id, userChoice);
    }

    /**
     * 发送确认响应
     * @param {string} sessionId - 会话ID
     * @param {Object} userChoice - 用户选择 {action: 'confirm'|'modify'|'cancel', message?: string}
     * @returns {Promise<boolean>} - 是否成功发送
     */
    async sendConfirmationResponse(sessionId, userChoice) {
        const { action, message } = userChoice;

        // 构造确认消息，按照API要求的格式：CONFIRM_ACTION:action:message
        let confirmationMessage = `CONFIRM_ACTION:${action}`;
        if (message) {
            confirmationMessage += `:${message}`;
        }

        console.log(`📤 发送确认响应: ${confirmationMessage}`);

        try {
            const response = await fetch(`${this.baseUrl}/api/v1/chat/stream`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: confirmationMessage,
                    session_id: sessionId
                })
            });

            if (!response.ok) {
                console.error(`❌ 确认响应失败: HTTP ${response.status}`);
                return false;
            }

            // 处理确认响应的结果
            if (response.body) {
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                try {
                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;

                        buffer += decoder.decode(value, { stream: true });
                        const lines = buffer.split('\n');
                        buffer = lines.pop() || '';

                        for (const line of lines) {
                            if (line.startsWith('data: ')) {
                                try {
                                    const responseData = JSON.parse(line.slice(6));
                                    
                                    if (responseData.chunk_type === 'confirmation_received') {
                                        console.log(`✅ 确认已接收: ${responseData.chunk}`);
                                        return action !== 'cancel'; // 取消返回false，其他返回true
                                    } else if (responseData.chunk_type === 'error') {
                                        console.error(`❌ 确认失败: ${responseData.chunk}`);
                                        return false;
                                    }
                                } catch (parseError) {
                                    console.warn(`⚠️ 解析确认响应失败: ${parseError.message}`);
                                }
                            }
                        }
                    }
                } finally {
                    reader.releaseLock();
                }
            }

            return action !== 'cancel';

        } catch (error) {
            console.error(`❌ 发送确认响应失败: ${error.message}`);
            return false;
        }
    }

    /**
     * 检查服务器连接
     * @returns {Promise<boolean>} - 连接是否正常
     */
    async checkServerConnection() {
        try {
            const response = await fetch(`${this.baseUrl}/health`, { timeout: 5000 });
            return response.ok;
        } catch (error) {
            console.error(`❌ 无法连接到服务器: ${error.message}`);
            return false;
        }
    }
}

// ==================== 使用示例 ====================

/**
 * 模拟用户确认交互的回调函数
 * 在实际应用中，这里可以显示UI界面让用户选择
 */
async function simulateUserConfirmation(confirmationData) {
    const { tasks, risk_level, timeout_seconds } = confirmationData;
    
    console.log('\n🤔 请选择操作:');
    console.log('   1. 确认执行 (confirm)');
    console.log('   2. 修改任务 (modify)');
    console.log('   3. 取消执行 (cancel)');

    // 模拟用户输入 - 在实际应用中这里应该是真实的用户交互
    // 这里为了演示，我们基于风险级别自动决策
    if (risk_level === 'high') {
        console.log('💡 检测到高风险任务，建议仔细审核');
        return {
            action: 'confirm',
            message: '执行'
        };
    } else if (risk_level === 'medium') {
        console.log('💡 中等风险任务，确认执行');
        return {
            action: 'confirm'
        };
    } else {
        console.log('💡 低风险任务，直接确认');
        return {
            action: 'confirm'
        };
    }
}

/**
 * 交互式用户确认函数（用于真实场景）
 * 需要在Node.js环境中安装 readline 模块
 */
async function interactiveUserConfirmation(confirmationData) {
    const readline = require('readline');
    
    const rl = readline.createInterface({
        input: process.stdin,
        output: process.stdout
    });

    return new Promise((resolve) => {
        console.log('\n🤔 请选择操作:');
        console.log('   1. 确认执行 (confirm)');
        console.log('   2. 修改任务 (modify)');
        console.log('   3. 取消执行 (cancel)');

        rl.question('请输入选择 (1/2/3): ', (choice) => {
            let result;

            switch (choice.trim()) {
                case '1':
                    result = { action: 'confirm' };
                    rl.close();
                    resolve(result);
                    break;
                    
                case '2':
                    rl.question('请输入修改建议: ', (modification) => {
                        result = { 
                            action: 'modify', 
                            message: modification.trim() 
                        };
                        rl.close();
                        resolve(result);
                    });
                    break;
                    
                case '3':
                    result = { action: 'cancel' };
                    rl.close();
                    resolve(result);
                    break;
                    
                default:
                    console.log('⚠️ 无效选择，默认取消');
                    result = { action: 'cancel' };
                    rl.close();
                    resolve(result);
                    break;
            }
        });
    });
}

// ==================== 演示主函数 ====================

async function demonstrateConfirmationFlow() {
    console.log('🚀 SimaCode 确认流程完整演示');
    console.log('=' .repeat(50));

    const client = new SimaCodeConfirmationClient();

    // 检查服务器连接
    console.log('🔍 检查服务器连接...');
    const isConnected = await client.checkServerConnection();
    
    if (!isConnected) {
        console.log('❌ 无法连接到SimaCode服务器');
        console.log('   请确保服务器正在运行:');
        console.log('   simacode serve --host 0.0.0.0 --port 8000');
        return;
    }

    console.log('✅ 服务器连接正常');

    // 测试任务列表
    const testTasks = [
        '创建一个HelloWorld程序',
        '创建一个Python项目的自动化测试框架',
        '实现文件备份和同步系统，包含文件监控和增量备份',
        '开发用户认证和权限管理模块，支持JWT和OAuth',
        '构建数据分析和可视化工具，集成机器学习模型'
    ];

    console.log('\n📋 可用测试任务:');
    testTasks.forEach((task, index) => {
        console.log(`   ${index + 1}. ${task}`);
    });

    // 选择任务（这里直接选择第一个作为演示）
    const selectedTask = testTasks[0];
    console.log(`\n🎯 选择任务: ${selectedTask}`);
    console.log('\n开始执行...\n');

    try {
        // 执行任务并处理确认流程
        const success = await client.executeTaskWithConfirmation(
            selectedTask,
            simulateUserConfirmation  // 使用模拟确认，也可以用 interactiveUserConfirmation
        );

        if (success) {
            console.log('\n🎉 任务执行成功完成!');
        } else {
            console.log('\n❌ 任务执行失败或被取消');
        }

    } catch (error) {
        console.error(`\n💥 演示过程中出现错误: ${error.message}`);
    }
}

// ==================== 导出和执行 ====================

// 如果在Node.js环境中直接运行
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        SimaCodeConfirmationClient,
        simulateUserConfirmation,
        interactiveUserConfirmation,
        demonstrateConfirmationFlow
    };

    // 如果直接运行此文件
    if (require.main === module) {
        demonstrateConfirmationFlow().catch(console.error);
    }
}

// 如果在浏览器环境中运行
if (typeof window !== 'undefined') {
    window.SimaCodeConfirmationClient = SimaCodeConfirmationClient;
    window.demonstrateConfirmationFlow = demonstrateConfirmationFlow;
}

/* 
使用说明:

1. Node.js环境运行:
   node confirmation_flow_example.js

2. 浏览器环境使用:
   <script src="confirmation_flow_example.js"></script>
   <script>demonstrateConfirmationFlow();</script>

3. 自定义确认处理:
   const client = new SimaCodeConfirmationClient('http://localhost:8000');
   client.executeTaskWithConfirmation('你的任务', yourConfirmationHandler);

4. 确认回调函数格式:
   async function yourConfirmationHandler(confirmationData) {
     // confirmationData 包含: tasks, risk_level, timeout_seconds等
     // 返回: { action: 'confirm'|'modify'|'cancel', message?: 'optional' }
   }
*/
