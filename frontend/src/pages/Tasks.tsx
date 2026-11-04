import { useEffect, useState, type FormEvent } from "react";
import { api, formatDate, fromInputValue, toInputValue } from "../lib/api";
import { PRIORITY_LABEL, STATUS_LABEL, type Priority, type Status, type Task } from "../lib/types";

type Draft = { title: string; description: string; due_at: string; priority: Priority; status: Status };
const EMPTY: Draft = { title: "", description: "", due_at: "", priority: "medium", status: "todo" };

export default function Tasks() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [filter, setFilter] = useState<{ status: string; priority: string; q: string }>({ status: "", priority: "", q: "" });
  const [editing, setEditing] = useState<Task | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    const params = new URLSearchParams(Object.entries(filter).filter(([, v]) => v));
    setTasks(await api<Task[]>(`/api/tasks?${params}`));
  };
  useEffect(() => { load(); }, [filter]); // eslint-disable-line react-hooks/exhaustive-deps

  const openNew = () => { setEditing(null); setDraft(EMPTY); setShowForm(true); };
  const openEdit = (t: Task) => {
    setEditing(t);
    setDraft({ title: t.title, description: t.description ?? "", due_at: toInputValue(t.due_at), priority: t.priority, status: t.status });
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

  const setStatus = async (t: Task, status: Status) => { await api(`/api/tasks/${t.id}`, { method: "PATCH", body: { status } }); load(); };
  const remove = async (t: Task) => {
    if (!confirm(`Xoá công việc "${t.title}"?`)) return;
    await api(`/api/tasks/${t.id}`, { method: "DELETE" });
    load();
  };
  const overdue = (t: Task) => t.status !== "done" && t.due_at && new Date(t.due_at) < new Date();

  return (
    <div className="page">
      <div className="toolbar">
        <h1>Công việc</h1>
        <button className="primary" onClick={openNew}>+ Thêm việc</button>
      </div>
      <div className="filters">
        <input placeholder="Tìm kiếm…" value={filter.q} onChange={(e) => setFilter({ ...filter, q: e.target.value })} />
        <select value={filter.status} onChange={(e) => setFilter({ ...filter, status: e.target.value })}>
          <option value="">Mọi trạng thái</option>
          {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select value={filter.priority} onChange={(e) => setFilter({ ...filter, priority: e.target.value })}>
          <option value="">Mọi mức ưu tiên</option>
          {Object.entries(PRIORITY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </div>

      {showForm && (
        <form className="card form" onSubmit={save}>
          <h3>{editing ? "Sửa công việc" : "Công việc mới"}</h3>
          <label>Tên công việc<input required value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} /></label>
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
      )}

      {tasks.length === 0 && <p className="muted">Chưa có công việc nào. Thêm bằng nút trên hoặc nói với trợ lý.</p>}
      <ul className="tasks">
        {tasks.map((t) => (
          <li key={t.id} className={`task ${t.status} ${overdue(t) ? "overdue" : ""}`}>
            <input type="checkbox" checked={t.status === "done"} onChange={() => setStatus(t, t.status === "done" ? "todo" : "done")} />
            <div className="grow" onClick={() => openEdit(t)}>
              <div className="title">{t.title}</div>
              {t.description && <div className="muted small">{t.description}</div>}
              <div className="meta">
                <span className={`badge p-${t.priority}`}>{PRIORITY_LABEL[t.priority]}</span>
                <span className="badge">{STATUS_LABEL[t.status]}</span>
                <span className={overdue(t) ? "danger-text" : "muted"}>{overdue(t) ? "Quá hạn · " : ""}{formatDate(t.due_at)}</span>
              </div>
            </div>
            <button className="link" onClick={() => remove(t)} title="Xoá">🗑️</button>
          </li>
        ))}
      </ul>
    </div>
  );
}
