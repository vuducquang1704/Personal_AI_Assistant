import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { speak } from "../lib/speech";
import type { Reminder } from "../lib/types";
import { IconBell } from "./Icons";

/** Hỏi server mỗi 30 giây, hiện thông báo và đọc to các nhắc nhở đến hạn. */
export default function ReminderWatcher() {
  const { user } = useAuth();
  const [items, setItems] = useState<Reminder[]>([]);

  useEffect(() => {
    if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
    let shown = new Set<number>();
    const poll = async () => {
      try {
        const due = await api<Reminder[]>("/api/reminders/due");
        const fresh = due.filter((r) => !shown.has(r.id));
        fresh.forEach((r) => {
          const text = r.message.replace(/^\[auto\]\s*/, "");
          if ("Notification" in window && Notification.permission === "granted") new Notification("Nhắc nhở", { body: text });
          speak(`Nhắc nhở: ${text}`, user?.voice_settings);
        });
        shown = new Set(due.map((r) => r.id));
        setItems(due);
      } catch { /* bỏ qua lỗi mạng tạm thời */ }
    };
    poll();
    const id = setInterval(poll, 30_000);
    return () => clearInterval(id);
  }, [user]);

  const dismiss = async (r: Reminder) => {
    await api(`/api/reminders/${r.id}/seen`, { method: "POST" });
    setItems((list) => list.filter((x) => x.id !== r.id));
  };

  if (!items.length) return null;
  return (
    <div className="toasts">
      {items.map((r) => (
        <div key={r.id} className="toast">
          <span className="ic"><IconBell size={18} /></span><span>{r.message.replace(/^\[auto\]\s*/, "")}</span>
          <button className="link" onClick={() => dismiss(r)}>Đã xem</button>
        </div>
      ))}
    </div>
  );
}
