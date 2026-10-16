import { useEffect } from "react";

const MIN_WIDTH = 48;

/** 화면의 모든 표(.table-wrap 안)에서 머리 칸 오른쪽 경계를 끌어 열 너비를 줄이고 늘릴 수 있게 한다.
 *  표가 새로 그려지거나 열 수가 바뀌면 다시 붙인다. 표마다 따로 코드를 넣지 않아도 된다. */
export default function ColumnResizer() {
  useEffect(() => {
    const root = document.querySelector("main") ?? document.body;
    let frame = 0;
    const scan = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => root.querySelectorAll<HTMLTableElement>(".table-wrap table").forEach(setup));
    };
    scan();
    const observer = new MutationObserver(scan);
    observer.observe(root, { childList: true, subtree: true });
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
    };
  }, []);
  return null;
}

function setup(table: HTMLTableElement) {
  const cells = Array.from(table.tHead?.rows[0]?.cells ?? []);
  if (cells.length === 0) return;
  const signature = String(cells.length);
  if (table.dataset.resizable === signature) return;
  // 지금 보이는 너비를 그대로 시작값으로 고정한다 (보이지 않는 표는 다음 기회에).
  const widths = cells.map((c) => c.getBoundingClientRect().width);
  if (widths.every((w) => w === 0)) return;
  table.dataset.resizable = signature;
  table.classList.add("table-resizable");
  table.style.minWidth = "0";
  table.style.width = `${widths.reduce((a, b) => a + b, 0)}px`;
  cells.forEach((cell, i) => {
    cell.style.width = `${widths[i]}px`;
    if (cell.querySelector(":scope > .col-resizer")) return;
    const handle = document.createElement("span");
    handle.className = "col-resizer";
    handle.title = "끌어서 열 너비 조절";
    handle.addEventListener("mousedown", (e) => startDrag(e, table, cell, handle));
    cell.appendChild(handle);
  });
}

function startDrag(e: MouseEvent, table: HTMLTableElement, cell: HTMLTableCellElement, handle: HTMLElement) {
  e.preventDefault();
  e.stopPropagation();
  const startX = e.clientX;
  const startWidth = cell.getBoundingClientRect().width;
  const startTable = table.getBoundingClientRect().width;
  handle.classList.add("dragging");
  document.body.classList.add("col-resizing");
  const move = (ev: MouseEvent) => {
    const width = Math.max(MIN_WIDTH, startWidth + ev.clientX - startX);
    cell.style.width = `${width}px`;
    table.style.width = `${startTable + width - startWidth}px`;
  };
  const up = () => {
    handle.classList.remove("dragging");
    document.body.classList.remove("col-resizing");
    document.removeEventListener("mousemove", move);
    document.removeEventListener("mouseup", up);
  };
  document.addEventListener("mousemove", move);
  document.addEventListener("mouseup", up);
}
