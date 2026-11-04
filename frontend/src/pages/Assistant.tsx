import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useChat } from "../lib/chat";
import { speak, stopSpeaking, sttSupported, useSpeechRecognition } from "../lib/speech";
import type { ChatMessage, PendingAction } from "../lib/types";
import { IconAlert, IconBell, IconChart, IconCheck, IconClock, IconMic, IconPlus, IconSend, IconSparkle, IconSpeaker, IconStop, IconTasks, IconTrash } from "../components/Icons";

interface ChatOut { conversation_id: number; reply: ChatMessage; pending_actions: PendingAction[] }

const SUGGESTIONS: { icon: ReactNode; text: string }[] = [
  { icon: <IconPlus size={18} />, text: "Thêm việc nộp báo cáo đồ án trước 5 giờ chiều thứ Sáu, ưu tiên cao" },
  { icon: <IconTasks size={18} />, text: "Hôm nay mình có những việc gì?" },
  { icon: <IconBell size={18} />, text: "Nhắc mình gọi điện cho thầy lúc 9 giờ sáng mai" },
  { icon: <IconChart size={18} />, text: "Tuần này tiến độ công việc của mình thế nào?" },
];

type Action = ChatMessage["actions"][number];

function describe(a: Action): { icon: ReactNode; cls: string; title: string; meta?: string } | null {
  const task = a.task as { title?: string; due_at?: string | null; priority?: string } | undefined;
  const rem = a.reminder as { message?: string; remind_at?: string } | undefined;
  const prio: Record<string, string> = { high: "Ưu tiên cao", medium: "Ưu tiên trung bình", low: "Ưu tiên thấp" };
  const meta = task ? [task.due_at, task.priority ? prio[task.priority] : null].filter(Boolean).join(" · ") : undefined;
  switch (a.type) {
    case "create_task": return { icon: <IconCheck size={16} />, cls: "create", title: `Đã tạo việc: ${task?.title ?? ""}`, meta };
    case "update_task": return { icon: <IconCheck size={16} />, cls: "", title: `Đã cập nhật: ${task?.title ?? ""}`, meta };
    case "delete_task_requested": return { icon: <IconTrash size={16} />, cls: "delete", title: `Yêu cầu xoá: ${task?.title ?? ""}` };
    case "set_reminder": return { icon: <IconClock size={16} />, cls: "", title: `Đã đặt nhắc nhở: ${rem?.message ?? ""}`, meta: rem?.remind_at };
    case "list_tasks": return { icon: <IconTasks size={16} />, cls: "", title: `Đã tra cứu ${(a.count as number) ?? 0} việc` };
    case "get_statistics": return { icon: <IconChart size={16} />, cls: "", title: "Đã xem thống kê tiến độ" };
    default: return null;
  }
}

function ActionCards({ actions }: { actions: ChatMessage["actions"] }) {
  const items = (actions ?? []).map(describe).filter(Boolean) as NonNullable<ReturnType<typeof describe>>[];
  if (!items.length) return null;
  return (
    <>
      {items.map((it, i) => (
        <div key={i} className={`action-card ${it.cls}`}>
          <span className="ic">{it.icon}</span>
          <div><div className="t">{it.title}</div>{it.meta && <div className="m">{it.meta}</div>}</div>
        </div>
      ))}
    </>
  );
}

