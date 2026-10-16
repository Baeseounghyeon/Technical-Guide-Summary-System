import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import { HOLIDAYS } from "./holidays";

/** 일정 목적과 표시 색 */
export const PURPOSES = [
  { key: "meeting", label: "미팅", color: "#e03131" },
  { key: "outside", label: "외근", color: "#1c6fe0" },
  { key: "vacation", label: "휴가", color: "#0f9d6b" },
  { key: "education", label: "교육", color: "#7b4fd6" },
  { key: "other", label: "기타", color: "#6b7280" },
] as const;
type PurposeKey = (typeof PURPOSES)[number]["key"];

interface CalendarEvent {
  id: number;
  title: string;
  purpose: PurposeKey;
  start_date: string;
  end_date: string;
  start_time: string | null;
  end_time: string | null;
  content: string | null;
}
type Draft = Omit<CalendarEvent, "id"> & { id?: number };

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];
const MAX_LANES = 4; // 한 주에 줄로 보여 줄 일정 수 (넘치면 '+N개')

// ---------- 날짜 도우미 (현지 날짜를 YYYY-MM-DD 문자열로 다룬다) ----------
const pad = (n: number) => String(n).padStart(2, "0");
const toKey = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const fromKey = (key: string) => {
  const [y, m, d] = key.split("-").map(Number);
  return new Date(y, m - 1, d);
};
const addDays = (d: Date, n: number) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
const purposeOf = (key: string) => PURPOSES.find((p) => p.key === key) ?? PURPOSES[PURPOSES.length - 1];

function timeLabel(e: CalendarEvent) {
  if (!e.start_time && !e.end_time) return "";
  return `${e.start_time ?? ""} ~ ${e.end_time ?? ""}`;
}

/** 홈 달력: 오늘·공휴일 표시, 개인 일정(목적별 색, 여러 날이면 이어서 길게) 추가·수정·삭제. */
export default function Calendar() {
  const today = toKey(new Date());
  const [month, setMonth] = useState(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });
  const [draft, setDraft] = useState<Draft | null>(null);

  // 달력에 보이는 6주(42일)
  const gridStart = addDays(month, -month.getDay());
  const days = Array.from({ length: 42 }, (_, i) => addDays(gridStart, i));
  const startKey = toKey(days[0]);
  const endKey = toKey(days[41]);

  const events = useQuery({
    queryKey: ["calendar", startKey, endKey],
    queryFn: () => api<CalendarEvent[]>(`/calendar/events?start=${startKey}&end=${endKey}`),
  });

  const weeks = Array.from({ length: 6 }, (_, w) => days.slice(w * 7, w * 7 + 7));
  const newDraft = (date: string): Draft => ({
    title: "", purpose: "meeting", start_date: date, end_date: date, start_time: "", end_time: "", content: "",
  });

  return (
    <section className="card calendar">
      <div className="calendar-head">
        <h2 className="section-title" style={{ margin: 0 }}>
          {month.getFullYear()}년 {month.getMonth() + 1}월
        </h2>
        <div className="actions">
          <button onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))} aria-label="이전 달">‹</button>
          <button
            onClick={() => {
              const now = new Date();
              setMonth(new Date(now.getFullYear(), now.getMonth(), 1));
            }}
          >
            오늘
          </button>
          <button onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))} aria-label="다음 달">›</button>
          <button className="primary" onClick={() => setDraft(newDraft(today))}>+ 일정 추가</button>
        </div>
      </div>
      <div className="calendar-legend">
        {PURPOSES.map((p) => (
          <span key={p.key}><i style={{ background: p.color }} />{p.label}</span>
        ))}
        <span className="muted">날짜를 누르면 일정을 추가하고, 일정을 누르면 고칠 수 있습니다.</span>
      </div>
      {events.error && <p className="error">{events.error.message}</p>}

      <div className="calendar-weekdays">
        {WEEKDAYS.map((w, i) => <div key={w} className={i === 0 ? "sun" : i === 6 ? "sat" : ""}>{w}</div>)}
      </div>
      {weeks.map((week) => (
        <Week
          key={toKey(week[0])}
          week={week}
          month={month.getMonth()}
          today={today}
          events={events.data ?? []}
          onDay={(date) => setDraft(newDraft(date))}
          onEvent={(e) => setDraft({ ...e, start_time: e.start_time ?? "", end_time: e.end_time ?? "", content: e.content ?? "" })}
        />
      ))}

      {draft && <EventDialog draft={draft} onClose={() => setDraft(null)} />}
    </section>
  );
}

