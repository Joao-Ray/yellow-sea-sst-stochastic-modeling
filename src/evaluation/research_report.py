"""Human-readable research report, manuscript draft, and audited comparison plots."""

from pathlib import Path
import base64
import html
import os
import numpy as np
import pandas as pd

MODEL_LABELS = {
    "climatology": "Calendar climatology",
    "persistence": "Anomaly persistence",
    "raw_persistence": "Raw SST persistence",
    "trend_seasonal": "Harmonics + trend",
    "ar_day": "AR + calendar cycle",
    "ar_harmonic": "AR + harmonics",
    "ar_harmonic_trend": "AR + harmonics + trend",
    "ridge_harmonic_trend": "Ridge + harmonics + trend",
}
ZH_LABELS = {
    "climatology": "日历季节均值",
    "persistence": "异常持续性基线",
    "raw_persistence": "原始温度持续性",
    "trend_seasonal": "季节谐波+趋势",
    "ar_day": "日历季节均值+AR",
    "ar_harmonic": "季节谐波+AR",
    "ar_harmonic_trend": "季节谐波+趋势+AR",
    "ridge_harmonic_trend": "季节谐波+趋势+岭回归",
}
RICH_MODELS = ["ar_day", "ar_harmonic", "ar_harmonic_trend", "ridge_harmonic_trend"]
DOMAIN_LABELS = {
    "iho_yellow_sea": "IHO Yellow Sea",
    "original_pilot_box": "Pilot box",
    "iho_interior": "IHO interior",
}


