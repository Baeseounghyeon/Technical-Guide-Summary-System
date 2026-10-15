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
  engineer: "엔지니어",
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
