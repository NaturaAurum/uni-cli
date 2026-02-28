# uni-cli Benchmark Report (Mock PoC)

## 1) Run Metadata

- Date: 2026-02-27 (UTC)
- Runner: `scripts/run_benchmark.py`
- Machine: local macOS (from current workspace)
- Unity version: N/A (mock execution)
- Project/Scene: N/A (mock execution)
- Scenario file: `bench/scenarios.mock.json`
- Tokenizer: `heuristic_char4` (`tiktoken` unavailable fallback)

## 2) Summary Table

| Scenario | Baseline Total Tokens | Wrapper Total Tokens | Reduction % | Baseline Success % | Wrapper Success % | Baseline p95 (ms) | Wrapper p95 (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|
| S1 hierarchy 조회 | 27,836 | 1,308 | 95.30 | 100.00 | 100.00 | 224.86 | 169.40 |
| S2 object 생성 | 1,672 | 396 | 76.32 | 100.00 | 100.00 | 173.91 | 143.96 |
| S3 reparent | 1,156 | 372 | 67.82 | 100.00 | 100.00 | 159.18 | 132.25 |
| S4 asset 검색 | 15,778 | 840 | 94.68 | 100.00 | 100.00 | 248.22 | 193.02 |
| S5 batch 작업 | 13,207 | 456 | 96.55 | 91.67 | 100.00 | 307.07 | 220.27 |
| TOTAL | 59,649 | 3,372 | 94.35 | 98.33 | 100.00 | 222.65 | 171.78 |

## 3) Headline Results

- Total token reduction: **94.35%**
- Success-rate delta: **+1.67%p** (wrapper - baseline)
- p95 latency delta: wrapper가 모든 시나리오에서 baseline보다 낮음

## 4) Failure Cases

- Scenario: `batch_ops`
- Mode: `baseline`
- Error: `BATCH_PARTIAL_FAILURE` (`2 operations failed due to duplicate names`)
- Observed failure count: 1 / 12 runs
- Note: wrapper mock path에서는 동일 구간 실패가 관찰되지 않음

## 5) Observations

- 토큰 절감의 주요 원인:
  - list/search 응답에서 verbose JSON을 compact summary로 축소
  - batch 결과를 per-item 상세 대신 summary 중심으로 반환
- 상대적으로 절감 폭이 낮은 구간:
  - `reparent`, `object_create`처럼 본래 payload가 작은 단건 명령

## 6) Next Improvements

- Real Unity 환경에서 동일 5개 시나리오 재측정 (`bench/scenarios.real.template.json` 기반)
- 토큰 카운터를 `tiktoken`으로 고정해 모델별 오차 축소
- batch 실패 케이스를 wrapper에서도 의도적으로 주입해 복구 전략(retry/rollback) 비교

