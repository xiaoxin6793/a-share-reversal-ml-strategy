# 数据目录

本目录存放月度面板数据文件 `monthly_panel.parquet`。

由于数据文件较大，未上传至 GitHub。请自行准备数据并放入此目录。

## 数据格式要求

| 列名 | 类型 | 说明 |
|------|------|------|
| `wind_code` | str | 证券代码（如 000001.SZ、600000.SH） |
| `date` | datetime | 月末日期 |
| `ret_monthly` | float | 月收益率（百分比形式，如 5.23 表示 5.23%） |
| `mktcap` | float | 总市值（元） |

## 数据来源

推荐使用 Wind、Tushare 或 CSMAR 数据库获取 A 股月度交易数据。