function Week({
  week, month, today, events, onDay, onEvent,
}: {
  week: Date[];
  month: number;
  today: string;
  events: CalendarEvent[];
  onDay: (date: string) => void;
  onEvent: (e: CalendarEvent) => void;
}) {
  const first = toKey(week[0]);
  const last = toKey(week[6]);
  // 이 주에 걸친 일정을 시작일·길이 순으로 줄(lane)에 배치한다.
  const inWeek = events
    .filter((e) => e.start_date <= last && e.end_date >= first)
    .sort((a, b) => a.start_date.localeCompare(b.start_date) || b.end_date.localeCompare(a.end_date) || (a.start_time ?? "").localeCompare(b.start_time ?? ""));
  const lanes: string[][] = []; // lane 마다 차지한 날짜 칸(0~6)의 끝 위치
  const placed: { e: CalendarEvent; col: number; span: number; lane: number; continuesBefore: boolean; continuesAfter: boolean }[] = [];
  const hidden: number[] = Array(7).fill(0);
  for (const e of inWeek) {
    const startCol = e.start_date < first ? 0 : fromKey(e.start_date).getDay();
    const endCol = e.end_date > last ? 6 : fromKey(e.end_date).getDay();
    let lane = lanes.findIndex((used) => used.every((range) => {
      const [s, t] = range.split("-").map(Number);
      return endCol < s || startCol > t;
    }));
    if (lane === -1) {
      lane = lanes.length;
      lanes.push([]);
    }
    if (lane >= MAX_LANES) {
      for (let c = startCol; c <= endCol; c++) hidden[c] += 1;
      continue;
    }
    lanes[lane].push(`${startCol}-${endCol}`);
    placed.push({ e, col: startCol, span: endCol - startCol + 1, lane, continuesBefore: e.start_date < first, continuesAfter: e.end_date > last });
  }
  const laneCount = Math.min(lanes.length, MAX_LANES);

  return (
    <div className="calendar-week" style={{ gridTemplateRows: `28px repeat(${laneCount}, 24px) minmax(18px, 1fr)` }}>
      {week.map((d, i) => {
        const key = toKey(d);
        const holiday = HOLIDAYS[key];
        const classes = [
          "calendar-day",
          d.getMonth() !== month ? "other-month" : "",
          key === today ? "today" : "",
          holiday || i === 0 ? "sun" : i === 6 ? "sat" : "",
        ].filter(Boolean).join(" ");
        return (
          <button key={key} className={classes} style={{ gridColumn: i + 1, gridRow: "1 / -1" }} onClick={() => onDay(key)} aria-label={`${key} 일정 추가`}>
            <span className="day-top">
              <span className="day-num">{d.getDate()}</span>
              {holiday && <span className="holiday-name" title={holiday}>{holiday}</span>}
            </span>
            {hidden[i] > 0 && <span className="more">+{hidden[i]}개</span>}
          </button>
        );
      })}
      {placed.map(({ e, col, span, lane, continuesBefore, continuesAfter }) => {
        const purpose = purposeOf(e.purpose);
        const tip = [e.title, `${purpose.label} · ${e.start_date}${e.end_date !== e.start_date ? ` ~ ${e.end_date}` : ""} ${timeLabel(e)}`, e.content ?? ""]
          .filter(Boolean)
          .join("\n");
        return (
          <button
            key={`${e.id}-${col}`}
            className={`calendar-bar${continuesBefore ? " cont-before" : ""}${continuesAfter ? " cont-after" : ""}`}
            style={{ gridColumn: `${col + 1} / span ${span}`, gridRow: lane + 2, background: purpose.color }}
            title={tip}
            onClick={(ev) => {
              ev.stopPropagation();
              onEvent(e);
            }}
          >
            {continuesBefore && "◀ "}
            {e.start_time && !continuesBefore ? `${e.start_time} ` : ""}
            {e.title}
          </button>
        );
      })}
    </div>
  );
}

