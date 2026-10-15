# 기술 가이드 요약 시스템

벤더의 방대한 기술 가이드를 목차별로 요약·번역하고, 사용자 검토를 거쳐 Word/PowerPoint 문서로 만드는 웹 서비스입니다.
기획과 설계는 [docs/PRODUCT_PLAN.md](docs/PRODUCT_PLAN.md)를 참고하세요.

현재 상태: **1단계 뼈대** (요약·번역·검토·문서 생성). 2단계(파트너 가이드 비교), 3단계(커뮤니티)는 아직 없습니다.

## 구조

```
backend/            FastAPI + SQLAlchemy (Python 3.12)
  app/
    routers/        API (인증, 관리자, 문서, 요약 가이드, 문서 생성)
    services/
      parsing/      PDF·Word·PPT·URL → 목차 트리
      llm/          요약 엔진 (mock / Claude)
      exporters/    Word·PPT 생성 (로고, 이력 관리 표, 파트너 템플릿)
      pipeline.py   Worker 작업 처리기
    worker.py       백그라운드 작업 처리 (DB 기반 큐)
  tests/            전체 흐름 + 파서 테스트
frontend/           React + TypeScript (Vite)
docs/               기획·설계 문서
```

## 처음 실행

PowerShell 기준입니다. 처음 한 번만 설치합니다.

```bash
cd backend; python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt; Copy-Item .env.example .env
```

```bash
cd frontend; npm install
```

## 개발 서버 실행

터미널 두 개에서 각각 실행합니다. `.env`의 `EMBEDDED_WORKER=true`면 API 서버 안에서 Worker도 함께 돕니다.

```bash
cd backend; .\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend; npm run dev
```

브라우저에서 http://localhost:5173 을 엽니다. 최초 관리자 계정은 `backend/.env`의 `ADMIN_EMAIL` / `ADMIN_PASSWORD`로 자동 생성됩니다.

사용 순서
1. 관리자: 벤더 도메인과 파트너사를 추가하고, 파트너사에 지원 벤더를 체크
2. 엔지니어: 가입 신청 → 관리자가 승인
3. 엔지니어: 문서 업로드 → 목차 확인(불필요 항목 제외) → 요약 시작
4. 목차 항목별로 승인 / 직접 수정 / 코멘트로 재생성 → 전 항목 승인
5. Word 또는 PowerPoint 생성 (로고·이력 관리 표 선택)

API 문서: http://localhost:8000/docs

## 테스트

```bash
cd backend; .\.venv\Scripts\python -m pytest -q
```

## 실제 요약 엔진 연결

`backend/.env`의 `LLM_PROVIDER`로 고릅니다. 바꾼 뒤에는 백엔드 서버를 재시작하세요.

| 값 | 과금 | 용도 |
|---|---|---|
| `mock` | 없음 | 화면·흐름 개발용 가짜 요약 |
| `claude_code` | 본인 Claude 구독 (Pro/Max) | **나 혼자 쓰는 동안** |
| `claude` | Claude API 사용량 | 다른 사람에게 서비스할 때 |

### 본인 구독으로 쓰기 (claude_code)

1. Claude Code 명령줄 도구를 설치합니다 (관리자 권한 불필요).

```bash
irm https://claude.ai/install.ps1 | iex
```

2. 새 PowerShell 창을 열고 `claude` 를 실행합니다. 브라우저가 열리면 구독 계정으로 로그인하고, `Login successful` 이 보이면 Enter 를 누른 뒤 `/exit` 로 나옵니다.
3. `backend/.env` 에서 `LLM_PROVIDER=claude_code`, `LLM_CONCURRENCY=2` 로 바꿉니다.
4. 연결을 확인합니다. CLI 위치, 로그인 방식(`claude.ai` 여야 구독), 짧은 요약 결과가 출력됩니다.

```bash
cd backend; .\.venv\Scripts\python -m app.services.llm.claude_code
```

알아둘 점
- 요약 한 건마다 구독 사용량이 차감됩니다. 500쪽 문서는 수십 번 호출되므로 한도에 닿으면 해당 섹션이 "실패"로 표시되고, 한도가 풀린 뒤 "코멘트로 재생성"으로 다시 돌리면 됩니다. 사용량을 아끼려면 `CLAUDE_CODE_MODEL=sonnet`.
- 환경 변수 `ANTHROPIC_API_KEY` 가 있으면 Claude Code가 구독 대신 API 키를 쓰므로, 엔진이 실행할 때 자동으로 제외합니다.
- 구독 로그인은 **본인 PC에서 본인 문서를 처리할 때만** 씁니다. 다른 사람이 이 서비스를 쓰게 되면 Anthropic 약관상 API 키(`claude`)로 바꿔야 합니다.

### Claude API로 쓰기 (claude)

API 키를 발급받은 뒤 `backend/.env`에서 다음 두 줄을 바꾸고 서버를 재시작합니다. 키는 채팅이나 저장소에 올리지 마세요.

```
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=발급받은-키
```

모델은 `claude-opus-5-5`, 요약 깊이는 `CLAUDE_EFFORT`(기본 `medium`)로 조절합니다.

## 운영 시 Worker 분리

`.env`에서 `EMBEDDED_WORKER=false`로 바꾸고 Worker를 별도 프로세스로 실행합니다.

```bash
cd backend; .\.venv\Scripts\python -m app.worker
```

## 알아둘 점

- 이 폴더는 OneDrive 동기화 폴더 안에 있습니다. `node_modules`, `.venv`, SQLite DB가 계속 동기화되어 느려지거나 DB 잠금이 생길 수 있으니, `C:\dev` 같은 동기화 밖 경로로 옮기는 것을 권장합니다.
- DB 스키마는 아직 마이그레이션 도구(Alembic) 없이 시작 시 자동 생성됩니다. 모델을 바꾸면 개발용 DB(`backend/data/app.db`)를 지우고 다시 시작하세요.
