"""
Step 4（修正版）: 生成所有图表
基于修正后的数据重新生成7张图表，用于报告和展示

图表列表：
  fig1  - 各策略累计净值（测试集）
  fig1b - 基线策略全样本净值（含训练/验证/测试分区）
  fig2  - 回撤曲线（测试集）
  fig3  - 绩效对比柱状图（夏普 + 年化收益）
  fig4  - Random Forest 特征重要性
  fig5  - FF3 Alpha 柱状图
  fig6  - 月度收益分布直方图
  fig7  - 年度收益热图
"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib import rcParams
import warnings
warnings.filterwarnings('ignore')

# 中文字体配置
rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
rcParams['axes.unicode_minus'] = False

# ============================================================
# 路径配置（使用相对路径）
# ============================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(BASE_DIR, 'results')
FIG_DIR     = os.path.join(BASE_DIR, 'report', 'figures')
os.makedirs(FIG_DIR, exist_ok=True)

VAL_END = '2022-12-31'

# 加载数据
bt_returns = pd.read_parquet(os.path.join(RESULTS_DIR, 'backtest_monthly_returns.parquet'))
bt_returns.index = pd.to_datetime(bt_returns.index)
perf_df = pd.read_csv(os.path.join(RESULTS_DIR, 'performance_summary.csv'))
attr_df = pd.read_csv(os.path.join(RESULTS_DIR, 'ff3_attribution.csv'))

# 测试集数据
test_bt = bt_returns[bt_returns.index > VAL_END].copy()
test_bt_cum = (1 + test_bt).cumprod()

# 策略颜色与标签配置
COLS_LABELS = [
    ('baseline_mom1_ls', '传统反转Mom1(基线)', '#1f77b4'),
    ('ml_Random_Forest_ls', 'Random Forest', '#d62728'),
    ('ml_XGBoost_ls', 'XGBoost', '#ff7f0e'),
    ('ml_OLSRidge_ls', 'Ridge', '#2ca02c'),
]

# ============================================================
# 图1: 净值曲线（测试集）
# ============================================================
print('生成图1: 净值曲线...')
fig, ax = plt.subplots(figsize=(12, 6))
for col, label, color in COLS_LABELS:
    if col in test_bt_cum.columns:
        s = test_bt_cum[col].dropna()
        ax.plot(s.index, s.values, label=label, color=color, linewidth=2)
ax.axhline(1, color='gray', linestyle='--', linewidth=0.8)
ax.set_title('图1: 各策略累计净值（测试集 2023-2025，已扣交易成本）', fontsize=14, fontweight='bold')
ax.set_xlabel('日期'); ax.set_ylabel('净值')
ax.legend(fontsize=10); ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, 'fig1_cumulative_returns.png'), dpi=150, bbox_inches='tight')
plt.close()

# ============================================================
# 图1b: 基线策略全样本净值
# ============================================================
print('生成图1b: 基线全样本净值...')
fig, ax = plt.subplots(figsize=(14, 6))
baseline_cols = [
    ('baseline_mom1_ls', '反转Mom1(多空)', '#1f77b4'),
    ('baseline_mom3_ls', '反转Mom3(多空)', '#ff7f0e'),
    ('baseline_mom6_ls', '反转Mom6(多空)', '#2ca02c'),
]
for col, label, color in baseline_cols:
    if col in bt_returns.columns:
        s = bt_returns[col].dropna()
        nav = (1 + s).cumprod()
        ax.plot(nav.index, nav.values, label=label, color=color, linewidth=1.5)

# 添加样本分区标注
ax.axvspan('2014-01-01', '2019-12-31', alpha=0.08, color='blue', label='训练集')
ax.axvspan('2020-01-01', '2022-12-31', alpha=0.08, color='orange', label='验证集')
ax.axvspan('2023-01-01', '2025-12-31', alpha=0.08, color='green', label='测试集')
ax.axhline(1, color='gray', linestyle='--', linewidth=0.8)
ax.set_title('图1b: 基线反转策略累计净值（全样本，已扣交易成本）', fontsize=14, fontweight='bold')
ax.set_xlabel('日期'); ax.set_ylabel('净值')
ax.legend(fontsize=9); ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, 'fig1b_baseline_full_sample.png'), dpi=150, bbox_inches='tight')
plt.close()

# ============================================================
# 图2: 回撤曲线（测试集）
# ============================================================
print('生成图2: 回撤曲线...')
fig, ax = plt.subplots(figsize=(12, 5))
for col, label, color in COLS_LABELS:
    if col in test_bt.columns:
        s = test_bt[col].dropna()
        cum = (1 + s).cumprod()
        dd = cum / cum.cummax() - 1
        ax.fill_between(dd.index, dd.values, 0, alpha=0.3, color=color, label=label)
        ax.plot(dd.index, dd.values, color=color, linewidth=1.5)
ax.set_title('图2: 各策略回撤曲线（测试集 2023-2025）', fontsize=14, fontweight='bold')
ax.set_xlabel('日期'); ax.set_ylabel('回撤')
ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1, decimals=0))
ax.legend(fontsize=10); ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, 'fig2_drawdowns.png'), dpi=150, bbox_inches='tight')
plt.close()

# ============================================================
# 图3: 绩效对比（柱状图）
# ============================================================
print('生成图3: 绩效对比...')
strategies_show = [
    '传统反转-Mom1(多空)', '传统反转-Mom3(多空)',
    'Random Forest(多空)', 'XGBoost(多空)',
    'OLS(Ridge)(多空)', 'Lasso(多空)',
]
pf = perf_df[perf_df['Label'].isin(strategies_show)].copy()
if not pf.empty:
    pf['Sharpe_num'] = pd.to_numeric(pf['Sharpe_num'], errors='coerce')
    pf['AnnRet_num'] = pd.to_numeric(pf['AnnRet_num'], errors='coerce')
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    bar_colors = ['#1f77b4', '#1f77b4', '#d62728', '#ff7f0e', '#2ca02c', '#9467bd']
    
    # 夏普比率
    bars1 = axes[0].bar(range(len(pf)), pf['Sharpe_num'], color=bar_colors)
    axes[0].set_xticks(range(len(pf)))
    axes[0].set_xticklabels(pf['Label'], rotation=30, ha='right', fontsize=9)
    axes[0].axhline(0, color='black', linewidth=0.8)
    axes[0].set_title('夏普比率（测试集）', fontsize=12, fontweight='bold')
    axes[0].set_ylabel('夏普比率')
    for bar, val in zip(bars1, pf['Sharpe_num']):
        y = bar.get_height()
        axes[0].text(bar.get_x() + bar.get_width()/2, y + 0.02*(1 if y >= 0 else -1),
                     f'{val:.3f}', ha='center', va='bottom' if y >= 0 else 'top', fontsize=8)
    
    # 年化收益
    bars2 = axes[1].bar(range(len(pf)), pf['AnnRet_num'] * 100, color=bar_colors)
    axes[1].set_xticks(range(len(pf)))
    axes[1].set_xticklabels(pf['Label'], rotation=30, ha='right', fontsize=9)
    axes[1].axhline(0, color='black', linewidth=0.8)
    axes[1].set_title('年化收益（测试集）', fontsize=12, fontweight='bold')
    axes[1].set_ylabel('年化收益 (%)')
    
    plt.suptitle('图3: 各策略绩效对比（测试集 2023-2025，已扣交易成本）', fontsize=13, fontweight='bold')
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, 'fig3_performance_comparison.png'), dpi=150, bbox_inches='tight')
    plt.close()

# ============================================================
# 图4: 特征重要性（Random Forest）
# ============================================================
print('生成图4: 特征重要性...')
fi_file = os.path.join(RESULTS_DIR, 'feature_importance_Random_Forest.csv')
if os.path.exists(fi_file):
    fi = pd.read_csv(fi_file, index_col=0)
    fi.columns = ['Importance']
    fi = fi.sort_values('Importance', ascending=True)
    # 中文标签映射
    fmap = {
        'mom1': '上月收益 (Mom1)',
        'mom3': '过去3月 (Mom3)',
        'mom6': '过去6月 (Mom6)',
        'mom12': '过去12月 (Mom12)',
        'log_mktcap': '对数市值 (Size)',
    }
    fi.index = [fmap.get(x, x) for x in fi.index]
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.barh(fi.index, fi['Importance'], color='#2196F3', edgecolor='white')
    for bar, val in zip(bars, fi['Importance']):
        ax.text(bar.get_width() + 0.005, bar.get_y() + bar.get_height()/2,
                f'{val:.3f}', va='center', fontsize=10)
    ax.set_title('图4: Random Forest 特征重要性 (Gini)', fontsize=13, fontweight='bold')
    ax.set_xlabel('特征重要性'); ax.grid(True, axis='x', alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(FIG_DIR, 'fig4_feature_importance.png'), dpi=150, bbox_inches='tight')
    plt.close()

# ============================================================
# 图5: FF3 Alpha 柱状图
# ============================================================
print('生成图5: FF3 Alpha...')
fig, ax = plt.subplots(figsize=(10, 6))
bar_colors = ['#2196F3' if p < 0.1 else '#90CAF9' for p in attr_df['Alpha_pvalue']]
bars = ax.bar(range(len(attr_df)), attr_df['Alpha(年化)'] * 100, color=bar_colors, edgecolor='white')
ax.set_xticks(range(len(attr_df)))
ax.set_xticklabels(attr_df['Strategy'], rotation=30, ha='right', fontsize=9)
ax.axhline(0, color='black', linewidth=0.8)
ax.set_title('图5: 各策略FF3归因Alpha（年化）', fontsize=13, fontweight='bold')
ax.set_ylabel('Alpha (%/年)')
from matplotlib.patches import Patch
legend_elements = [
    Patch(facecolor='#2196F3', label='Alpha显著 (p<0.1)'),
    Patch(facecolor='#90CAF9', label='Alpha不显著'),
]
ax.legend(handles=legend_elements, fontsize=9)
ax.grid(True, axis='y', alpha=0.3)
for bar, (_, row) in zip(bars, attr_df.iterrows()):
    val = row['Alpha(年化)'] * 100
    sig = '*' if row['Alpha_pvalue'] < 0.1 else ''
    y_off = 1 if val >= 0 else -3
    ax.text(bar.get_x() + bar.get_width()/2, val + y_off,
            f"{val:.1f}%{sig}", ha='center', fontsize=8)
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, 'fig5_ff3_alpha.png'), dpi=150, bbox_inches='tight')
plt.close()

# ============================================================
# 图6: 月度收益分布（测试集）
# ============================================================
print('生成图6: 月度收益分布...')
fig, axes = plt.subplots(1, 2, figsize=(12, 5))
pairs = [
    (axes[0], 'baseline_mom1_ls', '传统反转Mom1'),
    (axes[1], 'ml_Random_Forest_ls', 'Random Forest'),
]
for ax, col, title in pairs:
    if col in bt_returns.columns:
        data = test_bt[col].dropna() * 100 if col in test_bt.columns else bt_returns[col].dropna() * 100
        if len(data) > 0:
            ax.hist(data, bins=20, color='#2196F3', edgecolor='white', alpha=0.8)
            ax.axvline(data.mean(), color='red', linestyle='--', linewidth=2,
                       label='均值={:.2f}%'.format(data.mean()))
            ax.axvline(0, color='black', linewidth=1, alpha=0.5)
            ax.set_title(title + '\n月度收益分布（测试集）', fontsize=11, fontweight='bold')
            ax.set_xlabel('月度收益 (%)'); ax.set_ylabel('频率')
            ax.legend(fontsize=9); ax.grid(True, alpha=0.3)
plt.suptitle('图6: 月度收益分布（测试集 2023-2025）', fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, 'fig6_return_distribution.png'), dpi=150, bbox_inches='tight')
plt.close()

# ============================================================
# 图7: 年度收益热图（仅基线有全样本数据）
# ============================================================
print('生成图7: 年度收益热图...')
bt2 = bt_returns.copy()
bt2['year'] = bt2.index.year
cols_for_heatmap = ['baseline_mom1_ls', 'baseline_mom3_ls', 'baseline_mom6_ls']
yearly_baseline = bt2.groupby('year')[cols_for_heatmap].apply(lambda x: (1 + x).prod() - 1)
yearly_baseline.columns = ['反转Mom1', '反转Mom3', '反转Mom6']

fig, ax = plt.subplots(figsize=(12, 4))
im = ax.imshow(yearly_baseline.T.values * 100, cmap='RdYlGn', aspect='auto', vmin=-30, vmax=30)
ax.set_xticks(range(len(yearly_baseline.index)))
ax.set_xticklabels(yearly_baseline.index, fontsize=10)
ax.set_yticks(range(len(yearly_baseline.columns)))
ax.set_yticklabels(yearly_baseline.columns, fontsize=10)
for i in range(len(yearly_baseline.columns)):
    for j in range(len(yearly_baseline.index)):
        val = yearly_baseline.T.values[i, j] * 100
        if not np.isnan(val):
            ax.text(j, i, '{:.1f}%'.format(val), ha='center', va='center', fontsize=8)
plt.colorbar(im, ax=ax, label='年度收益 (%)')
ax.set_title('图7: 基线反转策略年度收益热图 (%)（全样本）', fontsize=13, fontweight='bold')
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, 'fig7_yearly_heatmap.png'), dpi=150, bbox_inches='tight')
plt.close()

print('\n✅ 所有图表生成完成！')
for f in sorted(os.listdir(FIG_DIR)):
    print(' ', f)
