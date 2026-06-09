"""
量化策略交互式 Dashboard（修正版 v2）
基于修正后的回测数据，如实反映研究结果

启动方式：
  streamlit run src/dashboard.py

功能模块：
  1. 净值与回撤 - 累计净值曲线 + 回撤图
  2. 绩效对比 - 各策略夏普比率、年化收益等指标
  3. FF3归因 - Fama-French三因子回归结果
  4. 特征重要性 - RF/XGBoost 特征重要性对比
  5. 策略说明 - 研究方法、局限性
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import json
import os

# ============================================================
# 路径配置（使用相对路径）
# ============================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "results")
FIG_DIR  = os.path.join(BASE_DIR, "report", "figures")

# ─── 页面配置 ───────────────────────────────────────────────
st.set_page_config(
    page_title="量化策略 Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── CSS ────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-title { font-size: 2.2rem; font-weight: 700; color: #1a1a2e; text-align: center; padding: 0.5rem 0 0.2rem 0; }
    .sub-title  { font-size: 1rem; color: #6c757d; text-align: center; margin-bottom: 1.5rem; }
    .metric-card { background: #f8f9fa; border-radius: 10px; padding: 1rem; text-align: center; border: 1px solid #e9ecef; }
    .period-badge { display: inline-block; background: #e8f4fd; color: #1a73e8; border-radius: 20px; padding: 2px 12px; font-size: 0.85rem; font-weight: 600; margin: 2px; }
    .warn-box { background: #fff3cd; border-left: 4px solid #ffc107; padding: 0.75rem 1rem; border-radius: 4px; font-size: 0.9rem; }
    .neg-box  { background: #fde8e8; border-left: 4px solid #e53e3e; padding: 0.75rem 1rem; border-radius: 4px; font-size: 0.9rem; }
    .info-box { background: #e8f4fd; border-left: 4px solid #2196F3; padding: 0.75rem 1rem; border-radius: 4px; font-size: 0.9rem; }
</style>
""", unsafe_allow_html=True)

# ─── 加载数据 ───────────────────────────────────────────────
@st.cache_data
def load_data():
    """加载回测结果数据"""
    returns = pd.read_parquet(os.path.join(DATA_DIR, "backtest_monthly_returns.parquet"))
    perf    = pd.read_csv(os.path.join(DATA_DIR, "performance_summary.csv"))
    ff3     = pd.read_csv(os.path.join(DATA_DIR, "ff3_attribution.csv"))
    rf_imp  = pd.read_csv(os.path.join(DATA_DIR, "feature_importance_Random_Forest.csv"))
    xgb_imp = pd.read_csv(os.path.join(DATA_DIR, "feature_importance_XGBoost.csv"))
    with open(os.path.join(DATA_DIR, "context.json"), encoding="utf-8") as f:
        ctx = json.load(f)
    return returns, perf, ff3, rf_imp, xgb_imp, ctx

returns, perf, ff3, rf_imp, xgb_imp, ctx = load_data()

TRAIN_END = pd.Timestamp(ctx["train_end"])
VAL_END   = pd.Timestamp(ctx["val_end"])
COST      = ctx["cost"]

# 标注哪些策略只有测试集数据
BASELINE_COLS = ["baseline_mom1_ls", "baseline_mom3_ls", "baseline_mom6_ls"]
ML_COLS       = ["ml_OLSRidge_ls", "ml_Lasso_ls", "ml_Random_Forest_ls", "ml_XGBoost_ls"]

COL_LABELS = {
    "baseline_mom1_ls": "反转-Mom1（基线）",
    "baseline_mom3_ls": "反转-Mom3",
    "baseline_mom6_ls": "反转-Mom6",
    "ml_OLSRidge_ls":   "Ridge 回归",
    "ml_Lasso_ls":      "Lasso 回归",
    "ml_Random_Forest_ls": "随机森林",
    "ml_XGBoost_ls":    "XGBoost",
}

COLORS = {
    "baseline_mom1_ls":     "#2196F3",
    "baseline_mom3_ls":     "#90CAF9",
    "baseline_mom6_ls":     "#BBDEFB",
    "ml_OLSRidge_ls":       "#FF9800",
    "ml_Lasso_ls":          "#FFC107",
    "ml_Random_Forest_ls":  "#4CAF50",
    "ml_XGBoost_ls":        "#F44336",
}

