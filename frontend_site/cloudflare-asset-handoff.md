Cloudflare / public image URL handoff

Project: 汽車服務系統
Status: LOCAL_ASSETS_READY
Public URL status: PUBLIC_URL_NOT_VERIFIED

What is already created:
- frontend_site/public/assets/logo-256.svg
- frontend_site/public/assets/industry-hero.svg
- frontend_site/public/assets/industry-background.svg
- frontend_site/public/assets/asset-manifest.json

Owner authorization boundary:
- Cloudflare Images or R2 upload requires the project owner to authorize the provider account.
- Cloudflare R2 Standard storage has a 10 GB-month/month free tier reference, but that does not mean a bucket is already created or connected.
- Do not ask the owner to paste passwords, OTP, API tokens, cookies, or private keys into chat.
- A public image URL is complete only after the provider or deployed site returns a reachable HTTPS URL and the asset manifest is updated with public_url_verified=true.
- The default industry background is a local generated SVG example. If the owner wants AI-generated photos or brand images, guide them to use their own authorized image-generation, Canva, Figma, or storage account, then replace the image slot and re-run validation.

Safe continuation:
1. Keep local assets in frontend_site/public/assets/.
2. If deploying the website, the frontend hosting provider may make these assets public under that site URL.
3. If using Cloudflare R2, create or select an owner-approved Standard bucket, upload only approved images, configure public/custom-domain access, then record the returned public HTTPS URLs in asset-manifest.json.
4. If using Cloudflare Images, upload only owner-approved images, record image IDs/delivery URLs, then validate reachable HTTPS URLs.
5. Re-run website validation before marking the project delivery complete.