export default function Assistant() {
  const { user } = useAuth();
  const voice = user?.voice_settings ?? {};
  const { convId, setConvId, reload: loadConvs, newChatTick } = useChat();
  const justCreated = useRef<number | null>(null);  // cuộc trò chuyện vừa tạo khi gửi tin, đã có sẵn nội dung trong khung
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState<PendingAction[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, busy, pending]);

  // Thanh bên đổi cuộc trò chuyện (hoặc bấm "Trò chuyện mới") -> tải lại nội dung khung chat
  useEffect(() => {
    if (convId !== null && convId === justCreated.current) return;
    stopSpeaking();
    setPending([]);
    setError("");
    if (convId === null) { setMessages([]); return; }
    let stale = false;
    api<ChatMessage[]>(`/api/chat/conversations/${convId}`).then((m) => { if (!stale) setMessages(m); }).catch(() => {});
    return () => { stale = true; };
  }, [convId, newChatTick]);

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
      if (!convId) { justCreated.current = r.conversation_id; setConvId(r.conversation_id); loadConvs(); }
      if (voice.auto_speak !== false || mode === "voice") speak(r.reply.text, voice);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [busy, convId, voice, setConvId, loadConvs]);

  const stt = useSpeechRecognition((t) => send(t, "voice"));

  const decide = async (p: PendingAction, decision: "confirm" | "cancel") => {
    const r = await api<{ message: string }>(`/api/chat/actions/${p.id}/${decision}`, { method: "POST" });
    setPending((list) => list.filter((x) => x.id !== p.id));
    const note: ChatMessage = { id: -Date.now(), role: "assistant", text: r.message, input_mode: "text", actions: [], created_at: new Date().toISOString() };
    setMessages((m) => [...m, note]);
    speak(r.message, voice);
  };

  const submit = (e: FormEvent) => { e.preventDefault(); send(input, "text"); };
  const firstName = user?.full_name?.trim().split(/\s+/).slice(-1)[0] ?? "";

  return (
    <div className="assistant">
      <section className="chat">
        <div className="messages">
          {messages.length === 0 ? (
            <div className="welcome">
              <h2>Xin chào{firstName ? `, ` : ""}<span className="grad">{firstName}</span>!</h2>
              <p className="muted">Bấm micro và nói, hoặc gõ yêu cầu. Mình sẽ lo phần còn lại.</p>
              <div className="suggestions">
                {SUGGESTIONS.map((s) => (
                  <button key={s.text} className="suggestion" onClick={() => send(s.text, "text")}>
                    <span>{s.icon}</span><span>{s.text}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="thread">
              {messages.map((m) => (
                <div key={m.id} className={`msg ${m.role}`}>
                  <span className="avatar">{m.role === "assistant" ? <IconSparkle size={16} /> : (user?.full_name ?? "B").charAt(0).toUpperCase()}</span>
                  <div className="msg-body">
                    <div className="bubble">
                      {m.input_mode === "voice" && <span className="voice-tag" title="Nói bằng giọng"><IconMic size={14} /></span>}
                      {m.text}
                      {m.role === "assistant" && (
                        <button className="icon-btn speak" onClick={() => speak(m.text, voice)} title="Đọc lại" aria-label="Đọc lại"><IconSpeaker size={16} /></button>
                      )}
                    </div>
                    {m.role === "assistant" && <ActionCards actions={m.actions} />}
                  </div>
                </div>
              ))}
              {pending.map((p) => (
                <div key={p.id} className="confirm">
                  <IconAlert size={18} /><span>{p.summary}?</span>
                  <button className="danger" onClick={() => decide(p, "confirm")}>Xác nhận</button>
                  <button onClick={() => decide(p, "cancel")}>Huỷ</button>
                </div>
              ))}
              {busy && (
                <div className="msg assistant">
                  <span className="avatar"><IconSparkle size={16} /></span>
                  <div className="msg-body"><div className="bubble"><span className="typing"><i /><i /><i /></span></div></div>
                </div>
              )}
              <div ref={endRef} />
            </div>
          )}
        </div>
        <div className="composer-wrap">
          {(error || stt.error) && <div className="error">{error || stt.error}</div>}
          {stt.listening && <div className="listening-hint">Đang nghe… {stt.interim && <span className="muted">“{stt.interim}”</span>}</div>}
          <form className="composer" onSubmit={submit}>
            <button
              type="button"
              className={`mic ${stt.listening ? "on" : ""}`}
              onClick={stt.listening ? stt.stop : stt.start}
              disabled={busy || !sttSupported()}
              title={sttSupported() ? (stt.listening ? "Bấm để dừng" : "Bấm để nói") : "Trình duyệt không hỗ trợ nhận dạng giọng nói, hãy dùng Chrome hoặc Edge"}
              aria-label="Nói"
            >{stt.listening ? <IconStop size={20} /> : <IconMic size={22} />}</button>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Nhập yêu cầu, ví dụ: thêm việc họp nhóm 3 giờ chiều mai"
              disabled={stt.listening}
              aria-label="Nhập yêu cầu"
            />
            <button className="primary send" disabled={busy || !input.trim()} aria-label="Gửi"><IconSend size={18} /></button>
          </form>
        </div>
      </section>
    </div>
  );
}
