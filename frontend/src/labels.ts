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
