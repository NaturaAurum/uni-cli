# Task 3: CLI 테스트 코드

## 목표

`cli/` Python 패키지에 pytest 기반 테스트 추가. 라이브 MCP 서버 없이 mock으로 동작.

## 테스트 범위

### 3-1. formatter/compact.py 테스트

| 케이스 | 입력 | 기대 출력 |
|--------|------|----------|
| Collection (hierarchy ls) | `{"result": [{"id": 1, "name": "Camera"}]}` | `row id=1 name="Camera"\nok op=hierarchy.ls count=1 ...` |
| Single item (object create) | `{"instanceId": 123, "name": "Cube"}` | `ok op=object.create id=123 name="Cube"` |
| Empty collection | `{"result": []}` | `ok op=... count=0 ...` |
| Error response | `{"error": "Not found"}` | `err op=... message="Not found"` |
| 특수문자 (공백, 따옴표) | name에 `"My Object"` | 따옴표 이스케이프 확인 |

### 3-2. transport/mcp_client.py 테스트

| 케이스 | 검증 내용 |
|--------|----------|
| JSON-RPC 요청 포맷 | `{"jsonrpc": "2.0", "method": "tools/call", "id": N, "params": {...}}` |
| 세션 ID 관리 | 첫 응답의 `mcp-session-id` 헤더를 이후 요청에 포함 |
| 시퀀스 번호 | 요청마다 id 증가 |
| McpError 발생 | JSON-RPC error code 시 McpError raise |
| Instance resolution | prefix match, name match, fallback 로직 |

mock: `unittest.mock.patch("urllib.request.urlopen")` — stdlib 범위 내.

### 3-3. commands/ 테스트

| 모듈 | 테스트 |
|------|--------|
| hierarchy.py | `run_ls()` → `client.call_tool("manage_hierarchy", {...})` 호출 확인 |
| object.py | `run_create()`, `run_delete()` → 올바른 params 전달 확인 |
| asset.py | `run_search()` → filter_type, search_pattern 전달 확인 |
| batch.py | `run_apply()` → operations list 전달 확인 |
| subsystem.py | `run_call()` → `manage_<subsystem>` tool name 생성 확인 |

### 3-4. main.py 테스트

| 케이스 | 검증 내용 |
|--------|----------|
| argparse | `hierarchy ls --limit 10` → 올바른 namespace |
| dispatch | command + action → 올바른 함수 호출 |
| format flag | `--format json` → JSON 출력, default → compact |

## 파일 구조

```
cli/
├── tests/
│   ├── __init__.py
│   ├── conftest.py            # shared fixtures (mock client, sample responses)
│   ├── test_formatter.py      # 3-1
│   ├── test_transport.py      # 3-2
│   ├── test_commands.py       # 3-3
│   └── test_main.py           # 3-4
└── pyproject.toml             # [project.optional-dependencies] test = ["pytest>=7.0"]
```

## pyproject.toml 변경

```toml
[project.optional-dependencies]
test = ["pytest>=7.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

## 완료 조건

- [ ] `cd cli && pip install -e ".[test]" && pytest` 통과
- [ ] 라이브 MCP 서버 없이 전체 테스트 실행 가능
- [ ] 커버리지: formatter, transport, commands, main 모두 포함
