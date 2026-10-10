# 黄海海表温度随机建模：开始使用

项目现在可以完整运行「NetCDF → 区域温度 → 季节异常 → 时间划分 → 预测比较 → 图表报告」。
已完成 2010–2025 年真实数据的完整探索研究、稳健性分析与论文初稿；另有模拟演示用于检查程序。
真实实验结果与局限见 [项目状态](PROJECT_STATUS.md)，详细报告在本地生成。

## 1. 准备环境

在项目根目录执行，推荐 Python 3.11：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows PowerShell 激活方式：`.venv\Scripts\Activate.ps1`。

## 2. 生成完整研究成果

```bash
python -m src.research
```

完成 3 种海域、3 个测试时期和 8 个模型的比较；模型选择和区间校准使用分开的时间段。
主海域采用有来源的 IHO Yellow Sea 多边形（包含渤海）。查看
`data/processed/research/完整研究报告.html`；论文初稿为 `manuscript_zh.md`。
首次运行下载约 47.7 MiB 的区域温度数据和约 1 MiB 的边界，后续校验并复用缓存。
详见 [完成说明](COMPLETION_zh.md)。

## 3. 一次跑通模拟演示

```bash
python -m src.demo
```

查看 `data/processed/demo/summary.md` 和 `overview.png`。
演示包含 2010–2019 年模拟温度、固定陆地格点、两天和十二天的缺测。
2010–2015 年训练，2016–2017 年验证，2018–2019 年测试；比较 1、7、30 天预测。
随机种子默认为 42；原始模拟数据、预测和报告均留在本地。

三个比较项是季节均值、持续性和 AR(1)。OU 是满足条件的 AR(1) 的连续时间解释，
会输出均值回复速度、长期均值、扩散强度和半衰期；它与 AR(1) 产生相同预测。

## 4. 验证一周真实 NOAA 数据

```bash
python -m src.data.download_oisst \
  --start-date 2022-01-01 --end-date 2022-01-07 \
  --output-dir data/raw/oisst-smoke

python -m src.data.preprocess \
  --input-dir data/raw/oisst-smoke \
  --output-file data/processed/noaa_smoke.csv \
  --climatology month \
  --climatology-start 2022-01-01 --climatology-end 2022-01-07
```

这一周只能验证数据管线。不能从一周数据得到可靠的季节均值或预测结论。
下载支持断点续跑（已存在的有效文件会跳过），HTML 错误页或空文件会被拒绝。

## 5. 保留的初次真实数据探索实验

现在可以先运行已经固定设计的真实数据探索实验：

```bash
python -m src.pilot
```

它自动从 NOAA PSL 官方服务获取 2010–2025 年区域子集，按月份下载、校验并续传。
训练期为 2010–2019 年，验证期为 2020–2022 年，测试期为 2023–2025 年。
从 AR(1/3/7/14) 中用验证期 7 天 RMSE 选阶，测试期保持训练系数不变。
同时提供成对时间块抽样的技能区间、残差日历相关、Q–Q 图和分年份区间覆盖率。

查看 `data/processed/pilot/报告_zh.md`。设计保存在 `configs/pilot.json`；
数据来源、旧版元数据兼容说明、每份文件的 SHA-256 与环境版本都写入报告附件。
这个实验仍使用矩形区域，属于探索阶段；准确海域边界与稳健性分析需要继续完成。

先确定研究期和海域。默认范围为北纬 31–39 度、东经 117–127 度，
按纬度余弦加权平均海洋格点。这个矩形也包括邻近海域，不能直接当作精确黄海边界。
目前以整个输入记录中有过有效 SST 的格点作为固定海洋掩膜。

完整年代的全球日文件需要较多磁盘与下载时间。正式实验应先规划下载范围；
也可使用上面的区域下载流程，地理海域掩膜仍需进一步完成。

取得多年数据后，预处理生成每日 CSV，再运行：

```bash
python -m src.evaluation.experiment \
  --input-file data/processed/yellow_sea_sst_daily.csv \
  --output-dir data/processed/experiment \
  --train-end 2010-12-31 --validation-end 2015-12-31 \
  --horizons 1 7 30
```

这个命令的日期示例适用于覆盖 1991–2025 年的输入，实际日期应依研究设计调整。
季节均值只用训练期原始观测计算，训练、预测起点和评分目标均排除插值值。
日历日气候态需要训练期覆盖全年；没有见过的 2 月 29 日取相邻两天季节均值的平均。

报告文件：

| 文件 | 内容 |
|---|---|
| `summary.md`、`overview.png` | 可读说明与图表 |
| `metrics.csv` | 验证/测试的样本数、MAE、RMSE、相对持续性的技能分数与区间覆盖率 |
| `predictions.csv` | 每条预测的目标日期、起点日期、步长、模型、真实值和区间 |
| `anomalies.csv` | 训练气候态得到的异常及所属时间段 |
| `parameters.json` | AR(1) 与等价 OU 参数 |
| `protocol.json` | 时间边界、缺测规则、输入校验和与实验假设 |

AR 的 95% 温度预测区间只考虑高斯创新误差，未包含参数与季节均值估计的不确定性。
相对技能分数为正表示本次样本上的 RMSE 较小，不代表统计显著优势。

## 6. 检查程序

```bash
python -m pytest -q
```

测试覆盖陆地与缺测区分、整段缺测插值限制、闰日处理、未来数据不影响训练、
多日预测不偷看中间观测、模型评分日期一致，以及 AR(1)/OU 等价关系。
GitHub Actions 会自动运行测试和离线演示。

## 查看新增时间验证与论文修订

完成原研究后执行：

```bash
python -m src.validation evaluate
```

在 `data/processed/validation/` 打开 `时间验证报告.html` 和 `论文修订稿.html`。
该命令直接使用 `paper/validation/frozen_protocol.json`，不按新数据调整模型。
结果支持一日预测在该窗口的改进，七日优势不明确，三十日点估计较差。
详见 [完整冻结协议](TEMPORAL_VALIDATION_zh.md)。
