# Task 6: Release Workflow

## 목표

Git tag push 시 자동으로 PyPI에 패키지 배포하는 GitHub Actions 워크플로우.

## 릴리즈 플로우

```
develop (squash merge) → main (merge commit) → git tag v0.1.0 → push tag
  → GitHub Actions → build + publish to PyPI
  → GitHub Release 자동 생성
```

## 워크플로우: `.github/workflows/release.yml`

### 트리거

```yaml
on:
  push:
    tags: ["v*"]
```

### Steps

```yaml
jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      id-token: write          # PyPI trusted publisher
      contents: write          # GitHub Release 생성
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }

      # 1. 버전 검증 — tag와 pyproject.toml version 일치 확인
      - name: Verify version
        run: |
          TAG_VERSION=${GITHUB_REF#refs/tags/v}
          PKG_VERSION=$(python3 -c "import tomllib; print(tomllib.load(open('cli/pyproject.toml','rb'))['project']['version'])")
          if [ "$TAG_VERSION" != "$PKG_VERSION" ]; then
            echo "Tag ($TAG_VERSION) != pyproject.toml ($PKG_VERSION)"
            exit 1
          fi

      # 2. 빌드
      - run: pip install build && python3 -m build
        working-directory: cli

      # 3. PyPI 배포 (Trusted Publisher 또는 API token)
      - uses: pypa/gh-action-pypi-publish@release/v1
        with:
          packages-dir: cli/dist/

      # 4. GitHub Release 생성
      - uses: softprops/action-gh-release@v2
        with:
          generate_release_notes: true
          files: cli/dist/*
```

## PyPI Trusted Publisher 설정 (권장)

API token 대신 OIDC Trusted Publisher 사용 시:
1. https://pypi.org → "Your projects" → "Publishing" → "Add a new pending publisher"
2. Owner: `NaturaAurum`, Repo: `uni-cli`, Workflow: `release.yml`, Environment: (빈값)
3. GitHub Secrets 불필요 — OIDC로 자동 인증

## 릴리즈 절차 (수동)

```bash
# 1. develop에서 작업 완료
# 2. develop → main PR 생성 + merge (merge commit)
# 3. main checkout → version bump
git checkout main
# cli/pyproject.toml version 수정 (예: 0.1.0 → 0.2.0)
# 4. tag + push
git tag v0.2.0
git push origin v0.2.0
# → GitHub Actions가 자동으로 PyPI 배포 + Release 생성
```

## 완료 조건

- [ ] `.github/workflows/release.yml` 생성
- [ ] Tag 버전과 pyproject.toml 버전 일치 검증 로직 포함
- [ ] PyPI Trusted Publisher 또는 API token 설정
- [ ] 테스트 릴리즈 (v0.1.0) 성공