# ─── 辅助函数 ───────────────────────────────────────────────
def compute_nav(s):
    """计算累计净值"""
    c = s.dropna()
    return (1 + c).cumprod()

def compute_drawdown(nav):
    """计算回撤"""
    return (nav - nav.cummax()) / nav.cummax()

def annual_return(s):
    """计算年化收益"""
    c = s.dropna()
    if len(c) == 0: return np.nan
    return (1 + c).prod() ** (12 / len(c)) - 1

def sharpe(s, rf_annual=0.03):
    """计算夏普比率"""
    c = s.dropna()
    if len(c) < 2 or c.std() == 0: return np.nan
    ar = annual_return(c)
    vol = c.std() * np.sqrt(12)
    return (ar - rf_annual) / vol

def max_dd(s):
    """计算最大回撤"""
    c = s.dropna()
    if len(c) == 0: return np.nan
    nav = (1 + c).cumprod()
    return ((nav / nav.cummax()) - 1).min()

def filter_period(s, start=None, end=None):
    """按时间范围过滤"""
    s = s.copy()
    if start: s = s[s.index >= pd.Timestamp(start)]
    if end:   s = s[s.index <= pd.Timestamp(end)]
    return s

# ─── 侧边栏 ────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ 参数设置")
    st.markdown("---")

    st.markdown("### 策略选择")
    all_strats = list(COL_LABELS.keys())
    selected = st.multiselect(
        "选择要展示的策略",
        options=all_strats,
        default=["baseline_mom1_ls", "ml_Random_Forest_ls", "ml_XGBoost_ls"],
        format_func=lambda x: COL_LABELS[x],
    )
    if not selected:
        selected = ["baseline_mom1_ls"]

    st.markdown("---")
    st.markdown("### 时间范围")
    min_date = returns.index.min().date()
    max_date = returns.index.max().date()
    date_range = st.slider("选择分析区间", min_value=min_date, max_value=max_date,
                           value=(min_date, max_date), format="YYYY-MM")

    st.markdown("---")
    st.markdown("### 交易成本敏感性")
    cost_bps = st.slider("单边交易成本（bps）", min_value=0, max_value=50,
                         value=int(COST * 10000), step=5)

    st.markdown("---")
    st.markdown('<div class="info-box">⚠️ 基线策略有全样本数据<br>ML策略仅有测试集(2023–2025)</div>', unsafe_allow_html=True)
    st.caption(f"数据清洗：Winsorize [{ctx.get('winsorize',['-50%','100%'])[0]*100:.0f}%, {ctx.get('winsorize',['-50%','100%'])[1]*100:.0f}%]")
    st.caption(f"剔除市值最小5%")

# ─── 主内容 ─────────────────────────────────────────────────
st.markdown('<div class="main-title">📈 机器学习改进反转策略 — 量化研究 Dashboard</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">A股全市场月频 · 多空组合 · 三段式样本外验证（修正版）</div>', unsafe_allow_html=True)

c1, c2, c3 = st.columns(3)
with c1:
    st.markdown('<div class="metric-card">🎓 <b>训练集</b><br><span class="period-badge">2014–2019</span></div>', unsafe_allow_html=True)
with c2:
    st.markdown('<div class="metric-card">🔍 <b>验证集</b><br><span class="period-badge">2020–2022</span></div>', unsafe_allow_html=True)
with c3:
    st.markdown('<div class="metric-card">🎯 <b>测试集（仅用一次）</b><br><span class="period-badge">2023–2025</span></div>', unsafe_allow_html=True)

# ★ 如实展示核心结论
st.markdown("---")
st.markdown('<div class="neg-box"><b>⚠️ 核心结论：机器学习未能有效改进反转策略</b><br>'
            '所有ML模型在测试集（2023–2025）上夏普比率均为负，表现不如简单的反转基线。'
            '这与 Gu et al. (2020) 的部分发现一致——在A股市场，仅靠动量/反转+市值特征，非线性模型难以产生显著超额收益。</div>',
            unsafe_allow_html=True)

st.markdown("---")

# ─── Tabs ──────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 净值与回撤", "🏆 绩效对比", "🧮 FF3 归因", "🌲 特征重要性", "📋 策略说明",
])

