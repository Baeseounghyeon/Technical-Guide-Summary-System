# 재구축 프롬프트 (unipoint 벤더 기술 가이드 요약 시스템)

> 작성일: 2026-10-15 · 기준 커밋: 이 문서가 들어간 커밋 (GitHub: Baeseounghyeon/Technical-Guide-Summary-System)

## 이 문서 사용법 (프롬프트에 포함하지 않음)

- **상황 A — 폴더나 GitHub 저장소가 남아 있다:** 아래 프롬프트를 쓸 필요 없이, Claude Code에서 그 폴더를 열고
  "`docs/REBUILD_PROMPT.md`와 `README.md`를 읽고 이 프로젝트를 이어서 작업해줘"라고만 하면 됩니다.
- **상황 B — 코드가 모두 사라졌다:** Claude Code(Pro 이상)에서 빈 폴더를 열고, 아래 `===== 프롬프트 시작 =====`부터
  `===== 프롬프트 끝 =====`까지를 그대로 붙여 넣습니다. 한 번에 다 만들기보다 프롬프트 안의 "만드는 순서"대로 단계별로 진행하게 됩니다.
- 로고 이미지(`unipoint-logo.png`)는 프롬프트로 전달되지 않으므로 함께 첨부하세요. 원본은 흰 배경의 unipoint 로고(409×118)입니다.

---

===== 프롬프트 시작 =====

너는 이 프로젝트의 개발자다. 아래 명세대로 "벤더 기술 가이드 요약 시스템" 웹 서비스를 처음부터 만든다.
나와는 **항상 한국어로** 대화한다(버튼·메시지가 영어로 와도 한국어로 답한다). 화면 문구, 코드 주석, 커밋 메시지도 한국어로 쓴다.
결정이 필요한 부분은 이 명세를 따르고, 명세에 없는 것만 나에게 질문한다.

## 1. 제품 개요

- **목적:** 수백 쪽짜리 벤더(제조사) 기술 가이드를 목차별 핵심 내용으로 요약·번역하고, 사용자 검토(피드백 필수)를 거쳐
  파트너사 양식의 Word/PowerPoint 문서로 만든다. 파트너사가 따로 만든 가이드의 오류를 벤더 원본과 비교해 찾고 수정 이력을 관리한다.
  같은 벤더를 지원하는 파트너사끼리 커뮤니티와 가이드 공유를 한다.
- **제공자:** 유니포인트(unipoint). 화면 디자인은 www.unipoint.co.kr 홈페이지 스타일을 따른다(9절).
- **사용 형태:** 웹 서비스(멀티 테넌트). 지금은 운영자 PC(Windows)에서 혼자 쓰는 개발 단계.

### 용어
- **벤더 = 도메인:** 기술 가이드 원본을 만든 제조사. 데이터 접근 경계의 기본 단위.
- **파트너사:** 벤더 제품을 지원하는 회사. 여러 벤더 도메인에 속할 수 있다(파트너사 ↔ 벤더 다대다).
- **원본 문서 / 요약 가이드 / 파트너 가이드 / 최종 문서(export)**.

### 역할
| 역할 | 권한 |
|---|---|
| platform_admin (플랫폼 관리자) | 모든 데이터, 가입 승인·수정·삭제, 파트너사·벤더 관리, 열람 신청 처리. 모든 벤더 도메인의 소속으로 취급 |
| partner_admin (파트너 관리자) | 자기 파트너사 로고·양식·용어집 관리, 자사 가이드 다운로드 요청 승인 |
| engineer (엔지니어) | 자기 파트너사·도메인 안에서 문서 업로드·요약·검토·문서 생성, 커뮤니티 |

## 2. 기술 스택과 실행 환경

- OS: Windows 10/11, PowerShell. Python 3.12, Node.js LTS(24), Git — 없으면 winget으로 설치
  (`winget install --id Python.Python.3.12 -e --source winget --scope user`, `OpenJS.NodeJS.LTS`, `Git.Git`).
  설치 직후에는 PATH가 새 셸에만 반영되므로 명령 실행 시 `$env:Path = Machine PATH + User PATH`로 갱신해서 쓴다.
- **백엔드:** FastAPI, SQLAlchemy 2(Mapped 타입), pydantic-settings, SQLite(개발, WAL 모드, foreign_keys ON) → 운영 시 PostgreSQL,
  PyJWT(HS256), pwdlib[argon2], PyMuPDF(`import pymupdf`), python-docx, python-pptx, trafilatura, httpx, anthropic(공식 SDK 1.x), tzdata, pytest.
  가상환경 `backend/.venv`.
- **프론트엔드:** React 19 + TypeScript + Vite 6, react-router-dom 7, @tanstack/react-query 5. 별도 UI 라이브러리 없이 CSS 한 파일(`src/styles.css`).
  Vite 개발 서버 5173, `/api`를 `http://localhost:8000`으로 프록시(`API_PROXY_TARGET` 환경 변수로 바꿀 수 있게).
- **작업 큐:** Redis 없이 DB `jobs` 테이블 기반. Worker 프로세스(`python -m app.worker`)가 폴링. 개발 중에는 `.env`의
  `EMBEDDED_WORKER=true`로 API 서버 안에서 스레드로 같이 돌린다. Worker 시작 시 RUNNING으로 남은 작업은 QUEUED로 되돌린다.
  작업 claim은 `UPDATE ... WHERE status='queued'`의 rowcount로 원자적으로.
- **DB 스키마:** Alembic 없이 시작 시 `create_all` + SQLite일 때 모델에만 있는 nullable 컬럼을 `ALTER TABLE ADD COLUMN`으로 자동 추가.
- **시각:** DB에는 UTC로 저장. SQLite가 tz를 잃으므로 응답 스키마의 datetime은 `UTCDateTime`(tz 없으면 UTC 부착) 타입으로 내보내고,
  문서에 찍는 날짜는 `Asia/Seoul`(설정 `DISPLAY_TIMEZONE`)로 변환. 클라이언트가 보낸 시각(세션 일정)은 저장 전 UTC로 변환.
