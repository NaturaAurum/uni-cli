# uni-cli Benchmark Report (Real MCP Run)

## 1) Run Metadata

- Date: 2026-02-27 (local)
- Runner: `scripts/run_benchmark.py`
- Unity version: `2022.3.62f2`
- Target instance: `uni-cli@eed8461035005b2a`
- Scenario file: `bench/scenarios.real.json`
- Tokenizer: `heuristic_char4` (`tiktoken` fallback)
- Notes:
  - 실측은 active instance `uni-cli` 대상으로 수행
  - baseline/wrapper 모두 동일한 MCP tool 호출 결과를 사용, wrapper는 compact 출력 규약으로 요약

## 2) Summary Table

| Scenario | Baseline Total Tokens | Wrapper Total Tokens | Reduction % | Baseline Success % | Wrapper Success % | Baseline p95 (ms) | Wrapper p95 (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|
| S1 hierarchy 조회 | 9,400 | 160 | 98.30 | 100.00 | 100.00 | 85.3 | 88.3 |
| S2 object 생성 | 1,140 | 180 | 84.21 | 100.00 | 100.00 | 81.7 | 79.8 |
| S3 reparent | 3,390 | 205 | 93.95 | 100.00 | 100.00 | 131.3 | 129.5 |
| S4 asset 검색 | 36,935 | 170 | 99.54 | 100.00 | 100.00 | 248.9 | 244.5 |
| S5 batch 작업 | 3,470 | 175 | 94.96 | 100.00 | 100.00 | 71.3 | 70.4 |
| TOTAL | 54,335 | 890 | 98.36 | 100.00 | 100.00 | 123.7 | 122.5 |

## 3) Headline Results

- Total token reduction: **98.36%**
- Success-rate delta: **0.00%p** (wrapper - baseline)
- p95 latency delta: wrapper가 baseline과 유사(전체 평균 p95 123.7ms -> 122.5ms)

## 4) Failure Cases

- 없음 (baseline/wrapper 모두 100% 성공)

## 5) Observations

- 가장 큰 절감 구간:
  - `asset_search` (대량 payload를 compact summary로 축약)
  - `hierarchy_query` (트리 구조 상세 JSON 대신 count/next 중심 응답)
- 상대적으로 절감률이 낮은 구간:
  - `object_create` (원래 payload가 단건이라 절감 여지가 제한적)

## 6) Next Improvements

- `heuristic_char4` 대신 `tiktoken` 고정으로 모델별 토큰 집계 정밀도 향상
- wrapper compact 출력에 `fields` 기반 선택적 상세 옵션 추가
- 동일 시나리오 반복 수(예: 30회) 확대로 p95/p99 안정화

