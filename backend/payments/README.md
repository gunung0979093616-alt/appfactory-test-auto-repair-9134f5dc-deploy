# PAYUNi Payment Backend Scaffold

This generated scaffold is for the developer's own project.

## What is generated

- Project-specific plan page: `frontend_site/payment.html`
- Server-side order creation: `backend/payments/payment_api.py`
- PAYUNi UPP adapter boundary: `backend/payments/payuni_adapter.py`
- Notify/Return separation
- Entitlement ledger
- Authenticated member account page: `frontend_site/account.html`
- Owner-only payment and entitlement overview: `frontend_site/admin/payments.html`
- Purchase time, activation time, expiry, remaining days or units, refund and reconciliation status
- Quota and expiry rules
- Refund/cancel/expiry reconciliation placeholder
- Desktop/mobile checkout tests
- Lifecycle result: `WAITING_STAGE3`, `SCAFFOLD_READY`, `WAITING_PROVIDER`, `TECHNICAL_VERIFICATION`, or `LIVE_READY`

## Launch gate

`PUBLIC_CHECKOUT_ENABLED=false`

Keep public checkout closed until the owner has completed PAYUNi merchant/KYC approval, current official docs review, secret-manager setup, sandbox/provider-approved test, Notify verification, Return polling, idempotent duplicate Notify, refund/cancel/expiry checks, desktop/mobile checkout tests, and owner-approved live smoke.

ReturnURL is display-only. It must not grant entitlement.

Automatic renewal is outside this Stage 4 execution scope. The generated payment rail is PAYUNi credit-card one-time payment only.

## Current project goal

建立三間汽車保養維修廠營運 ChatGPT App：先診斷等待過久的根因，再管理預約、接車、工單、技師技能、工位、零件等待、報價核准、進度通知與完工交車。不得在未驗證根因前只做排班系統。需要前後端網站、管理後台、工具、技能、測試與 ZIP。
