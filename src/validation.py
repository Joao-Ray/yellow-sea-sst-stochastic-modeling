"""Freeze selection before acquiring a new temporal holdout; score without refitting."""

import argparse
from datetime import date, datetime, timezone
import hashlib
from importlib.metadata import version
import json
import logging
import os
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import xarray as xr

from src.data.download_psl import download_regional_range
from src.data.preprocess import Region
from src.evaluation.bootstrap import skill_interval
from src.evaluation.calibration import empirical_radius
from src.evaluation.metrics import regression_metrics
from src.evaluation.research_experiment import fit_research_candidates
from src.models.autoregression import Autoregression
from src.models.seasonal import SeasonalFit


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_history(path):
    table = pd.read_csv(path, parse_dates=["date"]).set_index("date")
    values = table.sst_observed_celsius
    if values.index.has_duplicates or not values.index.equals(
        pd.date_range(values.index[0], values.index[-1])
    ):
        raise ValueError("history needs unique, ordered, complete daily dates")
    return values.replace([np.inf, -np.inf], np.nan)


def candidate_means(sst, models, cycles, residuals, horizon):
    means = {
        "climatology": cycles["day"],
        "persistence": cycles["day"] + residuals["day"].shift(horizon),
        "raw_persistence": sst.shift(horizon),
        "trend_seasonal": cycles["harmonic_trend"],
    }
    for name, (model, cycle, residual) in models.items():
        means[name] = cycle + model.forecast(residual, horizon)
    return means


def freeze_models(history, design, research_config):
    """Ignore every observation after calibration_end, even if supplied."""
    if design["baseline"] != "persistence":
        raise ValueError("the frozen validation baseline must be anomaly persistence")
    train, selection, calibration = [
        pd.Timestamp(design[k])
        for k in ("train_end", "selection_end", "calibration_end")
    ]
    if (
        not history.index[0]
        < train
        < selection
        < calibration
        < pd.Timestamp(design["test_start"])
        <= pd.Timestamp(design["test_end"])
    ):
        raise ValueError(
            "ordered fitting, selection, calibration and test dates required"
        )
    historical = history.loc[:calibration].asfreq("D")
    if historical.index[-1] != calibration:
        raise ValueError("history does not reach the calibration boundary")
    models, parameters, cycles, residuals, harmonic, trend = fit_research_candidates(
        historical, train, selection, research_config
    )
    chosen, scores, radii = {}, [], {}
    for h in design["horizons"]:
        means = candidate_means(historical, models, cycles, residuals, h)
        if set(means) != set(design["candidate_order"]):
            raise ValueError("candidate list must exactly match implemented methods")
        common = historical.notna()
        for predicted in means.values():
            common &= np.isfinite(predicted)
        choosing = common & (historical.index > train) & (historical.index <= selection)
        calibrating = common & (historical.index > selection)
        ranked = []
        for order, name in enumerate(design["candidate_order"]):
            metrics = regression_metrics(historical[choosing], means[name][choosing])
            if metrics["n"] < 100:
                raise ValueError("too few shared model-selection targets")
            scores.append({"horizon_days": h, "model": name, **metrics})
            ranked.append((metrics["rmse"], order, name))
        chosen[str(h)] = min(ranked)[2]
        for name in dict.fromkeys([chosen[str(h)], design["baseline"]]):
            radii[f"{h}/{name}"] = empirical_radius(
                historical[calibrating],
                means[name][calibrating],
                design["interval_level"],
            )
    day = cycles["day"].groupby(cycles["day"].index.strftime("%m-%d")).first()
    return {
        "design": design,
        "fit_config": {
            k: research_config[k]
            for k in (
                "harmonics",
                "ar_candidates",
                "selection_horizon",
                "ridge_order",
                "ridge_alphas",
            )
        },
        "selected_methods": chosen,
        "selection_scores": scores,
        "models": {k: v for k, v in parameters.items() if k in chosen.values()},
        "seasonal_fits": {
            "harmonic": harmonic.to_dict(),
            "harmonic_trend": trend.to_dict(),
        },
        "calendar_cycle": day.to_dict(),
        "interval_radii": radii,
        "fitting_rule": "training coefficients remain fixed; internal hyperparameters use selection-period 7-day RMSE; overall method uses selection-period RMSE separately at each horizon",
        "support_rule": "all eight candidates share selection/calibration targets; only selected method and baseline share new test targets at each horizon",
    }


