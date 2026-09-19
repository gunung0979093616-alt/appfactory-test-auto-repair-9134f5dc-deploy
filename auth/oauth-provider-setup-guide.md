# OAuth Provider Setup

```json
{
  "owner_must_do": [
    "登入 Google Cloud 或 provider",
    "建立或選擇 OAuth app",
    "設定 OAuth consent screen、應用程式名稱、授權網域、隱私權政策與支援信箱",
    "建立 Web OAuth client 並加入目前專案實際需要的 authorized JavaScript origins",
    "處理 OTP/CAPTCHA/法律確認"
  ],
  "agent_can_do": [
    "從實際 runtime 判斷 website login 是 ID-token POST 或 authorization-code callback",
    "產生實際需要的 origin、redirect URI 與 env manifest",
    "建立 validation checklist",
    "產生 Google 官方設定逐欄引導",
    "產生 ChatGPT 送審 OAuth 一致性檢查表",
    "引導 owner 提供遮罩後的官方完成狀態，不要求任何 secret 值"
  ],
  "agent_must_not_do": [
    "要求使用者把密碼或 OTP 貼進聊天",
    "把 client secret 寫入 repo",
    "重用參考案例的 client id、client secret、redirect uri 或品牌資料",
    "假裝已完成 live OAuth"
  ]
}
```
