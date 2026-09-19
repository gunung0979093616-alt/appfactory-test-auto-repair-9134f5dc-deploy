# ChatGPT 送審 OAuth 一致性

網站登入、後端 OAuth server、MCP protected resource 與 ChatGPT 送審資料必須指向同一套正式網域與同一套授權邏輯。

## 必須一致

- authorization endpoint
- token endpoint
- OAuth metadata
- protected resource metadata when MCP is used
- PKCE state and redirect_uri preservation
- refresh token lifecycle when long-lived connector sessions are required
- reviewer test path with seeded non-sensitive data

## 不可做

- make reviewer use the owner's Google account
- require real payment to test basic protected flow
- use JavaScript-only approval buttons for external OAuth clients
- change scopes or redirect URIs between website login and ChatGPT submission without a new review

## 送審前證據

- Provider console 完成畫面或安全設定摘要。
- Deployed authorization/token/metadata endpoints live smoke。
- Reviewer path 可用且只看到測試資料。
- ChatGPT native 或送審測試 transcript 顯示 OAuth 完成後可呼叫受保護工具。
