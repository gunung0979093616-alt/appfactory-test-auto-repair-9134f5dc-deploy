# 汽車服務系統 前端網站

這個資料夾是第二階段可部署的靜態預覽 fallback，不是最終 SaaS 前端架構。

第二階段正式網站前後端目標固定為：

- Next.js App Router
- React
- TypeScript / TSX
- Tailwind CSS

靜態預覽用來讓管理者檢查內容、頁面、UI/UX recipe、授權邊界與交接資料；正式產業網站需要在開發者本人授權的工作區建立或遷移到 Next.js / React / Tailwind 專案後，再完成 build、runtime、部署與驗證。

已包含：

- `index.html`：外掛首頁與測試問句。
- `marketing.html`：方案價值、交付內容、授權邊界與完成證據說明。
- `pricing.html`：方案、加值階段、ZIP / GitHub / Render / ChatGPT 交付層級。
- `guide.html`：下載、授權、部署、MCP、ChatGPT Developer Mode 測試步驟。
- `templates.html`：跨產業模板、設計來源與品質守門。
- `assets.html`：圖片上傳、素材儲存、公開網址與授權邊界。
- `connect.html`：Google / GitHub / Render / ChatGPT Developer Mode 授權與串接引導。
- `docs.html`：自然語言測試問句與驗收順序。
- `status.html`：本機、部署、MCP、ChatGPT 原生測試的完成邊界。
- `robots.txt`、`sitemap.xml`、`public/manifest.webmanifest`：靜態網站基本發布素材。

## 本機預覽

```text
python3 -m http.server 3000
```

## 下一步

```text
前端頁面檔案已完成；下一步幫我部署到 Vercel，產生網站網址。
```

## 邊界

Frontend site builder creates a deployable static website preview fallback, local assets, and local validation proof only. The Stage 2 production website/frontend target for generated plugin/SaaS products is Next.js App Router + React + TypeScript + Tailwind. A public website URL, public image URL, connector validation, platform review, or approval requires the project owner to complete the related provider authorization and must be verified with reachable live evidence.
