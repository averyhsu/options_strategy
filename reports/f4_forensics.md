# F4 forensics — characterizing the zero-acceptance (Pass 2 addendum)

The zero-acceptance verdict of `reports/fingerprint_match.md` STANDS.
This phase measures three candidate explanations. Weekend-search results
are INFERENCE about what the account plausibly contained — not an
accusation. Not investment advice.

## 1. No-F4 posterior (F4 hard gate demoted)

- accepted: 164 of 16384 (eps 1.766)
- accepted-set feature medians: {"sharpe_ann": 2.2862036104738337, "weekly_wr": NaN, "max_dd": 0.07860765355815685, "mean_daily": 0.002045681548086123}
- cadence structure: median live cycles 3.0, share trading <=7 of 17 weeks 74%, share full-cadence (>=15) 4%

The family region consistent with everything EXCEPT the July crater is
dominated by SELECTIVE traders — regime-gated configs that sit out most
weeks. Full-cadence weekly trading is essentially absent from the
posterior.

| dim | accepted | identified |
|---|---|---|
| short_put_delta | [0.05178, 0.4903] med 0.2518 | plateau |
| short_call_delta | [0.06295, 0.4966] med 0.2454 | plateau |
| long_put_offset_days | [7, 56] med 25.5 | plateau |
| long_call_offset_days | [7, 56] med 44 | plateau |
| long_strike_offset | [0, 100] med 55 | plateau |
| credit_threshold_frac | [0.2002, 0.5967] med 0.4254 | plateau |
| threshold_reference | max_gain (50), scenario_r (53), width (61) | plateau |
| require_credit | False (164) | YES |
| min_credit_frac | [0.000997, 0.1992] med 0.09591 | plateau |
| regime_action | any_event (106), bull_only (12), retracement_only (7), trade_all (39) | plateau |
| ema_len | 13 (70), 21 (57), 34 (37) | plateau |
| hysteresis | 0.0 (47), 0.25 (47), 0.5 (70) | plateau |
| defense | close_side_eod (40), none (124) | plateau |
| risk_definition | margin (13), scenario (74), width (77) | plateau |
| risk_fraction | 0.1 (49), 0.15 (69), 0.2 (46) | plateau |
| strike_family | delta (104), percentile (60) | plateau |
| coverage_q_put | [0.8011, 0.9499] med 0.8802 | plateau |
| coverage_q_call | [0.8007, 0.949] med 0.878 | plateau |
| wing_family | near (70), wide (94) | plateau |
| front_dte | 14 (41), 7 (123) | plateau |
| exit_mode | exit_7dte (67), hold (97) | plateau |

## 2. Weekend inverse search (real Jul 10 -> 13 marks, $1M account)

Spot moved -0.77% over the F4 weekend (daily spot vol Jun-Jul: 0.96%). Target loss: $111,100.

```json
[
  {
    "structure": "double_diagonal_7d_front",
    "status": "candidate",
    "pnl_per_unit_fri_to_mon": -347.5,
    "units_for_f4_loss": 319.7,
    "gross_premium_at_sizing": 2985313.0,
    "premium_frac_of_account": 2.985,
    "weekend_loss_frac_of_premium": 0.037
  },
  {
    "structure": "double_diagonal_14d_front",
    "status": "candidate",
    "pnl_per_unit_fri_to_mon": -710.0,
    "units_for_f4_loss": 156.5,
    "gross_premium_at_sizing": 1561659.0,
    "premium_frac_of_account": 1.562,
    "weekend_loss_frac_of_premium": 0.071
  },
  {
    "structure": "short_strangle_7d_1pct",
    "status": "candidate",
    "pnl_per_unit_fri_to_mon": -1185.0,
    "units_for_f4_loss": 93.8,
    "gross_premium_at_sizing": 252670.0,
    "premium_frac_of_account": 0.253,
    "weekend_loss_frac_of_premium": 0.44
  },
  {
    "structure": "short_strangle_7d_2pct",
    "status": "candidate",
    "pnl_per_unit_fri_to_mon": -927.5,
    "units_for_f4_loss": 119.8,
    "gross_premium_at_sizing": 99720.0,
    "premium_frac_of_account": 0.1,
    "weekend_loss_frac_of_premium": 1.114
  },
  {
    "structure": "short_strangle_7d_4pct",
    "status": "candidate",
    "pnl_per_unit_fri_to_mon": -240.0,
    "units_for_f4_loss": 462.9,
    "gross_premium_at_sizing": 91426.0,
    "premium_frac_of_account": 0.091,
    "weekend_loss_frac_of_premium": 1.215
  },
  {
    "structure": "short_strangle_14d_1pct",
    "status": "candidate",
    "pnl_per_unit_fri_to_mon": -990.0,
    "units_for_f4_loss": 112.2,
    "gross_premium_at_sizing": 708122.0,
    "premium_frac_of_account": 0.708,
    "weekend_loss_frac_of_premium": 0.157
  },
  {
    "structure": "short_strangle_14d_2pct",
    "status": "candidate",
    "pnl_per_unit_fri_to_mon": -1120.0,
    "units_for_f4_loss": 99.2,
    "gross_premium_at_sizing": 293125.0,
    "premium_frac_of_account": 0.293,
    "weekend_loss_frac_of_premium": 0.379
  },
  {
    "structure": "short_strangle_14d_4pct",
    "status": "candidate",
    "pnl_per_unit_fri_to_mon": -735.0,
    "units_for_f4_loss": 151.2,
    "gross_premium_at_sizing": 125460.0,
    "premium_frac_of_account": 0.125,
    "weekend_loss_frac_of_premium": 0.886
  },
  {
    "structure": "short_strangle_35d_1pct",
    "status": "candidate",
    "pnl_per_unit_fri_to_mon": -395.0,
    "units_for_f4_loss": 281.3,
    "gross_premium_at_sizing": 4868711.0,
    "premium_frac_of_account": 4.869,
    "weekend_loss_frac_of_premium": 0.023
  },
  {
    "structure": "short_strangle_35d_2pct",
    "status": "candidate",
    "pnl_per_unit_fri_to_mon": -485.0,
    "units_for_f4_loss": 229.1,
    "gross_premium_at_sizing": 2764901.0,
    "premium_frac_of_account": 2.765,
    "weekend_loss_frac_of_premium": 0.04
  },
  {
    "structure": "short_strangle_35d_4pct",
    "status": "candidate",
    "pnl_per_unit_fri_to_mon": -800.0,
    "units_for_f4_loss": 138.9,
    "gross_premium_at_sizing": 793671.0,
    "premium_frac_of_account": 0.794,
    "weekend_loss_frac_of_premium": 0.14
  },
  {
    "structure": "long_straddle_4d",
    "status": "gains_on_weekend",
    "pnl_per_unit": 1570.0
  },
  {
    "structure": "long_straddle_7d",
    "status": "gains_on_weekend",
    "pnl_per_unit": 1235.0
  },
  {
    "structure": "outright_index_delta",
    "status": "candidate",
    "spot_ret_fri_to_mon": -0.00774,
    "leverage_for_f4_loss": 14.4,
    "implied_daily_vol_at_that_leverage": 0.1374,
    "consistent_with_244bp_daily_vol": false
  }
]
```

