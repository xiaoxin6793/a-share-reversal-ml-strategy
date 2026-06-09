# A股短期反转策略与机器学习增强研究

> 量化策略回测、FF3因子归因与交互式Dashboard

## 📋 项目简介

本研究探索**机器学习能否有效改进传统短期反转策略**。基于A股全市场5,418只股票、2013–2025年的月频数据，构建了3种传统反转基线策略和4种机器学习策略（Ridge、Lasso、随机森林、XGBoost），采用三段式样本外验证（训练/验证/测试），并进行Fama-French三因子归因分析。

### 核心结论

**机器学习未能有效改进反转策略。** 在测试集（2023–2025）上：
- 基线反转 Mom1 多空：夏普比率 -0.263，年化收益 +0.24%
- 所有 ML 模型夏普比率为负（-0.7 ~ -0.9），表现不如简单基线
- FF3 Alpha 均为负且不显著

> ⚠️ 本研究如实报告负面结果。负面结果同样具有学术价值——它揭示了A股市场结构变化下传统因子的失效。

---

## 📁 项目结构

```
a-share-reversal-ml-strategy/
├── README.md                   # 本文件
├── requirements.txt            # Python 依赖
├── .gitignore
├── src/                        # 源代码
│   ├── step2_strategy_v2.py    # 策略回测（反转+ML）
│   ├── step3_ff3_v2.py         # FF3因子归因
│   ├── step4_charts_v2.py      # 图表生成
│   ├── generate_report_v2.py   # DOCX报告生成
│   └── dashboard.py            # Streamlit交互式Dashboard
├── data/                       # 数据目录（需自行准备）
│   └── monthly_panel.parquet   # 月度面板数据（未上传，见下方说明）
├── results/                    # 回测结果（由代码生成）
│   ├── backtest_monthly_returns.parquet
│   ├── performance_summary.csv
│   ├── ff3_attribution.csv
│   ├── ff3_factors.parquet
│   ├── feature_importance_*.csv
│   └── context.json
└── report/
    ├── report_final_v2.docx    # 最终研究报告
    └── figures/                # 图表文件
        ├── fig1_cumulative_returns.png
        ├── fig1b_baseline_full_sample.png
        ├── fig2_drawdowns.png
        ├── fig3_performance_comparison.png
        ├── fig4_feature_importance.png
        ├── fig5_ff3_alpha.png
        ├── fig6_return_distribution.png
        └── fig7_yearly_heatmap.png
```

---

## 🚀 快速开始

### 1. 环境配置

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 2. 数据准备

将 `monthly_panel.parquet` 放入 `data/` 目录。该文件需包含以下列：

| 列名 | 说明 |
|------|------|
| `wind_code` | 证券代码（如 000001.SZ） |
| `date` | 日期（月末） |
| `ret_monthly` | 月收益率（百分比，如 5.23 表示 5.23%） |
| `mktcap` | 市值（元） |

> 数据来源：CSMAR 数据库，覆盖 A 股全市场，时间范围 2013–2025。

### 3. 运行回测

按顺序执行：

```bash
# Step 2: 策略回测（生成 results/ 下的所有文件）
python src/step2_strategy_v2.py

# Step 3: FF3因子归因
python src/step3_ff3_v2.py

# Step 4: 生成图表
python src/step4_charts_v2.py

# 生成 DOCX 报告
python src/generate_report_v2.py
```

### 4. 启动 Dashboard

```bash
streamlit run src/dashboard.py
```

Dashboard 包含5个交互模块：
- 📊 净值与回撤
- 🏆 绩效对比
- 🧮 FF3因子归因
- 🌲 特征重要性
- 📋 策略说明

---

## 📊 研究方法

### 数据清洗

| 处理步骤 | 说明 |
|---------|------|
| Winsorize | 月收益率裁剪至 [-50%, +100%]，剔除 8,949 条极端值 |
| 市值过滤 | 剔除每期市值最小5%（壳公司），去除 27,252 条 |
| 最终样本 | 5,418 只股票，510,134 条观测 |

### 特征构建

| 特征 | 计算方式 |
|------|---------|
| Mom1 | 上月收益率（1个月反转信号） |
| Mom3 | 过去3个月累计收益 |
| Mom6 | 过去6个月累计收益 |
| Mom12 | 过去12个月累计收益 |
| log_mktcap | 对数市值 |

### 样本划分

| 区间 | 时间范围 | 用途 |
|------|---------|------|
| 训练集 | 2014-01 ~ 2019-12 | 模型训练 |
| 验证集 | 2020-01 ~ 2022-12 | 超参选择 |
| 测试集 | 2023-01 ~ 2025-11 | 最终评估（仅用一次） |

### 策略构建

- **基线策略**：按信号排序，做多前20%（过去涨幅最小）+ 做空后20%（过去涨幅最大）
- **ML策略**：用模型预测下月收益，做多预测最高20% + 做空预测最低20%
- **交易成本**：20 bps/月（多空各10bps单边）

---

## 📈 实证结果

### 测试集绩效（2023–2025，N=35个月）

| 策略 | 年化收益 | 年化波动 | 夏普比率 | 最大回撤 |
|------|---------|---------|---------|---------|
| 反转-Mom1（基线） | +0.24% | 8.98% | -0.263 | -12.25% |
| Ridge 回归 | -4.75% | 9.79% | -0.778 | -20.48% |
| Lasso 回归 | -5.05% | 9.83% | -0.798 | -20.66% |
| 随机森林 | -8.56% | 12.27% | -0.931 | -28.70% |
| XGBoost | -5.87% | 12.37% | -0.715 | -23.44% |

### FF3因子归因

所有策略的 Alpha 均为负且不显著（p > 0.05），说明策略收益可被三因子模型解释，不存在超额 Alpha。

---

## ⚠️ 局限性与讨论

1. **ML预测失效**：测试集IC为负，模型在A股上泛化能力差
2. **特征集有限**：仅5个价格/规模特征，缺少基本面和另类数据
3. **样本期短**：测试集仅35个月，统计检验力有限
4. **交易成本简化**：固定20bps/月，未考虑市场冲击
5. **做空限制**：A股做空困难，多空策略仅为理论构造

---

## 📚 参考文献

1. Jegadeesh, N., & Titman, S. (1993). Returns to buying winners and selling losers. *Journal of Finance*, 48(1), 65-91.
2. Fama, E. F., & French, K. R. (1993). Common risk factors in the returns on stocks and bonds. *Journal of Financial Economics*, 33(1), 3-56.
3. Gu, S., Kelly, B., & Xiu, D. (2020). Empirical asset pricing via machine learning. *Review of Financial Studies*, 33(5), 2223-2273.
4. Daniel, K., & Moskowitz, T. J. (2016). Momentum crashes. *Journal of Financial Economics*, 122(2), 221-247.
5. De Bondt, W. F. M., & Thaler, R. (1985). Does the stock market overreact? *Journal of Finance*, 40(3), 793-805.

---

## 📄 License

MIT License - 仅用于学术研究和教学目的。
