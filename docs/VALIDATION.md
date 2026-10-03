# Forecast validation and observational pilot protocol

## Data and target

The input is a daily regional SST series in Celsius. Date rows must be unique,
timezone-free midnight calendar dates. Reindexing exposes missing dates.
`sst_observed_celsius` is preferred; older `sst_celsius` inputs are accepted
with interpolated rows excluded whenever their flag is supplied. An older CSV
without flags must be checked by the researcher for prior imputation.
Previously computed anomaly columns are ignored.

The default preprocessing rectangle (31–39 N, 117–127 E) includes adjacent seas.
The empirical ocean mask excludes cells missing throughout the input record;
it can also exclude persistently unobserved ocean. A geographical mask and
region sensitivity analysis remain research work.

## Time splits and seasonal cycle

The caller explicitly fixes a training end and validation end before inspecting
test scores. Training includes the first date through `train_end`; validation
is the next day through `validation_end`; test is everything later.
Calendar-day or month climatology uses only raw training observations and is
frozen for every split. All seasonal bins must be represented. An unseen leap
day uses the mean of February 28 and March 1, both fitted within training.
There is no detrending or test-period refitting. The default experiment has no
selection. With `--ar-candidates`, candidate AR(p) coefficients use training
data only and order is selected on validation RMSE at an explicit horizon,
using common candidate support. Ties prefer the smaller order. Selected-model
validation scores are selection-biased; independent test scores are separate.

Exploratory preprocessing may interpolate complete short internal gaps.
Forecasting discards these values, so no future endpoint is used to construct
training pairs, forecast origins, or scoring targets. The raw column survives
preprocessing for this purpose.

## Forecast protocol

Parameters are estimated once on complete calendar-day training lag vectors. For a
target date `d` and horizon `h`, the origin is `d-h`; that date's actual
observation is available. This is a rolling-origin evaluation with fixed model
parameters, not a single forecast launched at the start of the test period.
No intermediate observations between origin and target enter an h-day forecast.

Compare:

- Climatology: zero anomaly at every horizon.
- Persistence: the origin anomaly at every horizon.
- AR(1): `X[t+1] = c + phi X[t] + epsilon[t+1]`, fit by OLS with an intercept;
  the h-day conditional mean is calculated recursively.
- When requested, the validation-selected AR(p), with all p observed origin
  lags present. All comparison models share its eligible support for each split
  and horizon; coefficients remain frozen. If p=1 it is the existing AR(1),
  not a duplicate leaderboard entry.

The exact OU interpretation `dX = theta(mu-X)dt + sigma dW` exists when
`0 < phi < 1`, using a one-day sampling interval:

```text
theta = -log(phi)
mu = c / (1-phi)
sigma² = innovation_variance * 2*theta / (1-phi²)
half_life = log(2) / theta
```

Its daily transition distribution equals the fitted AR(1), so OU is not a
fourth independent competitor. Nonstationary or negative-phi fits remain AR(1)
fits and report unavailable OU parameters rather than silently clipping phi.

## Support, metrics, and uncertainty

All compared models are scored on identical finite target/origin pairs for each
split and horizon. Missing dates are never bridged by an AR training pair.
Report candidate and scored counts, MAE, RMSE, and
`1 - RMSE_model / RMSE_persistence`. A zero baseline RMSE has undefined skill.

AR(1) Gaussian intervals use the unbiased training residual variance and
`variance_h = variance_1 * sum(phi^(2k), k=0..h-1)`. Report empirical 95%
coverage. These conditional intervals omit parameter and seasonal estimation
uncertainty and do not establish calibrated predictive coverage.

Scores are descriptive. Daily observations and overlapping h-day errors are
dependent; naive independent-sample significance tests are inappropriate.
The observational pilot supplies paired circular calendar-block percentile
skill intervals with 500 replicates, seed 42, and blocks at least 30 days and
at least the horizon. Calendar gaps remain gaps before resampling, and model
and baseline losses use the same block indices. Zero baseline loss yields an
undefined skill interval. At least two blocks are required. These intervals
assume approximate stationarity and depend on block length; trend, block-length
and boundary sensitivity, independent split replication, and final inference
remain research work. Conditional AR(p) intervals use impulse-response weights
and the fitted innovation variance, also omitting estimation uncertainty.

Residual correlations use actual calendar-lag pairs and report their counts.
The Q–Q plot and yearly test interval coverage are diagnostics, not skill tests.

## Reproduction and claims

The offline demo has a fixed seed and explicitly synthetic NetCDF metadata,
report titles, and protocol fields. It exercises the real preprocessing path,
CSV round-trip, model fitting, metrics, and figure generation. It supports
software validation only.

Observed runs preserve the input CSV SHA-256 and preprocessing sidecar in the
protocol when present. The pilot records a frozen config, runtime versions,
every monthly NOAA acquisition URL/checksum/version note, and source sizes.
Official PSL historical metadata before 2016 is accepted only for the known
OISST product; its SST equivalence to v2.1 is documented by NOAA NCEI. Later
files require v2.1 identity. NOAA service edge/date padding is cropped and
requested daily date coverage validated; recent provisional dates are refused.
Raw/derived data, fitted parameters, and generated figures remain local.
The completed pilot report describes its observed test scores and uncertainty,
with explicit limits. It does not establish model superiority across time
periods or an exact geographical Yellow Sea domain, and is not a manuscript
conclusion.
