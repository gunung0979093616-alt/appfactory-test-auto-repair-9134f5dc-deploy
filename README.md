# 汽車維修營運助手（隔離驗證專案）

這是由開發助手產生的跨產業端到端驗證 App，用於驗證：

- 前端網站與後端服務
- MCP 初始化、工具探索與工具呼叫
- 客戶專案工具與技能
- GitHub 到 Render 的部署流程
- 第一至第六階段的狀態與交付邊界

## 本機啟動

```bash
pip install -r requirements.txt
uvicorn server.server:app --host 0.0.0.0 --port 8000
```

此公開部署版本只包含客戶 App 的執行程式、測試與客戶專案技能，不包含開發助手母系統的私有路由、提示詞或內部技能原文。
