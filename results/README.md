# 结果目录

本目录存放回测结果文件，由 `src/step2_strategy_v2.py` 和 `src/step3_ff3_v2.py` 自动生成。

由于结果文件可由代码重新生成，未上传至 GitHub。运行代码后此目录将自动填充。

## 生成文件说明

| 文件名 | 生成脚本 | 说明 |
|--------|---------|------|
| `backtest_monthly_returns.parquet` | step2 | 各策略月度收益序列 |
| `performance_summary.csv` | step2 | 绩效指标汇总 |
| `ff3_attribution.csv` | step3 | FF3 三因子归因结果 |
| `ff3_factors.parquet` | step3 | FF3 因子数据 |
| `feature_importance_Random_Forest.csv` | step2 | 随机森林特征重要性 |
| `feature_importance_XGBoost.csv` | step2 | XGBoost 特征重要性 |
| `context.json` | step2 | 回测参数与时间范围配置 |
