# AI Provider Setup

This project can call OpenAI-compatible model APIs for an optional AI summary in the monitor email.

Supported built-in providers:

- Qwen / DashScope: `AI_PROVIDER=qwen`
- Kimi / Moonshot: `AI_PROVIDER=kimi`
- Any OpenAI-compatible service: set `AI_BASE_URL`, `AI_MODEL`, and `AI_API_KEY`

## Recommended: Qwen

Add these environment variables:

```text
AI_ENABLED=true
AI_PROVIDER=qwen
DASHSCOPE_API_KEY=your_dashscope_key
AI_MODEL=qwen-plus
```

`AI_MODEL` is optional. The default is `qwen-plus`.

## Kimi

Add these environment variables:

```text
AI_ENABLED=true
AI_PROVIDER=kimi
KIMI_API_KEY=your_kimi_key
AI_MODEL=kimi-k2.6
```

`AI_MODEL` is optional. The default is `kimi-k2.6`.

## Custom OpenAI-Compatible Provider

```text
AI_ENABLED=true
AI_BASE_URL=https://example.com/v1
AI_MODEL=your-model-name
AI_API_KEY=your_api_key
```

## GitHub Actions Secrets

Store keys in repository secrets, never in code:

1. Open the repository on GitHub.
2. Go to `Settings` -> `Secrets and variables` -> `Actions`.
3. Add one of these:
   - `DASHSCOPE_API_KEY` for Qwen
   - `KIMI_API_KEY` for Kimi
   - `AI_API_KEY` for a custom provider

The workflow must also expose those secrets as environment variables when it runs:

```yaml
env:
  AI_ENABLED: true
  AI_PROVIDER: qwen
  DASHSCOPE_API_KEY: ${{ secrets.DASHSCOPE_API_KEY }}
```

This repository's current GitHub token may not have the `workflow` permission needed to push workflow-file changes. If GitHub rejects workflow updates, add the `env` block manually in the GitHub UI or re-authenticate the CLI with `workflow` scope.

## Local Test

PowerShell:

```powershell
$env:AI_ENABLED='true'
$env:AI_PROVIDER='qwen'
$env:DASHSCOPE_API_KEY='your_dashscope_key'
python -c "from ai_client import chat_completion; print(chat_completion('用一句话回复：AI provider connected'))"
```

If no key is configured, the monitor still runs normally and simply skips the AI summary.
