"""Chinese reading guide for a completed, explicitly scoped observational pilot."""

from pathlib import Path

import pandas as pd

from src.evaluation.experiment import ExperimentResult


def write_chinese_summary(result: ExperimentResult, output_dir: Path) -> None:
    config = result.protocol["pilot_config"]
    chosen = result.parameters["selected_ar"]["order"]
    name = f"ar{chosen}"
    region = config["region"]
    test = result.metrics.query("split == 'test'")
    lines = [
        "# 黄海附近海域 SST：真实数据探索实验",
        "",
        f"使用 NOAA 真实观测分析产品，覆盖 {config['date_start']} 至 {config['date_end']}，共 {len(result.anomalies):,} 个日历日。",
        f"其中有效区域温度 {result.protocol['observed_days']:,} 天，缺测 {result.protocol['missing_days']} 天。",
        "",
        "这份报告是矩形区域的探索实验，不能直接作为精确黄海海域的最终研究结论。",
        "",
        "## 数据与实验范围",
        "",
        f"范围：北纬 {region['lat_min']}–{region['lat_max']} 度、东经 {region['lon_min']}–{region['lon_max']} 度；按纬度余弦加权平均海洋格点，包含邻近海域。",
        f"数据来自 NOAA PSL 官方 OISST 区域服务，按月份下载，共 {len(result.protocol['source_acquisitions'])} 份可校验文件，合计约 {result.protocol['source_bytes'] / 1024**2:.1f} MiB。",
        "[NOAA PSL 数据说明](https://psl.noaa.gov/data/gridded/data.noaa.oisst.v2.highres.html)；[NCEI OISST 产品说明](https://www.ncei.noaa.gov/products/optimum-interpolation-sst)。",
        "2016 年以前的 PSL 文件保留旧版元数据；NCEI 说明这一时期的 SST 在 v2.1 中保持相同。具体版本说明、下载地址、时间、校验和见 protocol.json。",
        "",
        f"训练截止：{config['train_end']}；验证截止：{config['validation_end']}；其后至 {config['date_end']} 为测试期。",
        "季节均值和模型系数只用训练期原始值估计。每条预测可使用起点当天的观测，多日预测不读取起点之后的中间观测；全程排除插值值。",
        f"候选 AR 阶数为 {config['ar_candidates']}，根据验证期 {config['selection_horizon']} 天预测的 RMSE 选择了 AR({chosen})。选定后不重新拟合；测试期未用于选阶。",
        "验证期成绩参与了选择，不能作为独立的最终效果证据。测试期每个步长的模型使用同一组有效日期评分。",
        "",
        "## 测试期比较",
        "",
        "| 预测步长 | 模型 | 样本数 | MAE（℃） | RMSE（℃） | 相对持续性技能 | 95% 技能区间 | 95% 预测区间覆盖率 |",
        "|---:|---|---:|---:|---:|---:|---|---:|",
    ]
    labels = {
        "ar1": "AR(1)",
        name: f"AR({chosen})",
        "climatology": "训练季节均值",
        "persistence": "持续性",
    }
    for row in test.itertuples():
        low, high = row.skill_ci_lower, row.skill_ci_upper
        interval = (
            f"[{low:.1%}, {high:.1%}]" if pd.notna(low) and pd.notna(high) else "未定义"
        )
        coverage = f"{row.coverage_95:.1%}" if row.model.startswith("ar") else "—"
        lines.append(
            f"| {row.horizon_days} 天 | {labels[row.model]} | {row.n} | {row.mae:.4f} | {row.rmse:.4f} | {row.rmse_skill_vs_persistence:.1%} | {interval} | {coverage} |"
        )
    lines += [
        "",
        "技能分数为 1 − 模型 RMSE / 持续性 RMSE。正值表示本次测试样本上误差较小；负值表示较大。",
        f"技能区间采用成对循环时间块抽样，{config['bootstrap_replicates']} 次、随机种子 {config['random_seed']}；块长至少 {config['bootstrap_block_days']} 天且不短于预测步长。",
        "这种区间依赖近似平稳性与块长设定，尚未检验趋势或不同时间段的稳健性。它不同于每条预测的温度区间。",
        "",
        "## 怎样理解本次结果",
        "",
    ]
    for row in test[test.model.eq(name)].itertuples():
        if pd.isna(row.skill_ci_lower):
            conclusion = "技能区间不可计算。"
        elif row.skill_ci_lower > 0:
            conclusion = "在本次测试期与块长设定下，较小误差的趋势较稳定；仍需更换时间段、块长和边界核验。"
        elif row.skill_ci_upper < 0:
            conclusion = "本次区间整体为负，模型的误差较持续性更大。"
        else:
            conclusion = "技能区间跨过或包含零，尚不足以认定稳定的预测提升。"
        calibration = (
            "覆盖明显低于名义 95%，这套条件区间可能低估预测不确定性。"
            if row.coverage_95 < 0.9
            else "覆盖较高，但仍需检查是否过宽及跨年份的稳定性。"
            if row.coverage_95 > 0.98
            else "整体覆盖接近名义水平，仍需查看各年份与残差结构。"
        )
        lines.append(
            f"- **{row.horizon_days} 天预测：** AR({chosen}) 相对持续性的技能点估计为 {row.rmse_skill_vs_persistence:.1%}。{conclusion} 预测区间实际覆盖为 {row.coverage_95:.1%}。{calibration}"
        )
    acf = pd.read_csv(output_dir / "residual_acf.csv")
    lag_one = acf[acf.model.eq(name) & acf.lag_days.eq(1)].iloc[0]
    lines += [
        "",
        f"选定模型的训练残差在相隔 1 天时相关系数为 {lag_one.correlation:.3f}（{int(lag_one.n_pairs):,} 对日期）。这提示残差仍有时间结构；独立创新假设需要进一步检验。",
        "Q–Q 图及各年份覆盖率同时保留，避免仅凭总体 RMSE 判断模型是否足以描述不确定性。",
    ]
    lines += [
        "",
        "## 图表",
        "",
        "![完整实验概览](overview.png)",
        "",
        "![残差与区间覆盖诊断](residual_diagnostics.png)",
        "",
        "残差相关按真实日历间隔计算，缺测不会压缩成相邻日期；Q–Q 图用于观察高斯创新假设是否合理。分年份覆盖率用于检查总体覆盖掩盖的时间变化。",
        "",
        "## 当前局限与下一步",
        "",
        "- 矩形范围包含邻近海域，需要换成有依据的黄海边界，并做边界敏感性比较。",
        "- 训练期日历日均值未做平滑，也未显式处理长期升温趋势。应检查趋势、季节均值窗口和不同训练时期。",
        "- AR 的温度预测区间只考虑高斯创新误差，未包含参数与季节均值估计的不确定性。",
        "- 时间块技能区间依赖近似平稳性；需要变更块长、重复时间划分，并比较各测试年份。",
        "- OU 是满足条件的 AR(1) 的连续时间解释，不能作为一个额外独立竞争模型。",
        "",
        "## 可复核文件",
        "",
        "`pilot_config.json` 固定设计；`protocol.json` 包含数据来源、校验和和环境版本；`parameters.json` 包含系数与 OU 解释。",
        "`metrics.csv`、`predictions.csv`、`regional_sst_daily.csv`、`anomalies.csv`、`residual_acf.csv`、`training_residuals.csv`、`coverage_by_year.csv` 支持逐项复核。",
        "",
        "数据由 NOAA PSL（Boulder, Colorado, USA）提供：https://psl.noaa.gov。数据 DOI：10.25921/RE9P-PT57。",
    ]
    (output_dir / "报告_zh.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
