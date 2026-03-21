# AI Skill

AI 對話技能，使用 OpenAI 相容格式 API，支援 Function Calling 操作其他技能。

## 概述

提供自然語言對話能力，並透過 Function Calling 機制調用其他技能（如行事曆）。

## 功能列表

| 功能 | 描述 | 權限等級 |
|------|------|----------|
| `chat` | 自然語言對話 | `user` |
| `function_call` | 調用其他技能 | `user` |

## 架構

```
用戶訊息 → AI Skill → LLM (with tools) → Function Calling → Calendar Skill → 回應
```

## 支援的 Function Tools

### calendar_list_events
列出即將到來的行程

**參數：**
- `max_results` (int): 最多返回幾筆，預設 10

### calendar_create_event
建立新行程

**參數：**
- `summary` (string, required): 行程標題
- `start_time` (string, required): 開始時間 ISO 格式
- `end_time` (string): 結束時間 ISO 格式
- `description` (string): 描述
- `location` (string): 地點

### calendar_delete_event
刪除行程

**參數：**
- `event_id` (string, required): 行程 ID

## 配置

```yaml
# env_config.yaml
ai:
  base_url: "https://api.openai.com/v1"  # 或其他相容 API
  api_key: "sk-xxx"
  model: "gpt-4o"
  max_tokens: 4096
  temperature: 0.7
```

## 使用範例

```
@bot 幫我查看今天的行程
@bot 新增一個明天下午3點的會議，標題是專案討論
@bot 我這週有什麼安排？
```

## 權限需求

```yaml
permissions:
  ai.chat:
    description: "AI 對話"
    default: true
  ai.function_call:
    description: "AI 調用技能"
    default: true
```
