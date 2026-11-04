import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { speak, stopSpeaking, sttSupported, useSpeechRecognition } from "../lib/speech";
import type { ChatMessage, PendingAction } from "../lib/types";

interface Conv { id: number; title: string; created_at: string }
interface ChatOut { conversation_id: number; reply: ChatMessage; pending_actions: PendingAction[] }

const SUGGESTIONS = [
  "Thêm việc nộp báo cáo đồ án trước 5 giờ chiều thứ Sáu, ưu tiên cao",
  "Hôm nay mình có những việc gì?",
  "Nhắc mình gọi điện cho thầy lúc 9 giờ sáng mai",
  "Đánh dấu việc nộp báo cáo là đã xong",
  "Tuần này tiến độ công việc của mình thế nào?",
];

function ActionChips({ actions }: { actions: ChatMessage["actions"] }) {
  const label: Record<string, string> = {
    create_task: "Đã tạo việc", update_task: "Đã cập nhật", list_tasks: "Đã tra cứu",
    delete_task_requested: "Yêu cầu xoá", set_reminder: "Đã đặt nhắc nhở", get_statistics: "Đã xem thống kê",
  };
  if (!actions?.length) return null;
  return (
    <div className="chips">
      {actions.map((a, i) => {
        const task = a.task as { title?: string } | undefined;
        return <span key={i} className="chip">{label[a.type] ?? a.type}{task?.title ? `: ${task.title}` : ""}</span>;
      })}
    </div>
  );
}

export default function Assistant() {
  const { user } = useAuth();
  const voice = user?.voice_settings ?? {};
  const [convs, setConvs] = useState<Conv[]>([]);
  const [convId, setConvId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState<PendingAction[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  const loadConvs = () => api<Conv[]>("/api/chat/conversations").then(setConvs).catch(() => {});
  useEffect(() => { loadConvs(); }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, busy]);

  const openConv = async (id: number | null) => {
    stopSpeaking();
    setConvId(id);
    setPending([]);
    setMessages(id ? await api<ChatMessage[]>(`/api/chat/conversations/${id}`) : []);
  };

  const send = useCallback(async (text: string, mode: "text" | "voice") => {
    if (!text.trim() || busy) return;
    setError("");
    setBusy(true);
    const temp: ChatMessage = { id: -Date.now(), role: "user", text, input_mode: mode, actions: [], created_at: new Date().toISOString() };
    setMessages((m) => [...m, temp]);
    setInput("");
    try {
      const r = await api<ChatOut>("/api/chat", { body: { message: text, conversation_id: convId, input_mode: mode } });
      setMessages((m) => [...m, r.reply]);
      setPending((p) => [...p, ...r.pending_actions]);
      if (!convId) { setConvId(r.conversation_id); loadConvs(); }
      if (voice.auto_speak !== false || mode === "voice") speak(r.reply.text, voice);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [busy, convId, voice]);

  const stt = useSpeechRecognition((t) => send(t, "voice"));

  const decide = async (p: PendingAction, decision: "confirm" | "cancel") => {
    const r = await api<{ message: string }>(`/api/chat/actions/${p.id}/${decision}`, { method: "POST" });
    setPending((list) => list.filter((x) => x.id !== p.id));
    const note: ChatMessage = { id: -Date.now(), role: "assistant", text: r.message, input_mode: "text", actions: [], created_at: new Date().toISOString() };
    setMessages((m) => [...m, note]);
    speak(r.message, voice);
  };

  const submit = (e: FormEvent) => { e.preventDefault(); send(input, "text"); };

  return (
    <div className="assistant">
      <aside className="convs">
        <button className="primary block" onClick={() => openConv(null)}>+ Cuộc trò chuyện mới</button>
        {convs.map((c) => (
          <button key={c.id} className={`conv ${c.id === convId ? "active" : ""}`} onClick={() => openConv(c.id)}>{c.title}</button>
        ))}
      </aside>
      <section className="chat">
        <div className="messages">
          {messages.length === 0 && (
            <div className="welcome">
              <h2>Xin chào{user ? `, ${user.full_name}` : ""}!</h2>
              <p className="muted">Bấm micro và nói, hoặc gõ yêu cầu. Ví dụ:</p>
              {SUGGESTIONS.map((s) => <button key={s} className="suggestion" onClick={() => send(s, "text")}>{s}</button>)}
            </div>
          )}
          {messages.map((m) => (
            <div key={m.id} className={`msg ${m.role}`}>
              <div className="bubble">
                {m.input_mode === "voice" && <span title="Nói bằng giọng">🎤 </span>}
                {m.text}
                {m.role === "assistant" && <button className="link small" onClick={() => speak(m.text, voice)} title="Đọc lại">🔊</button>}
              </div>
              {m.role === "assistant" && <ActionChips actions={m.actions} />}
            </div>
          ))}
          {pending.map((p) => (
            <div key={p.id} className="confirm">
              <span>⚠️ {p.summary}?</span>
              <button className="danger" onClick={() => decide(p, "confirm")}>Xác nhận</button>
              <button onClick={() => decide(p, "cancel")}>Huỷ</button>
            </div>
          ))}
          {busy && <div className="msg assistant"><div className="bubble typing">Đang suy nghĩ…</div></div>}
          <div ref={endRef} />
        </div>
        {(error || stt.error) && <div className="error">{error || stt.error}</div>}
        <form className="composer" onSubmit={submit}>
          <button
            type="button"
            className={`mic ${stt.listening ? "on" : ""}`}
            onClick={stt.listening ? stt.stop : stt.start}
            disabled={busy || !sttSupported()}
            title={sttSupported() ? "Bấm để nói" : "Trình duyệt không hỗ trợ nhận dạng giọng nói"}
          >🎤</button>
          <input
            value={stt.listening ? stt.interim || "Đang nghe…" : input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Nhập yêu cầu, ví dụ: thêm việc họp nhóm 3 giờ chiều mai"
            disabled={stt.listening}
          />
          <button className="primary" disabled={busy || !input.trim()}>Gửi</button>
        </form>
      </section>
    </div>
  );
}
