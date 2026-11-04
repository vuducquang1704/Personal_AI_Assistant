import { useState, type FormEvent } from "react";
import GoogleCalendarCard from "../components/GoogleCalendarCard";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { speak, sttSupported, ttsSupported, useVietnameseVoices } from "../lib/speech";
import type { VoiceSettings } from "../lib/types";

export default function Settings() {
  const { user, refresh } = useAuth();
  const voices = useVietnameseVoices();
  const [name, setName] = useState(user?.full_name ?? "");
  const [vs, setVs] = useState<VoiceSettings>({ voice: null, rate: 1, pitch: 1, auto_speak: true, ...user?.voice_settings });
  const [pw, setPw] = useState({ old_password: "", new_password: "" });
  const [msg, setMsg] = useState("");

  const save = async (e: FormEvent) => {
    e.preventDefault();
    await api("/api/auth/me", { method: "PATCH", body: { full_name: name, voice_settings: vs } });
    await refresh();
    setMsg("Đã lưu cài đặt.");
  };
  const changePw = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api("/api/auth/change-password", { body: pw });
      setPw({ old_password: "", new_password: "" });
      setMsg("Đã đổi mật khẩu.");
    } catch (err) { setMsg((err as Error).message); }
  };

  return (
    <div className="page narrow">
      <h1>Cài đặt</h1>
      {msg && <div className="ok">{msg}</div>}
      <form className="card form" onSubmit={save}>
        <h3>Tài khoản</h3>
        <label>Email<input value={user?.email} disabled /></label>
        <label>Họ và tên<input value={name} onChange={(e) => setName(e.target.value)} /></label>
        <h3>Giọng nói của trợ lý</h3>
        {!ttsSupported() && <p className="error">Trình duyệt không hỗ trợ đọc văn bản.</p>}
        {!sttSupported() && <p className="error">Trình duyệt không hỗ trợ nhận dạng giọng nói, hãy dùng Chrome hoặc Edge.</p>}
        <label>Giọng đọc
          <select value={vs.voice ?? ""} onChange={(e) => setVs({ ...vs, voice: e.target.value || null })}>
            <option value="">Tự động (giọng tiếng Việt đầu tiên)</option>
            {voices.map((v) => <option key={v.name} value={v.name}>{v.name} ({v.lang})</option>)}
          </select>
        </label>
        <label>Tốc độ: {vs.rate.toFixed(1)}x<input type="range" min={0.5} max={2} step={0.1} value={vs.rate} onChange={(e) => setVs({ ...vs, rate: +e.target.value })} /></label>
        <label>Cao độ: {vs.pitch.toFixed(1)}<input type="range" min={0} max={2} step={0.1} value={vs.pitch} onChange={(e) => setVs({ ...vs, pitch: +e.target.value })} /></label>
        <label className="check"><input type="checkbox" checked={vs.auto_speak} onChange={(e) => setVs({ ...vs, auto_speak: e.target.checked })} /> Tự động đọc câu trả lời</label>
        <div className="row end">
          <button type="button" onClick={() => speak("Xin chào, mình là trợ lý AI của bạn. Hôm nay bạn có ba việc cần làm.", vs)}>Nghe thử</button>
          <button className="primary">Lưu</button>
        </div>
      </form>
      <GoogleCalendarCard />
      <form className="card form" onSubmit={changePw}>
        <h3>Đổi mật khẩu</h3>
        <label>Mật khẩu hiện tại<input type="password" required value={pw.old_password} onChange={(e) => setPw({ ...pw, old_password: e.target.value })} /></label>
        <label>Mật khẩu mới<input type="password" required minLength={6} value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} /></label>
        <div className="row end"><button className="primary">Đổi mật khẩu</button></div>
      </form>
    </div>
  );
}
