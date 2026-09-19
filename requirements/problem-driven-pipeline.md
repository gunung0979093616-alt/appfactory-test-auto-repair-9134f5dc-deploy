# 跨產業問題驅動流程契約

## 一句話流程

找問題 → 排定問題重要性 → 判斷能不能解決 → 分析使用者會怎麼問 → 決定需要什麼資料 → 設計資料庫 → 設計索引 → 找資料來源 → 建立資料庫 → 驗證資料 → 設計 MCP 工具 → 建立 Skill → 開發後端 → 開發前端／Widget → 驗證產品 → 修復問題 → 部署上線。

## 專案產業

`general_operations`

## 流程表

| # | 步驟 | 階段 | 主要產物 | 狀態 |
|---|---|---|---|---|
| 1 | 產業類型 | 第一階段 | `requirements/requirements-spec.json` | completed_local |
| 2 | 問題探索 | 第一階段 | `requirements/requirement-model.json` | completed_local |
| 3 | 問題排序 | 第一階段 | `requirements/problem-driven-pipeline.json` | planned_minimum |
| 4 | 可解決性分析 | 第一階段 | `requirements/requirements-spec.json#solvability` | completed_local |
| 5 | 查詢模式分析 | 第一階段 | `data_schema/data-schema.json#query_rules` | next_stage |
| 6 | 資料需求分析 | 第一階段 | `requirements/requirements-spec.json#variables` | completed_local |
| 7 | 資料庫結構設計 | 第一階段 | `data_schema/data-schema.json` | next_stage |
| 8 | 索引設計 | 第一階段 | `database/indexes.sql` | next_stage |
| 9 | 資料來源探索 | 第一階段 | `data_inventory/data-inventory.json` | next_stage |
| 10 | 建立 SQLite 資料庫 | 第一階段 | `database/database.sqlite` | next_stage |
| 11 | 資料驗證 | 第一階段 | `database/data-quality-report.json` | next_stage |
| 12 | MCP 工具設計 | 第一階段 | `generated_mcp/design/tool-design.json` | next_stage |
| 13 | 技能設計 | 第一階段 | `skill/SKILL.md` | next_stage |
| 14 | 後端開發 | 第一／二階段 | `generated_mcp/server/server.py` | future_stage |
| 15 | 前端／互動元件開發 | 第二階段 | `frontend_site/index.html` | future_stage |
| 16 | 產品驗證 | 第二至第五階段 | `validation/` | future_stage |
| 17 | 問題修復 | 全階段 | `validation/* + CHANGELOG.md` | continuous_gate |
| 18 | 部署上線 | 第一至第五階段 | `deployment/` | owner_or_provider_gated |

## 不可誤報規則

Any downstream capability that lacks required data, schema, rows, authorization, or validation must be marked NOT_READY, DATA_INCOMPLETE, OWNER_ACTION_REQUIRED, or PROVIDER_GATED instead of PASS.

## 公開工具數量規則

This pipeline is an internal orchestration contract; it must be routed behind the existing public tools and must not add an 11th public MCP tool.