def prepare(config_path, research_dir, frozen_path):
    if frozen_path.exists():
        raise ValueError(
            "frozen protocol already exists; evaluate it without overwriting"
        )
    design = json.loads(config_path.read_text())
    research = json.loads((research_dir / "research_config.json").read_text())
    history_path = research_dir / f"{design['domain']}_daily.csv"
    history = read_history(history_path)
    if history.index[-1] >= pd.Timestamp(design["test_start"]):
        raise ValueError("prepare must not receive any new holdout targets")
    frozen = freeze_models(history, design, research)
    grid_path = research_dir / "grid_masks.csv"
    grid = pd.read_csv(grid_path).query("domain == @design['domain']")
    # Store the already-fixed 2010 mask, never classify ocean using 2026 values.
    frozen["spatial_mask"] = {
        "lat": sorted(grid.lat.unique().tolist()),
        "lon": sorted(grid.lon.unique().tolist()),
        "selected_cells": grid.loc[grid.selected, ["lat", "lon"]].values.tolist(),
        "mask_date": "2010-01-01",
        "minimum_valid_weight_fraction": 0.8,
        "acquisition_region": research["acquisition_region"],
    }
    frozen["provenance"] = {
        "frozen_utc": datetime.now(timezone.utc).isoformat(),
        "history_date_end": str(history.index[-1].date()),
        "historical_daily_csv_sha256": sha256(history_path),
        "historical_grid_masks_sha256": sha256(grid_path),
        "research_config_sha256": sha256(research_dir / "research_config.json"),
        "historical_protocol_sha256": sha256(research_dir / "protocol.json"),
        "boundary": json.loads((research_dir / "protocol.json").read_text())[
            "boundary"
        ],
        "holdout_seen_at_freeze": False,
        "previously_seen": "2010-2025 exploratory study, including its retrospective test comparisons",
    }
    frozen_path.parent.mkdir(parents=True, exist_ok=True)
    frozen_path.write_text(
        json.dumps(frozen, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    )
    print("Frozen protocol:", frozen_path, sha256(frozen_path))
    print("Selected methods:", frozen["selected_methods"])
    return frozen


def frozen_means(sst, frozen, horizon):
    """Use serialized fits; there is no estimator or tuning operation here."""
    daily = sst.sort_index().asfreq("D")
    day = pd.Series(
        daily.index.strftime("%m-%d").map(frozen["calendar_cycle"]),
        index=daily.index,
        dtype=float,
    )
    cycles = {"day": day}
    for name, params in frozen["seasonal_fits"].items():
        fit = SeasonalFit(
            tuple(params["coefficients"]),
            pd.Timestamp(params["origin"]),
            params["harmonics"],
            params["linear_trend"],
            params["n_training_observations"],
        )
        cycles[name] = fit.predict(daily.index)
    name = frozen["selected_methods"][str(horizon)]
    result = {frozen["design"]["baseline"]: day + (daily - day).shift(horizon)}
    if name == "climatology":
        result[name] = day
    elif name == "raw_persistence":
        result[name] = daily.shift(horizon)
    elif name == "trend_seasonal":
        result[name] = cycles["harmonic_trend"]
    elif name != "persistence":
        params = frozen["models"][name]["parameters"]
        model = Autoregression(
            params["intercept"],
            tuple(params["coefficients"]),
            params["innovation_variance"],
            params["n_pairs"],
        )
        transform = (
            "harmonic_trend" if name.startswith("ridge_") else name.removeprefix("ar_")
        )
        result[name] = cycles[transform] + model.forecast(
            daily - cycles[transform], horizon
        )
    return result


def aggregate_holdout(files, frozen):
    with xr.open_mfdataset(
        [str(p) for p in files], combine="by_coords", engine="netcdf4"
    ) as source:
        data = source.sst.load()
    mask = frozen["spatial_mask"]
    if not np.array_equal(data.lat.values, mask["lat"]) or not np.array_equal(
        data.lon.values, mask["lon"]
    ):
        raise ValueError("new data grid differs from the frozen historical mask")
    flags = np.zeros((len(mask["lat"]), len(mask["lon"])), dtype=bool)
    for lat, lon in mask["selected_cells"]:
        flags[mask["lat"].index(lat), mask["lon"].index(lon)] = True
    weights = xr.DataArray(
        flags * np.cos(np.deg2rad(data.lat.values))[:, None],
        dims=("lat", "lon"),
        coords={"lat": data.lat, "lon": data.lon},
    )
    fraction = weights.where(data.notnull(), 0).sum(("lat", "lon")) / weights.sum()
    values = (
        data.where(weights > 0)
        .weighted(weights)
        .mean(("lat", "lon"))
        .where(fraction >= mask["minimum_valid_weight_fraction"])
    )
    expected = pd.date_range(
        frozen["design"]["test_start"], frozen["design"]["test_end"]
    )
    if not pd.DatetimeIndex(data.time.values).equals(expected):
        raise ValueError("holdout must contain exactly all prespecified daily dates")
    return pd.DataFrame(
        {
            "sst_observed_celsius": values.values,
            "valid_ocean_weight_fraction": fraction.values,
        },
        index=expected,
    ).rename_axis("date")


def score_holdout(sst, frozen):
    design = frozen["design"]
    rows, forecasts, intervals = [], [], []
    for h in design["horizons"]:
        means = frozen_means(sst, frozen, h)
        observed = sst.reindex(next(iter(means.values())).index)
        common = (
            observed.notna()
            & (observed.index >= design["test_start"])
            & (observed.index <= design["test_end"])
        )
        for predicted in means.values():
            common &= np.isfinite(predicted)
        if common.sum() < design["minimum_scoring_days"]:
            raise ValueError("too few shared holdout scoring days")
        base = means[design["baseline"]][common]
        base_rmse = regression_metrics(observed[common], base)["rmse"]
        for name, predicted in means.items():
            scored = predicted[common]
            radius = frozen["interval_radii"][f"{h}/{name}"]["radius_celsius"]
            metrics = regression_metrics(observed[common], scored)
            row = {
                "horizon_days": h,
                "model": name,
                **metrics,
                "bias_celsius": float((scored - observed[common]).mean()),
                "rmse_skill_vs_persistence": float(1 - metrics["rmse"] / base_rmse),
                "coverage_calibrated": float(
                    ((scored - observed[common]).abs() <= radius).mean()
                ),
                "width_calibrated_celsius": 2 * radius,
            }
            rows.append(row)
            forecasts.append(
                pd.DataFrame(
                    {
                        "date": scored.index,
                        "origin_date": scored.index - pd.Timedelta(days=h),
                        "horizon_days": h,
                        "model": name,
                        "observed_sst_celsius": observed[common].values,
                        "predicted_sst_celsius": scored.values,
                        "calibrated_radius_celsius": radius,
                    }
                )
            )
            if name == design["baseline"]:
                continue
            for block in design["bootstrap_block_days"]:
                intervals.append(
                    {
                        "horizon_days": h,
                        "model": name,
                        **skill_interval(
                            observed[common],
                            scored,
                            base,
                            block_days=max(h, block),
                            replicates=design["bootstrap_replicates"],
                            seed=design["random_seed"],
                        ),
                    }
                )
    return (
        pd.DataFrame(rows),
        pd.concat(forecasts, ignore_index=True),
        pd.DataFrame(intervals),
    )


def evaluate(frozen_path, research_dir, raw_dir, output_dir):
    frozen = json.loads(frozen_path.read_text())
    design = frozen["design"]
    history_path = research_dir / f"{design['domain']}_daily.csv"
    if sha256(history_path) != frozen["provenance"]["historical_daily_csv_sha256"]:
        raise ValueError("history changed since the protocol was frozen")
    output_dir.mkdir(parents=True, exist_ok=True)
    protocol_hash = sha256(frozen_path)
    event_path = output_dir / "evaluation_protocol.json"
    if (
        event_path.exists()
        and json.loads(event_path.read_text())["frozen_protocol_sha256"]
        != protocol_hash
    ):
        raise ValueError("output belongs to a different frozen protocol")
    if frozen_path.resolve() != (output_dir / "frozen_protocol.json").resolve():
        shutil.copy2(frozen_path, output_dir / "frozen_protocol.json")
    files = download_regional_range(
        date.fromisoformat(design["test_start"]),
        date.fromisoformat(design["test_end"]),
        Region(**frozen["spatial_mask"]["acquisition_region"]),
        raw_dir,
    )
    holdout = aggregate_holdout(files, frozen)
    history = read_history(history_path)
    if history.index[-1] != pd.Timestamp(design["test_start"]) - pd.Timedelta(days=1):
        raise ValueError(
            "history must supply the context immediately before the holdout"
        )
    values = pd.concat([history, holdout.sst_observed_celsius])
    metrics, forecasts, intervals = score_holdout(values, frozen)
    holdout.to_csv(output_dir / "holdout_daily.csv", date_format="%Y-%m-%d")
    metrics.to_csv(output_dir / "metrics.csv", index=False)
    forecasts.to_csv(
        output_dir / "predictions.csv", index=False, date_format="%Y-%m-%d"
    )
    intervals.to_csv(output_dir / "block_sensitivity.csv", index=False)
    pd.DataFrame(frozen["selection_scores"]).to_csv(
        output_dir / "selection_scores.csv", index=False
    )
    event = {
        "frozen_protocol_sha256": protocol_hash,
        "evaluated_utc": datetime.now(timezone.utc).isoformat(),
        "design": design,
        "source_acquisitions": [
            json.loads(p.with_suffix(".json").read_text()) for p in files
        ],
        "quality": {
            "daily_records": len(holdout),
            "observed_days": int(holdout.sst_observed_celsius.notna().sum()),
            "minimum_valid_weight_fraction": float(
                holdout.valid_ocean_weight_fraction.min()
            ),
        },
        "interpretation": design["scope"],
        "runtime_versions": {
            name: version(name)
            for name in (
                "numpy",
                "pandas",
                "xarray",
                "netCDF4",
                "matplotlib",
                "shapely",
            )
        },
    }
    event_path.write_text(
        json.dumps(event, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    )
    write_validation_report(metrics, forecasts, intervals, frozen, event, output_dir)
    write_validation_manuscript(research_dir, output_dir, frozen, metrics, intervals)
    (output_dir / "checksums.json").write_text(
        json.dumps(
            {
                p.name: sha256(p)
                for p in output_dir.iterdir()
                if p.is_file() and p.name != "checksums.json"
            },
            indent=2,
        )
        + "\n"
    )
    print(metrics.to_string(index=False))


def write_validation_report(metrics, forecasts, intervals, frozen, event, output_dir):
    from src.evaluation.research_report import ZH_LABELS, _html_report

    os.environ.setdefault("MPLCONFIGDIR", str((output_dir / ".matplotlib").resolve()))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(3, 1, figsize=(11, 10), constrained_layout=True)
    for ax, h in zip(axes, frozen["design"]["horizons"]):
        name = frozen["selected_methods"][str(h)]
        group = forecasts.query("horizon_days == @h and model == @name")
        dates = pd.to_datetime(group.date)
        ax.plot(
            dates, group.observed_sst_celsius, color="#222222", lw=1, label="Observed"
        )
        ax.plot(
            dates,
            group.predicted_sst_celsius,
            color="#1874b6",
            lw=1,
            label="Frozen selected forecast",
        )
        ax.fill_between(
            dates,
            group.predicted_sst_celsius - group.calibrated_radius_celsius,
            group.predicted_sst_celsius + group.calibrated_radius_celsius,
            color="#1874b6",
            alpha=0.15,
            label="2022 calibrated interval",
        )
        ax.set(title=f"{h}-day horizon | {name}", ylabel="SST (°C)")
        ax.grid(alpha=0.15)
    axes[0].legend(fontsize=8)
    fig.suptitle(
        "Previously unexamined 2026 temporal targets | IHO Yellow Sea includes Bohai"
    )
    fig.savefig(output_dir / "temporal_validation.png", dpi=150)
    plt.close(fig)
    lines = [
        "# 黄海项目：2026 年冻结方案时间验证",
        "",
        "## 验证性质",
        "",
        "本次先固定方案、模型与区间，再获取此前未查看的 2026 年 1—8 月目标数据。2010—2025 年研究成绩已经被查看；本次属于同一 OISST 产品的新时期检验，不能称为独立实测数据验证或实时预报。主区域沿用包含渤海的 IHO 定义。",
        "",
        "## 固定规则",
        "",
        "2010—2019 年拟合参数；2020—2021 年选择 AR 阶数、岭惩罚和每个步长的最终方法；2022 年固定区间；2023—2025 年不参与此次拟合、选择或校准，仅 2025 年末观测提供 2026 年初预测的起点。每个目标日仍只读取 d−h 及更早观测。",
        "",
        f"冻结时间（UTC）：{frozen['provenance']['frozen_utc']}。完整系数、季节均值、校准半径、掩膜和历史来源校验和见 frozen_protocol.json；本次冻结文件 SHA-256：{event['frozen_protocol_sha256']}。",
        "",
        "候选列表含八种方法和强基线。最终方法按各步长的共同日期选择期 RMSE 最小值决定；不按 2023—2025 或 2026 最佳成绩挑选。",
        "",
        f"2026 验证共 {event['quality']['daily_records']} 天，有效 {event['quality']['observed_days']} 天，最低有效海洋权重比例 {event['quality']['minimum_valid_weight_fraction']:.1%}。沿用 2010-01-01 掩膜，不插值。",
        "",
        "## 预先选定方法的结果",
        "",
        "| 步长 | 冻结方法 | RMSE（℃） | 基线 RMSE（℃） | 技能 | 30 天块 95% 区间 | 覆盖率 | 区间全宽（℃） |",
        "|---:|---|---:|---:|---:|---|---:|---:|",
    ]
    for h in frozen["design"]["horizons"]:
        name = frozen["selected_methods"][str(h)]
        row = metrics.query("horizon_days == @h and model == @name").iloc[0]
        base = metrics.query("horizon_days == @h and model == 'persistence'").iloc[0]
        ci = intervals.query("horizon_days == @h and bootstrap_block_days == 30")
        interval = (
            "基线自身"
            if ci.empty
            else f"[{ci.iloc[0].skill_ci_lower:.1%}, {ci.iloc[0].skill_ci_upper:.1%}]"
        )
        lines.append(
            f"| {h} | {ZH_LABELS[name]} | {row.rmse:.4f} | {base.rmse:.4f} | {row.rmse_skill_vs_persistence:.1%} | {interval} | {row.coverage_calibrated:.1%} | {row.width_calibrated_celsius:.3f} |"
        )
    lines += [
        "",
        "![冻结方法在2026年的预测与历史校准区间](temporal_validation.png)",
        "",
        "## 结果解读",
        "",
        validation_interpretation(frozen, metrics, intervals),
        "",
        "## 解释边界",
        "",
        "正技能表示这一窗口 RMSE 低于异常持续性，负技能表示更差；区间跨零不能解释为明确优于基线。30/60 天块、1000 次成对抽样和固定种子均预先规定，完整敏感性见 block_sensitivity.csv。区间未作三步长多重比较校正，只有 243 天且跨季节，近似平稳性有限，不能当作长期性能保证。",
        "",
        "2022 年经验半径在本次保持固定。覆盖率需与名义 95% 对照；即使点预测较好，区间也可能不足。1—8 月未覆盖完整年度、只含一个新年份，仍需新时期和独立观测来源复核。此次未重新选择模型，未重新估计趋势，也未利用新成绩校准区间。",
        "",
        "## 复现",
        "",
        "先运行 python -m src.research 获得原历史数据。公开冻结文件 paper/validation/frozen_protocol.json 可直接交给 python -m src.validation evaluate。完整命令见 docs/TEMPORAL_VALIDATION_zh.md。数据由 [NOAA PSL 官方服务](https://psl.noaa.gov/data/gridded/data.noaa.oisst.v2.highres.html) 提供；每份下载的 URL、时间、SHA-256 保存在 evaluation_protocol.json。",
    ]
    text = "\n".join(lines) + "\n"
    (output_dir / "时间验证报告_zh.md").write_text(text)
    _html_report(lines, output_dir)
    (output_dir / "完整研究报告.html").rename(output_dir / "时间验证报告.html")
    html_path = output_dir / "时间验证报告.html"
    html_path.write_text(
        html_path.read_text().replace(
            "<title>黄海 SST 完整研究报告</title>",
            "<title>黄海 SST 2026 年时间验证</title>",
        )
    )


def validation_interpretation(frozen, metrics, intervals):
    sentences = []
    for h in frozen["design"]["horizons"]:
        name = frozen["selected_methods"][str(h)]
        row = metrics.loc[metrics.horizon_days.eq(h) & metrics.model.eq(name)].iloc[0]
        ci = intervals.loc[
            intervals.horizon_days.eq(h) & intervals.bootstrap_block_days.eq(30)
        ]
        change = "降低" if row.rmse_skill_vs_persistence >= 0 else "增加"
        statement = f"{h} 天方法的 RMSE 相对异常持续性{change} {abs(row.rmse_skill_vs_persistence):.1%}，经验区间覆盖 {row.coverage_calibrated:.1%}。"
        if not ci.empty:
            low, high = ci.iloc[0].skill_ci_lower, ci.iloc[0].skill_ci_upper
            if low > 0:
                statement += "两端为正的描述性技能区间支持该窗口的改进。"
            elif high < 0:
                statement += "描述性技能区间两端为负。"
            else:
                statement += "技能区间跨零，不能据此宣称稳定优于或劣于基线。"
        sentences.append(statement)
    return " ".join(sentences)


def write_validation_manuscript(research_dir, output_dir, frozen, metrics, intervals):
    """Rebuild an integrated draft from the reproducible original and new outputs."""
    base = (research_dir / "manuscript_zh.md").read_text()
    for image_path in research_dir.glob("*.png"):
        shutil.copy2(image_path, output_dir / image_path.name)
    summary = validation_interpretation(frozen, metrics, intervals)
    base = base.replace(
        "论文初稿 · 探索性回溯研究", "论文修订稿 · 探索性回溯与冻结方案时间验证"
    )
    base = base.replace(
        "本扩展是在初次试验成绩已被查看后设计",
        "原回溯扩展是在初次试验成绩已被查看后设计",
    )
    base = base.replace(
        "**关键词：**",
        "新增检验先冻结方案再获取 2026 年 1—8 月未查看目标，共 243 天；使用同一 OISST 产品，不构成独立观测来源验证。"
        + summary
        + "\n\n**关键词：**",
    )
    method = """### 3.5 新时期验证的冻结协议

原研究的 2010—2025 年成绩已被查看，随后设计新增的 2026-01-01—2026-08-31 时间窗口。训练截止 2019 年、选择截止 2021 年、校准截止 2022 年。AR 阶数和岭惩罚沿用选择期 7 天规则；另外在每个 1/7/30 天步长的共同选择期日期上，以摄氏温度 RMSE 最小值从八个候选中选择最终方法，精确平分按固定列表顺序决定。选择期每方法每步长均为 731 个目标，校准期为 365 个目标。

冻结文件保存具体系数、日历季节均值、经验半径、2010 年固定海洋格点和来源校验和；配置与参数在下载 2026 年数据之前上传至 [GitHub 冻结提交](https://github.com/Joao-Ray/yellow-sea-sst-stochastic-modeling/commit/d0f6f17d84054df852c96640fe8ca5a9033c8fcf)。这是事前仓库记录，并非外部正式预注册。仅评分选定方法与异常持续性，保持参数与半径不变。2025 年末观测只用于提供跨年预测起点；2026 年内观测按每个 d−h 起点顺序进入，不能读取起点后的观测。预先固定 30/60 天成对循环块、1000 次、种子 20261003，未作三步长多重比较校正。

"""
    base = base.replace("## 4. 结果", method + "## 4. 结果")
    report = (output_dir / "时间验证报告_zh.md").read_text()
    table = (
        report.split("## 预先选定方法的结果\n\n", 1)[1]
        .split("## 结果解读", 1)[0]
        .strip()
    )
    table = table.replace(
        "![冻结方法在2026年的预测与历史校准区间]",
        "![图6：冻结方案在2026年的预测与历史校准区间]",
    )
    results = (
        "### 4.4 此前未查看的 2026 年时间窗口\n\n固定的最终方法为 1 天趋势谐波岭回归，7/30 天趋势谐波 AR。243 天均有效，最低有效海洋权重比例为 100%；每步长方法与基线评分日期相同，无时间插值。\n\n"
        + table
        + "\n\n"
        + summary
        + "\n\n"
    )
    base = base.replace("## 5. 讨论", results + "## 5. 讨论")
    base = base.replace(
        "但所有扩展结果仍为探索性回溯证据",
        "但原 2010—2025 年扩展结果仍为探索性回溯证据",
    )
    base = base.replace(
        "未来确认需要真正未查看的时期或外部资料。",
        "本修订增加了 2026 年未查看时期检验，但数据产品、区域和研究者的先前信息仍相同，后续还需独立观测来源和更多未查看年份。",
    )
    base = base.replace(
        "## 6. 结论",
        "新窗口中 30 天误差的点估计高于基线，与 2023—2025 年回溯改善不同。这个差异限制了长期预测优势的概括；趋势误设、时间漂移和季节构成都是可能解释，本研究未区分其因果贡献。仅 1—8 月、一个新年份和少量长块限制了不确定性评估，不能视为完整年度或长期性能保证。\n\n## 6. 结论",
    )
    base = base.replace(
        "## 数据与代码可用性",
        "新增时间验证支持此窗口的一日方法改进，七日优势尚不明确，三十日点估计较差。总体结论应强调随步长和时期变化的技能，不能仅以最近回溯成绩宣称普遍优越。\n\n## 数据与代码可用性",
    )
    base = base.replace(
        "运行 `python -m src.research` 生成全部结果与本文初稿。",
        "运行 `python -m src.research` 生成原回溯，再运行 `python -m src.validation evaluate` 生成时间验证与本修订稿。",
    )
    base = base.replace(
        "raw/derived 数据不纳入 Git",
        "原始 SST、边界几何与完整逐日预测不纳入 Git，公开汇总表与图作为审阅材料",
    )
    (output_dir / "manuscript_zh.md").write_text(base)
    _lines = base.splitlines()
    from src.evaluation.research_report import _html_report

    _html_report(_lines, output_dir)
    (output_dir / "完整研究报告.html").rename(output_dir / "论文修订稿.html")
    html_path = output_dir / "论文修订稿.html"
    html_path.write_text(
        html_path.read_text().replace(
            "<title>黄海 SST 完整研究报告</title>", "<title>黄海 SST 论文修订稿</title>"
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "evaluate"))
    parser.add_argument("--config", type=Path, default=Path("configs/validation.json"))
    parser.add_argument(
        "--frozen", type=Path, default=Path("paper/validation/frozen_protocol.json")
    )
    parser.add_argument(
        "--research-dir", type=Path, default=Path("data/processed/research")
    )
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/validation"))
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/processed/validation")
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if args.action == "prepare":
        prepare(args.config, args.research_dir, args.frozen)
    else:
        evaluate(args.frozen, args.research_dir, args.raw_dir, args.output_dir)


if __name__ == "__main__":
    main()
