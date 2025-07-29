## UI-TARS-MCP
UI-TARS-MCP是一个运行在第三方服务器，通过 Streamable http 协议来和SimaCode交互的MCP Server.

### 功能定义
UI-TARS-MCP通过调用 能够理解自然语言的 UI-TARS 来操作来对当前主机做包括图形界面/WEB程序执行复杂任务。
在SIMACHAT调用UI-TARS-MCP时，只需要传递自然语言指令即可，比如“打开网址，输入用户名和密码..."

### 启动UI-TARS Agent
可以通过下列指令来启动， 但是不需要确保其守护进程已经开启后才启动MCP服务
agent-tars serve \
--provider volcengine \
--model doubao-1-5-thinking-vision-pro-250428 \
--apiKey {apiKey}

### UI-TARS 的使用

通过执行本地命令 agent-tars run --provider volcengine --model doubao-1-5-thinking-vision-pro-250428 --apiKey {apiKey} --input "指令" 即可让UI-TARS所在的主机执行对应的程序


#### 1. 打开网站并自动验证
在打开一些网站时，目标网站会设置一些验证措施，用户需要配合验证后才能继续浏览，UI-TARS拥有能打开网站，并且继续执行验证的能力。