- **실행:** `.claude/launch.json`에 backend(`backend/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --port 8000`)와
  frontend(`C:/Program Files/nodejs/node.exe frontend/node_modules/vite/bin/vite.js frontend --port 5173 --strictPort`) 두 개.
- **.env (backend/.env, Git 제외) / .env.example(커밋):**
  `DATABASE_URL`(기본 backend/data/app.db), `STORAGE_DIR`(기본 backend/storage), `JWT_SECRET`(32자 이상),
  `ADMIN_EMAIL=admin@example.com`, `ADMIN_PASSWORD=admin-dev-password`(최초 실행 시 플랫폼 관리자 자동 생성, 이름 "관리자"),
  `LLM_PROVIDER=mock|claude_code|claude`, `LLM_CONCURRENCY=4`, `CLAUDE_CODE_PATH`, `CLAUDE_CODE_MODEL=opus`,
  `CLAUDE_CODE_TIMEOUT_SECONDS=900`, `ANTHROPIC_API_KEY`, `CLAUDE_MODEL=claude-opus-5-5`, `CLAUDE_EFFORT=medium`,
  `EMBEDDED_WORKER=true`, `DISPLAY_TIMEZONE=Asia/Seoul`, `WORKER_POLL_SECONDS=2`.
- `.gitignore`: `.venv/ __pycache__/ .pytest_cache/ .env backend/data/ backend/storage/ node_modules/ frontend/dist/ *.tsbuildinfo`.

## 3. 폴더 구조

```
backend/app/
  config.py db.py models.py schemas.py security.py deps.py main.py worker.py
  routers/  auth admin vendors partners documents guides exports partner_guides community dashboard sharing
  services/ jobs.py pipeline.py partner_review.py
    parsing/  base.py pdf.py office.py web.py __init__.py
    llm/      base.py prompts.py mock.py claude.py claude_code.py __init__.py
    exporters/ base.py docx_export.py pptx_export.py corrections.py
backend/tests/  conftest(테스트 전용 tmp DB·storage, LLM_PROVIDER=mock, EMBEDDED_WORKER=false) + 기능별 테스트
frontend/src/  main.tsx App.tsx api.ts auth.tsx labels.ts types.ts styles.css NotificationBell.tsx assets/unipoint-logo.png
  pages/ Login Signup Dashboard(홈) Documents Document Guide PartnerGuide Shared Community Domain Post Settings Admin
docs/ PRODUCT_PLAN.md REBUILD_PROMPT.md
```

## 4. 데이터 모델 (모든 테이블)

- **vendors** id, name(unique), description, created_at
- **partners** id, name(unique), logo_path, docx_template_path, pptx_template_path, created_at; `partner_vendors`(partner_id, vendor_id) 다대다
- **users** id, email(unique), password_hash, name, phone, department, company_name(가입 시 입력한 회사명), role, status(pending/active/suspended/deleted), partner_id, created_at
- **source_documents** id, vendor_id, partner_id(업로더의 파트너사, 관리자 업로드는 null), uploaded_by, title, source_type(pdf/docx/pptx/url), file_path, url, page_count, status(uploaded/parsing/parsed/failed), error, created_at
- **sections** id, document_id, parent_id(목차 트리), order_index, level, title, page_start, page_end, text, included(요약 대상 여부)
- **guides** id, document_id, target_language(ko/en/ja/zh/vi), status(queued/summarizing/reviewing/approved), overview, created_by, created_at
- **section_summaries** id, guide_id, section_id(unique 쌍), version, content(markdown), key_steps(JSON), warnings(JSON), status(pending/generating/draft/approved/failed), error, updated_at
- **summary_revisions** id, summary_id, version, content, origin(generated/regenerated/edited), comment, author_id, created_at
- **glossary_terms** id, vendor_id, target_language, source_term, target_term (unique vendor+lang+source)
- **exports** id, guide_id, partner_id(로고·양식을 가져올 파트너사), format(docx/pptx), doc_version, include_logo, use_partner_template, revision(JSON: company, department, engineer, phone, email, change_note), status(queued/done/failed), file_path, error, created_by, created_at
- **jobs** id, kind, payload(JSON), status, progress_current/total, error, created_at, started_at, finished_at.
  kind: parse_document, summarize_guide, regenerate_section, export_guide, parse_partner_guide, compare_partner_guide, export_correction
- **partner_guides** id, guide_id(비교 기준 요약 가이드), partner_id, uploaded_by, title, source_type, file_path, status(uploaded/parsing/matched/comparing/reviewing/failed), error, progress_current/total, created_at
- **partner_sections** id, partner_guide_id, order_index, level, title, page_start/end, text, matched_section_id(벤더 원본 sections), match_method(auto/manual)
- **findings** id, partner_guide_id, partner_section_id, vendor_section_id, category(wrong_value/wrong_command/missing_step/wrong_order/missing_warning/contradiction/outdated), severity(high/medium/low), before_text, after_text, reason, evidence, locatable(before가 원문에 그대로 있는지), status(open/accepted/rejected), final_text, decision_note, decided_by, decided_at, created_at
- **correction_logs** id, partner_guide_id, finding_id, action(accepted/rejected/reopened), before_text, after_text, reason, note, user_id, created_at
- **correction_exports** id, partner_guide_id, kind(tracked/report), status, file_path, applied_count, skipped_count, error, created_by, created_at
- **posts** id, vendor_id, author_id, title, body, product, version, tags(JSON), status(open/resolved), solution_comment_id, created_at, updated_at
- **comments** id, post_id, author_id, body, created_at
- **session_events** id, vendor_id, organizer_id, title, description, starts_at, ends_at, join_url, created_at; **event_attendees**(event_id, user_id)
- **access_grants** id, user_id, vendor_id, reason, requested_days, status(pending/approved/rejected/revoked), grant_type(read/member), decided_by, decided_at, expires_at, decision_note, created_at
- **download_requests** id, guide_id, requester_id, requester_partner_id, owner_partner_id, message, status(pending/approved/rejected), decided_by, decided_at, decision_note, created_at
- **notifications** id, user_id, kind(download_request/download_decision), title, body, link, related_id, read_at, created_at