# ═══════════════════════════════════════════════════════════
# TAB 1: 净值与回撤
# ═══════════════════════════════════════════════════════════
with tab1:
    st.subheader("累计净值 & 最大回撤")

    start_dt, end_dt = str(date_range[0]), str(date_range[1])
    ret_filtered = returns.copy()

    # 成本调整
    cost_adj = (cost_bps / 10000 - COST)
    if cost_adj != 0:
        ret_filtered = ret_filtered - cost_adj

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.6, 0.4],
                        vertical_spacing=0.06, subplot_titles=("累计净值（多空）", "最大回撤"))

    for col in selected:
        s = filter_period(ret_filtered[col], start_dt, end_dt).dropna()
        if len(s) == 0:
            continue
        nav = compute_nav(s)
        dd  = compute_drawdown(nav)
        label = COL_LABELS[col]
        color = COLORS[col]

        fig.add_trace(go.Scatter(
            x=nav.index, y=nav.values, name=label,
            line=dict(color=color, width=2),
            hovertemplate=f"<b>{label}</b><br>日期: %{{x|%Y-%m}}<br>净值: %{{y:.3f}}<extra></extra>",
        ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=dd.index, y=dd.values * 100, name=label,
            line=dict(color=color, width=1.5, dash="dot"), showlegend=False,
            hovertemplate=f"<b>{label}</b><br>回撤: %{{y:.1f}}%<extra></extra>",
        ), row=2, col=1)

    # 区域标注
    for x0, x1, lbl, clr in [
        ("2014-01-01", "2019-12-31", "训练集", "#2196F3"),
        ("2020-01-01", "2022-12-31", "验证集", "#FF9800"),
        ("2023-01-01", "2025-12-31", "测试集", "#4CAF50"),
    ]:
        for r in range(1, 3):
            fig.add_vrect(x0=x0, x1=x1, fillcolor=clr, opacity=0.06, line_width=0, row=r, col=1)

    fig.update_layout(height=560, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                      hovermode="x unified", paper_bgcolor="white", plot_bgcolor="white")
    fig.update_yaxes(title_text="净值", row=1, col=1, gridcolor="#f0f0f0")
    fig.update_yaxes(title_text="回撤 (%)", row=2, col=1, gridcolor="#f0f0f0")
    fig.update_xaxes(gridcolor="#f0f0f0")
    st.plotly_chart(fig, use_container_width=True)

    if cost_bps != int(COST * 10000):
        st.markdown(f'<div class="warn-box">⚠️ 已调整交易成本至 <b>{cost_bps} bps</b></div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════
# TAB 2: 绩效对比
# ═══════════════════════════════════════════════════════════
with tab2:
    st.subheader("多策略绩效指标对比")

    st.markdown('<div class="info-box">📊 以下均为 <b>测试集（2023–2025）</b> 结果。基线策略有全样本数据，ML策略仅测试集。</div>', unsafe_allow_html=True)

    rows = []
    for col in all_strats:
        s = ret_filtered[col].dropna()
        s_test = s[s.index >= "2023-01-01"] if len(s[s.index >= "2023-01-01"]) > 0 else s
        nav = compute_nav(s_test)
        rows.append({
            "策略": COL_LABELS[col],
            "年化收益": f"{annual_return(s_test)*100:.2f}%",
            "年化波动": f"{s_test.std()*np.sqrt(12)*100:.2f}%",
            "夏普比率": f"{sharpe(s_test):.3f}",
            "最大回撤": f"{max_dd(s_test)*100:.2f}%",
            "胜率": f"{(s_test > 0).mean()*100:.1f}%",
            "N": len(s_test),
        })

    df_perf = pd.DataFrame(rows)

    def highlight_best(df):
        styles = pd.DataFrame('', index=df.index, columns=df.columns)
        sharpe_vals = df["夏普比率"].astype(float)
        best_idx = sharpe_vals.idxmax()
        styles.loc[best_idx] = 'background-color: #e8f5e9; font-weight: bold'
        return styles

    st.dataframe(df_perf.style.apply(highlight_best, axis=None), use_container_width=True, hide_index=True)
    st.caption("✅ 绿色高亮 = 夏普比率最高")

    # 柱状图
    col_a, col_b = st.columns(2)
    sharpe_vals = [float(r["夏普比率"]) for r in rows]
    ret_vals    = [float(r["年化收益"].replace('%','')) for r in rows]
    names       = [r["策略"] for r in rows]
    bar_colors  = [COLORS[c] for c in all_strats]

    with col_a:
        fig_s = go.Figure(go.Bar(x=names, y=sharpe_vals, marker_color=bar_colors,
                                  text=[f"{v:.3f}" for v in sharpe_vals], textposition="outside"))
        fig_s.add_hline(y=0, line_dash="dash", line_color="gray")
        fig_s.update_layout(title="夏普比率（测试集）", height=380, yaxis_title="夏普比率",
                            paper_bgcolor="white", plot_bgcolor="white", xaxis_tickangle=-30)
        st.plotly_chart(fig_s, use_container_width=True)

    with col_b:
        fig_r = go.Figure(go.Bar(x=names, y=ret_vals, marker_color=bar_colors,
                                  text=[f"{v:.1f}%" for v in ret_vals], textposition="outside"))
        fig_r.add_hline(y=0, line_dash="dash", line_color="gray")
        fig_r.update_layout(title="年化收益（测试集）", height=380, yaxis_title="年化收益 (%)",
                            paper_bgcolor="white", plot_bgcolor="white", xaxis_tickangle=-30)
        st.plotly_chart(fig_r, use_container_width=True)

# ═══════════════════════════════════════════════════════════
# TAB 3: FF3 归因
# ═══════════════════════════════════════════════════════════
with tab3:
    st.subheader("Fama-French 三因子归因分析")

    st.markdown("""
    **模型**：$R_{p,t} - r_f = \\alpha + \\beta_{MKT} \\cdot MKT_t + \\beta_{SMB} \\cdot SMB_t + \\beta_{HML} \\cdot HML_t + \\epsilon_t$

    显著性：p < 0.05 ✅ ｜ p < 0.10 ⭐
    """)

    ff3_show = ff3.copy()
    ff3_show["Alpha(月)"]   = ff3_show["Alpha(月)"].map(lambda x: f"{x*100:.3f}%")
    ff3_show["Alpha(年化)"] = ff3_show["Alpha(年化)"].map(lambda x: f"{x*100:.1f}%")
    ff3_show["Alpha_pvalue"] = ff3_show["Alpha_pvalue"].map(
        lambda x: f"{x:.4f}" + (" ✅" if x < 0.05 else (" ⭐" if x < 0.10 else "")))
    ff3_show["Alpha_tstat"] = ff3_show["Alpha_tstat"].map(lambda x: f"{x:.3f}")
    for c in ["MKT_beta", "SMB_beta", "HML_beta", "R_squared"]:
        ff3_show[c] = ff3_show[c].map(lambda x: f"{x:.3f}")

    ff3_show = ff3_show[["Strategy", "Alpha(月)", "Alpha(年化)", "Alpha_tstat", "Alpha_pvalue",
                          "MKT_beta", "SMB_beta", "HML_beta", "R_squared"]]
    ff3_show.columns = ["策略", "Alpha(月)", "Alpha(年化)", "t统计量", "p值",
                        "市场β", "规模β", "价值β", "R²"]
    st.dataframe(ff3_show, use_container_width=True, hide_index=True)

    # Alpha 柱状图
    fig_alpha = go.Figure()
    for _, row in ff3.iterrows():
        alpha = row["Alpha(年化)"] * 100
        pval  = row["Alpha_pvalue"]
        color = "#4CAF50" if alpha > 0 else "#F44336"
        fig_alpha.add_trace(go.Bar(
            x=[row["Strategy"]], y=[alpha], marker_color=color,
            text=[f"{alpha:.1f}%"], textposition="outside", showlegend=False,
        ))

    fig_alpha.add_hline(y=0, line_dash="dash", line_color="gray")
    fig_alpha.update_layout(title="年化 Alpha（FF3 回归残差）", height=400,
                            yaxis_title="年化 Alpha (%)", paper_bgcolor="white",
                            plot_bgcolor="white", xaxis_tickangle=-20)
    st.plotly_chart(fig_alpha, use_container_width=True)

    st.markdown('<div class="neg-box">⚠️ 所有策略的 Alpha 均为负且不显著（p > 0.05），说明策略收益可被三因子模型解释，'
                '不存在超额 Alpha。ML模型甚至比基线表现更差。</div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════
# TAB 4: 特征重要性
# ═══════════════════════════════════════════════════════════
with tab4:
    st.subheader("机器学习模型特征重要性")

    model_choice = st.radio("选择模型", ["随机森林", "XGBoost"], horizontal=True)

    if model_choice == "随机森林":
        imp_df = rf_imp.copy(); imp_col = "Random Forest"; color = "#4CAF50"
    else:
        imp_df = xgb_imp.copy(); imp_col = "XGBoost"; color = "#F44336"

    imp_df = imp_df.rename(columns={"Unnamed: 0": "特征", imp_col: "重要性"})
    imp_df = imp_df.sort_values("重要性", ascending=True)

    feat_labels = {"mom1": "1月反转(Mom1)", "mom3": "3月动量(Mom3)",
                   "mom6": "6月动量(Mom6)", "mom12": "12月动量(Mom12)", "log_mktcap": "对数市值"}
    imp_df["特征"] = imp_df["特征"].map(lambda x: feat_labels.get(x, x))

    fig_imp = go.Figure(go.Bar(
        x=imp_df["重要性"] * 100, y=imp_df["特征"], orientation="h",
        marker_color=color, text=[f"{v*100:.1f}%" for v in imp_df["重要性"]], textposition="outside",
    ))
    fig_imp.update_layout(title=f"{model_choice} — 特征重要性", height=380,
                          xaxis_title="重要性 (%)", paper_bgcolor="white", plot_bgcolor="white")
    st.plotly_chart(fig_imp, use_container_width=True)

    comp_df = pd.DataFrame({
        "特征": [feat_labels.get(f, f) for f in rf_imp.iloc[:, 0]],
        "随机森林": (rf_imp["Random Forest"] * 100).map(lambda x: f"{x:.1f}%"),
        "XGBoost":  (xgb_imp["XGBoost"] * 100).map(lambda x: f"{x:.1f}%"),
    })
    st.markdown("#### 两模型特征重要性对比")
    st.dataframe(comp_df, use_container_width=True, hide_index=True)

    st.info("💡 6月动量（Mom6）重要性最高（~48%），说明中期反转效应是最强信号。但重要性高≠预测有效——测试集IC为负。")

# ═══════════════════════════════════════════════════════════
# TAB 5: 策略说明
# ═══════════════════════════════════════════════════════════
with tab5:
    st.subheader("📋 研究说明")
    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown("""
### 研究问题
> 机器学习能否有效改进传统反转策略？

### 结论（修正后）
**机器学习未能改进反转策略。** 在测试集（2023–2025）上：
- 基线反转 Mom1 多空：夏普 -0.263
- 所有 ML 模型：夏普 -0.7 ~ -0.9
- 测试集 IC 均为负，说明模型预测方向错误

### 数据清洗（修正）
- 收益 Winsorize：[-50%, +100%]（剔除8,949条极端值）
- 剔除市值最小5%（壳公司）
- 最终：5,418只股票，510,134条观测
        """)

    with col_r:
        st.markdown("""
### 模型与特征
| 模型 | 测试IC | 测试夏普 |
|------|--------|---------|
| Ridge | -0.023 | -0.778 |
| Lasso | -0.025 | -0.798 |
| RF | -0.015 | -0.931 |
| XGBoost | -0.009 | -0.715 |

### 样本划分
```
训练集  2014-01 ~ 2019-12 (156K obs)
验证集  2020-01 ~ 2022-12 (122K obs)
测试集  2023-01 ~ 2025-11 (163K obs) ← 仅用一次
```

### 参考文献
- Gu, Kelly & Xiu (2020) — 机器学习与股票收益
- Fama & French (1993) — 三因子模型
- Jegadeesh & Titman (1993) — 动量/反转
        """)

    st.markdown("---")
    st.markdown("""
### ⚠️ 局限性
1. **ML预测失效**：测试集IC为负，模型在A股上泛化能力差
2. **样本期短**：测试集仅35个月，统计检验力有限
3. **特征集有限**：仅5个价格/规模特征，缺少基本面和另类数据
4. **交易成本**：固定20bps/月，未考虑市场冲击
5. **生存偏差**：可能未完整剔除退市股票

### 💡 可能原因
- A 股市场效率提升，简单动量/反转 Alpha 衰减
- 特征不够丰富（缺少 P/B、ROE、换手率等）
- 2023–2025 市场结构变化（注册制改革），历史规律失效
    """)

st.markdown("---")
st.caption("量化金融研究项目 · 机器学习改进反转策略（修正版） · 数据来源：CSMAR")
