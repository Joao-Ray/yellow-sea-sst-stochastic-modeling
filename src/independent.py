"""Verify frozen regional predictions against independent AMSR2 instrument targets."""

import argparse
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from functools import partial
from importlib.metadata import version
import json
import logging
import os
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import xarray as xr

from src.data.download_amsr2 import acquire_day
from src.evaluation.bootstrap import skill_interval
from src.validation import sha256


FROZEN = Path("paper/independent/frozen_protocol.json")


def load_inputs(frozen_path):
    protocol = json.loads(frozen_path.read_text())
    for name, expected in protocol["input_sha256"].items():
        if sha256(name) != expected:
            raise ValueError(f"frozen verification input changed: {name}")
    model_protocol = json.loads(
        Path("paper/validation/frozen_protocol.json").read_text()
    )
    predictions = pd.read_csv(
        "data/processed/validation/predictions.csv", parse_dates=["date", "origin_date"]
    )
    regional = (
        pd.read_csv(
            "data/processed/research/iho_yellow_sea_daily.csv", parse_dates=["date"]
        )
        .set_index("date")
        .sst_observed_celsius
    )
    # The already locked prediction CSV also retains the 2026 NOAA observations.
    # They enter projection only through .loc[d-h], never through .loc[d].
    targets = predictions.groupby("date").observed_sst_celsius
    if not targets.nunique(dropna=False).eq(1).all():
        raise ValueError("frozen regional target observations disagree between rows")
    regional = pd.concat([regional, targets.first()]).sort_index()
    if regional.index.has_duplicates:
        raise ValueError("historical and 2026 regional observations overlap")
    return protocol, model_protocol, predictions, regional


def load_origin_fields(config, mask):
    # December 2025 supplies 30-day origins for early January; no new NOAA data.
    files = list(Path("data/raw/research").glob("*20251201-20251231*.nc")) + list(
        Path("data/raw/validation").glob("*.nc")
    )
    if len(files) != 9:
        raise ValueError("the nine cached December-August NOAA subsets are required")
    records = []
    for p in files:
        m = json.loads(p.with_suffix(".json").read_text())
        if sha256(p) != m["sha256"]:
            raise ValueError("NOAA cached origin field failed checksum")
        records.append(m)
    with xr.open_mfdataset(
        [str(p) for p in files], combine="by_coords", engine="netcdf4"
    ) as ds:
        fields = ds.sst.load()
    if not np.array_equal(fields.lat, mask["lat"]) or not np.array_equal(
        fields.lon, mask["lon"]
    ):
        raise ValueError("NOAA grid differs from frozen mask")
    expected = pd.date_range("2025-12-01", config["date_end"])
    if not pd.DatetimeIndex(fields.time.values).equals(expected):
        raise ValueError("NOAA origin fields do not cover the required daily context")
    return fields, records


def quality_mask(sst, hours, masks, fixed):
    valid = np.isfinite(sst) & (sst >= -3) & (sst <= 35)
    valid &= np.isfinite(hours) & (hours >= 0) & (hours < 24)
    for flag in masks:
        if not np.isin(flag, [0, 1]).all():
            raise ValueError("AMSR2 mask must contain only documented zero/one flags")
        valid &= flag == 0
    return valid & fixed


def project_forecast(origin_field, forecast_regional, origin_regional):
    """Persist each cell's observed origin offset from the regional mean."""
    return origin_field + float(forecast_regional) - float(origin_regional)


def weighted_daily_score(observed, predictions, weights, valid, minimum):
    common = valid & np.isfinite(observed)
    for values in predictions.values():
        common &= np.isfinite(values)
    count = int(common.sum())
    if count < minimum:
        return None, common
    w = weights[common]
    w = w / w.sum()
    rows = {}
    for name, values in predictions.items():
        error = values[common] - observed[common]
        rows[name] = {
            "mse": float(w @ error**2),
            "mae": float(w @ abs(error)),
            "bias": float(w @ error),
        }
    return rows, common


def paired_loss_interval(model_loss, baseline_loss, block, config):
    # Transform already-aggregated daily loss to positive pseudo-errors solely
    # to reuse paired calendar-block sampling; no spatial observations resampled.
    zero = pd.Series(0.0, index=model_loss.index)
    return skill_interval(
        zero,
        np.sqrt(model_loss),
        np.sqrt(baseline_loss),
        block_days=block,
        replicates=config["bootstrap_replicates"],
        seed=config["random_seed"],
    )


