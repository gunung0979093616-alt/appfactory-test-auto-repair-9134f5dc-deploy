# Session and Cookie Boundary

```json
{
  "cookie": "httpOnly, secure in production, sameSite appropriate for ChatGPT/OAuth flow",
  "token_storage": "server-side or signed session only; never expose OAuth refresh token to frontend",
  "logout": "clear session and revoke project-local session; provider revocation optional by provider capability"
}
```
