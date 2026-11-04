import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../lib/api";

type GoogleStatus = {
  configured: boolean;
  connected: boolean;
  email: string | null;
  sync_enabled: boolean;
  reminder_minutes: number;
  last_error: string | null;
};

const RESULT_TEXT: Record<string, [string, string]> = {
  connected: ["ok", "Đã kết nối Google Calendar. Các việc có hạn chót đã được đưa lên lịch."],
  denied: ["error", "Bạn đã huỷ cấp quyền cho Google Calendar."],
  error: ["error", "Kết nối Google không thành công, hãy thử lại."],
};

type Email = { id: string; from: string; subject: string; snippet: string; category: string; important: boolean; summary: string | null };
type EmailList = { items: Email[]; counts: Record<string, number>; labels: Record<string, string>; important: number };
const ORDER = ["needs_reply", "read_later", "notice", "promo"];

/** Lọc email chưa đọc 3 ngày gần đây theo nhóm, và tạo việc "Trả lời ..." cho email cần phản hồi. */
function EmailSection() {
  const [data, setData] = useState<EmailList | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<[string, string] | null>(null);
  const [open, setOpen] = useState<string>("needs_reply");

  const load = async (summarize = false) => {
    setBusy(true); setNote(null);
    try { setData(await api<EmailList>(`/api/google/emails${summarize ? "?summarize=true" : ""}`)); }
    catch (e) { setNote(["error", (e as Error).message]); }
    finally { setBusy(false); }
  };
  const makeTasks = async () => {
    setBusy(true);
    try {
      const r = await api<{ created: number }>("/api/google/emails/tasks", { method: "POST" });
      setNote(["ok", r.created ? `Đã tạo ${r.created} việc trả lời email, hạn 17:00 hôm nay.` : "Các email cần trả lời đều đã có việc."]);
    } catch (e) { setNote(["error", (e as Error).message]); }
    finally { setBusy(false); }
  };

  return (
    <div className="email-box">
      <h4>Email cần trả lời</h4>
      <p className="muted small">Mỗi sáng 8 giờ, trợ lý đọc email chưa đọc trong 3 ngày gần đây, tóm tắt các email quan trọng, tạo việc cho email cần trả lời và nhắc bạn. Bạn cũng có thể hỏi trợ lý bằng giọng nói: “có email nào quan trọng không?”. Trợ lý chỉ đọc, không gửi hay xoá email.</p>
      {note && <div className={note[0]}>{note[1]}</div>}
      {data && (
        <div className="email-groups">
          {ORDER.map((k) => (
            <div key={k} className="email-group">
              <button type="button" className={`email-tab ${open === k ? "active" : ""}`} onClick={() => setOpen(k)}>
                {data.labels[k]} <b>{data.counts[k] ?? 0}</b>
              </button>
            </div>
          ))}
          <ul className="email-list">
            {data.items.filter((i) => i.category === open).map((i) => (
              <li key={i.id}>
                <b>{i.important && <span className="badge-imp">Quan trọng</span>}{i.subject}</b>
                <span className="muted small">{i.from}</span>
                <span className="small">{i.summary ? `Tóm tắt: ${i.summary}` : i.snippet}</span>
              </li>
            ))}
            {!data.items.some((i) => i.category === open) && <li className="muted small">Không có email nào.</li>}
          </ul>
        </div>
      )}
      <div className="row end">
        <button type="button" disabled={busy} onClick={() => load(false)}>{data ? "Tải lại" : "Kiểm tra email"}</button>
        <button type="button" disabled={busy || !data || !data.important} onClick={() => load(true)} title="Dùng AI tóm tắt các email quan trọng">Tóm tắt email quan trọng{data ? ` (${data.important})` : ""}</button>
        <button type="button" className="primary" disabled={busy || !data || !data.counts.needs_reply} onClick={makeTasks}>Tạo việc trả lời</button>
      </div>
    </div>
  );
}

