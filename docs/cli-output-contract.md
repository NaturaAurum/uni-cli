# uni-cli CLI Output Contract (Draft v0.1)

## 1) Principles

- 기본 응답 모드는 반드시 `compact`.
- 토큰 최적화가 기본값이고, 상세 출력은 opt-in.
- list/search 계열 명령은 paging/field filtering 없이는 동작하지 않는다.

## 2) Required Flags for Collection Commands

적용 대상: hierarchy list, asset search, batch result list 등 다건 반환 명령

필수 플래그:

- `--fields`: 반환 필드 화이트리스트
- `--limit`: 페이지 크기
- `--cursor`: 페이지 위치 (`0` 허용)

동작:

- 누락 시 즉시 실패: `err code=INVALID_ARGUMENT msg=missing_required_flag`

## 3) Default Output Shape (`compact`)

성공 단건:

`ok op=<op> id=<id> [k=v ...]`

성공 다건:

`row <field1>=<value1> <field2>=<value2> ...`
`ok op=<op> count=<n> next=<cursor_or_dash> truncated=<0_or_1>`

실패:

`err code=<code> msg=<short_message>`

주의:

- stack trace, 내부 경로, 원본 payload 덤프는 기본 출력에 포함 금지
- multiline 에러는 `--verbose`일 때만 허용

## 4) Payload Guardrails

- `--limit` 최대값: 200
- compact 응답 최대 직렬화 크기: 8 KB
- 8 KB 초과 예상 시:
  - 가능하면 자동 truncate 후 `truncated=1` + `next` 반환
  - 불가하면 실패: `err code=PAYLOAD_TOO_LARGE msg=reduce_fields_or_limit`

## 5) Optional Verbosity Modes

- `--format compact` (default)
- `--format json` (디버깅/정밀 분석용)
- `--verbose` (에러 상세 추적용)

원칙:

- `json`/`verbose`는 벤치마크 기본값으로 사용 금지
- 벤치마크는 항상 compact 기준으로 수행

## 6) Batch Command Rules

- 기본 출력은 summary only
- per-item 상세는 실패 항목 최대 3개까지만 포함
- 전체 상세가 필요하면 `--verbose` 명시 필요

예시:

`ok op=batch.apply total=100 ok_count=98 fail_count=2 fail_ids=obj_019,obj_044`