def evaluate_pairs(files, fields, frozen_model, regional_predictions, regional, config):
    mask = frozen_model["spatial_mask"]
    fixed = np.zeros((len(mask["lat"]), len(mask["lon"])), dtype=bool)
    for lat, lon in mask["selected_cells"]:
        fixed[mask["lat"].index(lat), mask["lon"].index(lon)] = True
    weights = np.cos(np.deg2rad(mask["lat"]))[:, None] * np.ones_like(fixed)
    predictions = regional_predictions.set_index(["date", "horizon_days", "model"])
    daily, coverage, agreement = [], [], []
    for path in files:
        if path is None:
            continue
        day = pd.Timestamp(Path(path).stem.removeprefix("amsr2-"))
        with np.load(path) as source:
            if not np.array_equal(source["lat"], mask["lat"]) or not np.array_equal(
                source["lon"], mask["lon"]
            ):
                raise ValueError("external sensor grid differs from NOAA grid")
            for pass_index, pass_name in enumerate(["ascending", "descending"]):
                observed, hours = source["SST"][pass_index], source["time"][pass_index]
                valid = quality_mask(
                    observed,
                    hours,
                    [
                        source[k][pass_index]
                        for k in [
                            "land_mask",
                            "coast_mask",
                            "sea_ice_mask",
                            "noobs_mask",
                        ]
                    ],
                    fixed,
                )
                coverage.append(
                    {
                        "date": day,
                        "pass": pass_name,
                        "valid_cells": int(valid.sum()),
                        "fixed_ocean_cells": int(fixed.sum()),
                        "valid_weight_fraction": float(
                            weights[valid].sum() / weights[fixed].sum()
                        ),
                    }
                )
                today = fields.sel(time=day).values
                agree, support = weighted_daily_score(
                    observed,
                    {"oisst_same_day": today},
                    weights,
                    valid,
                    config["minimum_daily_cells"],
                )
                if agree:
                    agreement.append(
                        {
                            "date": day,
                            "pass": pass_name,
                            "n_cells": int(support.sum()),
                            **agree["oisst_same_day"],
                        }
                    )
                for h in config["horizons"]:
                    origin = day - pd.Timedelta(days=h)
                    origin_field = fields.sel(time=origin).values
                    selected = frozen_model["selected_methods"][str(h)]
                    means = {
                        name: project_forecast(
                            origin_field,
                            predictions.loc[(day, h, name), "predicted_sst_celsius"],
                            regional.loc[origin],
                        )
                        for name in [selected, "persistence"]
                    }
                    means["raw_grid_persistence"] = origin_field
                    scores, common = weighted_daily_score(
                        observed, means, weights, valid, config["minimum_daily_cells"]
                    )
                    if scores is None:
                        continue
                    for name, score in scores.items():
                        daily.append(
                            {
                                "date": day,
                                "origin_date": origin,
                                "pass": pass_name,
                                "horizon_days": h,
                                "model": name,
                                "n_cells": int(common.sum()),
                                **score,
                                "observed_mean_celsius": float(
                                    np.average(
                                        observed[common], weights=weights[common]
                                    )
                                ),
                                "predicted_mean_celsius": float(
                                    np.average(
                                        means[name][common], weights=weights[common]
                                    )
                                ),
                            }
                        )
    return pd.DataFrame(daily), pd.DataFrame(coverage), pd.DataFrame(agreement)


def aggregate_results(daily, agreement, config):
    metrics, blocks = [], []
    for (pass_name, h), group in daily.groupby(["pass", "horizon_days"]):
        base = group.loc[group.model.eq("persistence")].set_index("date").sort_index()
        if len(base) < config["minimum_scoring_days"]:
            raise ValueError(f"insufficient matched days for {pass_name}/{h}")
        baseline_rmse = np.sqrt(base.mse.mean())
        for name, values in group.groupby("model"):
            values = values.set_index("date").sort_index()
            if not values.index.equals(base.index) or not np.array_equal(
                values.n_cells, base.n_cells
            ):
                raise ValueError(
                    "methods must share exactly the same observation support"
                )
            rmse = float(np.sqrt(values.mse.mean()))
            metrics.append(
                {
                    "pass": pass_name,
                    "horizon_days": int(h),
                    "model": name,
                    "n_days": len(values),
                    "n_cell_day_pairs": int(values.n_cells.sum()),
                    "rmse": rmse,
                    "mae": float(values.mae.mean()),
                    "bias_celsius": float(values.bias.mean()),
                    "rmse_skill_vs_persistence": float(1 - rmse / baseline_rmse),
                }
            )
            if name != "persistence":
                for block in config["bootstrap_block_days"]:
                    blocks.append(
                        {
                            "pass": pass_name,
                            "horizon_days": int(h),
                            "model": name,
                            **paired_loss_interval(
                                values.mse, base.mse, max(h, block), config
                            ),
                        }
                    )
    agreement_metrics = []
    for name, group in agreement.groupby("pass"):
        agreement_metrics.append(
            {
                "pass": name,
                "n_days": len(group),
                "n_cell_day_pairs": int(group.n_cells.sum()),
                "rms_difference_celsius": float(np.sqrt(group.mse.mean())),
                "mean_difference_oisst_minus_amsr2_celsius": float(group.bias.mean()),
                "mean_absolute_difference_celsius": float(group.mae.mean()),
            }
        )
    return pd.DataFrame(metrics), pd.DataFrame(blocks), pd.DataFrame(agreement_metrics)