/** Thẻ kết nối và cấu hình đồng bộ Google Calendar trong trang Cài đặt. */
export default function GoogleCalendarCard() {
  const [params, setParams] = useSearchParams();
  const [st, setSt] = useState<GoogleStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<[string, string] | null>(null);

  useEffect(() => {
    const r = params.get("google");
    if (r && RESULT_TEXT[r]) {
      setNote(RESULT_TEXT[r]);
      params.delete("google");
      setParams(params, { replace: true });
    }
    api<GoogleStatus>("/api/google/status").then(setSt).catch(() => setSt(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    try { await fn(); } catch (e) { setNote(["error", (e as Error).message]); } finally { setBusy(false); }
  };

  const connect = () => run(async () => {
    const { url } = await api<{ url: string }>("/api/google/auth-url");
    window.location.href = url;
  });
  const patch = (body: Partial<GoogleStatus>) => run(async () => setSt(await api<GoogleStatus>("/api/google", { method: "PATCH", body })));
  const syncNow = () => run(async () => {
    const r = await api<GoogleStatus & { synced: number }>("/api/google/sync", { method: "POST" });
    setSt(r);
    setNote(["ok", `Đã đồng bộ ${r.synced} công việc lên Google Calendar.`]);
  });
  const disconnect = () => {
    if (!confirm("Ngắt kết nối Google Calendar? Các sự kiện đã tạo vẫn giữ trên lịch của bạn.")) return;
    run(async () => {
      await api("/api/google", { method: "DELETE" });
      setSt(await api<GoogleStatus>("/api/google/status"));
      setNote(["ok", "Đã ngắt kết nối Google Calendar."]);
    });
  };

  return (
    <div className="card form">
      <h3>Google Calendar và Gmail</h3>
      <p className="muted small">
        Việc có hạn chót được tạo thành sự kiện trên lịch Google kèm thông báo nhắc trước hạn. Việc hoàn thành hoặc bị xoá sẽ tự gỡ khỏi lịch.
      </p>
      {note && <div className={note[0]}>{note[1]}</div>}
      {!st ? (
        <p className="muted small">Đang tải…</p>
      ) : !st.configured ? (
        <p className="error">Máy chủ chưa cấu hình GOOGLE_CLIENT_ID và GOOGLE_CLIENT_SECRET (xem README, mục Google Calendar).</p>
      ) : !st.connected ? (
        <div className="row end"><button className="primary" disabled={busy} onClick={connect}>Kết nối Google Calendar</button></div>
      ) : (
        <>
          <p>Đã kết nối với <b>{st.email ?? "tài khoản Google"}</b></p>
          {st.last_error && <p className="error">Lần đồng bộ gần nhất bị lỗi: {st.last_error}</p>}
          <label className="check">
            <input type="checkbox" checked={st.sync_enabled} disabled={busy} onChange={(e) => patch({ sync_enabled: e.target.checked })} />
            Tự động đồng bộ công việc lên lịch
          </label>
          <label>Nhắc trước hạn
            <select value={st.reminder_minutes} disabled={busy} onChange={(e) => patch({ reminder_minutes: +e.target.value })}>
              {[0, 10, 15, 30, 60, 120, 1440].map((m) => (
                <option key={m} value={m}>{m === 0 ? "Đúng giờ" : m < 60 ? `${m} phút` : m === 1440 ? "1 ngày" : `${m / 60} giờ`}</option>
              ))}
            </select>
          </label>
          <div className="row end">
            <button type="button" disabled={busy} onClick={disconnect}>Ngắt kết nối</button>
            {st.last_error && <button type="button" disabled={busy} onClick={connect}>Kết nối lại</button>}
            <button type="button" className="primary" disabled={busy || !st.sync_enabled} onClick={syncNow}>Đồng bộ ngay</button>
          </div>
          <EmailSection />
        </>
      )}
    </div>
  );
}
