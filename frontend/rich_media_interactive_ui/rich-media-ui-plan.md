# 跨產業 ChatGPT 原生內容渲染

## 目標

建立三間汽車保養維修廠營運 ChatGPT App：先診斷等待過久的根因，再管理預約、接車、工單、技師技能、工位、零件等待、報價核准、進度通知與完工交車。不得在未驗證根因前只做排班系統。需要前後端網站、管理後台、工具、技能、測試與 ZIP。

## 架構

`interactive-decoupled`：資料工具與渲染工具分離，透過標準化 structuredContent 接到版本化 MCP Apps UI 資源。

## 支援呈現

- `card`
- `list`
- `carousel`
- `table`
- `chart`
- `gallery`
- `video`
- `map`
- `detail`
- `form`
- `dashboard`

## 邊界

Generated schema, renderer runtime, MCP Apps resource contract, and local validation proof only; not deployed frontend, remote MCP, ChatGPT native rendering, payment, submission, or OpenAI approval proof
