"""
Step 3（修正版）: Fama-French 三因子归因
使用截面代理因子（与上一版相同），但基于修正后的回测数据

因子构建方法：
- MKT: 全市场等权平均收益 - 无风险利率
- SMB: 小市值组合收益 - 大市值组合收益（30%/70%分位）
- HML: 高动量组合收益 - 低动量组合收益（用12月动量代理价值因子）
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd
import numpy as np
import statsmodels.api as sm
import os, warnings
warnings.filterwarnings('ignore')

# ============================================================
# 路径配置（使用相对路径）
# ============================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PANEL_FILE = os.path.join(BASE_DIR, "data", "monthly_panel.parquet")
RESULTS_DIR = os.path.join(BASE_DIR, "results")

# ============================================================
# 1. 构建FF3代理因子（与策略同样的数据清洗）
# ============================================================
print("构建Fama-French三因子代理...")

panel = pd.read_parquet(PANEL_FILE)
panel = panel[panel['wind_code'].str.endswith(('.SZ', '.SH'))].copy()
panel['ret'] = panel['ret_monthly'] / 100.0

# 与step2同样的清洗，确保一致性
panel['ret'] = panel['ret'].clip(-0.50, 1.00)
if 'mktcap' in panel.columns:
    keep_mask = panel.groupby(panel['date'].astype(str))['mktcap'].transform(
        lambda x: x >= x.quantile(0.05)
    )
    panel = panel[keep_mask].reset_index(drop=True)

panel = panel.sort_values(['wind_code', 'date'])

rf_monthly = 0.03 / 12  # 月度无风险利率

def build_ff3_proxy(panel, rf=0.03/12):
    """
    构建Fama-French三因子代理
    
    注意：此处的HML因子用12月动量排序构建，
    严格来说应是B/M（账面市值比），但由于数据限制，
    用动量排序作为代理。这一局限性在报告中有讨论。
    """
    results = []
    panel_sorted = panel.copy()
    panel_sorted['mom12'] = panel_sorted.groupby('wind_code')['ret'].transform(
        lambda x: x.shift(1).rolling(12, min_periods=8).apply(lambda r: (1+r).prod()-1, raw=True)
    )

    for date, grp in panel_sorted.groupby('date'):
        grp = grp.dropna(subset=['ret', 'mktcap'])
        if len(grp) < 50:
            continue
        
        # 市场因子
        mkt = grp['ret'].mean() - rf

        # 规模因子（SMB）：小盘 - 大盘
        grp_sorted_cap = grp.sort_values('mktcap')
        n = len(grp_sorted_cap)
        small = grp_sorted_cap.iloc[:int(n*0.3)]['ret'].mean()  # 最小30%
        big   = grp_sorted_cap.iloc[int(n*0.7):]['ret'].mean()  # 最大30%
        smb   = small - big

        # 价值因子代理（HML）：高动量 - 低动量
        grp_hml = grp.dropna(subset=['mom12'])
        hml = np.nan
        if len(grp_hml) >= 50:
            grp_sorted_mom = grp_hml.sort_values('mom12')
            n2 = len(grp_sorted_mom)
            high_bm = grp_sorted_mom.iloc[:int(n2*0.3)]['ret'].mean()
            low_bm  = grp_sorted_mom.iloc[int(n2*0.7):]['ret'].mean()
            hml = high_bm - low_bm

        results.append({'date': date, 'MKT': mkt, 'SMB': smb, 'HML': hml, 'RF': rf})

    return pd.DataFrame(results).set_index('date').sort_index()

ff3_df = build_ff3_proxy(panel)
print(f"FF3因子: {len(ff3_df)} 期 ({ff3_df.index.min().strftime('%Y-%m')} ~ {ff3_df.index.max().strftime('%Y-%m')})")
print("\n年化因子收益:")
for col in ['MKT','SMB','HML']:
    print(f"  {col}: {ff3_df[col].mean()*12*100:.2f}%/年")

ff3_df.to_parquet(os.path.join(RESULTS_DIR, 'ff3_factors.parquet'))

# ============================================================
# 2. FF3回归
# ============================================================
print("\n加载策略月度收益...")
bt_returns = pd.read_parquet(os.path.join(RESULTS_DIR, 'backtest_monthly_returns.parquet'))

# 对齐日期格式
bt_returns.index = pd.to_datetime(bt_returns.index).to_period('M').to_timestamp()
ff3_monthly = ff3_df.copy()
ff3_monthly.index = pd.to_datetime(ff3_monthly.index).to_period('M').to_timestamp()

combined = bt_returns.join(ff3_monthly[['MKT', 'SMB', 'HML']], how='inner')
print(f"对齐后: {len(combined)} 行")

def run_ff3_regression(strategy_ret, mkt, smb, hml, strategy_name, rf=0.03/12):
    """
    运行Fama-French三因子回归：
    R_p - Rf = alpha + beta_MKT * MKT + beta_SMB * SMB + beta_HML * HML + epsilon
    
    使用 HC3 异方差稳健标准误
    """
    data = pd.DataFrame({
        'ret': strategy_ret, 'MKT': mkt, 'SMB': smb, 'HML': hml
    }).dropna()
    if len(data) < 12:
        return None
    y = data['ret'] - rf
    X = sm.add_constant(data[['MKT', 'SMB', 'HML']])
    model = sm.OLS(y, X).fit(cov_type='HC3')
    return {
        'Strategy': strategy_name,
        'N_obs': len(data),
        'Alpha(月)': model.params.get('const', np.nan),
        'Alpha(年化)': model.params.get('const', np.nan) * 12,
        'Alpha_pvalue': model.pvalues.get('const', np.nan),
        'Alpha_tstat': model.tvalues.get('const', np.nan),
        'MKT_beta': model.params.get('MKT', np.nan),
        'MKT_pvalue': model.pvalues.get('MKT', np.nan),
        'SMB_beta': model.params.get('SMB', np.nan),
        'SMB_pvalue': model.pvalues.get('SMB', np.nan),
        'HML_beta': model.params.get('HML', np.nan),
        'HML_pvalue': model.pvalues.get('HML', np.nan),
        'R_squared': model.rsquared,
        'Adj_R2': model.rsquared_adj,
    }

# 策略标签映射
STRATEGY_LABELS = {
    'baseline_mom1_ls': '反转策略Mom1(多空)',
    'baseline_mom3_ls': '反转策略Mom3(多空)',
    'baseline_mom6_ls': '反转策略Mom6(多空)',
    'ml_OLSRidge_ls': 'Ridge(多空)',
    'ml_Lasso_ls': 'Lasso(多空)',
    'ml_Random_Forest_ls': 'RandomForest(多空)',
    'ml_XGBoost_ls': 'XGBoost(多空)',
}

print("\n" + "=" * 60)
print("FF3因子归因结果")
print("=" * 60)

attr_results = []
for col in bt_returns.columns:
    if col in combined.columns:
        label = STRATEGY_LABELS.get(col, col)
        result = run_ff3_regression(
            combined[col], combined['MKT'], combined['SMB'], combined['HML'],
            strategy_name=label
        )
        if result:
            attr_results.append(result)
            m = result
            sig = "**" if m['Alpha_pvalue'] < 0.05 else ("*" if m['Alpha_pvalue'] < 0.1 else "  ")
            print(f"  [{label}]  N={m['N_obs']}")
            print(f"    Alpha: {m['Alpha(年化)']*100:.2f}%/年  t={m['Alpha_tstat']:.2f}  p={m['Alpha_pvalue']:.3f} {sig}")
            print(f"    MKTβ={m['MKT_beta']:.3f}  SMBβ={m['SMB_beta']:.3f}  HMLβ={m['HML_beta']:.3f}  R²={m['R_squared']:.3f}")

attr_df = pd.DataFrame(attr_results)
attr_df.to_csv(os.path.join(RESULTS_DIR, 'ff3_attribution.csv'), index=False, encoding='utf-8-sig')
print(f"\n✅ FF3归因已保存")
