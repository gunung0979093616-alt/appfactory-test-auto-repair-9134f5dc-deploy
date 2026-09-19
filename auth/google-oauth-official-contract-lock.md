# Google OAuth 官方設定合約鎖

本文件把參考案例的 OAuth 經驗轉成通用守門；不得複製參考案例的品牌、帳號、client id、client secret、token、cookie 或 production URL。

## Owner 必做

- 登入 Google Cloud 或 provider
- 建立或選擇 OAuth app
- 設定 OAuth consent screen、應用程式名稱、授權網域、隱私權政策與支援信箱
- 建立 Web OAuth client 並加入目前專案實際需要的 authorized JavaScript origins
- 處理 OTP/CAPTCHA/法律確認

## Frontend 合約

- login page must preserve safe next=/oauth-continue?...
- cross-origin auth fetch must include credentials when cookie sessions are used
- account switching must be available for cross-account testing

## Backend 合約

- Google ID token audience, issuer and signature are verified server-side before creating a local session
- session cookie is httpOnly and secure in production
- protected APIs authorize by local account and role, not by raw Google token in the browser

## Secret 邊界

- 只記錄 secret 放在哪個部署平台或 Secret Manager，不記錄 secret 值。
- 測試報告只能保留遮罩後 client id、redirect host、trace id、狀態碼與時間。
