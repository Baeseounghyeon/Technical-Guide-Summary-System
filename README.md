# 기술 가이드 요약 시스템

벤더의 방대한 기술 가이드를 목차별로 요약·번역하고, 사용자 검토를 거쳐 Word/PowerPoint 문서로 만드는 웹 서비스입니다.
기획과 설계는 [docs/PRODUCT_PLAN.md](docs/PRODUCT_PLAN.md), 처음부터 다시 만들 때 쓰는 상세 명세(프롬프트)는 [docs/REBUILD_PROMPT.md](docs/REBUILD_PROMPT.md)를 참고하세요.

현재 상태: **1단계**(요약·번역·검토·문서 생성), **2단계**(파트너 가이드 비교·오류 수정·이력), **3단계**(벤더 도메인 커뮤니티) 기본 기능이 모두 있습니다. 요약·오류 탐지는 아직 가짜 엔진으로 동작합니다.

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
6. (2단계) 요약 가이드 화면 아래 "파트너 가이드 비교"에서 파트너가 만든 가이드를 올림 → 목차 매칭 확인 → 비교 시작
   → 오류 후보별 수락 / 고쳐서 수락 / 거절(사유 필수) → 변경 추적 수정본(Word 원본만)·수정 보고서 내려받기
7. (3단계) 상단 "커뮤니티" → 소속 벤더 도메인에서 이슈 공유(해결 댓글 지정, 검색·태그)와 온라인 세션 일정(참석 표시)
   → 다른 벤더 도메인은 열람 신청 → 관리자 화면에서 기간을 정해 승인하면 그 기간 동안 읽기만 가능 (회수 가능)

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

## DB: Supabase(PostgreSQL)

기본은 SQLite(`backend/data/app.db`)이고, `backend/.env`에 `DATABASE_URL`을 넣으면 PostgreSQL을 씁니다. 지금은 Supabase(서울 리전)에 연결되어 있습니다.

1. Supabase 대시보드 → 프로젝트 → **Connect** → **Direct** → **Shared pooler** 주소를 복사합니다.
2. `backend/.env`에 `DATABASE_URL=postgresql+psycopg://postgres.프로젝트ID:비밀번호@...pooler.supabase.com:5432/postgres` 형식으로 넣습니다.
   맨 앞을 `postgresql+psycopg://`로 바꾸고, 비밀번호의 특수문자는 퍼센트 인코딩합니다(`@`→`%40`, `#`→`%23`, `%`→`%25`).
3. 서버를 시작하면 테이블이 자동으로 생기고, Supabase 공개 API로 테이블이 노출되지 않도록 모든 테이블에 RLS가 켜집니다.

기존 SQLite 데이터를 비어 있는 PostgreSQL로 옮길 때(대상에 데이터가 있으면 멈춤):

```bash
cd backend; .\.venv\Scripts\python -m app.migrate_to_postgres
```

업로드·생성 파일은 DB가 아니라 `backend/storage` 폴더에 그대로 있습니다. SQLite로 돌아가려면 `.env`의 `DATABASE_URL` 줄을 지우면 됩니다(옮긴 뒤 바뀐 데이터는 SQLite에 없음).

## 업무 구분: 엔지니어 / 영업

사용자마다 업무 구분(`track`)이 있습니다. 가입 신청 때 고르고, 관리자 화면 가입자 표의 "엔지니어 / 영업" 탭에서 확인·변경합니다(권한과 별개).

| 구분 | 메뉴 | 내용 |
|---|---|---|
| 엔지니어 | 홈 · 문서 · 가이드(가이드 공유) · 커뮤니티 · 설정 | 기술 가이드 핵심 요약 (기존 기능) |
| 영업 | 홈 · 문서 · **견적서** · 커뮤니티 | 견적서 생성(준비 중), 견적서 양식·로고 업로드, 참고 자료(규격서·제품 기능·가격표) 관리 |

최고 관리자 계정(`shbae@unipoint.co.kr`, 플랫폼 관리자)은 가이드·견적서·설정·관리자 메뉴를 모두 씁니다. 업무 구분이 영업인 플랫폼 관리자는 가이드 대신 견적서 메뉴만 봅니다.

**문서 종류:** 문서 가져오기에서 등록할 탭(벤더 규격서 / 벤더 기술 가이드 / 벤더 브로슈어)과 설명을 고릅니다.
문서 화면은 종류별 탭과 벤더 선택으로 나뉘고, 상단 "문서" 메뉴에 마우스를 올리면 세 탭으로 바로 갈 수 있습니다. 종류가 없던 기존 문서는 기술 가이드로 봅니다.

**가이드 메뉴:** 상단 "가이드"(예전 "가이드 공유")를 누르면 '벤더 기술 가이드'로 등록한 문서만 모은 "등록된 가이드" 표가 나옵니다.
벤더와 가이드 종류(기술 가이드 / 트러블 슈팅 가이드, 문서 가져오기에서 선택)로 거를 수 있고, 마우스를 올리면 "가이드 공유" 화면으로 갈 수 있습니다.

