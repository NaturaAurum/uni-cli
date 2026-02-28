# Task 2: Unity Editor 로드 테스트

## 목표

`com.uni-cli.tools` UPM 패키지의 4개 C# tool이 unity-mcp의 `CommandRegistry`에 자동 등록되는지 실제 Unity Editor에서 검증.

## 전제 조건

- Unity 2022.3 프로젝트 (`unity-project/`) 열린 상태
- unity-mcp MCP 서버 실행 중 (`http://127.0.0.1:8080/mcp`)
- `unity-project/Packages/manifest.json`에 `"com.uni-cli.tools": "file:../../package"` 참조 존재

## 검증 절차

### 2-1. MCP tools/list에서 새 tool 확인

```bash
# MCP tools/list 호출하여 등록된 tool 목록 확인
PYTHONPATH=cli/src python3 -m uni_cli.main tools
```

**기대 결과**: 기존 31개 tool + 아래 4개 추가:
- `manage_ui_toolkit`
- `manage_addressables`
- `manage_dots`
- `manage_shader_graph`

### 2-2. 각 tool 기본 호출 테스트

```bash
# UI Toolkit — list_documents (빈 프로젝트라도 에러 없이 응답)
PYTHONPATH=cli/src python3 -m uni_cli.main subsystem ui_toolkit list_documents

# Shader Graph — list_graphs
PYTHONPATH=cli/src python3 -m uni_cli.main subsystem shader_graph list_graphs

# Addressables — list_groups (패키지 미설치 시 "not installed" 에러 기대)
PYTHONPATH=cli/src python3 -m uni_cli.main subsystem addressables list_groups

# DOTS — list_worlds (패키지 미설치 시 "not installed" 에러 기대)
PYTHONPATH=cli/src python3 -m uni_cli.main subsystem dots list_worlds
```

### 2-3. 컴파일 에러 확인

Unity Console에 C# 컴파일 에러가 없는지 확인.

## 완료 조건

- [ ] 4개 tool이 MCP tools/list에 등록됨
- [ ] 각 tool 기본 action 호출 시 정상 응답 (또는 expected error)
- [ ] Unity Console에 컴파일 에러 없음

## 참고

- `[McpForUnityTool]` attribute가 활성화되어 있어야 함 (이전 세션에서 확인 완료)
- `CommandRegistry.Initialize()`가 모든 Editor 어셈블리를 리플렉션 스캔하여 자동 발견
- optional 패키지(Addressables, DOTS)는 미설치 시 `ErrorResponse("... not installed")` 반환이 정상