def write_research_report(
    metrics: pd.DataFrame,
    yearly: pd.DataFrame,
    skill: pd.DataFrame,
    models: dict,
    protocol: dict,
    output_dir: Path,
):
    os.environ.setdefault("MPLCONFIGDIR", str((output_dir / ".matplotlib").resolve()))
    _plots(metrics, skill, output_dir)
    _residual_plot(output_dir)
    config = protocol["design"]
    latest = metrics[metrics.domain.eq("iho_yellow_sea") & metrics.fold.eq("2023-2025")]
    residual_table = pd.read_csv(output_dir / "residual_diagnostics.csv")
    residual_focus = residual_table[
        residual_table.domain.eq("iho_yellow_sea")
        & residual_table.fold.eq("2023-2025")
        & residual_table.lag_days.eq(1)
    ]
    trend_residual = residual_focus[residual_focus.model.eq("ar_harmonic_trend")].iloc[
        0
    ]
    ridge_residual = residual_focus[
        residual_focus.model.eq("ridge_harmonic_trend")
    ].iloc[0]
    quality = protocol["data_quality"]["domains"]
    lines = [
        "# 黄海海表温度随机建模：完整科研复现报告",
        "",
        "## 完成范围",
        "",
        "本版本完成真实数据获取与来源校验、明确海域定义、时间隔离的模型选择和区间校准、三段测试时期、三种区域、块长敏感性、正则化模型比较、图表与论文初稿。",
        "这是一项完整的探索性回溯研究。最初实验的测试成绩已经被查看，因此本扩展不能声称使用了全新的确认性测试集，也不保证某个模型必然更好。",
        "",
        "## 数据与海域",
        "",
        f"NOAA OISST 区域数据：{config['date_start']}—{config['date_end']}，{len(protocol['source_acquisitions'])} 份按月文件，约 {protocol['source_bytes'] / 1024**2:.1f} MiB。原文件与边界仅从官方服务获取，来源、版本、请求与 SHA-256 见 protocol.json。",
        "主区域采用 Marine Regions IHO Sea Areas 的 Yellow Sea（MRGID 4303），以 0.25° 格点中心落在多边形内作为规则，再与首日有效海洋格点相交。",
        "**该 IHO 数据集的 Yellow Sea 多边形包含渤海。本文名称和结果严格对应这个操作定义，不应与排除渤海的狭义黄海混用。**",
        "敏感性区域分别为原先 31–39°N、117–127°E 矩形，以及主多边形向内收缩 0.125° 的区域。收缩按经纬度平面计算，不是等距离岸线缓冲；用于检查边界格点选择的影响。",
        "固定陆地掩膜来自 2010-01-01，不利用未来有效格点决定海洋范围。有效权重达到固定区域的 80% 才保留当日均值；不进行时间插值。",
        "",
        "| 区域 | 海洋格点 | 日历日 | 有效日 | 缺测日 | 最低有效权重比例 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in quality:
        lines.append(
            f"| {row['domain']} | {row['ocean_grid_cells']} | {row['daily_records']} | {row['observed_days']} | {row['missing_days']} | {row['min_valid_fraction']:.1%} |"
        )
    lines += [
        "",
        "![海域及格点掩膜](domain_map.png)",
        "",
        "## 公平比较与区间校准",
        "",
        "每次回溯都先固定训练期：季节均值、三阶年度谐波、可选线性趋势、AR 系数和岭回归标准化仅用训练观测。",
        "AR 阶数 1/3/7/14 或岭回归的惩罚强度，只按后续选择期 7 天 RMSE 决定；紧接着的单独校准期用于估计绝对误差的 95% 半径。测试期不改变选择、系数或半径。",
        "所有模型输出回到同一摄氏温度尺度。每个目标 d、步长 h 仅能读取 d−h 及更早的必要观测；每个步长所有模型共用同一组评分日期。",
        "主要技能分数以原实验的异常持续性为基线：将起点的训练季节异常延续，再加目标日的固定训练季节均值。另报告直接延续起点温度的原始持续性。",
        "经验区间使用 ceil((n+1)×0.95) 阶绝对校准误差。由于误差存在时间相关和分布变化，它不是保证 95% 覆盖的分布无关区间；应检查实际测试覆盖和宽度。",
        "AR 的原始高斯区间同时保留比较。岭回归仅报告经验校准区间，避免把惩罚估计当成精确高斯分布。",
        "",
        "| 测试时期 | 训练截止 | 模型选择截止 | 区间校准截止 | 测试截止 |",
        "|---|---|---|---|---|",
    ]
    for fold in config["folds"]:
        lines.append(
            f"| {fold['name']} | {fold['train_end']} | {fold['selection_end']} | {fold['calibration_end']} | {fold['test_end']} |"
        )
    lines += [
        "",
        "## 主区域最近测试期：2023–2025",
        "",
        "| 步长 | 模型 | 样本数 | RMSE（℃） | 技能 | 95% 技能区间（30天块） | 经验区间覆盖 | 区间全宽（℃） |",
        "|---:|---|---:|---:|---:|---|---:|---:|",
    ]
    for row in latest.itertuples():
        lines.append(
            f"| {row.horizon_days} 天 | {ZH_LABELS[row.model]} | {row.n} | {row.rmse:.4f} | {row.rmse_skill_vs_persistence:.1%} | [{row.skill_ci_lower:.1%}, {row.skill_ci_upper:.1%}] | {row.coverage_calibrated:.1%} | {row.width_calibrated_celsius:.3f} |"
        )
    lines += [
        "",
        "技能区间为成对循环日历块抽样的百分位区间，500 次、种子 42；主表块长 30 天。正值表示本次 RMSE 低于异常持续性；区间包含零时不能据此认定提升稳定。多重比较未做显著性校正。",
        "",
        "## 稳健性结果",
        "",
        "| 模型 | 区域×时期×步长组合 | 点估计为正 | 30天技能区间下界大于零 |",
        "|---|---:|---:|---:|",
    ]
    for name in RICH_MODELS:
        group = metrics[metrics.model.eq(name)]
        lines.append(
            f"| {ZH_LABELS[name]} | {len(group)} | {int(group.rmse_skill_vs_persistence.gt(0).sum())} | {int(group.skill_ci_lower.gt(0).sum())} |"
        )
    lines += [
        "",
        "这里的组合不是独立重复样本：区域互相重叠，各回溯的训练期资料也重叠。计数用于描述一致性，不是统计显著性或胜率检验。",
        "",
        "![完整实验概览](research_overview.png)",
        "",
        "![跨海域与时期的技能](robustness.png)",
        "",
        "![块长敏感性](block_sensitivity.png)",
        "",
        "## 训练残差诊断",
        "",
        "![训练残差结构](residual_diagnostics.png)",
        "",
        "残差只来自训练期资料；相关系数按真实日历间隔计算。Q–Q 图展示尾部是否偏离高斯分布，不能仅凭图形证明创新独立。逐模型与时期统计见 residual_diagnostics.csv。",
        f"主区域最近回溯中，趋势谐波 AR 的一日残差相关为 {trend_residual.correlation:.3f}，岭回归为 {ridge_residual.correlation:.3f}；两者的超额峰度分别为 {trend_residual.excess_kurtosis:.2f} 与 {ridge_residual.excess_kurtosis:.2f}，尾部仍偏离高斯假设。",
        "",
        "## 模型选择记录",
        "",
        "| 区域 / 时期 | 日历 AR 阶数 | 谐波 AR 阶数 | 趋势谐波 AR 阶数 | 岭回归 alpha | 训练线性趋势（℃/年） |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for key, result in models.items():
        chosen = result["models"]
        lines.append(
            f"| {key} | {chosen['ar_day']['selected_order']} | {chosen['ar_harmonic']['selected_order']} | {chosen['ar_harmonic_trend']['selected_order']} | {chosen['ridge_harmonic_trend']['selected_alpha']} | {result['seasonal_fits']['harmonic_trend']['trend_celsius_per_year']:.4f} |"
        )
    lines += ["", "## 区间校准检查", ""]
    for horizon in config["horizons"]:
        row = latest[
            latest.model.eq("ar_harmonic_trend") & latest.horizon_days.eq(horizon)
        ].iloc[0]
        lines.append(
            f"- **{horizon} 天，趋势谐波 AR：** 原始高斯区间覆盖 {row.coverage_gaussian:.1%}、全宽 {row.width_gaussian_celsius:.3f}℃；独立校准期经验区间覆盖 {row.coverage_calibrated:.1%}、全宽 {row.width_calibrated_celsius:.3f}℃。改善或不足均按实际数字判断，不预设校准必然有效。"
        )
    lines += [
        "",
        "逐年 RMSE、偏差和覆盖率见 yearly_metrics.csv；误差半径、校准样本和秩见 calibration_radii.csv。",
        "",
        "## 结论与边界",
        "",
        "项目已有完整可复现的软件与真实数据研究结果。论文初稿（manuscript_zh.md）由这些输出生成，可逐项追溯。",
        "模型选择受限于所列候选，季节谐波阶数与线性趋势形式是预先固定的探索设计。未来趋势可能改变；区域均值会隐藏空间差异；OISST 是融合分析产品而非独立格点实测。",
        "原始高斯区间忽略参数与季节估计误差；经验校准依赖历史校准期；循环块抽样依赖近似平稳性和块长。图表不能消除这些假设。",
        "本文没有证明因果机制，也没有宣称模型在任意未来时期均优于持续性。完成未来确认性研究需要新的未查看时期或外部数据；这不会阻止本探索项目作为完整成果交付。",
        "",
        "## 复现与文件",
        "",
        "在安装 requirements.txt 后运行 `python -m src.research`。完整流程校验缓存、固定配置，并生成报告、表格和论文初稿。首次运行需要网络，后续有完整缓存时可以离线复现。",
        "`research_config.json`、`protocol.json`、`models.json`、`metrics.csv`、`yearly_metrics.csv`、`block_sensitivity.csv`、`calibration_radii.csv`、`predictions.csv`、`grid_masks.csv`、`data_quality.csv` 和三个区域的每日 CSV 支持复核；checksums.json 校验全部交付文件。",
        "",
        "## 来源",
        "",
        "- NOAA/NCEI OISST v2.1：[产品说明](https://www.ncei.noaa.gov/products/optimum-interpolation-sst)，DOI [10.25921/RE9P-PT57](https://doi.org/10.25921/RE9P-PT57)。",
        "- 数据由 [NOAA PSL](https://psl.noaa.gov/data/gridded/data.noaa.oisst.v2.highres.html)（Boulder, Colorado, USA）提供。2016 年前的旧元数据说明保留在来源记录中。",
        "- Flanders Marine Institute (2018), [IHO Sea Areas, version 3](https://doi.org/10.14284/323)；[Yellow Sea MRGID 4303](https://www.marineregions.org/gazetteer.php?id=4303&p=details)。多边形仅从供应方下载，代码仓库不重新分发。",
    ]
    report = "\n".join(lines) + "\n"
    (output_dir / "完整研究报告_zh.md").write_text(report)
    _manuscript(latest, metrics, models, protocol, output_dir, residual_focus)
    _html_report(lines, output_dir)


def _plots(metrics, skill, output_dir):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    latest = metrics[metrics.domain.eq("iho_yellow_sea") & metrics.fold.eq("2023-2025")]
    figure, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    for name, label in DOMAIN_LABELS.items():
        series = (
            pd.read_csv(output_dir / f"{name}_daily.csv", parse_dates=["date"])
            .set_index("date")
            .sst_observed_celsius
        )
        axes[0, 0].plot(series.resample("YS").mean(), marker=".", label=label)
    axes[0, 0].set(title="Annual mean SST by defined domain", ylabel="SST (°C)")
    axes[0, 0].legend(fontsize=7)
    for name in MODEL_LABELS:
        group = latest[latest.model.eq(name)].sort_values("horizon_days")
        axes[0, 1].plot(
            group.horizon_days, group.rmse, marker="o", lw=1.3, label=MODEL_LABELS[name]
        )
    axes[0, 1].set(
        title="IHO domain | 2023–2025 test RMSE",
        xlabel="Horizon (days)",
        ylabel="RMSE (°C)",
        xticks=[1, 7, 30],
    )
    axes[0, 1].legend(fontsize=6, ncol=2)
    for name in RICH_MODELS:
        group = latest[latest.model.eq(name)].sort_values("horizon_days")
        axes[1, 0].plot(
            group.horizon_days,
            group.coverage_calibrated,
            marker="o",
            label=MODEL_LABELS[name],
        )
    axes[1, 0].axhline(0.95, color="black", ls="--", lw=0.8, label="Nominal 95%")
    axes[1, 0].set(
        title="Separate-period empirical interval calibration",
        xlabel="Horizon (days)",
        ylabel="Test coverage",
        ylim=(0, 1.02),
        xticks=[1, 7, 30],
    )
    axes[1, 0].legend(fontsize=7)
    for offset, name in enumerate(RICH_MODELS):
        group = latest[latest.model.eq(name)].sort_values("horizon_days")
        x = np.arange(3) + (offset - 1.5) * 0.13
        axes[1, 1].vlines(
            x, group.skill_ci_lower, group.skill_ci_upper, lw=1.5, color=f"C{offset}"
        )
        axes[1, 1].scatter(
            x,
            group.rmse_skill_vs_persistence,
            s=20,
            color=f"C{offset}",
            label=MODEL_LABELS[name],
        )
    axes[1, 1].axhline(0, color="black", ls="--", lw=0.8)
    axes[1, 1].set(
        title="Skill vs anomaly persistence | 30-day block CIs",
        ylabel="RMSE skill",
        xticks=[0, 1, 2],
        xticklabels=[1, 7, 30],
        xlabel="Horizon (days)",
    )
    axes[1, 1].legend(fontsize=7)
    for axis in axes.ravel():
        axis.grid(alpha=0.15)
    figure.suptitle("Complete exploratory SST backtest | IHO Yellow Sea includes Bohai")
    figure.savefig(output_dir / "research_overview.png", dpi=150)
    plt.close(figure)
    figure, axes = plt.subplots(1, 2, figsize=(13, 7), constrained_layout=True)
    selected = metrics[metrics.model.isin(RICH_MODELS)]
    bound = max(0.1, float(selected.rmse_skill_vs_persistence.abs().max()))
    for axis, horizon in zip(axes, [7, 30]):
        group = selected[selected.horizon_days.eq(horizon)].copy()
        group["case"] = group.domain.map(DOMAIN_LABELS) + " / " + group.fold
        table = group.pivot(
            index="case", columns="model", values="rmse_skill_vs_persistence"
        ).reindex(columns=RICH_MODELS)
        graphic = axis.imshow(
            table, cmap="RdBu", vmin=-bound, vmax=bound, aspect="auto"
        )
        axis.set(
            title=f"{horizon}-day RMSE skill vs anomaly persistence",
            yticks=np.arange(len(table)),
            yticklabels=table.index,
            xticks=np.arange(4),
            xticklabels=["Calendar AR", "Harmonic AR", "Trend AR", "Trend ridge"],
        )
        for i in range(len(table)):
            for j in range(4):
                axis.text(
                    j,
                    i,
                    f"{table.iloc[i, j]:.0%}",
                    ha="center",
                    va="center",
                    fontsize=8,
                    color="white" if abs(table.iloc[i, j]) > bound * 0.6 else "black",
                )
    figure.colorbar(
        graphic, ax=axes, shrink=0.7, label="RMSE skill (not independent cases)"
    )
    figure.suptitle("Retrospective robustness across domains and disjoint test periods")
    figure.savefig(output_dir / "robustness.png", dpi=150)
    plt.close(figure)
    figure, axes = plt.subplots(1, 3, figsize=(14, 5), constrained_layout=True)
    focus = skill[
        skill.domain.eq("iho_yellow_sea")
        & skill.fold.eq("2023-2025")
        & skill.model.isin(RICH_MODELS)
    ]
    for axis, horizon in zip(axes, [1, 7, 30]):
        for i, name in enumerate(RICH_MODELS):
            group = focus[
                focus.horizon_days.eq(horizon) & focus.model.eq(name)
            ].sort_values("bootstrap_block_days")
            axis.plot(
                group.bootstrap_block_days,
                group.rmse_skill_vs_persistence,
                ".-",
                color=f"C{i}",
                label=MODEL_LABELS[name],
            )
            axis.vlines(
                group.bootstrap_block_days + (i - 1.5) * 0.5,
                group.skill_ci_lower,
                group.skill_ci_upper,
                color=f"C{i}",
                lw=1.1,
            )
        axis.axhline(0, color="black", ls="--", lw=0.8)
        axis.set(
            title=f"{horizon}-day horizon",
            xlabel="Effective block length (days)",
            ylabel="RMSE skill with percentile 95% CI",
        )
        axis.grid(alpha=0.15)
    axes[1].legend(fontsize=6)
    figure.suptitle(
        "Block-length sensitivity | IHO domain / 2023–2025 | 500 paired replicates"
    )
    figure.savefig(output_dir / "block_sensitivity.png", dpi=150)
    plt.close(figure)


def _manuscript(latest, metrics, models, protocol, output_dir, residual_focus):
    quality = next(
        q
        for q in protocol["data_quality"]["domains"]
        if q["domain"] == "iho_yellow_sea"
    )
    result_rows = []
    trend_residual = residual_focus[residual_focus.model.eq("ar_harmonic_trend")].iloc[
        0
    ]
    ridge_residual = residual_focus[
        residual_focus.model.eq("ridge_harmonic_trend")
    ].iloc[0]
    for horizon in [1, 7, 30]:
        comparison = latest[latest.horizon_days.eq(horizon)]
        baseline = comparison[comparison.model.eq("persistence")].iloc[0]
        best = (
            comparison[comparison.model.isin(RICH_MODELS)]
            .sort_values(["rmse", "model"])
            .iloc[0]
        )
        result_rows.append(
            f"{horizon} 天时，异常持续性 RMSE 为 {baseline.rmse:.4f}℃；该测试表中误差最小的扩展模型为 {ZH_LABELS[best.model]}，RMSE {best.rmse:.4f}℃、技能 {best.rmse_skill_vs_persistence:.1%}、30 天块区间 [{best.skill_ci_lower:.1%}, {best.skill_ci_upper:.1%}]。这一“最小误差”是测试结果的事后描述，不是部署模型选择规则。"
        )
    lines = [
        "# 黄海区域海表温度的随机建模、正则化预测与时间回溯评估",
        "",
        "**论文初稿 · 探索性回溯研究 · 2026-10-03**",
        "",
        "## 摘要",
        "",
        f"本研究使用 NOAA OISST 2010–2025 年每日海表温度分析产品，对 Marine Regions IHO Yellow Sea 定义下的区域均值进行预测比较。主区域包含 {quality['ocean_grid_cells']} 个首日有效海洋格点，共 {quality['observed_days']} 个有效日。研究比较训练日历季节均值、异常及原始温度持续性、季节谐波、线性趋势、自回归与正则化自回归。模型参数、选择和区间校准使用先后分离的时间段；2017–2019、2020–2022、2023–2025 三段用于回溯测试。另考察区域与块长敏感性。",
        " ".join(result_rows),
        "结果支持按明确海域和时期评估模型；精度、区间覆盖和结构稳定性须分别考察。本扩展是在初次试验成绩已被查看后设计，不能视为未触碰测试集的确认性证明。",
        "",
        "**关键词：** 海表温度；黄海；OISST；自回归；岭回归；时间块抽样；区间校准",
        "",
        "## 1. 引言",
        "",
        "区域海表温度具有明显季节性与持续性。单靠较低短期预测误差，难以区分对季节周期的利用、对异常持续性的刻画及对长期变化的外推。随机过程模型还依赖创新误差与稳定性假设，因此应同时检查预测区间与时期变化。",
        "本项目围绕三个问题展开：（1）不同季节/趋势处理能否在特定回溯时期减少持续性基线的误差；（2）正则化的滞后模型是否呈现一致的描述性技能；（3）单独历史校准期的经验区间在后续时期是否接近名义覆盖。研究不把 OU 的连续时间解释作为与 AR(1) 独立的额外模型。",
        "",
        "## 2. 数据与研究海域",
        "",
        "OISST 是 0.25° 的融合分析产品，结合卫星与现场资料；它不是每个格点独立实测。数据通过 NOAA PSL 官方服务按月获取，保留产品元数据、请求地址、下载时间和校验和。2016 年前的 PSL 旧版元数据依据 NCEI 对 v2.1 历史 SST 等价性的说明记录，2016 年以后要求 v2.1 标识。[1–3]",
        "海域采用 Flanders Marine Institute IHO Sea Areas v3 中 MRGID 4303。**该多边形包含渤海**，本文结果适用于这一操作定义。每个格点以中心是否被多边形覆盖选择，再与 2010-01-01 有效海洋格点相交；区域 SST 使用纬度余弦权重。边界敏感性包括原试验矩形与向内收缩 0.125° 的多边形，后者为经纬度平面操作而非地理等距离岸线缓冲。[4]",
        f"主区域 {quality['daily_records']} 个日历日中有效 {quality['observed_days']} 天、缺测 {quality['missing_days']} 天；最低有效权重比例 {quality['min_valid_fraction']:.1%}。未使用时间插值。图 1 显示区域、首日土地/缺测格点与选定海洋格点。",
        "",
        "![图1：海域定义与格点选择](domain_map.png)",
        "",
        "## 3. 方法",
        "",
        "### 3.1 确定性季节项与趋势",
        "",
        "训练期日历日均值按月日字符串计算，闰日不会导致三月以后错位。谐波方案为截距加三组年度正余弦；趋势方案再加入从训练首日起计算的线性年份项。所有系数只在训练期通过最小二乘估计。谐波相位使用共同闰年模板。线性趋势向测试期外推是一项建模假设，不能解释为未来升温的已知速度。",
        "### 3.2 随机过程与正则化",
        "",
        "移除确定性项后，用完整连续日历滞后向量拟合带截距 AR(p)：xₜ = c + Σ φⱼxₜ₋ⱼ + εₜ。候选 p = 1,3,7,14，仅用选择期 7 天 RMSE 选阶。岭回归固定 14 阶，训练期中心化和标准化滞后变量，最小化训练均方误差加 alpha 倍标准化系数平方和；截距不惩罚，alpha 从 0.001/0.01/0.1/1.0 中用同一选择规则决定。所有最终参数仍保留训练期拟合值。",
        "满足 0<φ<1 的 AR(1) 有精确 OU 日采样解释：θ=−log(φ)、μ=c/(1−φ)、σ²=Var(ε)·2θ/(1−φ²)。两者日转移与预测相同，因此不增加独立比较项。",
        "### 3.3 时间协议与基线",
        "",
        "每次回溯依次划分训练、选择、区间校准、测试。第一回溯训练截止 2014 年，2015 年选择、2016 年校准、2017–2019 年测试；第二回溯截止 2017 年训练，2018 年选择、2019 年校准、2020–2022 年测试；第三回溯截止 2019 年训练，2020–2021 年选择、2022 年校准、2023–2025 年测试。测试时期互不重叠，训练期资料重叠。",
        "目标 d、步长 h 的观测起点为 d−h；递归预测只用该起点及更早的滞后向量，不读取中间未来观测。所有预测加回固定确定性项后在摄氏温度尺度评分，保证模型目标一致。主要基线是原日历季节异常的持续性，另报告原始温度持续性和季节/趋势基线。每步长所有模型使用共同有效日期。",
        "### 3.4 指标、技能与不确定性",
        "",
        "报告 MAE、RMSE、预测偏差、95% 区间覆盖和全宽。技能为 1−RMSE模型/RMSE异常持续性。成对循环日历块抽样在模型与基线平方误差上使用相同索引，保留日历缺口；500 次、种子 42，块长取 max(h,15/30/60)。95% 百分位技能区间依赖近似平稳性，未作多重比较校正。",
        "AR 原始高斯条件区间使用训练创新方差与冲击响应平方和，忽略参数和季节项估计误差。经验区间的半径取单独校准期 ceil((n+1)×0.95) 阶绝对误差；串行相关及分布漂移下不保证覆盖。岭回归仅报告经验区间。逐年评分检验总体均值掩盖的变化。",
        "",
        "## 4. 结果",
        "",
        "### 4.1 最近测试期主区域",
        "",
        *result_rows,
        "",
        "| 步长 | 模型 | RMSE（℃） | 技能 | 95% 技能区间 | 经验覆盖 | 全宽（℃） |",
        "|---:|---|---:|---:|---|---:|---:|",
    ]
    for row in latest[
        latest.model.isin(["persistence", "raw_persistence"] + RICH_MODELS)
    ].itertuples():
        lines.append(
            f"| {row.horizon_days} | {ZH_LABELS[row.model]} | {row.rmse:.4f} | {row.rmse_skill_vs_persistence:.1%} | [{row.skill_ci_lower:.1%}, {row.skill_ci_upper:.1%}] | {row.coverage_calibrated:.1%} | {row.width_calibrated_celsius:.3f} |"
        )
    lines += [
        "",
        "![图2：区域年度温度、模型误差、覆盖与技能区间](research_overview.png)",
        "",
        "### 4.2 区域、时期和块长",
        "",
        "图 3 保留全部区域与三个测试时期的 7/30 天技能点估计。区域互相重叠，因此不能把各格视作独立实验。图 4 显示最近主区域技能区间对块长的变化；点估计不因块长改变，但依赖误差抽样的区间会改变。详细结果与逐年偏差在配套 CSV 中保留。",
        "",
        "![图3：回溯与边界敏感性](robustness.png)",
        "",
        "![图4：块长敏感性](block_sensitivity.png)",
        "",
        "### 4.3 残差与区间校准",
        "",
        f"主区域最近回溯的训练创新中，趋势谐波 AR 一日相关为 {trend_residual.correlation:.3f}，岭回归为 {ridge_residual.correlation:.3f}。超额峰度分别为 {trend_residual.excess_kurtosis:.2f} 与 {ridge_residual.excess_kurtosis:.2f}。岭回归的短期残差相关较弱，但尾部偏离仍明显；降低相关不等于证明高斯创新假设。",
        "",
        "![图5：训练残差的相关结构与Q–Q](residual_diagnostics.png)",
        "",
        "## 5. 讨论",
        "",
        "持续性是必要的强基线，模型复杂度本身不保证较好预测。季节平滑可能减少短记录日历均值的噪声；线性趋势改变长期均值的外推方式；岭回归约束相关滞后的系数。这些机制是模型设定的解释，不能仅凭本回溯建立因果关系。",
        "较低 RMSE 与较好区间覆盖是不同目标。校准样本来自过去，不能消除后续时期的分布变化；扩大区间也会影响实用性，故必须同时报告宽度。区域均值可掩盖沿岸和海盆内的差异，IHO 定义又包含渤海；改用狭义黄海需要新的明确海域来源并重新计算。",
        "本扩展在初次矩形试验测试成绩已被查看后形成。虽然本次计算严格隔离时间段，并在运行前固定新配置，但所有扩展结果仍为探索性回溯证据。测试表中事后最佳模型不应直接成为部署模型；未来确认需要真正未查看的时期或外部资料。",
        "",
        "## 6. 结论",
        "",
        "本项目交付完整、可追溯的海域 SST 预测研究流程与真实数据结果，涵盖随机过程、正则化、校准与稳健性。数值结论仅适用于所定义海域、数据产品、时段和候选模型。研究不承诺复杂模型优于持续性，不把技能区间误解为温度预测区间，也不把探索性回溯视为最终确认。",
        "",
        "## 数据与代码可用性",
        "",
        "代码仓库：https://github.com/Joao-Ray/yellow-sea-sst-stochastic-modeling。运行 `python -m src.research` 生成全部结果与本文初稿。raw/derived 数据不纳入 Git；官方下载 URL、SHA-256、版本、环境与配置在 protocol.json 中记录。边界从 Marine Regions 获取，不镜像重新分发。",
        "",
        "## 参考资料",
        "",
        "1. NOAA/NCEI. OISST Version 2.1. DOI: [10.25921/RE9P-PT57](https://doi.org/10.25921/RE9P-PT57)；[官方产品说明](https://www.ncei.noaa.gov/products/optimum-interpolation-sst)。",
        "2. Huang et al. (2021). Improvements of the Daily Optimum Interpolation Sea Surface Temperature (DOISST) Version 2.1. [10.1175/JCLI-D-20-0166.1](https://doi.org/10.1175/JCLI-D-20-0166.1)。",
        "3. NOAA PSL. [OISST 数据与服务](https://psl.noaa.gov/data/gridded/data.noaa.oisst.v2.highres.html)。",
        "4. Flanders Marine Institute (2018). IHO Sea Areas, version 3. [10.14284/323](https://doi.org/10.14284/323)；[Yellow Sea MRGID 4303](https://www.marineregions.org/gazetteer.php?id=4303&p=details)。",
    ]
    (output_dir / "manuscript_zh.md").write_text("\n".join(lines) + "\n")


def _html_report(lines, output_dir):
    # The generated report uses only a controlled subset of Markdown. Keep the
    # HTML standalone by embedding its own generated plots; no remote assets.
    import re

    def inline(value):
        value = html.escape(value)
        value = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", value)
        value = re.sub(r"`(.*?)`", r"<code>\1</code>", value)
        value = re.sub(
            r"\[([^\]]+)\]\((https://[^)]+)\)", r'<a href="\2">\1</a>', value
        )
        return value

    blocks, in_table, in_list = [], False, False
    for line in lines:
        if not line.startswith("|") and in_table:
            blocks.append("</tbody></table></div>")
            in_table = False
        if not line.startswith("- ") and in_list:
            blocks.append("</ul>")
            in_list = False
        if not line:
            continue
        if line.startswith("!["):
            name = line.rsplit("(", 1)[1].rstrip(")")
            data = base64.b64encode((output_dir / name).read_bytes()).decode()
            blocks.append(
                f'<figure><img src="data:image/png;base64,{data}" alt="{html.escape(name)}"></figure>'
            )
        elif line.startswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if all(re.fullmatch(r"[:\- ]+", cell) for cell in cells):
                continue
            if not in_table:
                blocks.append(
                    '<div class="table"><table><thead><tr>'
                    + "".join(f"<th>{inline(cell)}</th>" for cell in cells)
                    + "</tr></thead><tbody>"
                )
                in_table = True
            else:
                blocks.append(
                    "<tr>"
                    + "".join(f"<td>{inline(cell)}</td>" for cell in cells)
                    + "</tr>"
                )
        elif line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            blocks.append(f"<h{level}>{inline(line[level:].strip())}</h{level}>")
        elif line.startswith("- "):
            if not in_list:
                blocks.append("<ul>")
                in_list = True
            blocks.append(f"<li>{inline(line[2:])}</li>")
        else:
            blocks.append(f"<p>{inline(line)}</p>")
    if in_table:
        blocks.append("</tbody></table></div>")
    if in_list:
        blocks.append("</ul>")
    css = 'body{margin:0;background:#f3f6f9;color:#203040;font:16px/1.8 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}main{max-width:1100px;margin:auto;padding:48px;background:white}h1{font-size:32px}h2{margin-top:40px;border-bottom:2px solid #d8e4ec;padding-bottom:8px}a{color:#126599}img{width:100%;height:auto}figure{margin:24px 0}.table{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:13px}td,th{border-bottom:1px solid #dfe5ec;padding:9px;text-align:left;white-space:nowrap}th{background:#eef4f8}code{background:#edf2f7;padding:2px 5px;border-radius:4px}@media print{body{background:white}main{padding:0}h2{break-after:avoid}figure,table{break-inside:avoid}}'
    document = (
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>黄海 SST 完整研究报告</title><style>'
        + css
        + "</style><main>"
        + "\n".join(blocks)
        + "</main></html>"
    )
    (output_dir / "完整研究报告.html").write_text(document)


def _residual_plot(output_dir):
    from statistics import NormalDist
    import matplotlib.pyplot as plt

    residuals = pd.read_csv(output_dir / "training_residuals.csv", parse_dates=["date"])
    focus = residuals[
        residuals.domain.eq("iho_yellow_sea") & residuals.fold.eq("2023-2025")
    ].set_index("date")
    diagnostics = pd.read_csv(output_dir / "residual_diagnostics.csv")
    diagnostic = diagnostics[
        diagnostics.domain.eq("iho_yellow_sea") & diagnostics.fold.eq("2023-2025")
    ]
    figure, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    for i, name in enumerate(RICH_MODELS):
        values = focus[name].dropna()
        axes[0, 0].hist(
            values,
            bins=60,
            density=True,
            histtype="step",
            label=MODEL_LABELS[name],
            color=f"C{i}",
        )
        group = diagnostic[diagnostic.model.eq(name)].sort_values("lag_days")
        axes[0, 1].bar(
            np.arange(3) + (i - 1.5) * 0.18,
            group.correlation,
            width=0.17,
            label=MODEL_LABELS[name],
        )
    axes[0, 0].set(
        title="Training innovation histograms", xlabel="Residual (°C)", ylabel="Density"
    )
    axes[0, 0].legend(fontsize=6)
    axes[0, 1].set(
        title="Calendar-lag residual correlations",
        xticks=[0, 1, 2],
        xticklabels=[1, 7, 30],
        xlabel="Lag (days)",
        ylabel="Correlation",
    )
    axes[0, 1].axhline(0, color="black", lw=0.7)
    axes[0, 1].legend(fontsize=6)
    for axis, name in zip(axes[1], ["ar_harmonic_trend", "ridge_harmonic_trend"]):
        values = focus[name].dropna().sort_values().values
        standardized = (values - values.mean()) / values.std(ddof=1)
        quantile = np.array(
            [NormalDist().inv_cdf((i + 0.5) / len(values)) for i in range(len(values))]
        )
        axis.scatter(quantile, standardized, s=4, alpha=0.35)
        axis.plot([-4, 4], [-4, 4], "--", color="black", lw=0.8)
        axis.set(
            title=MODEL_LABELS[name] + " | Q–Q",
            xlabel="Standard normal quantile",
            ylabel="Standardized innovation quantile",
        )
    for axis in axes.ravel():
        axis.grid(alpha=0.15)
    figure.suptitle("Training-only residual diagnostics | IHO / latest backtest")
    figure.savefig(output_dir / "residual_diagnostics.png", dpi=150)
    plt.close(figure)
