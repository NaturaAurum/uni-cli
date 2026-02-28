# uni-cli Benchmark Report Template

## 1) Run Metadata

- Date:
- Runner:
- Machine:
- OS:
- Unity version:
- Project/Scene:
- Scenario file:
- Tokenizer:

## 2) Summary Table

| Scenario | Baseline Total Tokens | Wrapper Total Tokens | Reduction % | Baseline Success % | Wrapper Success % | Baseline p95 (ms) | Wrapper p95 (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|
| S1 hierarchy 조회 |  |  |  |  |  |  |  |
| S2 object 생성 |  |  |  |  |  |  |  |
| S3 reparent |  |  |  |  |  |  |  |
| S4 asset 검색 |  |  |  |  |  |  |  |
| S5 batch 작업 |  |  |  |  |  |  |  |
| TOTAL |  |  |  |  |  |  |  |

## 3) Headline Results

- Total token reduction:
- Success-rate delta:
- Latency delta (p50/p95):

## 4) Failure Cases

- Scenario:
- Mode (`baseline` or `wrapper`):
- Error code / message:
- Repro hints:

## 5) Observations

- What worked well:
- Token saving drivers:
- Where wrapper underperformed:

## 6) Next Improvements

- Improve command surface:
- Add server-side filters:
- Add batch atomicity/rollback strategy:
- Add retries/timeouts:

