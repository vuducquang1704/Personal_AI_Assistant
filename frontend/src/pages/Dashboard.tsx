import { useEffect, useState } from "react";
import { api, formatDate } from "../lib/api";
import { PRIORITY_LABEL, type Priority, type Stats, type Task } from "../lib/types";

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
  const tiles = [
    ["Tổng số việc", s.total], ["Đang mở", s.todo + s.in_progress], ["Hoàn thành", s.done],
    ["Quá hạn", s.overdue], ["Đến hạn hôm nay", s.due_today], ["Đến hạn 7 ngày tới", s.due_this_week],
  ] as const;

  return (
    <div className="page">
      <h1>Thống kê tiến độ</h1>
      <div className="tiles">
        {tiles.map(([label, v]) => (
          <div key={label} className={`tile ${label === "Quá hạn" && v > 0 ? "warn" : ""}`}>
            <div className="value">{v}</div><div className="muted small">{label}</div>
          </div>
        ))}
      </div>
      <div className="grid2">
        <div className="card">
          <h3>Tỉ lệ hoàn thành</h3>
          <div className="progress"><div style={{ width: `${s.completion_rate * 100}%` }} /></div>
          <p className="muted small">{Math.round(s.completion_rate * 100)}% công việc đã hoàn thành</p>
          <h3>Việc đang mở theo mức ưu tiên</h3>
          {(Object.keys(PRIORITY_LABEL) as Priority[]).map((p) => (
            <div key={p} className="row between"><span className={`badge p-${p}`}>{PRIORITY_LABEL[p]}</span><b>{s.by_priority[p]}</b></div>
          ))}
        </div>
        <div className="card">
          <h3>Hoàn thành 7 ngày qua</h3>
          <div className="bars">
            {s.completed_last_7_days.map((d) => (
              <div key={d.date} className="bar">
                <div className="fill" style={{ height: `${(d.count / max) * 100}%` }} title={`${d.count} việc`} />
                <span className="small muted">{d.date.slice(8)}/{d.date.slice(5, 7)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="card">
        <h3>Sắp đến hạn</h3>
        {upcoming.length === 0 ? <p className="muted">Không có việc nào đến hạn trong 7 ngày tới.</p> : (
          <ul className="plain">
            {upcoming.map((t) => <li key={t.id} className="row between"><span>{t.title}</span><span className="muted small">{formatDate(t.due_at)}</span></li>)}
          </ul>
        )}
      </div>
    </div>
  );
}
