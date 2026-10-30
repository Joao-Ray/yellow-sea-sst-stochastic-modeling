# Frozen independent AMSR2 instrument verification

- [Chinese report](独立观测验证报告_zh.md)
- [Protocol frozen before external observations](frozen_protocol.json)
- [Matched scores](metrics.csv), [paired daily-loss intervals](block_sensitivity.csv)
- [Daily observation coverage](coverage.csv), [same-day product agreement](matched_product_agreement.csv)
- [Source URLs, UTC acquisition times, strong ETags and range/subset hashes](provenance.json)
- [Integrated manuscript](../manuscript_zh.md)
- [Reproduction and interpretation](../../docs/INDEPENDENT_VALIDATION_zh.md)

Protocol was publicly committed in a3deb64 before acquiring 2026 AMSR2 targets.
The original OISST 2026 scores had already been viewed. No model retuning,
refitting, spatial coefficient fitting or bias correction uses external targets.
Daily matched spatial loss is weighted by latitude, then days receive equal
weight; paired 30/60-day bootstrap blocks do not resample spatial cells.

1 天 RMSE 2.1108℃、技能 0.4%、有效日 225；7 天 RMSE 2.2264℃、技能 1.1%、有效日 225；30 天 RMSE 2.3533℃、技能 0.7%、有效日 225。

三个步长的30天块技能区间均跨零，独立观测未确认稳定预测优势。完成的是独立仪器来源的离岸格点验证。AMSR2 漂移校准存在 Reynolds SST 共同参考，不能声称完全统计独立；缺测岸区与全海域均值未获得直接外部真值。
