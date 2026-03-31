# AutoFlow

**基于多智能体的自治工作流引擎** — 让智能体像团队一样协作，实现 24/7 全自动生产力。

## 快速开始

```bash
# 安装
pip install -e ".[dev]"

# 配置 API Key
export OPENAI_API_KEY="your-api-key"

# 查看系统状态
autoflow status

# 运行工作流
autoflow run dev-pipeline --input "实现一个快速排序函数"

# 启动守护进程
autoflow start --daemon
```

## 项目结构

```
src/autoflow/
├── core/          # Agent 运行时、消息协议、工作流引擎
├── messaging/     # 消息总线（Redis Streams / InMemory）
├── llm/           # LLM 统一网关（多模型支持）
├── tools/         # 可扩展工具系统
├── cli/           # 命令行接口
├── config/        # 配置管理
├── observability/ # 日志与监控
└── security/      # 沙箱与密钥管理
```

## 文档

- [产品需求文档 (PRD)](docs/PRD.md)
- [技术实现方案](docs/TECHNICAL_DESIGN.md)
- [项目目录结构](docs/PROJECT_STRUCTURE.md)

## License

Apache License 2.0