function EventDialog({ draft, onClose }: { draft: Draft; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<Draft>(draft);
  const editing = draft.id != null;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const done = () => {
    queryClient.invalidateQueries({ queryKey: ["calendar"] });
    onClose();
  };
  const save = useMutation({
    mutationFn: () => {
      const body = { ...form, start_time: form.start_time || null, end_time: form.end_time || null, content: form.content || null };
      return editing
        ? api(`/calendar/events/${draft.id}`, { method: "PUT", json: body })
        : api("/calendar/events", { method: "POST", json: body });
    },
    onSuccess: done,
  });
  const remove = useMutation({ mutationFn: () => api(`/calendar/events/${draft.id}`, { method: "DELETE" }), onSuccess: done });

  const set = (key: keyof Draft) => (e: { target: { value: string } }) => {
    const value = e.target.value;
    setForm((f) => {
      const next = { ...f, [key]: value };
      // 시작 날짜를 끝 날짜보다 뒤로 옮기면 끝 날짜도 따라간다.
      if (key === "start_date" && next.end_date < value) next.end_date = value;
      return next;
    });
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate();
  };
  const error = save.error ?? remove.error;

  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <form className="modal form" role="dialog" aria-modal="true" aria-label="일정" onSubmit={submit}>
        <div className="summary-head">
          <h2 style={{ margin: 0 }}>{editing ? "일정 수정" : "일정 추가"}</h2>
          <button type="button" className="link" onClick={onClose}>닫기</button>
        </div>
        <label>
          제목
          <input value={form.title} onChange={set("title")} placeholder="예: SK쉴더스 CM 제안 미팅" required maxLength={200} autoFocus />
        </label>
        <div className="purpose-picker" role="radiogroup" aria-label="목적">
          {PURPOSES.map((p) => (
            <label key={p.key} className={`purpose-chip${form.purpose === p.key ? " selected" : ""}`} style={{ ["--chip" as string]: p.color }}>
              <input type="radio" name="purpose" value={p.key} checked={form.purpose === p.key} onChange={set("purpose")} />
              {p.label}
            </label>
          ))}
        </div>
        <div className="form-row">
          <label>시작 날짜<input type="date" value={form.start_date} onChange={set("start_date")} required /></label>
          <label>끝 날짜<input type="date" value={form.end_date} min={form.start_date} onChange={set("end_date")} required /></label>
        </div>
        <div className="form-row">
          <label>시작 시간<input type="time" value={form.start_time ?? ""} onChange={set("start_time")} /></label>
          <label>끝 시간<input type="time" value={form.end_time ?? ""} onChange={set("end_time")} /></label>
        </div>
        <label>
          내용
          <textarea value={form.content ?? ""} onChange={set("content")} rows={4} placeholder="장소, 참석자, 준비할 것 등" />
        </label>
        {error && <p className="error">{error.message}</p>}
        <div className="actions">
          <button className="primary" disabled={save.isPending}>{editing ? "저장" : "추가"}</button>
          {editing && (
            <button
              type="button"
              className="link danger-link"
              disabled={remove.isPending}
              onClick={() => window.confirm("이 일정을 삭제할까요?") && remove.mutate()}
            >
              삭제
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
