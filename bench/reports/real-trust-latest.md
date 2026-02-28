# uni-cli Benchmark Report (Trust Run)

## Run Metadata

- Date: 2026-02-27 (local)
- Runner: `scripts/run_real_benchmark.py`
- Environment: Unity Editor `2022.3.62f2` + `mcp-for-unity-server`
- Instance: `uni-cli-bench@47cd16e15b01f9ac`
- Tokenizer: `tiktoken:o200k_base`
- Iterations: `30` per scenario/mode
- Warmup: `3`
- Repetitions: `2`

## Scenario Results (Run 1)

| Scenario | Baseline Tokens | Wrapper Tokens | Reduction % |
|---|---:|---:|---:|
| hierarchy_query | 10,680 | 1,020 | 90.45 |
| object_create | 9,420 | 1,350 | 85.67 |
| reparent | 32,940 | 1,410 | 95.72 |
| asset_search | 279,120 | 1,200 | 99.57 |
| batch_ops | 28,230 | 1,140 | 95.96 |
| TOTAL | 360,390 | 6,120 | 98.30 |

## Reliability Summary

- Overall token reduction (Run 1): **98.30%**
- 95% bootstrap CI (Run 1): **97.81% ~ 98.63%**
- Overall token reduction (Run 2): **98.30%**
- 95% bootstrap CI (Run 2): **97.82% ~ 98.63%**
- Cross-run reduction stdev: **0.0000**
- Success rate: baseline/wrapper 모두 **100%**

## Interpretation

- 절감 방향과 크기 모두 매우 안정적이며, 이번 조건에서는 wrapper CLI가 baseline 대비 토큰을 약 **98.3%** 줄였습니다.
- 신뢰구간 하한(약 97.8%) 기준으로도 절감 효과가 충분히 큽니다.
- `asset_search`, `reparent`, `batch_ops`에서 절감 효과가 특히 큽니다.

## Scope Limits

- 본 수치는 "agent-visible request/response text" 기준 토큰 절감입니다.
- 모델 내부 reasoning token, 네트워크/서버 내부 오버헤드는 포함하지 않습니다.
