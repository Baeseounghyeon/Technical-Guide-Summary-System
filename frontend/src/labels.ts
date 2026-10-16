export const LANGUAGES = [
  { code: "ko", label: "한국어" },
  { code: "en", label: "English" },
  { code: "ja", label: "日本語" },
  { code: "zh", label: "中文(简体)" },
  { code: "vi", label: "Tiếng Việt" },
];

export const languageLabel = (code: string) => LANGUAGES.find((l) => l.code === code)?.label ?? code;

export const STATUS_LABELS: Record<string, string> = {
  uploaded: "대기",
  parsing: "분석 중",
  parsed: "분석 완료",
  failed: "실패",
  queued: "대기",
  summarizing: "요약 중",
  reviewing: "검토 중",
  approved: "승인",
  pending: "대기",
  generating: "생성 중",
  draft: "초안",
  done: "완료",
  active: "사용 중",
  suspended: "정지",
};

export const ROLE_LABELS: Record<string, string> = {
  platform_admin: "플랫폼 관리자",
  partner_admin: "파트너 관리자",
  engineer: "일반 사용자",
};

/** 업무 구분 (권한과 별개) */
export const TRACK_LABELS: Record<string, string> = {
  engineer: "엔지니어",
  sales: "영업",
};

export const QUOTE_CATEGORY_LABELS: Record<string, string> = {
  spec: "규격서",
  feature: "제품 기능",
  price: "가격표",
  other: "기타",
};

export const ORIGIN_LABELS: Record<string, string> = {
  generated: "자동 생성",
  regenerated: "피드백 재생성",
  edited: "직접 수정",
};

export const PARTNER_GUIDE_STATUS: Record<string, string> = {
  uploaded: "대기",
  parsing: "분석 중",
  matched: "매칭 확인",
  comparing: "비교 중",
  reviewing: "검토 중",
  failed: "실패",
};

export const FINDING_CATEGORY: Record<string, string> = {
  wrong_value: "잘못된 값",
  wrong_command: "잘못된 명령",
  missing_step: "누락된 절차",
  wrong_order: "순서 오류",
  missing_warning: "누락된 주의사항",
  contradiction: "원본과 모순",
  outdated: "구버전 내용",
};

export const SEVERITY_LABELS: Record<string, string> = { high: "심각도 높음", medium: "심각도 보통", low: "심각도 낮음" };

export const FINDING_STATUS: Record<string, string> = { open: "미결정", accepted: "수락", rejected: "거절" };

export const LOG_ACTION: Record<string, string> = { accepted: "수락", rejected: "거절", reopened: "되돌림" };

export const ACCESS_LABELS: Record<string, string> = { member: "소속 도메인", granted: "열람 승인 (읽기 전용)", none: "접근 불가" };

export const POST_STATUS: Record<string, string> = { open: "해결 중", resolved: "해결됨" };

export const GRANT_STATUS: Record<string, string> = {
  pending: "승인 대기",
  approved: "승인",
  rejected: "거절",
  revoked: "회수",
};

/** 문서 종류(목적). 상단 '문서' 메뉴와 문서 화면 탭에 쓴다. */
export const DOC_TYPES = [
  { key: "spec", label: "규격서", full: "벤더 규격서" },
  { key: "guide", label: "기술 가이드", full: "벤더 기술 가이드" },
  { key: "brochure", label: "브로슈어", full: "벤더 브로슈어" },
] as const;
export type DocTypeKey = (typeof DOC_TYPES)[number]["key"];

/** 기술 가이드 문서의 세부 종류 (가이드 화면의 종류 선택) */
export const GUIDE_KINDS = [
  { key: "technical", label: "기술 가이드" },
  { key: "troubleshooting", label: "트러블 슈팅 가이드" },
] as const;
export type GuideKindKey = (typeof GUIDE_KINDS)[number]["key"];
