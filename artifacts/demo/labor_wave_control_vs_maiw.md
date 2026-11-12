# Counterfactual Evaluation — labor_constraint_wave_risk

> Deterministic Counterfactual Simulation — same seed, same disruption, MAIW intervention vs no intervention

Evaluated: 2026-11-12T18:18:17.927601+00:00  
Scenario: `labor_constraint_wave_risk`  
Horizon: 1800s (30 sim-min)  

## OUTCOME SUMMARY
```
CONTROL
  Recovery         : not reached within 1800s horizon
  Peak backlog     : 42
  Wave compl @300s : 25.0

MAIW
  Recovery         : 180.0s after the disruption (3.0 sim-min)
  Peak backlog     : 40
  Wave compl @300s : 25.8
  MAIW cycles      : 10

DELTA
  Recovery time    : MAIW recovered; Control did not
  Backlog AUC      : 46.8% reduction with MAIW
  Wave risk AUC    : 90.0% reduction with MAIW
  AUC window       : first 30 ticks of both runs
```

## KPI AT FIXED HORIZONS
```
 horizon                     metric     control        maiw
────────────────────────────────────────────────────────────
    300s            pending_backlog          28          22
                    wave_risk_score        95.0         0.0
                  wave_completion %        25.0        25.8
                  throughput (u/hr)        30.0        31.0
                     proj_service %       100.0       100.0

    600s            pending_backlog           6           0
                    wave_risk_score        95.0         0.0
                  wave_completion %        82.5        87.5
                  throughput (u/hr)        99.0       105.0
                     proj_service %       100.0       100.0

    900s            pending_backlog           5           0
                    wave_risk_score        95.0         0.0
                  wave_completion %        95.8       100.0
                  throughput (u/hr)       115.0       120.0
                     proj_service %       100.0       100.0

   1200s            pending_backlog           5           0
                    wave_risk_score        95.0         0.0
                  wave_completion %        95.8       100.0
                  throughput (u/hr)       115.0       120.0
                     proj_service %       100.0       100.0

   1800s            pending_backlog           5           0
                    wave_risk_score        95.0         0.0
                  wave_completion %        95.8       100.0
                  throughput (u/hr)       115.0       120.0
                     proj_service %         0.0       100.0

```

## CONTROL TRAJECTORY
```
tick  scenario   risk_lv  risk_sc  backlog  wave_%  recov
────────────────────────────────────────────────────────────
   1  +     60s      CRIT     95.0       42    0.0%
   2  +    120s      CRIT     95.0       42    0.0%
   3  +    180s      CRIT     95.0       42    0.0%
   4  +    240s      CRIT     95.0       28   24.2%
   5  +    300s      CRIT     95.0       28   25.0%
   6  +    360s      CRIT     95.0       19   46.7%
   7  +    420s      CRIT     95.0       12   65.0%
   8  +    480s      CRIT     95.0       12   65.0%
   9  +    540s      CRIT     95.0       10   74.2%
  10  +    600s      CRIT     95.0        6   82.5%
  11  +    660s      CRIT     95.0        6   82.5%
  12  +    720s      CRIT     95.0        5   88.3%
  13  +    780s      CRIT     95.0        5   90.0%
  14  +    840s      CRIT     95.0        5   90.0%
  15  +    900s      CRIT     95.0        5   95.8%
  16  +    960s      CRIT     95.0        5   95.8%
  17  +   1020s      CRIT     95.0        5   95.8%
  18  +   1080s      CRIT     95.0        5   95.8%
  19  +   1140s      CRIT     95.0        5   95.8%
  20  +   1200s      CRIT     95.0        5   95.8%
  21  +   1260s      CRIT     95.0        5   95.8%
  22  +   1320s      CRIT     95.0        5   95.8%
  23  +   1380s      CRIT     95.0        5   95.8%
  24  +   1440s      CRIT     95.0        5   95.8%
  25  +   1500s      CRIT     95.0        5   95.8%
  26  +   1560s      CRIT     95.0        5   95.8%
  27  +   1620s      CRIT     95.0        5   95.8%
  28  +   1680s      CRIT     95.0        5   95.8%
  29  +   1740s      CRIT     95.0        5   95.8%
  30  +   1800s      CRIT     95.0        5   95.8%
```

## MAIW TRAJECTORY
```
tick  scenario   risk_lv  risk_sc  backlog  wave_%  recov
────────────────────────────────────────────────────────────
   1  +     60s      CRIT     95.0       40    0.0% [c2]
   2  +    120s      CRIT     95.0       39    0.0% [c3]
   3  +    180s      CRIT     95.0       38    0.0% [c4]
   4  +    240s      NONE      0.0       23   24.2% [c5]
   5  +    300s      NONE      0.0       22   25.8% [c6] ◀
   6  +    360s      NONE      0.0       12   48.3% [c7]
   7  +    420s      NONE      0.0        4   69.2% [c8]
   8  +    480s      NONE      0.0        3   69.2% [c9]
   9  +    540s      NONE      0.0        1   79.2% [c10]
  10  +    600s      NONE      0.0        0   87.5%
  11  +    660s      NONE      0.0        0   89.2%
  12  +    720s      NONE      0.0        0   95.0%
  13  +    780s      NONE      0.0        0   96.7%
  14  +    840s      NONE      0.0        0   98.3%
  15  +    900s      NONE      0.0        0  100.0%
  16  +    960s      NONE      0.0        0  100.0%
  17  +   1020s      NONE      0.0        0  100.0%
  18  +   1080s      NONE      0.0        0  100.0%
  19  +   1140s      NONE      0.0        0  100.0%
  20  +   1200s      NONE      0.0        0  100.0%
  21  +   1260s      NONE      0.0        0  100.0%
  22  +   1320s      NONE      0.0        0  100.0%
  23  +   1380s      NONE      0.0        0  100.0%
  24  +   1440s      NONE      0.0        0  100.0%
  25  +   1500s      NONE      0.0        0  100.0%
  26  +   1560s      NONE      0.0        0  100.0%
  27  +   1620s      NONE      0.0        0  100.0%
  28  +   1680s      NONE      0.0        0  100.0%
  29  +   1740s      NONE      0.0        0  100.0%
  30  +   1800s      NONE      0.0        0  100.0%
```

---
*Evaluation wall time: 289.9s*