## 5. 권한·접근 규칙

- 로그인: 이메일 대소문자 무시. pending이면 "관리자 승인 대기 중입니다.", 그 외 비활성은 "사용이 중지된 계정입니다."(403). 로그인 이메일은 형식 검증 없이 str(가입만 EmailStr).
- `accessible_vendors(user)`: 관리자는 전체, 나머지는 소속 파트너사의 벤더.
- **문서·가이드 접근:** 관리자 또는 (doc.partner_id == user.partner_id 이고 doc.vendor가 내 도메인). 아니면 **404**(존재 여부도 숨김).
- **커뮤니티 접근:** member(내 파트너사 도메인: 읽기·쓰기) / granted(관리자가 승인한 기간 한정 읽기 전용, 만료 전) / none(403 "열람 신청 후 관리자 승인").
  읽기 전용 사용자는 글·댓글·일정 등록 불가(403), 세션 참석 표시는 가능. 다른 도메인 글 id 직접 접근은 404.
- **타 도메인 열람 신청:** 사용자가 사유·기간(7/30/90일) 신청 → 관리자가 **승인 방식 선택**:
  read(신청자만, 기간 지정, expires_at) 또는 member(신청자의 **파트너사 전체**에 그 벤더를 partner_vendors로 추가, 기간 없음).
  회수 시 read는 차단, member는 partner_vendors에서 제거. 이미 소속이면 400, 대기 중 신청 있으면 409. 모든 기록 보존.
- **가이드 공유:** 같은 벤더 도메인에서 다른 파트너사가 최종 문서까지 만든(approved + done export) 가이드만 목록에 노출(메타데이터만).
  요청은 파트너사 단위로 승인된다. 승인권자: 소유 파트너사의 partner_admin + 그 문서를 올린 사람(+ 플랫폼 관리자).
  승인되면 요청 파트너사 사용자 모두가 `/api/exports/{id}/download`로 받을 수 있다(가이드 편집 화면은 여전히 404). 거절 후 재요청 가능. 관리자 업로드 문서(partner 없음)는 공유 대상 아님.
- **가입자 삭제:** 하드 삭제 대신 status=deleted, 이메일을 `deleted-{id}-{8hex}@deleted.invalid`로 바꿔 같은 메일로 재가입 가능, phone 제거.
  작성 기록(문서·이력·글)은 유지. 자기 자신 삭제 400, 이미 삭제 409. 목록은 기본적으로 deleted 제외.
- 웹 URL 가져오기: http/https만, 호스트를 DNS 조회해 사설·루프백 등 비전역 IP면 거부(SSRF 방지), 리다이렉트 최종 URL도 재검사.

## 6. 기능 상세

### 6.1 계정
- 가입 신청(이메일, 비밀번호 8자 이상, 이름, 소속 회사, 부서, 연락처) → 관리자가 파트너사·권한 지정해 승인.
  승인 화면에서 신청 회사명과 같은 이름의 파트너사를 기본 선택(목록이 늦게 와도 반영되게 매 렌더 계산).
- 승인된 사람도 관리자가 소속·권한을 "수정"할 수 있다(같은 승인 API 재사용).

### 6.2 문서 업로드와 목차 파싱
- 입력: PDF, .docx, .pptx 파일 또는 웹 URL(.doc/.ppt 구형식 미지원, 스캔 PDF는 "텍스트를 추출할 수 없습니다" 실패).
- 제목 우선순위: 사용자 입력 > 문서 메타데이터 제목 > 파일명(URL). 파서는 메타데이터 없으면 None을 돌려주고, 파일명은 job payload의 fallback_title로 전달.
- **PDF:** 책갈피 목차(`get_toc`)가 있으면 그 기준. 같은 쪽에 여러 제목이 있을 수 있으므로 쪽 단위가 아니라 **본문에서 제목 문자열을 정규식(단어를 `\s+`로 연결, 대소문자 무시)으로 찾아 그 위치에서 자르고**, 섹션 본문은 제목 줄 다음부터(제목 중복 없음). 첫 목차 앞 내용은 "(표지·서문)" 섹션.
  책갈피가 없으면 글자 크기로 추정: 가장 많이 쓰인 크기를 본문, 1.15배 이상·120자 이하 줄을 제목(큰 순서로 최대 3단계), 연속된 같은 단계 제목 줄은 합친다.
- **Word:** `iter_inner_content()`로 문단·표 순서대로, 스타일명 `Heading N`/`제목 N`이 목차, 표는 셀을 ` | `로 이어 본문에.
- **PPT:** 슬라이드마다 섹션(제목 없으면 "슬라이드 N"), 표·발표자 노트 포함, 같은 제목의 연속 슬라이드는 합친다.
- **URL:** httpx로 받아 trafilatura markdown 추출 → `#` 제목으로 분할. (여러 페이지 수집은 TODO)
- 법적 고지·목차·색인·저작권·개정 이력·"(표지·서문)" 같은 제목(정확히 일치하는 정규식, "Indexing configuration" 같은 건 제외 안 함)은 기본으로 요약 대상에서 제외.
- 문서 화면에서 목차 트리를 보고 체크박스로 포함/제외(PATCH /sections) 후 언어를 골라 "요약 시작".

