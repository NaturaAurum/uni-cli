# Task 5: PyPI 배포 준비

## 목표

`pip install uni-cli`로 설치 가능하도록 패키지 빌드 검증 + PyPI 업로드 준비.

## 검증 항목

### 5-1. pyproject.toml 완성도

현재 상태 확인 필요:

| 필드 | 현재 | 필요 작업 |
|------|------|----------|
| name | `uni-cli` | ✅ |
| version | `0.1.0` | ✅ |
| description | 있음 | ✅ |
| readme | `README.md` | ⚠️ cli/README.md 없음 — 루트 README 참조 불가 (wheel 빌드 시 포함 안됨) |
| license | `MIT` | ✅ |
| requires-python | `>=3.10` | ✅ |
| dependencies | `[]` | ✅ (stdlib only) |
| project.urls | 없음 | 추가 필요 (Homepage, Repository, Issues) |

### 5-2. CLI 전용 README

`cli/README.md` 생성 필요 — PyPI 페이지에 표시될 내용.
루트 README에서 CLI 관련 부분만 추출하거나, 별도 간결한 버전 작성.

### 5-3. 로컬 빌드 테스트

```bash
cd cli
pip install build
python3 -m build          # dist/ 에 .whl + .tar.gz 생성
pip install dist/uni_cli-0.1.0-py3-none-any.whl
uni-cli --help            # 정상 동작 확인
pip uninstall uni-cli
```

### 5-4. project.urls 추가

```toml
[project.urls]
Homepage = "https://github.com/NaturaAurum/uni-cli"
Repository = "https://github.com/NaturaAurum/uni-cli"
Issues = "https://github.com/NaturaAurum/uni-cli/issues"
```

### 5-5. PyPI 계정 준비

- https://pypi.org 계정 + API token 생성
- GitHub Secrets에 `PYPI_API_TOKEN` 등록 (Task 6에서 사용)

## 완료 조건

- [ ] `python3 -m build` 성공
- [ ] 빌드된 wheel 설치 후 `uni-cli --help` 정상 동작
- [ ] `cli/README.md` 존재 (PyPI 페이지용)
- [ ] `project.urls` 추가
- [ ] PyPI API token 준비 (수동)
