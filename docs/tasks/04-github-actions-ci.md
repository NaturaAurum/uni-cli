# Task 4: GitHub Actions CI

## 목표

PR / push 시 자동으로 lint + compile check + test 실행하는 CI 워크플로우.

## 워크플로우: `.github/workflows/ci.yml`

### 트리거

```yaml
on:
  push:
    branches: [develop, main]
  pull_request:
    branches: [develop, main]
```

### Jobs

#### Job 1: lint

```
- Python 3.12
- pip install ruff
- ruff check cli/src/ cli/tests/ bench/scripts/
- ruff format --check cli/src/ cli/tests/
```

#### Job 2: typecheck (py_compile)

```
- Python 3.12
- python3 -m py_compile로 cli/src/ 전체 .py 파일 컴파일 체크
- bench/scripts/ .py 파일도 포함
```

#### Job 3: test

```
- Python 3.10, 3.11, 3.12 매트릭스
- cd cli && pip install -e ".[test]"
- pytest --tb=short
```

### 참고

- C# 컴파일은 Unity Editor가 필요하므로 CI에서 제외 (Task 2에서 수동 검증)
- ruff 설정이 없으면 `.ruff.toml` 또는 `pyproject.toml`에 기본 설정 추가 필요

## ruff 설정 (cli/pyproject.toml에 추가)

```toml
[tool.ruff]
target-version = "py310"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "W", "I"]
```

## 완료 조건

- [ ] `.github/workflows/ci.yml` 생성
- [ ] ruff 설정 추가
- [ ] develop/main push + PR에서 CI 동작
- [ ] lint, compile, test 3개 job 모두 green
