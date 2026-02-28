# uni-cli Benchmark Design

## 1) Goal

`unity-mcp` direct usage 대비 `agent-optimized wrapper CLI`가 얼마나 토큰을 줄이는지 정량화한다.

핵심 질문:

- 동일 작업에서 총 토큰(input + output)이 얼마나 절감되는가?
- 성공률/지연시간이 희생되지 않는가?

## 2) Comparison Target

- Baseline: direct MCP tool call flow (우선 검토 대상: `CoplayDev/unity-mcp`)
- Candidate: same bridge 위에 얹은 `uni-cli` wrapper

주의:

- Unity/프로젝트/씬/머신은 baseline과 wrapper에서 동일해야 한다.
- 각 시나리오의 기능적 기대 결과(assertion)는 동일해야 한다.

## 3) Scenarios (Required 5)

| ID | Scenario | Baseline Intent | Wrapper Intent | Success Condition |
|---|---|---|---|---|
| S1 | hierarchy 조회 | hierarchy 목록 조회 | compact 목록 조회 | 최소 1개 노드 반환 + exit 0 |
| S2 | object 생성 | GameObject 생성 호출 | create 명령 | 생성된 object id 반환 + exit 0 |
| S3 | reparent | 부모 변경 호출 | reparent 명령 | parentId 변경 확인 + exit 0 |
| S4 | asset 검색 | asset DB 검색 | fields 제한 검색 | limit 이내 결과 + cursor 반환 |
| S5 | batch 작업 | 다중 create/move 호출 | batch apply 명령 | 요약 결과 반환 + 실패 항목 집계 |

## 4) Metrics

필수 지표:

- `total_tokens`: input_tokens + output_tokens
- `success_rate`: 성공 실행 / 전체 실행
- `latency_ms`: p50, p95, max

보조 지표:

- `input_tokens`, `output_tokens` 분리
- 실패 케이스별 에러 코드 빈도

## 5) Measurement Method

실행 원칙:

- Warmup 후 측정: 기본 warmup 3회
- 측정 반복: 시나리오당 기본 30회
- Timeout: 기본 20초 (초과 시 실패 처리)

토큰 카운트:

- 1순위: `tiktoken` (`o200k_base`)로 문자열 길이 측정
- 폴백: 휴리스틱 `ceil(chars / 4)`

입력/출력 정의:

- 입력: agent가 전송한 요청 문자열(`request_text`)
- 출력: 명령 stdout + stderr

## 6) Analysis Rules

토큰 절감률:

`token_reduction_pct = (baseline_total - wrapper_total) / baseline_total * 100`

판정 기준(초안):

- `token_reduction_pct >= 30%`
- `success_rate`는 baseline 대비 동등 이상 (또는 -1%p 이내)
- `latency_p95` 악화가 20% 미만

## 7) Artifacts

- 실행기: `scripts/run_benchmark.py`
- Mock 시나리오: `bench/scenarios.mock.json`
- Real 시나리오 템플릿: `bench/scenarios.real.template.json`
- 리포트 템플릿: `docs/result-report-template.md`

