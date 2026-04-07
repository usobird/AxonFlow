"""默认配置常量"""

# 默认 Agent 消息处理超时（秒）
DEFAULT_AGENT_TIMEOUT = 300

# 默认工作流最大迭代次数
DEFAULT_MAX_ITERATIONS = 10

# 默认工作流超时（秒）
DEFAULT_WORKFLOW_TIMEOUT = 3600

# 默认 LLM 调用重试次数
DEFAULT_LLM_RETRIES = 3

# 默认消息队列阻塞等待时间（毫秒）
DEFAULT_QUEUE_BLOCK_MS = 5000

# 默认工具执行超时（秒）
DEFAULT_TOOL_TIMEOUT = 30

# Redis Stream 键前缀
REDIS_KEY_PREFIX = "axonflow"
REDIS_AGENT_INBOX_PATTERN = f"{REDIS_KEY_PREFIX}:agent:{{agent_id}}:inbox"
REDIS_WORKFLOW_STATE_PATTERN = f"{REDIS_KEY_PREFIX}:workflow:{{workflow_id}}:state"