def run(frozen_path, raw_dir, output_dir, workers):
    protocol, model, predictions, regional = load_inputs(frozen_path)
    config = protocol["config"]
    output_dir.mkdir(parents=True, exist_ok=True)
    event_path = output_dir / "protocol.json"
    frozen_hash = sha256(frozen_path)
    if (
        event_path.exists()
        and json.loads(event_path.read_text())["frozen_protocol_sha256"] != frozen_hash
    ):
        raise ValueError("output belongs to a different protocol")
    dates = [
        day.date() for day in pd.date_range(config["date_start"], config["date_end"])
    ]
    if not 1 <= workers <= 3:
        raise ValueError("workers must be in 1..3")
    acquire = partial(
        acquire_day,
        region=model["spatial_mask"]["acquisition_region"],
        output_dir=raw_dir,
    )
    files = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for i, path in enumerate(pool.map(acquire, dates), 1):
            files.append(path)
            logging.info(
                "AMSR2 original observations: %s/%s UTC days acquired", i, len(dates)
            )
    fields, origin_records = load_origin_fields(config, model["spatial_mask"])
    daily, coverage, agreement = evaluate_pairs(
        files, fields, model, predictions, regional, config
    )
    metrics, blocks, agreement_metrics = aggregate_results(daily, agreement, config)
    for name, frame in [
        ("daily_metrics", daily),
        ("coverage", coverage),
        ("matched_product_daily", agreement),
        ("metrics", metrics),
        ("block_sensitivity", blocks),
        ("matched_product_agreement", agreement_metrics),
    ]:
        frame.to_csv(output_dir / (name + ".csv"), index=False, date_format="%Y-%m-%d")
    source_records = [
        json.loads(Path(p).with_suffix(".json").read_text()) for p in files if p
    ]
    missing = [str(day) for day, p in zip(dates, files) if p is None]
    event = {
        "frozen_protocol_sha256": frozen_hash,
        "frozen_utc": protocol["frozen_utc"],
        "evaluated_utc": datetime.now(timezone.utc).isoformat(),
        "config": config,
        "source_acquisitions": source_records,
        "missing_global_dates": missing,
        "origin_fields": origin_records,
        "runtime_versions": {
            k: version(k)
            for k in ["numpy", "pandas", "xarray", "netCDF4", "h5py", "matplotlib"]
        },
        "acquired_source_bytes": sum(p["acquired_bytes"] for p in source_records),
        "input_sha256": protocol["input_sha256"],
        "interpretation": config["scope"],
        "implementation_notes": [
            "Initial scoring execution stopped before producing results because regional origins ended in 2025. The repair appends 2026 origin observations already retained in the SHA-locked prediction CSV, reads only d-h, and changes no frozen rule or model."
        ],
    }
    if any(
        datetime.fromisoformat(row["acquired_utc"])
        <= datetime.fromisoformat(protocol["frozen_utc"])
        for row in source_records
    ):
        raise ValueError("external observations were acquired before this freeze")
    event_path.write_text(json.dumps(event, ensure_ascii=False, indent=2) + "\n")
    shutil.copy2(frozen_path, output_dir / "frozen_protocol.json")
    write_report(
        metrics, blocks, agreement_metrics, daily, coverage, event, model, output_dir
    )
    write_manuscript(output_dir)
    write_public_provenance(event, output_dir)
    (output_dir / "checksums.json").write_text(
        json.dumps(
            {
                p.name: sha256(p)
                for p in output_dir.iterdir()
                if p.is_file() and p.name != "checksums.json"
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    print(metrics.to_string(index=False))


def write_report(
    metrics, blocks, agreement_metrics, daily, coverage, event, model, output_dir
):
    from src.evaluation.research_report import ZH_LABELS, _html_report

    os.environ.setdefault("MPLCONFIGDIR", str((output_dir / ".matplotlib").resolve()))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(12, 9), constrained_layout=True)
    for pass_name, color in [("descending", "#1874b6"), ("ascending", "#d76e19")]:
        cover = coverage.loc[coverage["pass"].eq(pass_name)].sort_values("date")
        axes[0, 0].plot(
            cover.date, cover.valid_weight_fraction, label=pass_name, color=color
        )
        diff = pd.read_csv(
            output_dir / "matched_product_daily.csv", parse_dates=["date"]
        )
        diff = (
            diff.loc[diff["pass"].eq(pass_name)]
            .set_index("date")
            .sort_index()
            .asfreq("D")
        )
        axes[0, 1].plot(diff.index, diff.bias, label=pass_name, color=color, alpha=0.8)
        selected = metrics.loc[
            metrics["pass"].eq(pass_name)
            & metrics.model.isin(model["selected_methods"].values())
        ].sort_values("horizon_days")
        axes[1, 0].plot(
            selected.horizon_days,
            selected.rmse,
            "o-",
            label=pass_name + " selected",
            color=color,
        )
        base = metrics.loc[
            metrics["pass"].eq(pass_name) & metrics.model.eq("persistence")
        ].sort_values("horizon_days")
        axes[1, 0].plot(
            base.horizon_days,
            base.rmse,
            "s--",
            label=pass_name + " baseline",
            color=color,
        )
    axes[0, 0].set(
        title="Observed offshore coverage", ylabel="Fraction of fixed IHO ocean weight"
    )
    axes[0, 1].set(
        title="Matched same-day OISST minus AMSR2", ylabel="Daily weighted bias (°C)"
    )
    axes[0, 1].axhline(0, color="grey", lw=0.7)
    axes[1, 0].set(
        title="Frozen spatial projection vs external observations",
        xlabel="Forecast horizon (days)",
        ylabel="RMSE (°C)",
    )
    primary = blocks.loc[
        blocks["pass"].eq("descending")
        & blocks.model.isin(model["selected_methods"].values())
    ]
    for offset, block in [(-0.12, 30), (0.12, 60)]:
        g = primary.loc[primary.bootstrap_block_days.eq(block)].sort_values(
            "horizon_days"
        )
        selected = metrics.loc[
            metrics["pass"].eq("descending")
            & metrics.model.isin(model["selected_methods"].values())
        ].sort_values("horizon_days")
        x = np.arange(len(g)) + offset
        axes[1, 1].vlines(
            x,
            g.skill_ci_lower * 100,
            g.skill_ci_upper * 100,
            colors="#1874b6" if block == 30 else "#d76e19",
            lw=2,
            label=f"{block}-day blocks",
        )
        axes[1, 1].scatter(
            x,
            selected.rmse_skill_vs_persistence * 100,
            s=25,
            color="#1874b6" if block == 30 else "#d76e19",
        )
    axes[1, 1].axhline(0, color="grey", lw=0.7)
    axes[1, 1].set(
        xticks=np.arange(3),
        xticklabels=["1", "7", "30"],
        xlabel="Forecast horizon (days)",
        ylabel="Skill vs anomaly persistence (%)",
        title="Primary nighttime paired daily-loss intervals",
    )
    for ax in axes.ravel():
        ax.grid(alpha=0.15)
        ax.legend(fontsize=7)
    for ax in axes[0]:
        ax.tick_params(axis="x", rotation=25)
    fig.suptitle(
        "Independent AMSR2 instrument check | observed cells, fixed origin-only projection"
    )
    fig.savefig(output_dir / "independent_validation.png", dpi=150)
    plt.close(fig)
    lines = [
        "# 黄海项目：AMSR2 独立传感器观测验证",
        "",
        "## 已完成的验证与独立性",
        "",
        "本次直接获取 RSS/JAXA GCOM-W1 AMSR2 v8.2 微波卫星原始三级观测格网，使用 2026 年 1—8 月资料，与已经冻结的预测逐格点匹配。它不是 OISST 的另一下载副本。NOAA 的当前 OISST 说明列出 ACSPO AVHRR/VIIRS、船舶/浮标/Argo 和海冰等输入；AMSR2 不在列出的传感器中。据此将本次资料视为独立观测仪器来源。[1–3]",
        "",
        "**独立仪器不等于完全统计独立。** RSS v8.2 长期仪器漂移分析/校准使用过 Reynolds SST 等参考资料；这种共同参考依赖必须披露。本次不把结果称为完全独立的绝对真值检验。仍存在卫星反演误差、数十公里仪器足迹（6.93 GHz 通道约 62×35 km）与 0.25° 格点不等价、近表层与日平均差异，以及沿岸/降雨/海冰缺测。",
        "",
        "## 冻结与匹配规则",
        "",
        f"方案先于新观测获取固定。冻结 UTC：{event['frozen_utc']}；冻结 SHA-256：{event['frozen_protocol_sha256']}；[事前 GitHub 提交](https://github.com/Joao-Ray/yellow-sea-sst-stochastic-modeling/commit/a3deb64aba90017d59b47ac1c9404f0efbe41ad7)。此前 2026 OISST 成绩已经被查看，本次只是独立传感器的新目标，不能重新声称原窗口从未查看。",
        "",
        "主分析为下降轨（约当地凌晨 1:30），上升轨（约下午 1:30）为预先规定的敏感性。使用文件 UTC 日期和像元时间；时间须在 [0,24) 小时。SST 须有限且在官方 [-3,35]℃范围，land/coast/sea_ice/noobs 均为 0，并属于 2010 年固定海洋格点。缺测不插值、不补成 OISST。每天至少 20 个共同有效格点才评分；不能把未观测岸区当成已验证。",
        "",
        "区域预测不能直接当成单点温度。事前规定零参数空间投影：格点预测 = 起点格点 OISST + 冻结区域目标预测 − 起点区域 OISST。即起点格点相对区域均值的偏差保持不变。原异常持续性采用相同投影；另评分直接格点持续性。全部只读取 d−h 及更早观测，不利用目标日 OISST 调整预测。目标日 OISST 只在独立的产品一致性表中与 AMSR2 比较。",
        "",
        "每目标日内用纬度余弦归一化权重聚合共同格点的平方/绝对/有符号误差，随后各日等权。统计样本为日期，不把数万相邻格点误当独立重复实验。30/60 天成对循环日历块、1000 次、固定种子，保留日历缺口。检验的是固定空间投影在可见离岸格点的性能；不是原全黄海区域均值直接获得独立实测真值。",
        "",
        "## 主分析：夜间观测",
        "",
        "| 步长 | 冻结方法 | 有效日 | 格点日配对数 | RMSE（℃） | 基线RMSE（℃） | 技能 | 30天块95%区间 | 60天块95%区间 |",
        "|---:|---|---:|---:|---:|---:|---:|---|---|",
    ]
    conclusions = []
    for h in [1, 7, 30]:
        name = model["selected_methods"][str(h)]
        row = metrics.loc[
            metrics["pass"].eq("descending")
            & metrics.horizon_days.eq(h)
            & metrics.model.eq(name)
        ].iloc[0]
        base = metrics.loc[
            metrics["pass"].eq("descending")
            & metrics.horizon_days.eq(h)
            & metrics.model.eq("persistence")
        ].iloc[0]
        ci = blocks.loc[
            blocks["pass"].eq("descending")
            & blocks.horizon_days.eq(h)
            & blocks.model.eq(name)
            & blocks.bootstrap_block_days.eq(30)
        ].iloc[0]
        ci60 = blocks.loc[
            blocks["pass"].eq("descending")
            & blocks.horizon_days.eq(h)
            & blocks.model.eq(name)
            & blocks.bootstrap_block_days.eq(60)
        ].iloc[0]
        lines.append(
            f"| {h} | {ZH_LABELS[name]} | {row.n_days} | {row.n_cell_day_pairs} | {row.rmse:.4f} | {base.rmse:.4f} | {row.rmse_skill_vs_persistence:.1%} | [{ci.skill_ci_lower:.2%}, {ci.skill_ci_upper:.2%}] | [{ci60.skill_ci_lower:.2%}, {ci60.skill_ci_upper:.2%}] |"
        )
        conclusion = (
            "至少一种块长区间跨零或块长间方向不同，优势不明确"
            if not (
                min(ci.skill_ci_lower, ci60.skill_ci_lower) > 0
                or max(ci.skill_ci_upper, ci60.skill_ci_upper) < 0
            )
            else "30/60天块区间两端均为正"
            if min(ci.skill_ci_lower, ci60.skill_ci_lower) > 0
            else "30/60天块区间两端均为负"
        )
        conclusions.append(
            f"{h} 天技能 {row.rmse_skill_vs_persistence:.1%}，{conclusion}。"
        )
    lines += [
        "",
        " ".join(conclusions),
        "",
        "![独立观测的覆盖、一致性和预测验证](independent_validation.png)",
        "",
        "## 日夜与产品对照",
        "",
        "| 观测轨道 | 有效日 | 同格点OISST与AMSR2 RMS差（℃） | OISST−AMSR2偏差（℃） |",
        "|---|---:|---:|---:|",
    ]
    product_summary = " ".join(
        f"{row['pass']} 同日产品RMS差 {row['rms_difference_celsius']:.3f}℃、OISST−AMSR2偏差 {row['mean_difference_oisst_minus_amsr2_celsius']:.3f}℃。"
        for row in agreement_metrics.to_dict("records")
    )
    for row in agreement_metrics.itertuples():
        lines.append(
            f"| {row.pass_ if hasattr(row, 'pass_') else row[1]} | {row.n_days} | {row.rms_difference_celsius:.4f} | {row.mean_difference_oisst_minus_amsr2_celsius:.4f} |"
        )
    lines += [
        "",
        product_summary
        + "这些较大的产品差异限制模型技能的可辨识性；不能把全部差异当成预测模型误差，也未按结果删去异常日期或进行偏差校正。",
        "",
    ]
    lines += [
        "",
        "### 日夜敏感性与直接格点持续性",
        "",
        "| 轨道 | 步长 | 选定方法RMSE（℃） | 直接格点持续性RMSE（℃） | 选定方法相对异常持续性技能 |",
        "|---|---:|---:|---:|---:|",
    ]
    for pass_name in ["descending", "ascending"]:
        for h in [1, 7, 30]:
            group = metrics.loc[
                metrics["pass"].eq(pass_name) & metrics.horizon_days.eq(h)
            ].set_index("model")
            chosen = group.loc[model["selected_methods"][str(h)]]
            raw = group.loc["raw_grid_persistence"]
            lines.append(
                f"| {pass_name} | {h} | {chosen.rmse:.4f} | {raw.rmse:.4f} | {chosen.rmse_skill_vs_persistence:.1%} |"
            )
    lines += [
        "",
        "### 观测覆盖范围",
        "",
        "| 轨道 | 至少20格点的日期数 | 每日有效格点中位数 | 有效权重比例最小/中位/最大 |",
        "|---|---:|---:|---|",
    ]
    for pass_name, group in coverage.groupby("pass"):
        fraction = group.valid_weight_fraction
        lines.append(
            f"| {pass_name} | {int(group.valid_cells.ge(20).sum())} | {group.valid_cells.median():.0f} | {fraction.min():.1%} / {fraction.median():.1%} / {fraction.max():.1%} |"
        )
    lines += [
        "",
        "上升轨、直接格点持续性以及全部预先规定块长均在 metrics.csv 和 block_sensitivity.csv 中保留。产品差异表的目标日 OISST 未进入预测。卫星误差和空间投影误差都包含在预测RMSE中，不能单独归因于随机模型。",
        "",
        "## 数据完整性与复现",
        "",
        f"配置日期共 243 天，官方文件缺失日期 {len(event['missing_global_dates'])} 天；实际字节范围下载约 {event['acquired_source_bytes'] / 1024**2:.1f} MiB。范围读取逐块验证强 ETag、字节区间与 SHA-256，并校验裁剪数据；未声称对未下载的全球文件进行了完整校验。所有 URL、时间、原产品属性、逐块和裁剪校验记录在 protocol.json 中。",
        "",
        "运行 python -m src.independent，读取 paper/independent/frozen_protocol.json，不调整原模型。原始区域观测留在 data/raw/independent/，逐日匹配评分、覆盖和报告生成到 data/processed/independent/。原研究和同源时间验证保持原记录。",
        "",
        "## 参考资料与致谢",
        "",
        "1. [NOAA OISST 当前输入与更新说明](https://www.ncei.noaa.gov/products/optimum-interpolation-sst)。2021-10 起 ACSPO AVHRR/VIIRS 输入，2023-04 起船舶偏差调整；旧目录 AVHRR 名称不能理解为始终只有 AVHRR。",
        "2. Wentz et al. (2021). RSS GCOM-W1 AMSR2 Daily Environmental Suite, v8.2. [10.56236/RSS-bq](https://www.remss.com/DOI/RSS-bq.html)。",
        "3. [RSS v8.2 仪器漂移技术报告](https://images.remss.com/papers/tech_reports/2021/AMSR-2_Air-Sea_Essential_Climate_Variables_RSS_Version_8.2.pdf)。其中明确披露 Reynolds SST 在漂移分析中的使用。",
        "",
        "AMSR2 AS-ECV 由 Remote Sensing Systems 生产、NASA 支持，原始辐射计观测由 JAXA 提供。研究感谢这些机构的数据支持。仪器足迹与轨道时间见 [RSS 仪器说明](https://www.remss.com/missions/amsr/)。",
    ]
    audit_path = output_dir / "source_audit.json"
    if audit_path.exists():
        audit = json.loads(audit_path.read_text())
        lines += [
            "",
            "### 事后原文件读取复核",
            "",
            f"因同日产品差异较大，对 {audit['date']} 官方完整文件使用 netCDF4 自动掩膜/缩放进行第二读取方式复核，SST、时间、四种质量标记与原 h5py 范围裁剪全部逐值一致；官方 pass 标记明确 1=上升日间、2=下降夜间。完整全球文件 SHA-256 为 {audit['complete_global_sha256']}。记录见 source_audit.json。这是事后读取诊断，不是另一个观测来源，未据此改变质量规则、删日期或重调模型。",
            "",
        ]
    (output_dir / "独立观测验证报告_zh.md").write_text("\n".join(lines).rstrip() + "\n")
    _html_report(lines, output_dir)
    (output_dir / "完整研究报告.html").rename(output_dir / "独立观测验证报告.html")
    report_html = output_dir / "独立观测验证报告.html"
    report_html.write_text(
        report_html.read_text().replace(
            "<title>黄海 SST 完整研究报告</title>",
            "<title>黄海 SST 独立仪器观测验证</title>",
        )
    )


def write_public_provenance(event, output_dir):
    """Keep a compact, public audit while retaining full original attributes locally."""
    public = {k: v for k, v in event.items() if k != "source_acquisitions"}
    public["source_acquisitions"] = [
        {
            k: v
            for k, v in row.items()
            if k not in ("source_attributes", "variable_attributes")
        }
        for row in event["source_acquisitions"]
    ]
    public["full_attribute_records"] = (
        "Local data/processed/independent/protocol.json; copied into results archive"
    )
    (output_dir / "provenance.json").write_text(
        json.dumps(public, ensure_ascii=False, indent=2) + "\n"
    )


def write_manuscript(output_dir):
    """Integrate all three evidence stages into one reproducible paper draft."""
    from src.evaluation.research_report import _html_report

    base_dir = Path("data/processed/validation")
    base = (base_dir / "manuscript_zh.md").read_text()
    for image in base_dir.glob("*.png"):
        shutil.copy2(image, output_dir / image.name)
    report = (output_dir / "独立观测验证报告_zh.md").read_text()
    methods = report.split("## 冻结与匹配规则\n\n", 1)[1].split(
        "## 主分析：夜间观测", 1
    )[0]
    source_description = "独立仪器检验直接获取 RSS/JAXA GCOM-W1 AMSR2 v8.2 官方每日三级微波 SST。NOAA 当前列出的 OISST 传感器输入没有 AMSR2，据此推断仪器来源独立；不把这个输入清单当成排除全部共同处理依赖的证明。RSS 漂移分析使用 Reynolds SST，需披露共同参考。[1,5–7] 微波观测有数十公里仪器足迹（6.93 GHz 通道约 62×35 km）、日夜和近表层差异；降雨、沿岸及海冰造成缺测，只评分真实有效观测。\n\n"
    base = base.replace("## 3. 方法", source_description + "## 3. 方法", 1)
    results = report.split("## 主分析：夜间观测\n\n", 1)[1].split(
        "## 数据完整性与复现", 1
    )[0]
    results = results.replace("## 日夜与产品对照", "#### 日夜与产品对照")
    results = results.replace(
        "![独立观测的覆盖、一致性和预测验证]",
        "![图7：独立观测的覆盖、一致性和预测验证]",
    )
    metrics = pd.read_csv(output_dir / "metrics.csv")
    frozen = json.loads(Path("paper/validation/frozen_protocol.json").read_text())
    statements = []
    for h in [1, 7, 30]:
        row = metrics.loc[
            metrics["pass"].eq("descending")
            & metrics.horizon_days.eq(h)
            & metrics.model.eq(frozen["selected_methods"][str(h)])
        ].iloc[0]
        statements.append(
            f"{h} 天 RMSE {row.rmse:.3f}℃、相对异常持续性技能 {row.rmse_skill_vs_persistence:.1%}"
        )
    intervals = pd.read_csv(output_dir / "block_sensitivity.csv")
    primary_intervals = intervals.loc[
        intervals["pass"].eq("descending")
        & intervals.bootstrap_block_days.eq(30)
        & intervals.model.isin(frozen["selected_methods"].values())
    ]
    uncertainty = (
        "三个步长的30天块技能区间均跨零，未确认外部观测上的稳定优势。"
        if (
            (primary_intervals.skill_ci_lower <= 0)
            & (primary_intervals.skill_ci_upper >= 0)
        ).all()
        else "技能区间的符号和块长敏感性须结合结果表解读。"
    )
    summary = (
        "新增 AMSR2 独立仪器来源检验，在夜间有效离岸格点上的固定空间投影得到："
        + "；".join(statements)
        + "。"
        + uncertainty
        + "这是可见格点的检验，不能解释为全海域实测均值验证；仪器校准的共同参考依赖仍存在。"
    )
    base = base.replace(
        "OISST 是 0.25° 的融合分析产品",
        "OISST 自 2021-10 起采用 ACSPO AVHRR/VIIRS，自 2023-04 起调整船舶偏差；旧 AVHRR 目录名不代表始终只有这一传感器。OISST 是 0.25° 的融合分析产品",
    )
    base = base.replace("**关键词：**", summary + "\n\n**关键词：**", 1)
    base = base.replace(
        "探索性回溯与冻结方案时间验证", "探索性回溯、冻结时间验证与独立仪器检验"
    )
    base = base.replace(
        "## 4. 结果",
        "### 3.6 独立仪器来源与冻结空间匹配\n\n" + methods + "## 4. 结果",
        1,
    )
    base = base.replace(
        "## 5. 讨论",
        "### 4.5 AMSR2 微波观测的独立仪器检验\n\n" + results + "## 5. 讨论",
        1,
    )
    base = base.replace(
        "后续还需独立观测来源和更多未查看年份。",
        "本修订进一步完成了 AMSR2 独立仪器来源检验，但尚未建立完全统计独立、完整岸区覆盖和更多未查看年份的证据。",
    )
    caveat = "AMSR2 与 OISST 的同格点差异同时包含反演、日夜、足迹和融合处理差异；空间投影也保持起点空间偏差不变。因此该检验评价的是冻结区域模型加事前空间投影的联合性能，不能把格点误差全部归因于区域模型。RSS v8.2 漂移分析使用 Reynolds SST；独立传感器不等于完全统计独立。[5–6] 30/60 天块区间仍依赖近似平稳性，三步长与两轨道的多重比较未校正。\n\n"
    base = base.replace("## 6. 结论", caveat + "## 6. 结论", 1)
    base = base.replace(
        "## 数据与代码可用性",
        summary
        + " 外部观测的全部既定步长、日夜敏感性和较差结果均保留，不依据新观测重调模型。\n\n## 数据与代码可用性",
        1,
    )
    base = base.replace(
        "生成时间验证与本修订稿。",
        "生成时间验证，再运行 `python -m src.independent` 生成独立仪器验证与本修订稿。",
    )
    base += "\n5. Wentz et al. (2021). RSS GCOM-W1 AMSR2 Daily Environmental Suite, v8.2. [10.56236/RSS-bq](https://www.remss.com/DOI/RSS-bq.html)。\n6. Remote Sensing Systems (2021). [AMSR-2 Air-Sea Essential Climate Variables, RSS Version 8.2](https://images.remss.com/papers/tech_reports/2021/AMSR-2_Air-Sea_Essential_Climate_Variables_RSS_Version_8.2.pdf)。\n"
    base += "\n7. Remote Sensing Systems. [AMSR 仪器、通道足迹与每日观测说明](https://www.remss.com/missions/amsr/)。\n"
    (output_dir / "manuscript_zh.md").write_text(base)
    _html_report(base.splitlines(), output_dir)
    (output_dir / "完整研究报告.html").rename(output_dir / "论文修订稿.html")
    html = output_dir / "论文修订稿.html"
    html.write_text(
        html.read_text().replace(
            "<title>黄海 SST 完整研究报告</title>",
            "<title>黄海 SST 论文修订稿 · 独立仪器验证</title>",
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen", type=Path, default=FROZEN)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/independent"))
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/processed/independent")
    )
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    run(args.frozen, args.raw_dir, args.output_dir, args.workers)


if __name__ == "__main__":
    main()
