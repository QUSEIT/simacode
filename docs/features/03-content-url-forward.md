# 内容转发URL工具
在config/mcp_servers.yaml增加对应的配置，包括FORWARD_URL，默认为http://localhost/smc_forward
在src/simacode/tools/smc_content_coder.py增加一个工具，1 在 能够将 内容转化为base64字串，最后和 FORWARD_URL拼成类似
FORWARD_URL?ct=<base64字串>
并返回连接
