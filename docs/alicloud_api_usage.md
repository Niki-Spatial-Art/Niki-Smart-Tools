# 阿里云 API 使用说明

本项目目前没有部署在阿里云上，也没有使用阿里云数据库、ECS、函数计算或对象存储。

当前与阿里云相关的部分主要是可选 AI 摘要能力：通义千问 / DashScope OpenAI-compatible API。

## 已接入的阿里云能力

| 能力 | 使用位置 | 是否必需 | 用途 |
| --- | --- | --- | --- |
| 通义千问 DashScope OpenAI-compatible Chat Completions | `ai_client.py` | 可选 | 生成中文策略简报、风险提醒和盘后总结 |

默认配置：

```text
AI_ENABLED=true
AI_PROVIDER=qwen
DASHSCOPE_API_KEY=your_dashscope_api_key
```

代码中的默认端点：

```text
https://dashscope.aliyuncs.com/compatible-mode/v1
```

默认模型：

```text
qwen-plus
```

官方参考：

- 阿里云百炼 OpenAI 兼容 Chat 文档：<https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions>
- 阿里云 DashScope OpenAI 兼容调用说明：<https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope>

## 没有 DashScope 也能运行吗

可以。

如果 `AI_ENABLED=false`，或者没有 `DASHSCOPE_API_KEY`，项目会跳过 AI 简报，行情、动作卡、纸面日志、维护记录仍然可以运行。

## 目前没有使用的阿里云能力

- 没有使用阿里云 ECS 托管服务。
- 没有使用阿里云 RDS / MongoDB / PolarDB。
- 没有使用对象存储 OSS。
- 没有使用函数计算。
- 没有使用阿里云向量检索。

## 可以在会上怎么讲

> 当前版本把阿里云通义千问作为可选的“中文策略简报层”，数据和交易纪律仍在本地完成。未来如果要走更少架构的路线，可以把数据存储、向量检索、Agent 记忆和自动摘要逐步统一到云上，但真实交易执行仍保留人工确认闸门。
