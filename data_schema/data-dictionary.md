# 資料字典

## Entity: `business_record`

- `record_id` (string): general_operations 專案所需欄位：record_id。 required=True
- `record_name` (string): general_operations 專案所需欄位：record_name。 required=True
- `status` (string): general_operations 專案所需欄位：status。 required=True
- `updated_at` (datetime): 資料最後更新時間。 required=True
- `data_source_type` (string): 資料來源類型，例如 CSV、Google Sheet、資料庫或 API。 required=True
- `category` (string): general_operations 專案所需欄位：category。 required=False
- `owner` (string): general_operations 專案所需欄位：owner。 required=False
- `date_range` (datetime): general_operations 專案所需欄位：date_range。 required=False
- `notes` (string): general_operations 專案所需欄位：notes。 required=False