### 6.3 요약·번역 (요약 엔진 3종, `get_provider()`)
- **mock(기본):** AI 없이 각 목차 앞 5줄을 "> [모의 요약 · 언어] 경로" 머리말과 함께 보여 주고, `1.`/`Step N` 줄을 절차로, warning/caution/important/주의/경고 줄을 주의사항으로 뽑는다. 번역 안 함(실제 요약·번역은 Claude 필요).
- **claude:** Claude API. 모델 `claude-opus-5-5`, AsyncAnthropic, `client.beta.messages.stream(...)` + `get_final_message()`,
  `betas=["server-side-fallback-2026-07-01"]`, `fallbacks="default"`(안전 분류기 거절 시 서버가 대체 모델로 재시도),
  `output_config={"effort": CLAUDE_EFFORT, "format": {"type":"json_schema","schema": ...}}`, thinking 파라미터는 생략(적응형 기본),
  시스템 프롬프트와 용어집 블록에 `cache_control: ephemeral`. stop_reason이 refusal/max_tokens면 오류.
- **claude_code:** 본인 Claude 구독(개인 사용 전용). Claude Code CLI를 비대화 실행:
  `claude -p --output-format json --json-schema <스키마> --system-prompt-file <파일> --model <opus|sonnet> --tools "" --max-turns 3 --no-session-persistence --safe-mode`,
  원문은 표준 입력(명령줄 길이 제한 회피), 결과는 JSON의 `structured_output`(없으면 `result`를 JSON 파싱), `is_error`/`subtype!=success`면 오류.
  빈 전용 폴더(`storage/claude-code`)에서 실행하고 시스템 프롬프트 파일(system-summarize.md, system-review.md)을 거기에 쓴다.
  **환경 변수에서 ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, ANTHROPIC_PROFILE, ANTHROPIC_FEDERATION_RULE_ID, ANTHROPIC_ORGANIZATION_ID,
  CLAUDE_CODE_USE_BEDROCK/VERTEX/FOUNDRY, CLAUDECODE, CLAUDE_CODE_ENTRYPOINT를 제거**(API 키가 있으면 구독 대신 과금되고, 중첩 실행 오인 방지).
  CLI 위치: 설정값 → PATH → `%USERPROFILE%\.local\bin\claude.exe`. 없으면 설치 안내 오류. 연결 확인: `python -m app.services.llm.claude_code`
  (CLI 위치, `claude auth status`의 authMethod가 claude.ai인지, 짧은 요약 1건). 다른 사람에게 서비스할 때는 약관상 API 키(claude)로 전환.
- **요약 시스템 프롬프트(영어):** 요청에 적힌 목표 언어로 작성 / 명령어·CLI·코드·설정 키와 값·경로·포트·버전·제품명은 번역하지 않고 원문 유지, UI 라벨은 원문+괄호 번역 /
  모든 경고·주의 유지 / 절차는 순서대로, 사전 조건 먼저 / 원문에 없는 사실 추가 금지 / 분량은 원문의 10~25% / 법적·마케팅 문구면 한 문장 / 용어집 사용.
- 출력 스키마: `{summary_markdown, key_steps[], warnings[]}` (additionalProperties false). 개요: `{overview_markdown}` 5~10개 bullet.
- 섹션별 병렬(semaphore LLM_CONCURRENCY), 한 섹션 실패는 failed로 기록하고 계속, 진행률 job에 기록, 끝나면 전체 개요 생성 → guide reviewing.
- 벤더별 용어집(설정 화면에서 관리)을 프롬프트에 포함.

### 6.4 검토(피드백 필수)
- 목차 항목별 카드: 승인 / 직접 수정(새 버전, 다시 승인 필요) / 코멘트로 재생성(이전 요약+코멘트를 넣어 재생성, 버전 증가) / 변경 이력(v1 자동 생성, v2 피드백 재생성 + 코멘트, 직접 수정).
- **초안 일괄 승인:** "초안 N개 전체 승인" 버튼(확인 창: 읽지 않은 항목도 승인됨, 생성 중·실패 제외 안내). API는 draft만 승인하고 `{approved, remaining, guide_status}` 반환.
- 모든 항목이 승인되어야 guide approved, 그 전에는 최종 문서 생성 409.
- 생성 중이면 2초마다 자동 새로 고침.

### 6.5 최종 문서 (Word / PowerPoint)
- 생성 화면: 형식, 문서 버전, **로고·양식을 쓸 파트너사 선택**(관리자는 모든 파트너사, 그 외는 자기 파트너사 고정; 기본값은 문서의 파트너사),
  선택한 파트너사의 로고·Word 양식·PPT 양식 등록 상태와 **그 자리에서 업로드/교체**(관리자·파트너 관리자만),
  "파트너 양식 사용"·"표지에 로고 넣기"(해당 파일이 없으면 비활성), "문서 이력 관리 표 넣기"(소속 회사·부서·엔지니어·연락처·메일·변경 내용, 내 정보로 미리 채움).
  서버도 검증: 양식/로고 없으면 400, 다른 파트너사 양식 사용은 403(관리자 제외).
- **Word:** 양식이 있으면 `.dotx`는 [Content_Types].xml의 template.main+xml을 document.main+xml로 바꿔 열고, **본문(문단·표·그림)을 모두 지우고 마지막 sectPr(용지·여백·머리글/바닥글 연결)만 남겨** 디자인만 쓴다(기본 글꼴 변경 안 함).
  양식이 없으면 기본 문서 + 본문 글꼴 10.5pt, 동아시아 글꼴 "맑은 고딕".
  구성: (로고) 제목(Title) · 벤더 · 언어(한국어 등 원어명) · 문서 버전 · 생성일(KST) → 문서 이력 표(Table Grid) → 쪽 나눔 → "목차" + TOC 필드(`TOC \o "1-3" \h \z \u`, 열 때 업데이트 updateFields) → 쪽 나눔 → 개요 → 목차 항목별 제목(Heading 1~4)·요약(markdown: 소제목 굵게, `-`→List Bullet, `1.`→List Number, 코드블록 Consolas 9pt, 인라인 **굵게**/`코드`)·"주의 사항" 목록·"원본 p.x–y"(8pt 기울임).
  스타일이 양식에 없으면(KeyError) 기본 문단으로 대체. 로고는 양식 미사용 시에만 머리글에도 넣는다.
