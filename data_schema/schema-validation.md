# Schema 驗證規則

## 驗證規則

- 所有 required 欄位在正式匯入前必須有來源對應。
- 不得把 sample data 當成 production proof。

## 隱私規則

- 欄位預設 developer_private，除非明確標 public_ok。

## readiness

- status: `ready_for_database_design`
- can_start_database_design: `True`
- can_start_skill_definition: `True`
