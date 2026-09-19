# Reviewer Login Path

```json
{
  "required": true,
  "purpose": "OpenAI/ChatGPT review must be able to test without being blocked by unclear login or paid-only access.",
  "options": [
    "demo reviewer account",
    "time-limited reviewer bypass",
    "seeded test data with no real customer data"
  ],
  "must_not": [
    "給 reviewer 真實付費者資料",
    "讓 reviewer 需要真刷卡才可測基本功能"
  ]
}
```
