# OAuth 手機與跨帳號測試矩陣

| Case | Surface | Account | Expected |
| --- | --- | --- | --- |
| desktop-owner | Chrome desktop | owner Google account | login -> callback -> /api/me -> logout |
| desktop-second-user | Chrome desktop incognito | second Google account | login creates a distinct local user and does not inherit owner session |
| mobile-safari | iOS Safari or responsive emulation | normal user | login buttons visible, no blank page, callback returns to intended page |
| mobile-chrome | Android Chrome or responsive emulation | normal user | OAuth resume survives app/browser switch |
| chatgpt-reviewer | ChatGPT native review path | reviewer account or seeded bypass | authorization-code + PKCE completes and protected tool/API works |
| negative-open-redirect | any browser | anonymous | unsafe next such as //evil.test is rejected |
| negative-unauthorized | API probe | anonymous | protected endpoint returns auth challenge and no private data |

所有失敗都要先分類為 provider setup、frontend resume、backend callback、session cookie、ChatGPT submission metadata、reviewer path 或 native client loading，不可直接要求使用者重建帳號。
