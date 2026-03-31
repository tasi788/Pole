# Calendar Skill

Google Calendar 行事曆技能

## 概述

提供 Google Calendar 的完整操作能力，包括查詢、新增、修改、刪除行程。

## 功能列表

| 功能 | 描述 | 權限等級 |
|------|------|----------|
| `list_events` | 列出即將到來的行程 | `user` |
| `get_event` | 取得特定行程詳情 | `user` |
| `create_event` | 建立新行程 | `user` |
| `update_event` | 修改現有行程 | `user` |
| `delete_event` | 刪除行程 | `admin` |

## 觸發關鍵字

當用戶 mention bot 並包含以下關鍵字時觸發：

- 中文：`行事曆`、`日曆`、`行程`、`會議`、`活動`、`提醒`
- 英文：`calendar`、`schedule`、`meeting`、`event`、`remind`

## 工具層 (Tools)

### GoogleCalendarAPI

底層 Google Calendar API 封裝，提供原始 API 操作。

```python
class GoogleCalendarAPI:
    def list_events(calendar_id, time_min, max_results) -> list[dict]
    def get_event(calendar_id, event_id) -> dict
    def insert_event(calendar_id, event_body) -> dict
    def update_event(calendar_id, event_id, event_body) -> dict
    def delete_event(calendar_id, event_id) -> bool
```

## 技能層 (Skill)

### CalendarSkill

組合工具層，提供高階業務邏輯。

```python
class CalendarSkill:
    async def get_today_schedule() -> str
    async def get_upcoming_events(days: int = 7) -> str
    async def quick_add_event(text: str) -> str
    async def cancel_event(event_id: str) -> str
```

## 權限需求

```yaml
permissions:
  calendar.read:
    description: "讀取行事曆"
    default: true
  calendar.write:
    description: "新增/修改行程"
    default: true
  calendar.delete:
    description: "刪除行程"
    default: false
    require_admin: true
```

## 配置

```yaml
# env_config.yaml
google_calendar:
  credentials_path: "service_account.json"
  default_calendar_id: "primary"
  timezone: "Asia/Taipei"
```

## 使用範例

### 查詢行程
```
@bot 查看今天的行程
@bot 這週有什麼會議
@bot 顯示行事曆
```

### 新增行程
```
@bot 新增行程：明天下午3點開會
@bot 建立活動 專案討論 2024-01-15 14:00
```

### 刪除行程 (需要 admin 權限)
```
@bot 取消會議 [event_id]
```
