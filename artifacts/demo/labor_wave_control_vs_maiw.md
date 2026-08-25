# Counterfactual Evaluation — labor_constraint_wave_risk

> Deterministic Counterfactual Simulation — same seed, same disruption, MAIW intervention vs no intervention

Evaluated: 2026-08-25T05:26:18.201162+00:00  
Scenario: `labor_constraint_wave_risk`  
Horizon: 1800s (30 sim-min)  

## OUTCOME SUMMARY
```
CONTROL
  Recovery         : not reached within 1800s horizon
  Peak backlog     : 5
  Wave compl @300s : None

MAIW
  Recovery         : 300.0s (5.0 sim-min)
  Peak backlog     : 3
  Wave compl @300s : None
  MAIW cycles      : 6

DELTA
  Recovery time    : MAIW recovered; Control did not
  Backlog AUC      : 92.0% reduction with MAIW
  Wave risk AUC    : 86.7% reduction with MAIW
```

## KPI AT FIXED HORIZONS
```
 horizon                     metric     control        maiw
────────────────────────────────────────────────────────────
    300s            pending_backlog           —           —
                    wave_risk_score           —           —
                  wave_completion %           —           —
                  throughput (u/hr)           —           —
                     proj_service %           —           —

    600s            pending_backlog           —           —
                    wave_risk_score           —           —
                  wave_completion %           —           —
                  throughput (u/hr)           —           —
                     proj_service %           —           —

    900s            pending_backlog           —           —
                    wave_risk_score           —           —
                  wave_completion %           —           —
                  throughput (u/hr)           —           —
                     proj_service %           —           —

   1200s            pending_backlog           —           —
                    wave_risk_score           —           —
                  wave_completion %           —           —
                  throughput (u/hr)           —           —
                     proj_service %           —           —

   1800s            pending_backlog           —           —
                    wave_risk_score           —           —
                  wave_completion %           —           —
                  throughput (u/hr)           —           —
                     proj_service %           —           —

```

## CONTROL TRAJECTORY
```
tick  elapsed   risk_lv  risk_sc  backlog  wave_%  recov
────────────────────────────────────────────────────────────
   1  +  5460s      CRIT     95.0        5    0.0%
   2  +  5520s      CRIT     95.0        5    0.0%
   3  +  5580s      CRIT     95.0        5    0.0%
   4  +  5640s      CRIT     95.0        5    0.0%
   5  +  5700s      CRIT     95.0        5   28.6%
   6  +  5760s      CRIT     95.0        5   28.6%
   7  +  5820s      CRIT     95.0        5   28.6%
   8  +  5880s      CRIT     95.0        5   28.6%
   9  +  5940s      CRIT     95.0        5   28.6%
  10  +  6000s      CRIT     95.0        5   28.6%
  11  +  6060s      CRIT     95.0        5   28.6%
  12  +  6120s      CRIT     95.0        5   28.6%
  13  +  6180s      CRIT     95.0        5   28.6%
  14  +  6240s      CRIT     95.0        5   28.6%
  15  +  6300s      CRIT     95.0        5   28.6%
  16  +  6360s      CRIT     95.0        5   28.6%
  17  +  6420s      CRIT     95.0        5   28.6%
  18  +  6480s      CRIT     95.0        5   28.6%
  19  +  6540s      CRIT     95.0        5   28.6%
  20  +  6600s      CRIT     95.0        5   28.6%
  21  +  6660s      CRIT     95.0        5   28.6%
  22  +  6720s      CRIT     95.0        5   28.6%
  23  +  6780s      CRIT     95.0        5   28.6%
  24  +  6840s      CRIT     95.0        5   28.6%
  25  +  6900s      CRIT     95.0        5   28.6%
  26  +  6960s      CRIT     95.0        5   28.6%
  27  +  7020s      CRIT     95.0        5   28.6%
  28  +  7080s      CRIT     95.0        5   28.6%
  29  +  7140s      CRIT     95.0        5   28.6%
  30  +  7200s      CRIT     95.0        5   28.6%
```

## MAIW TRAJECTORY
```
tick  elapsed   risk_lv  risk_sc  backlog  wave_%  recov
────────────────────────────────────────────────────────────
   1  +  5460s      CRIT     95.0        3    0.0% [c2]
   2  +  5520s      CRIT     95.0        3    0.0% [c3]
   3  +  5580s      CRIT     95.0        3    0.0% [c4]
   4  +  5640s      CRIT     95.0        3    0.0% [c5]
   5  +  5700s      NONE      0.0        0   57.1% [c6]
   6  +  5760s      NONE      0.0        0   57.1% ◀
   7  +  5820s      NONE      0.0        0   71.4%
```

---
*Evaluation wall time: 20.4s*