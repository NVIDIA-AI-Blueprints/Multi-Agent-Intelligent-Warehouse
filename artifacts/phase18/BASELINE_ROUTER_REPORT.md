# Baseline Router Report — Phase 18C

## Evaluation Identity

| Field | Value |
|-------|-------|
| Phase | 18C |
| Dataset | `eval-fixture-dataset-v1` |
| Semantic Checksum | `fixture-checksum-abc123` |
| Run Timestamp | 2026-09-12T01:02:13.314783+00:00 |
| Deployment Mode | nvidia_hosted |
| Endpoint Status | LIVE — deployment_mode=nvidia_hosted |
| Cases | 3 |

## Candidate Models

- `nvidia/nemotron-3-super-120b-a12b`
- `nvidia/nemotron-3.5-lightning-30b-a3b`

## Case Results

### Case: `wave17-labor-risk-v1`

**Prompt:** Why is Wave 17 at risk? Based on the current labor allocation and shift assignments, what is the primary bottleneck and ...

**Task family:** ASK

**Router selected:** `nvidia/nemotron-3-super-120b-a12b` via rule `high_reasoning`

| Model | Quality | Latency | Pass | Error |
|-------|---------|---------|------|-------|
| `nvidia/nemotron-3-super-120b-a12b` | 0.40 | 2515ms | NO |  |

**Oracle:**
- Best quality: `nvidia/nemotron-3-super-120b-a12b` (score=0.40)
- Fastest passing: `None` (0ms)
- Lowest cost: unavailable (no pricing metadata)

**Router regret:**
- Quality regret: none
- Latency regret: none

### Case: `equipment-failure-v1`

**Prompt:** Is equipment contributing to the delay in Wave 17? Check the conveyor system and forklift status and explain whether any...

**Task family:** ASK

**Router selected:** `nvidia/nemotron-3-super-120b-a12b` via rule `high_reasoning`

| Model | Quality | Latency | Pass | Error |
|-------|---------|---------|------|-------|
| `nvidia/nemotron-3-super-120b-a12b` | 0.80 | 2348ms | NO |  |

**Oracle:**
- Best quality: `nvidia/nemotron-3-super-120b-a12b` (score=0.80)
- Fastest passing: `None` (0ms)
- Lowest cost: unavailable (no pricing metadata)

**Router regret:**
- Quality regret: none
- Latency regret: none

### Case: `healthy-baseline-v1`

**Prompt:** Analyze the current operational state of Wave 17. Is the wave on track? Are there any issues that require intervention?...

**Task family:** ANALYZE

**Router selected:** `nvidia/nemotron-3-super-120b-a12b` via rule `medium_reasoning`

| Model | Quality | Latency | Pass | Error |
|-------|---------|---------|------|-------|
| `nvidia/nemotron-3.5-lightning-30b-a3b` | 0.50 | 48570ms | NO |  |
| `nvidia/nemotron-3-super-120b-a12b` | 0.50 | 1447ms | NO |  |

**Oracle:**
- Best quality: `nvidia/nemotron-3-super-120b-a12b` (score=0.50)
- Fastest passing: `None` (0ms)
- Lowest cost: unavailable (no pricing metadata)

**Router regret:**
- Quality regret: none
- Latency regret: none

## Findings

See individual case results above for per-case quality, latency, and regret analysis.

Nano (low-risk ASK) and Super (high-risk ANALYZE) findings are reported per case.

## Decision Gate

**CURRENT ROUTER SUFFICIENT**