**메뉴 구성:** 홈 · 문서 · 규격서 · 가이드 · (견적서) · 브로슈어 · 커뮤니티 · 요청 · (설정 · 관리자). 각 메뉴에 마우스를 올리면 하위 메뉴가 펼쳐집니다.
- 문서: 문서 등록(종류 규격서/가이드/브로슈어 선택) / 등록한 문서(종류 탭, 벤더·등록자 선택)
- 규격서·브로슈어: 등록한 ○○ / 조직 요청 ○○(같은 조직이 등록한 문서)
- 가이드: 가이드 등록 / 등록한 가이드 / 조직 요청 가이드(같은 조직의 요약 요청, 최종 문서 받기) / 가이드 공유
- 요청: 내 요청 사항(내가 등록한 문서, 내려받기·삭제) / 권한 승인(내 도메인 권한 요청 결과, 관리자는 승인 화면) / 도메인 권한 요청

**업무 구분별 권한:** 엔지니어는 가이드(등록·요약·검토·최종 문서)와 브로슈어, 영업은 규격서·견적서와 브로슈어를 등록·수정합니다. 그 밖의 종류는 내려받기만 됩니다(관리자는 전부).
서버에서도 막고(`deps.user_permissions`), 문서 등록의 종류 선택지도 권한에 맞게 줄어듭니다. 다른 업무의 권한은 요청 > 권한 승인 요청(범위·신청자 정보·내용)으로 신청하고, 관리자 화면 "권한 승인 요청 처리"에서 승인·반려·회수합니다.
관리자 가입자 수정에서는 성명·회사명·이메일·전화번호·부서를 고치고, 도메인을 사용자별로 체크할 수 있습니다(끄면 소속 파트너사 도메인을 그대로 사용).

**열람 범위:** 내 조직 문서 + 다른 조직이 '가이드 공유'로 내 조직에 공유한 문서 + 도메인 권한 요청이 승인된 벤더의 문서(다른 조직 것 포함).
공유·열람으로 보는 문서는 읽기 전용(보기·내려받기)이고, 삭제는 올린 사람이나 관리자만 합니다. 도메인 권한 요청은 요청 일자·목적과 이름·메일·회사명(가입 정보로 미리 채움)을 받아 관리자 화면 "도메인 권한 요청 승인"에서 승인·반려합니다.
예전 '가이드 공유'(다른 파트너 가이드 다운로드 요청) 화면은 메뉴에서 빠졌고 알림 링크로만 열립니다.

**문서 표 공통:** 다운로드 아이콘을 누르면 원본 파일 또는 분석한 목차별 본문으로 만든 PowerPoint·Word·Excel·PDF 를 고를 수 있고(원본이 PDF 면 PDF 는 원본 그대로),
플랫폼 관리자는 문서를 삭제할 수 있습니다(목차·요약 가이드·생성 문서 기록도 함께 삭제). 모든 표는 머리 칸 오른쪽 경계를 끌어 열 너비를 조절합니다.
가이드 화면은 벤더·가이드 종류·파트너·작성자로 거릅니다.

**홈 달력:** 오늘·한국 공휴일(`frontend/src/holidays.ts`, 2025~2027년, 해마다 추가 필요)과 개인 일정을 보여 줍니다.
날짜를 눌러 일정(제목·목적·기간·시간·내용)을 추가하고, 목적별 색(미팅 빨강, 외근 파랑, 휴가 초록, 교육 보라, 기타 회색)으로 여러 날을 이어 표시합니다. 일정은 본인만 봅니다.

견적서 양식(.xlsx/.docx/.pptx/.pdf)과 견적서 로고는 회사별로 저장되며 엔지니어 문서용 로고·양식과 따로 관리됩니다(올리기는 회사 관리자·플랫폼 관리자).
참고 자료는 같은 회사 영업 담당자끼리 공유됩니다.

## AI 사용 비용 관리

외부 사용자가 웹에서 문서를 많이 넣어도 비용이 통제되도록 다음을 적용했습니다.

**한 번 요약할 때의 비용 줄이기**
- 모델은 요약 본문 하나만 씁니다. 절차·주의사항 목록은 본문의 번호 목록과 `> ⚠` 줄에서 코드로 뽑습니다(같은 내용을 두 번 쓰지 않음).
- 요약·개요는 `CLAUDE_SUMMARY_EFFORT=low`, 정확도가 중요한 오류 탐지·목차 매칭은 `CLAUDE_EFFORT=medium`.
- PDF의 쪽마다 반복되는 머리말·꼬리말(문서명·저작권·쪽 번호)은 요약 전에 지웁니다.
- 같은 문서를 같은 언어로 다시 요약할 수 없습니다(기존 가이드에서 이어서 검토).

