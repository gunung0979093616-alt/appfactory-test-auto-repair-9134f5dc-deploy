# 持續資料同步操作手冊

1. 先以開發者自有資料來源建立 candidate，不直接覆蓋公開資料。
2. 檢查格式、唯一鍵、筆數、checksum 與抽樣資料；任何錯誤都保留上一個 published version。
3. 驗證通過後才原子切換 current version；API、MCP、網站與後台只能讀取 current_published_records。
4. 差異先做有限範圍修復；仍失敗時停止並留下 completed_with_mismatch，不可無限重跑。
5. 刪除必須由來源提供 `_deleted=true`，檔案暫時消失不等於刪除。
6. 雲端排程、外部 API、Google、R2 或正式資料庫必須由帳號本人授權；密碼、OTP、token、secret 不得貼在聊天。

本機驗證不等於雲端排程或正式資料來源已上線。