- **PowerPoint:** 양식이 있으면 `.potx`도 같은 방식으로 열고 **기존 슬라이드를 모두 삭제**(sldIdLst 제거 + drop_rel), 마스터·레이아웃·크기 유지, 글자 크기는 레이아웃에 맡김.
  양식 없으면 16:9(13.333×7.5in), 본문 18pt. 레이아웃은 자리표시자 종류로 찾는다: 표지=CENTER_TITLE 또는 TITLE+SUBTITLE, 본문=TITLE+BODY/OBJECT.
  구성: 표지(제목, "벤더 · 언어 · v버전 · 날짜", 로고) → 문서 이력 표 슬라이드(본문 자리표시자 제거 후 표) → 개요 → 목차별 슬라이드(핵심 절차 없으면 요약 줄, 주의사항은 "⚠ ", 원본 쪽), 7줄 넘으면 "(계속)" 슬라이드, 본문 TEXT_TO_FIT_SHAPE.
- 이력 표는 같은 버전을 Word·PPT로 각각 만들어도 **버전당 한 줄**(마지막 것). 날짜는 KST.
- 다운로드 파일명: `{문서제목}_{언어}_v{버전}.{형식}`.

### 6.6 2단계 — 파트너 가이드 비교·오류 수정
- 요약 가이드 화면 하단 "파트너 가이드 비교"(가이드가 approved여야 업로드 가능, 아니면 409) → PDF/Word/PPT 업로드 → 파싱 + **목차 자동 매칭** → 상태 matched.
- 매칭 확인 화면: 파트너 목차 ↔ 벤더 원본 목차(포함된 것만) 선택 상자로 수동 수정(다른 문서 목차 지정은 400), 연결 안 된 항목은 비교 안 함.
- **mock 매칭:** 제목 유사도(SequenceMatcher, 앞 번호 제거)와 기술 토큰 코사인 유사도 `|A∩B|/sqrt(|A||B|)`. 토큰 = 하이픈/슬래시 낱말(aer-cli), 버전·3~5자리 숫자, **숫자 앞 낱말**(port, firmware). 점수 `max(title, 0.4*title + 1.2*overlap)` ≥ 0.35면 연결. 한국어 제목 ↔ 영어 원본도 연결된다.
- **Claude 매칭:** 양쪽 목차(키·제목·발췌 300자)를 주고 `{matches:[{partner_key, vendor_key(-1=없음)}]}`.
- **오류 탐지(비교 시작):** 매칭된 항목마다 벤더 원본(하위 목차 포함) + 승인된 요약(참고) + 파트너 텍스트를 주고 `{findings:[{category, severity, before(파트너 원문 그대로의 최소 구간), after, reason(가이드 언어), evidence(원본 인용)}]}`.
  검토 시스템 프롬프트: 원본이 정답, 잘못된 값·명령, 누락 절차·사전조건·순서, 누락/모순 경고, 원본과 모순만 보고. 문체·번역·의도적 생략·원본에 없는 내용은 보고하지 않음, 애매하면 보고 안 함.
  mock 탐지: 파트너의 버전/포트 값이 원본에 없고, 같은 "앞 낱말"의 원본 값이 다르면 wrong_value(high); 백틱 명령이 원본에 없고 같은 첫 단어 명령이 원본에 정확히 하나면 wrong_command(medium). before는 그 줄 전체.
  다시 비교하면 미결정 후보만 지우고 다시 찾으며, 이미 결정한 (섹션, before)는 중복 생성하지 않는다. locatable = before가 파트너 원문에 그대로 있는지.
- 결정: 수락 / 고쳐서 수락(final_text) / 거절(사유 필수, 없으면 400) / 되돌리기(reopen). 결정된 것을 다시 결정하려면 되돌린 뒤(409). 모든 결정은 correction_logs.
- 결과 파일: **변경 내용 추적 수정본**(원본이 Word일 때만): 수락 항목의 before가 있는 문단을 찾아 runs를 지우고 일반 run + `w:del`(w:delText) + `w:ins` + 나머지로 다시 구성(첫 run 서식 복사, 같은 문단 여러 수정은 겹치지 않게 한 번에, author=생성자 이름). 반영/제외 건수 기록.
  **수정 보고서**(모든 형식): 가로 방향 Word, 제목·대상·기준 문서·작성일·건수 요약, 표(No, 위치, 유형, 심각도, 수정 전, 수정 후, 사유, 벤더 원본 근거(p.), 결정, 결정자·일시, 메모) 8pt.
- 화면: 진행률, 매칭 표, 오류 후보 카드(유형·심각도·상태 배지, 수정 전(취소선)/후, 사유, 원본 근거, 위치 못 찾음 경고), 필터(미결정/수락/거절/전체), 수정 이력 표, 수정본·보고서 생성/다운로드.