## 3. Model-gap bounds (top-50 soft-ranked, live window, Track B)

```json
{
  "n_runs": 550,
  "base_median_sharpe": 2.106501468713149,
  "best_sharpe": 5.132776257279784,
  "best_rows": [
    {
      "idx": 6961,
      "defense": "buy_back_short/t-1",
      "fill_model": "mid",
      "sharpe_live": 5.132776257279784,
      "pct_positive_live": 0.3493975903614458,
      "max_dd_live": 0.09974793364421797,
      "dd_peak_live": "2026-04-20",
      "n_weeks_traded": 18
    },
    {
      "idx": 6961,
      "defense": "buy_back_short/t-1",
      "fill_model": "optimistic",
      "sharpe_live": 5.132776257279784,
      "pct_positive_live": 0.3493975903614458,
      "max_dd_live": 0.09974793364421797,
      "dd_peak_live": "2026-04-20",
      "n_weeks_traded": 18
    },
    {
      "idx": 6961,
      "defense": "none",
      "fill_model": "mid",
      "sharpe_live": 5.102964648226375,
      "pct_positive_live": 0.3493975903614458,
      "max_dd_live": 0.09951938660046744,
      "dd_peak_live": "2026-04-20",
      "n_weeks_traded": 18
    },
    {
      "idx": 6961,
      "defense": "roll_out/immediate",
      "fill_model": "mid",
      "sharpe_live": 5.020162037318079,
      "pct_positive_live": 0.3373493975903614,
      "max_dd_live": 0.10204529124591122,
      "dd_peak_live": "2026-04-20",
      "n_weeks_traded": 18
    },
    {
      "idx": 6961,
      "defense": "roll_out_away/immediate",
      "fill_model": "mid",
      "sharpe_live": 4.962798680985744,
      "pct_positive_live": 0.3373493975903614,
      "max_dd_live": 0.12515039281189422,
      "dd_peak_live": "2026-04-20",
      "n_weeks_traded": 18
    },
    {
      "idx": 16025,
      "defense": "convert_vertical/immediate",
      "fill_model": "mid",
      "sharpe_live": 4.866873178053189,
      "pct_positive_live": 0.37349397590361444,
      "max_dd_live": 0.03425513567522753,
      "dd_peak_live": "2026-04-20",
      "n_weeks_traded": 22
    },
    {
      "idx": 16025,
      "defense": "convert_vertical/immediate",
      "fill_model": "optimistic",
      "sharpe_live": 4.866873178053189,
      "pct_positive_live": 0.37349397590361444,
      "max_dd_live": 0.03425513567522753,
      "dd_peak_live": "2026-04-20",
      "n_weeks_traded": 22
    },
    {
      "idx": 6961,
      "defense": "convert_vertical/immediate",
      "fill_model": "mid",
      "sharpe_live": 4.820774616742413,
      "pct_positive_live": 0.37349397590361444,
      "max_dd_live": 0.1055942438611378,
      "dd_peak_live": "2026-04-20",
      "n_weeks_traded": 18
    },
    {
      "idx": 1398,
      "defense": "none",
      "fill_model": "mid",
      "sharpe_live": 4.813038184494931,
      "pct_positive_live": 0.3493975903614458,
      "max_dd_live": 0.06666590085319812,
      "dd_peak_live": "2026-05-15",
      "n_weeks_traded": 22
    },
    {
      "idx": 1398,
      "defense": "none",
      "fill_model": "optimistic",
      "sharpe_live": 4.813038184494931,
      "pct_positive_live": 0.3493975903614458,
      "max_dd_live": 0.06666590085319812,
      "dd_peak_live": "2026-05-15",
      "n_weeks_traded": 22
    }
  ],
  "n_reaching_record_scalars": 0,
  "n_dd_peak_in_f4_window": 0
}
```

## 4. Sleeve sensitivity (<=1 event/week, |e| <= 1.5% NAV)

- configs evaluated: 50
- F4 magnitude reachable (base already craters >= 9.6% on some day): 1
- F11 reachable: 3
- JOINTLY reachable: 0

A sleeve bounded at 1.5% NAV per event cannot manufacture an 11.1%
single-weekend crater; it can only close the F11 (%-positive-days) gap.
