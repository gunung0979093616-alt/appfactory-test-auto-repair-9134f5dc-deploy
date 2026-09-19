# 資料查詢與營運基礎套件

這是第二階段依專案產業自動產生的基礎套件，不需要 React，也不會阻止後續升級成 React／Tailwind。

- 套件：`operations-dashboard`
- 版型：`operations-dashboard`
- 動效：`status-reveal`
- 用途：讓條件、結果、來源、狀態與管理資料容易核對。

## 元件

- `search_filter`：條件搜尋，依產業欄位篩選資料
- `result_card`：結果卡片，整理重點、狀態與下一步
- `source_evidence`：來源與更新狀態，顯示資料來源與更新時間
- `admin_record_table`：管理資料表，提供管理者查詢與維護紀錄

## 使用方式

- `components.css` 已由網站主樣式載入。
- `interactions.js` 已由所有頁面載入。
- `design-tokens.json` 可用來安全調整色彩、版型、斷點與動效。
- `component-catalog.json` 記錄本產業選用了哪些元件及原因。
- JavaScript 關閉時內容仍可讀；使用者要求減少動態效果時會自動停用動畫。