### 6.7 3단계 — 벤더 도메인 커뮤니티
- 커뮤니티 홈: 내 도메인 카드(소속/열람 승인(만료일)/글 수·예정 세션 수), **"다른 도메인 권한"** 한 섹션(접근 불가 도메인별 사유·기간 신청 또는 "승인 대기 중", 지난 신청 기록은 접어서) — id `access`.
- 도메인 화면 탭: **이슈 공유**(검색: 제목·본문·제품·버전, 상태 필터, 태그 클릭 필터, 새 글: 제목·제품·버전·태그(쉼표/공백, # 제거, 중복 제거, 최대 10)·내용) / **온라인 세션**(예정/지난, 등록: 제목·시작·종료·접속 링크·설명, datetime-local을 UTC ISO로 보냄, 참석/참석 취소, 참석자 목록, 등록자·관리자 삭제).
- 글 상세: 작성자(소속 파트너사), 해결됨 표시/다시 열기, **댓글을 "해결 방법"으로 지정**(초록 강조), 작성자·관리자만 수정·삭제, 해결 댓글 삭제 시 지정 해제, 읽기 전용이면 "댓글을 쓸 수 없습니다".

### 6.8 가이드 공유 + 상단 알림
- 메뉴 "가이드 공유" 탭: 다른 파트너 가이드(문서·벤더·파트너사·언어·형식·최근 생성·상태; 요청 전/거절됨이면 사유 입력 후 "다운로드 요청", 승인됨이면 형식별 "받기"),
  받은 요청(요청자·문서·요청 파트너사·사유·상태, 승인권자만 메모와 승인/거절), 보낸 요청.
- 요청 시 승인권자 전원에게 알림(download_request, link `/shared?tab=incoming`), 한 명이 처리하면 같은 요청의 다른 알림은 읽음 처리, 요청자에게 결과 알림(download_decision, 메모 포함).
- 상단 🔔: 읽지 않은 수 배지(9+), 30초 폴링, 드롭다운(제목·본문·시각, 읽지 않은 것 강조, 대기 중 요청은 **알림 안에서 승인/거절**, 클릭 시 읽음+이동, 모두 읽음). 바깥 클릭·Esc로 닫힘.

### 6.9 홈(대시보드)
- 로그인 후 첫 화면 `/`(메뉴 이름 "홈"). 기존 문서 화면은 `/documents`.
- 상단 **남색 구역(화면 폭 전체)**에 "내 처리 현황" + 오른쪽 "+ 새 문서 올리기"(작은 흰 테두리 버튼).
  카드: 처리한 문서(내가 올린 문서 수) / 처리 완료(요약 승인 완료) / 처리 미완료(분석 중·요약 전·요약 중·검토 중, 검토 대기 항목 수 표시) / 실패 / 생성한 최종 문서 수. 카드를 누르면 아래 표 필터.
- 표: 문서 이름(가이드 있으면 가이드 화면, 없으면 문서 화면 링크, 요약 언어), 벤더, 형식·쪽수, 등록일, 진행 단계 배지(분석 중→요약 전→요약 중→검토 중→승인 완료→문서 생성 완료/분석 실패), 요약 승인 진행 막대(승인/전체), 최종 문서 수.
  단계는 문서의 가장 최근 가이드 기준. 분석·요약 중이면 3초마다 새로 고침. 다른 사람이 올린 문서는 세지 않는다.
- 홈에는 인사말이나 제품 소개 문구를 넣지 않는다.

### 6.10 관리자 화면 (섹션 3개)
1. **가입자** 표 — 열 순서: **이름, 소속(파트너사 + 부서, 미지정이면 신청 회사명), 이메일, 전화번호, 도메인, 상태**, 그리고 동작 열.
   권한 열·가입 일시 열 없음(가입 일시는 이름에 마우스를 올리면 툴팁). 승인 대기자는 맨 위·강조, "승인 대기 N명" 배지.
   도메인: 정식 도메인(초록 배지) + 기간 한정 읽기(파란 배지 "벤더 읽기 ~만료일"), 플랫폼 관리자는 "전체 도메인".
   동작: 승인 대기는 "승인하기", 그 외 "수정"(같은 줄 아래 펼침: 소속 파트너사(도메인 목록 표시)·권한 선택, 승인/변경 저장), "삭제"(빨간 링크, 확인 창, 본인 행엔 없음).
   검색(이름·메일·회사), 상태 필터(전체/사용 중/승인 대기/정지). 표 최소 너비로 가로 스크롤.
2. **다른 도메인 권한 신청** — 대기 신청: 신청자·파트너사→벤더·사유, 승인 방식 라디오(기간 한정 읽기 전용(일수) / 정식 소속 부여 — "{파트너사} 전체가 {벤더} 도메인에서 읽기·쓰기·문서 업로드"), 메모, 승인/거절.
   "처리한 신청도 보기"로 지난 것(승인·정식 소속/읽기 전용·기간 만료/소속 해제됨·회수 버튼).
3. **파트너사 · 벤더 도메인** — 새 벤더·새 파트너사 추가, 파트너사별 지원 벤더 체크박스.

### 6.11 설정 화면 (플랫폼 관리자·파트너 관리자)
- 파트너사 로고·양식(id `logo`): 관리자는 파트너사 선택, 로고 미리보기(GET /partners/{id}/logo, 인증 Blob), 로고(.png/.jpg)·Word 양식(.docx/.dotx)·PowerPoint 양식(.pptx/.potx) 업로드.
- 벤더 용어집: 벤더·언어 선택, 원어→번역어 추가(같은 원어면 갱신), 행 단위 수정. 수정은 관리자·파트너 관리자만.

## 7. API 목록 (모두 `/api` 접두사)

인증 `POST /auth/signup`, `POST /auth/login`, `GET /auth/me`(partner_name, vendors 포함) ·
관리자 `GET /admin/users?status=`(AdminUserOut: partner_name, domains, read_grants), `POST /admin/users/{id}/approve {partner_id, role}`, `DELETE /admin/users/{id}`, `POST /admin/users/{id}/suspend`, `GET|POST /admin/partners`, `PUT /admin/partners/{id}/vendors {vendor_ids}`, `POST /admin/vendors` ·
벤더 `GET /vendors`, `GET|PUT /vendors/{id}/glossary` · 파트너 `GET /partners/{id}`, `GET /partners/{id}/logo`, `POST /partners/{id}/assets/{logo|docx_template|pptx_template}` ·
문서 `POST /documents`(multipart: vendor_id, title?, file 또는 url), `GET /documents`, `GET /documents/{id}`(sections, guides), `PATCH /sections/{id} {included}` ·
가이드 `POST /documents/{id}/guides {target_language}`, `GET /guides/{id}`(partner_id, progress, items), `POST /guides/{id}/summaries/{sid}/approve`, `POST /guides/{id}/approve-all`, `PUT /guides/{id}/summaries/{sid} {content}`, `POST .../regenerate {comment}`, `GET .../revisions` ·
최종 문서 `POST /guides/{id}/exports {format, partner_id?, doc_version, include_logo, use_partner_template, revision?}`, `GET /guides/{id}/exports`, `GET /exports/{id}/download`(공유 승인 시 다른 파트너사도 허용) ·
2단계 `POST|GET /guides/{id}/partner-guides`, `GET /partner-guides/{id}`(sections, vendor_sections, findings, counts), `PATCH /partner-sections/{id} {matched_section_id}`, `POST /partner-guides/{id}/compare`, `POST /findings/{id}/decision {action: accept|reject|reopen, final_text?, note?}`, `GET /partner-guides/{id}/history`, `POST|GET /partner-guides/{id}/exports {kind: tracked|report}`, `GET /correction-exports/{id}/download` ·
커뮤니티 `GET /community/domains`, `GET|POST /community/{vendor_id}/posts`(q, status, tag), `GET|PUT|DELETE /community/posts/{id}`, `PATCH /community/posts/{id}/status {status, solution_comment_id?}`, `POST /community/posts/{id}/comments`, `DELETE /community/comments/{id}`, `GET /community/{vendor_id}/events?scope=upcoming|past`, `POST /community/{vendor_id}/events`, `PUT|DELETE /community/events/{id}`, `POST /community/events/{id}/rsvp?attending=`, `POST /community/{vendor_id}/access-requests {reason, days}`, `GET /community/access-requests/mine`, `GET /admin/access-requests?status=`, `POST /admin/access-requests/{id}/decision {approve, grant_type: read|member, days?, note?}`, `POST /admin/access-requests/{id}/revoke` ·
공유·알림 `GET /shared-guides`, `GET /shared-guides/{guide_id}/exports`, `POST /shared-guides/{guide_id}/requests {message}`, `GET /download-requests/incoming|outgoing`, `POST /download-requests/{id}/decision {approve, note}`, `GET /notifications`({unread, items[actionable]}), `POST /notifications/{id}/read`, `POST /notifications/read-all` ·
홈 `GET /dashboard`({counts, documents}) · `GET /health`.

## 8. 프론트엔드 공통

- `api.ts`: 토큰은 localStorage `techguide.token`(try/catch), `api<T>(path, {json|body})`, 오류 시 `detail`을 메시지로, 401이면 토큰 삭제, `download(path)`는 Content-Disposition(filename* utf-8) 파싱해 Blob 저장, `fetchBlob`.
- `auth.tsx`: me 쿼리, login/logout. 라우트는 `Protected`(roles 옵션)로 감싼다. `#앵커` 주소면 요소가 그려질 때까지 100ms 간격으로 찾아 스크롤.
- 라벨(labels.ts)에 상태·역할·유형 한국어 표기. 언어: 한국어/English/日本語/中文(简体)/Tiếng Việt.

## 9. 디자인 명세 (unipoint 홈페이지 스타일)

- 참고: www.unipoint.co.kr — 진한 남색 배경 구역, 선명한 파랑 강조, Pretendard, 굵은 메뉴, 테두리 버튼, 제목 뒤 파란 점("핵심 솔루션.").
- **주황색은 화면 어디에도 쓰지 않는다**(로고 이미지 속 주황 점만 예외).
- 색 토큰: bg `#f8f8fa`, surface `#fff`, surface-2 `#f4f6f9`, text `#222`, text-2 `#555`, muted `#8a8f98`, border `#e5e7eb`, border-strong `#cfd4dc`,
  navy `#000b34`, navy-2 `#151f43`, on-navy `#f9f9fc`/`#c7d2df`/`#8395a6`, accent `#0078ff`(hover `#0062d1`, soft `#e8f2ff`),
  ok `#0f9d6b`(soft `#e9f8f1`), danger `#e03131`(soft `#fdeeee`), 진행·대기·검토 표시는 파랑(soft) 계열. radius 8px / 작은 것 4px, 그림자 아주 옅게.
- 글꼴: Pretendard Variable(jsdelivr `orioncactus/pretendard@v1.3.9 ... pretendardvariable-dynamic-subset.min.css`), 숫자는 Montserrat(Google Fonts 600/700). 대체 글꼴 맑은 고딕. 브라우저 탭 제목 "unipoint · 기술 가이드".
- 로고: 첨부한 unipoint 로고를 흰 배경 → 투명 PNG로 변환(밝기 `min(r,g,b)`가 255에 가까운 가장자리만 알파 처리, `(255-min)*255/70`을 상한 255로, 흰색이 섞인 만큼 색 복원, 여백 크롭)해 `src/assets/unipoint-logo.png`. 로고의 실제 색: 파랑 `#4456a5`, 주황 `#e87e00`.
- **상단 바:** 흰 배경(반투명+blur), 높이 72px, 아래 테두리, sticky. 왼쪽 로고(높이 22px, 링크 `/`). 가운데 메뉴 **홈 · 문서 · 가이드 공유 · 커뮤니티 · 설정(관리자·파트너 관리자) · 관리자(플랫폼 관리자)** — 굵게, 활성은 파란 글자 + 아래 2px 파란 밑줄, 가로 스크롤(줄바꿈 없음).
  오른쪽: 알림 벨(사각 아이콘 버튼, 파란 숫자 배지) + **사용자 버튼**(파란 테두리, 파란 사각 이니셜 + 이름 + ▾). 로그아웃 버튼은 상단에 두지 않는다.
- **사용자 드롭다운**(이름 클릭): 이름, 메일, 권한·소속(이름과 권한명이 같으면 권한 생략) / 회사 로고·양식 변경(→ `/settings#logo`, 관리자·파트너 관리자) / 다른 도메인 권한 신청(→ `/community#access`, 관리자 제외) / 관리자 페이지(플랫폼 관리자) / 구분선 / 로그아웃(빨강). 바깥 클릭·Esc로 닫힘.
- 페이지 제목(h1)과 `.section-title` 뒤에 7px 파란 점. 표 머리 위 2px 남색 선. 탭·필터는 밑줄형. 버튼은 각진(4px) 테두리형, primary는 파란 채움.
- 홈의 남색 구역: `width:100vw; margin-left: calc(50% - 50vw)`, 안쪽 최대 1200px, 카드 navy-2, 라벨 앞 색 점(완료 초록, 실패 빨강 등), 숫자 Montserrat 2.1rem. body에 `overflow-x: clip`(가로 스크롤 방지).
- 커뮤니티 도메인 카드는 남색 카드. 로그인·가입 카드: 위 3px 남색 선, 로고(높이 36px), "로그인" 아래 "벤더 기술 가이드 요약 · 공유".
- 모바일(≤860px): 메뉴가 둘째 줄로, 이름 숨김.

## 10. 테스트 (pytest, 모두 통과해야 함)

test_flow(가입 승인→업로드→파싱→요약→재생성·수정·이력→승인→Word/PPT·로고·이력 표·한국어 표기→도메인 격리), test_parsers(PDF 책갈피 분할·같은 쪽 제목·제목 줄 제외, 글자 크기 추정, markdown 분할, 상용구 판정),
test_claude_code(가짜 CLI로 옵션·API 키 제거·표준 입력·한글·오류·설치 안내), test_settings(로고·양식 업로드 권한, 용어집 권한), test_partner_review(한국어 파트너 가이드 매칭·3건 탐지·결정·재비교 중복 없음·추적 수정본 XML·보고서·격리),
test_community(공유·해결 댓글·검색·세션 UTC·차단·읽기 승인·만료·회수·정식 소속 부여/회수·삭제 권한), test_bulk_approve, test_templates(.dotx 본문 삭제·머리글 로고 유지, PPT 기존 슬라이드 삭제·4:3 유지·레이아웃, 관리자 파트너 선택, 타 파트너 403),
test_dashboard(집계·단계·타인 제외), test_admin_users(목록 필드·삭제·재가입·자기 삭제 불가), test_sharing(목록 범위·요청·알림·승인권자·다운로드·거절 후 재요청).
프론트는 `tsc -b` 통과.

## 11. 만드는 순서 (단계마다 테스트·브라우저 확인·커밋)

1. 개발 환경 설치, 저장소 초기화(.gitignore), 백엔드 뼈대(설정·DB·모델·인증·작업 큐·Worker), 파서, mock 엔진, Word/PPT 생성, 1단계 화면, test_flow·test_parsers.
2. 설정 화면(로고·양식·용어집), Claude 엔진 2종(claude, claude_code)과 prompts.py 공유.
3. 2단계 파트너 가이드 비교 전체.
4. 3단계 커뮤니티와 열람 승인(read/member).
5. 일괄 승인, 양식 적용 방식(내용 삭제·디자인 유지)과 생성 화면 파트너사 선택·업로드.
6. 관리자 가입자 표·수정·삭제, 홈 대시보드, 가이드 공유·알림.
7. 9절 디자인 전체 적용, 로고.
8. README(설치·실행·엔진 전환·Claude Code 설치), docs/PRODUCT_PLAN.md 갱신.

## 12. 작업 방식

- 모든 답변·진행 안내·요약은 한국어. 변경 후 백엔드 pytest와 프론트 `tsc -b`를 돌리고, 화면은 브라우저로 직접 확인한 뒤 결과를 사실대로 보고한다.
- 내가 같은 브라우저 창에 로그인해 있으면 그 세션을 로그아웃시키지 말고, 확인은 다른 포트(예: 5174, localStorage 분리)의 확인용 화면에서 한다.
- 시험 데이터는 이름에 "테스트"를 넣어 구분하고, 내가 만든 실제 데이터(파트너사·문서)를 임의로 바꾸지 않는다.
- 커밋은 기능 단위로, GitHub push는 내가 요청할 때만. 비밀번호·API 키는 채팅에 쓰지 않는다.
- 이 PC 폴더가 OneDrive 안에 있어 node_modules·.venv·SQLite가 동기화될 수 있으니 필요 시 동기화 밖 경로를 권한다.

## 13. Claude 연결 (실제 요약·번역)

- 가짜 엔진은 요약·번역을 하지 않는다. 실제 품질은 Claude 연결 후 확인.
- **구독(개인 사용):** PowerShell `irm https://claude.ai/install.ps1 | iex` → 설치 위치 `%USERPROFILE%\.local\bin\claude.exe`(PATH에 없을 수 있음:
  `& "$env:USERPROFILE\.local\bin\claude.exe" auth login`) → "Claude account with subscription" 선택 → 브라우저에서 구독 계정 로그인 →
  `backend/.env`에 `LLM_PROVIDER=claude_code`, `LLM_CONCURRENCY=2` → `python -m app.services.llm.claude_code`로 확인.
- **API:** `LLM_PROVIDER=claude`, `ANTHROPIC_API_KEY=...`(.env에만). 다른 사람에게 서비스할 때는 반드시 API.

## 14. 남은 일 (알려진 한계)

- 실제 Claude로 요약·번역·오류 탐지 품질 확인과 지시문 조정, 아주 긴 섹션 분할·짧은 섹션 묶음.
- 요약 편집기 서식(TipTap), 여러 페이지 웹 문서 수집, 스캔 PDF OCR, Alembic·PostgreSQL 전환.
- 커뮤니티 알림(메일/메신저), 첨부 파일, 열람 감사 로그. 운영 서버 위치 결정.

===== 프롬프트 끝 =====
