import { useEffect, useState, type ReactNode } from "react";
import { api, formatDate } from "../lib/api";
import { PRIORITY_LABEL, type Priority, type Stats, type Task } from "../lib/types";
import { IconAlert, IconCheck, IconClock, IconTasks } from "../components/Icons";

function Tile({ icon, label, value, tone = "" }: { icon: ReactNode; label: string; value: number; tone?: string }) {
  return (
    <div className={`tile ${tone}`}>
      <span className="ic">{icon}</span>
      <span className="value">{value}</span>
      <span className="muted small">{label}</span>
    </div>
  );
}

function Ring({ value }: { value: number }) {
  const r = 52, c = 2 * Math.PI * r;
  return (
    <div className="ring">
      <svg viewBox="0 0 130 130" width="130" height="130">
        <circle cx="65" cy="65" r={r} fill="none" stroke="var(--surface-2)" strokeWidth="12" />
        <circle cx="65" cy="65" r={r} fill="none" stroke="var(--ok)" strokeWidth="12" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - value)} transform="rotate(-90 65 65)" style={{ transition: "stroke-dashoffset .6s" }} />
      </svg>
      <div className="pct">{Math.round(value * 100)}%</div>
    </div>
  );
}

export default function Dashboard() {
  const [s, setS] = useState<Stats | null>(null);
  const [upcoming, setUpcoming] = useState<Task[]>([]);

  useEffect(() => {
    api<Stats>("/api/tasks/stats").then(setS);
    const in7 = new Date(Date.now() + 7 * 864e5).toISOString();
    api<Task[]>(`/api/tasks?due_to=${encodeURIComponent(in7)}&limit=50`).then((ts) => setUpcoming(ts.filter((t) => t.status !== "done").slice(0, 8)));
  }, []);

  if (!s) return <div className="page muted">Đang tải…</div>;
  const max = Math.max(1, ...s.completed_last_7_days.map((d) => d.count));
  const open = s.todo + s.in_progress;

  return (
    <div className="page">
      <div className="page-head"><div><h1>Thống kê tiến độ</h1><p className="muted">Tổng quan công việc của bạn</p></div></div>
      <div className="tiles">
        <Tile icon={<IconTasks size={18} />} label="Tổng số việc" value={s.total} />
        <Tile icon={<IconClock size={18} />} label="Đang mở" value={open} tone="amber" />
        <Tile icon={<IconCheck size={18} />} label="Hoàn thành" value={s.done} tone="ok" />
        <Tile icon={<IconAlert size={18} />} label="Quá hạn" value={s.overdue} tone={s.overdue > 0 ? "warn" : ""} />
        <Tile icon={<IconClock size={18} />} label="Đến hạn hôm nay" value={s.due_today} />
        <Tile icon={<IconClock size={18} />} label="Đến hạn 7 ngày tới" value={s.due_this_week} />
      </div>
      <div className="grid2">
        <div className="card">
          <h3>Tỉ lệ hoàn thành</h3>
          <div className="ring-wrap">
            <Ring value={s.completion_rate} />
            <div className="legend">
              <span className="muted small">Việc đang mở theo ưu tiên</span>
              {(Object.keys(PRIORITY_LABEL) as Priority[]).map((p) => (
                <div key={p} className="row between"><span className={`badge p-${p}`}>{PRIORITY_LABEL[p]}</span><b>{s.by_priority[p]}</b></div>
              ))}
            </div>
          </div>
        </div>
        <div className="card">
          <h3>Hoàn thành 7 ngày qua</h3>
          <div className="bars">
            {s.completed_last_7_days.map((d) => (
              <div key={d.date} className={`bar ${d.count === 0 ? "empty-bar" : ""}`}>
                <span className="num">{d.count || ""}</span>
                <div className="fill" style={{ height: `${(d.count / max) * 100}%` }} title={`${d.count} việc`} />
                <span className="small muted">{d.date.slice(8)}/{d.date.slice(5, 7)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="card">
        <h3>Sắp đến hạn</h3>
        {upcoming.length === 0 ? <p className="muted" style={{ marginBottom: 0 }}>Không có việc nào đến hạn trong 7 ngày tới.</p> : (
          <ul className="plain">
            {upcoming.map((t) => (
              <li key={t.id} className="row between">
                <span style={{ display: "flex", gap: ".6rem", alignItems: "center" }}><span className={`badge p-${t.priority}`}>{PRIORITY_LABEL[t.priority]}</span>{t.title}</span>
                <span className="muted small">{formatDate(t.due_at)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
