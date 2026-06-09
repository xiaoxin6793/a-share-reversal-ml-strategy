"""
Step 2（修正版）: 构建反转策略 + 机器学习策略
修正内容：
  1. 收益率 Winsorize（去极端值：月收益裁剪至 [-50%, +100%]）
  2. 剔除市值最小5%的壳公司
  3. 基线策略全样本运行，ML策略仅测试集
  4. 交易成本20bps/月
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge, Lasso
import xgboost as xgb
from sklearn.preprocessing import StandardScaler
import warnings, os, json
warnings.filterwarnings('ignore')

# ============================================================
# 路径配置（使用相对路径）
# ============================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PANEL_FILE = os.path.join(BASE_DIR, "data", "monthly_panel.parquet")
RESULTS_DIR = os.path.join(BASE_DIR, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

# ============================================================
# 1. 加载数据，清洗
# ============================================================
print("=" * 60)
print("Step 2: 策略回测（修正版）")
print("=" * 60)

print("\n加载月度面板数据...")
panel = pd.read_parquet(PANEL_FILE)
panel = panel[panel['wind_code'].str.endswith(('.SZ', '.SH'))].copy()
panel['ret'] = panel['ret_monthly'] / 100.0

# ★ 修正1: Winsorize 极端收益
# 原始数据中存在极端值（月收益 2432%、-95% 等），
# 这些通常是数据异常或壳公司炒作，不具代表性
ret_lo, ret_hi = -0.50, 1.00
n_clipped = ((panel['ret'] < ret_lo) | (panel['ret'] > ret_hi)).sum()
panel['ret'] = panel['ret'].clip(ret_lo, ret_hi)
print(f"  Winsorize [{ret_lo*100:.0f}%, {ret_hi*100:.0f}%]: 影响 {n_clipped} 条 ({n_clipped/len(panel)*100:.2f}%)")

# ★ 修正2: 剔除市值最小5%（壳公司/数据异常）
# 小市值公司流动性差、数据质量低，且壳资源炒作严重
if 'mktcap' in panel.columns:
    before = len(panel)
    # 每期独立过滤，保留 date 列
    keep_mask = panel.groupby(panel['date'].astype(str))['mktcap'].transform(
        lambda x: x >= x.quantile(0.05)
    )
    panel = panel[keep_mask].reset_index(drop=True)
    print(f"  剔除最小5%市值: {before - len(panel)} 条 → {len(panel)} 条")

panel = panel.sort_values(['wind_code', 'date']).reset_index(drop=True)
print(f"数据范围: {panel['date'].min().strftime('%Y-%m')} ~ {panel['date'].max().strftime('%Y-%m')}")
print(f"股票数: {panel['wind_code'].nunique()}, 总观测: {len(panel)}")

# ============================================================
# 2. 构建特征
# ============================================================
print("\n构建特征...")
panel = panel.copy()
panel = panel.sort_values(['wind_code', 'date'])
grp = panel.groupby('wind_code')

# 动量/反转特征：使用 lag(1) 避免未来信息泄露
panel['mom1'] = grp['ret'].shift(1)  # 1月反转信号
panel['mom3'] = grp['ret'].shift(1).rolling(3, min_periods=2).apply(
    lambda x: (1 + x).prod() - 1, raw=True
).values  # 3月累计收益
panel['mom6'] = grp['ret'].shift(1).rolling(6, min_periods=4).apply(
    lambda x: (1 + x).prod() - 1, raw=True
).values  # 6月累计收益
panel['mom12'] = grp['ret'].shift(1).rolling(12, min_periods=8).apply(
    lambda x: (1 + x).prod() - 1, raw=True
).values  # 12月累计收益
panel['log_mktcap'] = np.log(panel['mktcap'].clip(lower=1e6))  # 对数市值
panel['ret_next'] = grp['ret'].shift(-1)  # 下月收益（预测目标）

# ============================================================
# 3. 样本分割
# ============================================================
TRAIN_END = '2019-12-31'  # 训练集结束
VAL_END   = '2022-12-31'  # 验证集结束
FEATURES  = ['mom1', 'mom3', 'mom6', 'mom12', 'log_mktcap']
TARGET    = 'ret_next'
COST      = 0.002  # 20bps/月交易成本

panel_valid = panel.dropna(subset=FEATURES + [TARGET]).copy()
train_df = panel_valid[panel_valid['date'] <= TRAIN_END]
val_df   = panel_valid[(panel_valid['date'] > TRAIN_END) & (panel_valid['date'] <= VAL_END)]
test_df  = panel_valid[panel_valid['date'] > VAL_END]

print(f"\n样本划分:")
print(f"  训练集: {train_df['date'].min().strftime('%Y-%m')} ~ {train_df['date'].max().strftime('%Y-%m')}  ({len(train_df):,} obs)")
print(f"  验证集: {val_df['date'].min().strftime('%Y-%m')} ~ {val_df['date'].max().strftime('%Y-%m')}  ({len(val_df):,} obs)")
print(f"  测试集: {test_df['date'].min().strftime('%Y-%m')} ~ {test_df['date'].max().strftime('%Y-%m')}  ({len(test_df):,} obs)")

# ============================================================
# 4. 基线反转策略（全样本）
# ============================================================
print("\n构建基线反转策略...")

def run_reversal_strategy(df, signal_col='mom1'):
    """传统反转策略：按信号排序，做多过去涨幅最小的20%，做空涨幅最大的20%"""
    results = []
    for date, grp in df.groupby('date'):
        grp = grp.dropna(subset=[signal_col, 'ret_next'])
        if len(grp) < 20:
            continue
        grp = grp.copy()
        grp['rank'] = grp[signal_col].rank(pct=True)
        long_leg  = grp[grp['rank'] <= 0.2]   # 过去涨幅最小 → 做多（反转逻辑）
        short_leg = grp[grp['rank'] >= 0.8]   # 过去涨幅最大 → 做空
        ls_ret    = long_leg['ret_next'].mean() - short_leg['ret_next'].mean()
        long_ret  = long_leg['ret_next'].mean()
        results.append({'date': date, 'ls_ret': ls_ret, 'long_ret': long_ret})
    return pd.DataFrame(results).set_index('date').sort_index()

bt_mom1 = run_reversal_strategy(panel_valid, 'mom1')
bt_mom3 = run_reversal_strategy(panel_valid, 'mom3')
bt_mom6 = run_reversal_strategy(panel_valid, 'mom6')

# 扣除交易成本（多空各10bps单边，共20bps/月）
for bt in [bt_mom1, bt_mom3, bt_mom6]:
    bt['ls_ret_net']   = bt['ls_ret'] - COST
    bt['long_ret_net'] = bt['long_ret'] - COST / 2

print(f"  mom1: {len(bt_mom1)} 期 ({bt_mom1.index.min().strftime('%Y-%m')} ~ {bt_mom1.index.max().strftime('%Y-%m')})")

# ============================================================
# 5. 机器学习策略（仅测试集）
# ============================================================
print("\n训练机器学习模型...")
X_train = train_df[FEATURES].values
y_train = train_df[TARGET].values
X_val   = val_df[FEATURES].values
y_val   = val_df[TARGET].values
X_test  = test_df[FEATURES].values
y_test  = test_df[TARGET].values

# 标准化（基于训练集统计量）
scaler = StandardScaler()
X_train_s = scaler.fit_transform(X_train)
X_val_s   = scaler.transform(X_val)
X_test_s  = scaler.transform(X_test)

# 模型定义
models = {
    'OLS(Ridge)': Ridge(alpha=1.0),
    'Lasso': Lasso(alpha=0.001, max_iter=5000),
    'Random Forest': RandomForestRegressor(
        n_estimators=200, max_depth=5,
        min_samples_leaf=50, n_jobs=-1, random_state=42
    ),
    'XGBoost': xgb.XGBRegressor(
        n_estimators=200, max_depth=3, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        random_state=42, verbosity=0
    ),
}

ml_bt_results = {}
ml_metrics = {}

for model_name, model in models.items():
    print(f"  训练 {model_name}...")
    model.fit(X_train_s, y_train)

    # 预测
    val_pred  = model.predict(X_val_s)
    test_pred = model.predict(X_test_s)

    # 计算信息系数（IC）
    val_ic  = np.corrcoef(val_pred, y_val)[0, 1]
    test_ic = np.corrcoef(test_pred, y_test)[0, 1]

    # 测试集多空组合：按预测排序，做多预测最高20%，做空最低20%
    test_df_copy = test_df.copy()
    test_df_copy['pred'] = test_pred
    bt_ml_results = []
    for date, grp in test_df_copy.groupby('date'):
        grp = grp.dropna(subset=['pred', 'ret_next'])
        if len(grp) < 20:
            continue
        grp = grp.copy()
        grp['rank'] = grp['pred'].rank(pct=True)
        long_leg  = grp[grp['rank'] >= 0.8]   # 预测涨幅最高 → 做多
        short_leg = grp[grp['rank'] <= 0.2]   # 预测涨幅最低 → 做空
        ls_ret    = long_leg['ret_next'].mean() - short_leg['ret_next'].mean()
        long_ret  = long_leg['ret_next'].mean()
        bt_ml_results.append({
            'date': date,
            'ls_ret': ls_ret - COST,        # 扣除交易成本
            'long_ret': long_ret - COST / 2,
        })

    bt_ml = pd.DataFrame(bt_ml_results).set_index('date').sort_index()
    ml_bt_results[model_name] = bt_ml

    # 计算绩效指标
    s = bt_ml['ls_ret']
    ar = (1+s).prod()**(12/len(s)) - 1 if len(s) > 0 else np.nan
    vol = s.std() * np.sqrt(12) if len(s) > 1 else np.nan
    sr = (ar - 0.03) / vol if vol > 0 else np.nan  # 无风险利率3%
    cum = (1+s).cumprod()
    dd = (cum / cum.cummax() - 1).min()

    ml_metrics[model_name] = {
        'val_ic': val_ic, 'test_ic': test_ic,
        'ann_ret': ar, 'sharpe': sr, 'max_dd': dd,
    }
    print(f"    ValIC={val_ic:.4f}, TestIC={test_ic:.4f}, 夏普={sr:.3f}, 年化={ar*100:.2f}%")

# ============================================================
# 6. 汇总绩效表（测试集）
# ============================================================
print("\n" + "=" * 60)
print("绩效汇总（测试集 2023-2025）")
print("=" * 60)

def calc_metrics(ret_series, label='策略'):
    """计算策略绩效指标：年化收益、波动率、夏普比率、最大回撤"""
    ret = ret_series.dropna()
    if len(ret) == 0:
        return None
    ann_ret = (1 + ret).prod() ** (12 / len(ret)) - 1
    ann_vol = ret.std() * np.sqrt(12)
    rf = 0.03  # 无风险利率3%/年
    sharpe = (ann_ret - rf) / ann_vol if ann_vol > 0 else 0
    cum = (1 + ret).cumprod()
    dd = (cum / cum.cummax() - 1).min()
    return {
        'Label': label,
        'Ann. Return': f"{ann_ret*100:.2f}%",
        'Ann. Vol': f"{ann_vol*100:.2f}%",
        'Sharpe Ratio': f"{sharpe:.3f}",
        'Max Drawdown': f"{dd*100:.2f}%",
        'Sharpe_num': sharpe, 'AnnRet_num': ann_ret,
        'AnnVol_num': ann_vol, 'MaxDD_num': dd,
    }

summary_rows = []
for label, bt, col in [
    ('传统反转-Mom1(多空)', bt_mom1, 'ls_ret_net'),
    ('传统反转-Mom1(仅多)', bt_mom1, 'long_ret_net'),
    ('传统反转-Mom3(多空)', bt_mom3, 'ls_ret_net'),
]:
    test_bt = bt[bt.index > VAL_END]
    m = calc_metrics(test_bt[col], label)
    if m:
        summary_rows.append(m)
        print(f"  {label}: 夏普={m['Sharpe Ratio']}, 年化={m['Ann. Return']}, 回撤={m['Max Drawdown']}")

for model_name in models:
    bt_ml = ml_bt_results[model_name]
    m = calc_metrics(bt_ml['ls_ret'], f"{model_name}(多空)")
    if m:
        summary_rows.append(m)
        print(f"  {model_name}(多空): 夏普={m['Sharpe Ratio']}, 年化={m['Ann. Return']}, 回撤={m['Max Drawdown']}")

summary_df = pd.DataFrame(summary_rows)

# ============================================================
# 7. 保存结果
# ============================================================
all_bt = {}
all_bt['baseline_mom1_ls'] = bt_mom1['ls_ret_net']
all_bt['baseline_mom3_ls'] = bt_mom3['ls_ret_net']
all_bt['baseline_mom6_ls'] = bt_mom6['ls_ret_net']
for model_name, bt_ml in ml_bt_results.items():
    safe_name = model_name.replace(' ', '_').replace('(', '').replace(')', '')
    all_bt[f'ml_{safe_name}_ls'] = bt_ml['ls_ret']

bt_df = pd.DataFrame(all_bt)
bt_df.to_parquet(os.path.join(RESULTS_DIR, 'backtest_monthly_returns.parquet'))
summary_df.to_csv(os.path.join(RESULTS_DIR, 'performance_summary.csv'), index=False, encoding='utf-8-sig')

# 保存特征重要性
for model_name, model in models.items():
    if hasattr(model, 'feature_importances_'):
        fi = pd.Series(model.feature_importances_, index=FEATURES, name=model_name)
        fi.to_csv(os.path.join(RESULTS_DIR, f'feature_importance_{model_name.replace(" ","_")}.csv'))
        print(f"\n{model_name} 特征重要性:")
        print(fi.sort_values(ascending=False).to_string())

# 保存上下文信息
ctx = {
    'train_end': TRAIN_END, 'val_end': VAL_END,
    'features': FEATURES, 'cost': COST,
    'winsorize': [ret_lo, ret_hi],
    'baseline_test_sharpe_mom1_ls': float(
        bt_mom1[bt_mom1.index > VAL_END]['ls_ret_net'].mean() /
        bt_mom1[bt_mom1.index > VAL_END]['ls_ret_net'].std() * np.sqrt(12)
    ) if len(bt_mom1[bt_mom1.index > VAL_END]) > 0 else None,
}
with open(os.path.join(RESULTS_DIR, 'context.json'), 'w') as f:
    json.dump(ctx, f, indent=2, ensure_ascii=False)

print(f"\n✅ 结果已保存至: {RESULTS_DIR}")