**사용 한도** (플랫폼 관리자는 회사·재생성 한도에서 제외, 전체 예산은 적용)

| 설정 | 기본값 | 내용 |
|---|---|---|
| `DEFAULT_MONTHLY_PAGE_QUOTA` | 300 | 회사별 월 처리량(쪽). 관리자 화면에서 회사별로 바꿀 수 있음 |
| `CHARS_PER_PAGE` | 2000 | 원문 2,000자 = 1쪽으로 계산 |
| `DAILY_REGENERATE_LIMIT` | 30 | 사용자별 하루 '코멘트로 재생성' 횟수 |
| `MONTHLY_BUDGET_USD` | 0(제한 없음) | 전체 월 예산(달러). 실제 토큰으로 계산한 비용이 넘으면 모든 AI 요청을 막음 |

문서 화면은 요약 전에 예상 사용량과 남은 양을 보여 주고, 관리자 화면 "AI 사용량 · 회사별 한도"에서 이번 달 비용과 회사별 사용량을 봅니다.
Anthropic 콘솔(Limits)의 월 사용 한도도 함께 걸어 두면 이중으로 막을 수 있습니다.

## Vercel 배포 (화면 + 서버)

화면(React)은 정적 파일로, 서버(FastAPI)는 Python 함수(`api/index.py`)로 한 프로젝트에 올라갑니다. 설정은 `vercel.json`.
Vercel 함수는 상주하지 않으므로 다음처럼 동작합니다.

- **파일:** Supabase Storage 비공개 버킷(`techguide`)에 저장. 업로드는 브라우저가 저장소로 직접 올리고(요청 크기 4.5MB 제한 회피), 다운로드는 5분짜리 서명 주소로 받습니다.
- **작업(파싱·요약·문서 생성):** 작업을 등록한 응답에 `X-Jobs-Queued` 헤더가 붙으면 화면이 `/api/jobs/kick`을 호출해 처리를 시작합니다.
  한 번에 `JOB_TIME_BUDGET_SECONDS`(240초)만 처리하고, 남으면 `/api/jobs/run`을 다시 불러 이어 갑니다. 끊겨도 Supabase pg_cron이 1분마다 `/api/jobs/run`을 불러 이어서 처리합니다.
- **지역:** 함수는 서울(`icn1`)에서 실행되어 Supabase(서울)와 가깝습니다.

### Vercel 환경 변수 (Project Settings → Environment Variables)

| 이름 | 값 |
|---|---|
| `DATABASE_URL` | Supabase **Transaction pooler**(포트 6543) 주소, `postgresql+psycopg://...` 형식 |
| `JWT_SECRET` | 32자 이상 임의 문자열 (로컬 `.env`의 `VERCEL_JWT_SECRET` 값) |
| `STORAGE_BACKEND` | `supabase` |
| `SUPABASE_URL` | `https://프로젝트ID.supabase.co` |
| `SUPABASE_SERVICE_KEY` | Supabase secret 키 (`sb_secret_...`) |
| `LLM_PROVIDER` | `claude` |
| `ANTHROPIC_API_KEY` | Claude API 키 |
| `LLM_CONCURRENCY` | `4` |
| `JOB_TIME_BUDGET_SECONDS` | `240` |
| `CRON_SECRET` | 임의 문자열 (로컬 `.env`의 `CRON_SECRET`과 같은 값) |
| `MONTHLY_BUDGET_USD` | 전체 월 예산(달러), 예: `30` |

`ADMIN_EMAIL`/`ADMIN_PASSWORD`는 넣지 않습니다(관리자 계정이 이미 DB에 있음). 구독 엔진(`claude_code`)은 Vercel에서 실행되지 않습니다.

### 배포 후 한 번: 1분 예약 작업 등록

```bash
cd backend; .\.venv\Scripts\python -m app.setup_cron https://배포주소.vercel.app
```

### 기존 PC 파일을 저장소로 옮기기 (한 번)

```bash
cd backend; .\.venv\Scripts\python -m app.migrate_files_to_storage
```

## 운영 시 Worker 분리

`.env`에서 `EMBEDDED_WORKER=false`로 바꾸고 Worker를 별도 프로세스로 실행합니다.

```bash
cd backend; .\.venv\Scripts\python -m app.worker
```

## 알아둘 점

- 이 폴더는 OneDrive 동기화 폴더 안에 있습니다. `node_modules`, `.venv`, SQLite DB가 계속 동기화되어 느려지거나 DB 잠금이 생길 수 있으니, `C:\dev` 같은 동기화 밖 경로로 옮기는 것을 권장합니다.
- DB 스키마는 아직 마이그레이션 도구(Alembic) 없이 시작 시 자동 생성되고, 모델에 새로 생긴 nullable 컬럼만 자동으로 추가됩니다. 컬럼 형식 변경·삭제는 직접 처리해야 합니다.
