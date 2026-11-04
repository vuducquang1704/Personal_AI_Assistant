import { useEffect, useMemo, useState, type FormEvent } from "react";
import { api, formatDate, fromInputValue, toInputValue } from "../lib/api";
import { PRIORITY_LABEL, STATUS_LABEL, type Priority, type Status, type Task } from "../lib/types";
import Modal from "../components/Modal";
import { IconCheck, IconClock, IconPlus, IconTrash } from "../components/Icons";

type Draft = { title: string; description: string; due_at: string; priority: Priority; status: Status };
const EMPTY: Draft = { title: "", description: "", due_at: "", priority: "medium", status: "todo" };

function startOfDay(d: Date) { const x = new Date(d); x.setHours(0, 0, 0, 0); return x; }

export default function Tasks() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [filter, setFilter] = useState({ status: "", priority: "", q: "" });
  const [editing, setEditing] = useState<Task | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    const params = new URLSearchParams(Object.entries(filter).filter(([, v]) => v));
    setTasks(await api<Task[]>(`/api/tasks?${params}`));
    setLoaded(true);
  };
  useEffect(() => { load(); }, [filter]); // eslint-disable-line react-hooks/exhaustive-deps

  const openNew = () => { setEditing(null); setDraft(EMPTY); setError(""); setShowForm(true); };
  const openEdit = (t: Task) => {
    setEditing(t);
    setDraft({ title: t.title, description: t.description ?? "", due_at: toInputValue(t.due_at), priority: t.priority, status: t.status });
    setError("");
    setShowForm(true);
  };

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    const body = { ...draft, description: draft.description || null, due_at: fromInputValue(draft.due_at) };
    try {
      if (editing) await api(`/api/tasks/${editing.id}`, { method: "PATCH", body });
      else await api("/api/tasks", { body });
      setShowForm(false);
      load();
    } catch (err) { setError((err as Error).message); }
  };

  const toggle = async (t: Task) => { await api(`/api/tasks/${t.id}`, { method: "PATCH", body: { status: t.status === "done" ? "todo" : "done" } }); load(); };
  const remove = async (t: Task) => {
    if (!confirm(`Xoá công việc "${t.title}"?`)) return;
    await api(`/api/tasks/${t.id}`, { method: "DELETE" });
    load();
  };

  const groups = useMemo(() => {
    const now = new Date();
    const today = startOfDay(now);
    const tomorrow = new Date(today.getTime() + 864e5);
    const g: { key: string; title: string; cls?: string; items: Task[] }[] = [
      { key: "late", title: "Quá hạn", cls: "danger", items: [] },
      { key: "today", title: "Hôm nay", items: [] },
      { key: "upcoming", title: "Sắp tới", items: [] },
      { key: "nodue", title: "Không có hạn", items: [] },
      { key: "done", title: "Đã hoàn thành", items: [] },
    ];
    for (const t of tasks) {
      if (t.status === "done") g[4].items.push(t);
      else if (!t.due_at) g[3].items.push(t);
      else {
        const d = new Date(t.due_at);
        if (d < now) g[0].items.push(t);
        else if (d < tomorrow) g[1].items.push(t);
        else g[2].items.push(t);
      }
    }
    return g.filter((x) => x.items.length);
  }, [tasks]);

  const isLate = (t: Task) => t.status !== "done" && !!t.due_at && new Date(t.due_at) < new Date();

  return (
    <div className="page">
      <div className="page-head">
        <div><h1>Công việc</h1><p className="muted">{tasks.filter((t) => t.status !== "done").length} việc đang mở</p></div>
        <button className="primary" onClick={openNew}><IconPlus size={18} />Thêm việc</button>
      </div>
      <div className="filters">
        <input placeholder="Tìm kiếm công việc…" value={filter.q} onChange={(e) => setFilter({ ...filter, q: e.target.value })} aria-label="Tìm kiếm" />
        <select value={filter.status} onChange={(e) => setFilter({ ...filter, status: e.target.value })} aria-label="Lọc trạng thái">
          <option value="">Mọi trạng thái</option>
          {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select value={filter.priority} onChange={(e) => setFilter({ ...filter, priority: e.target.value })} aria-label="Lọc ưu tiên">
          <option value="">Mọi mức ưu tiên</option>
          {Object.entries(PRIORITY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </div>

      {loaded && tasks.length === 0 && (
        <div className="empty card"><div className="big">🗒️</div><p>Chưa có công việc nào.<br />Thêm bằng nút phía trên, hoặc nói với trợ lý.</p></div>
      )}

      {groups.map((g) => (
        <section key={g.key}>
          <div className={`group-title ${g.cls ?? ""}`}>{g.title}<span className="count">{g.items.length}</span></div>
          <ul className="tasks">
            {g.items.map((t) => (
              <li key={t.id} className={`task pr-${t.priority} ${t.status === "done" ? "done" : ""}`}>
                <button className="check-btn" onClick={() => toggle(t)} aria-label={t.status === "done" ? "Đánh dấu chưa xong" : "Đánh dấu hoàn thành"}>
                  {t.status === "done" && <IconCheck size={14} />}
                </button>
                <div className="grow" onClick={() => openEdit(t)}>
                  <div className="title">{t.title}</div>
                  {t.description && <div className="muted small">{t.description}</div>}
                  <div className="meta">
                    <span className={`badge p-${t.priority}`}>{PRIORITY_LABEL[t.priority]}</span>
                    {t.status === "in_progress" && <span className="badge">Đang làm</span>}
                    <span className={`due ${isLate(t) ? "late" : ""}`}><IconClock size={13} />{formatDate(t.due_at)}</span>
                  </div>
                </div>
                <button className="icon-btn" onClick={() => remove(t)} title="Xoá" aria-label="Xoá"><IconTrash size={18} /></button>
              </li>
            ))}
          </ul>
        </section>
      ))}

      {showForm && (
        <Modal title={editing ? "Sửa công việc" : "Công việc mới"} onClose={() => setShowForm(false)}>
          <form onSubmit={save}>
            <label>Tên công việc<input required autoFocus value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} /></label>
            <label>Mô tả<textarea value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></label>
            <div className="row">
              <label>Hạn chót<input type="datetime-local" value={draft.due_at} onChange={(e) => setDraft({ ...draft, due_at: e.target.value })} /></label>
              <label>Ưu tiên
                <select value={draft.priority} onChange={(e) => setDraft({ ...draft, priority: e.target.value as Priority })}>
                  {Object.entries(PRIORITY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </label>
              <label>Trạng thái
                <select value={draft.status} onChange={(e) => setDraft({ ...draft, status: e.target.value as Status })}>
                  {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </label>
            </div>
            {error && <div className="error">{error}</div>}
            <div className="row end">
              <button type="button" onClick={() => setShowForm(false)}>Huỷ</button>
              <button className="primary">Lưu</button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
