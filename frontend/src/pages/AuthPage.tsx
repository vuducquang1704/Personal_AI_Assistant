import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { IconBell, IconCheck, IconMic, IconSparkle } from "../components/Icons";

export default function AuthPage({ mode }: { mode: "login" | "register" }) {
  const { login, register } = useAuth();
  const nav = useNavigate();
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const isLogin = mode === "login";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (isLogin) await login(form.email, form.password);
      else await register(form.full_name, form.email, form.password);
      nav("/");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth">
      <section className="auth-hero">
        <span className="logo"><IconMic size={24} /></span>
        <h2>Nói một câu, việc đã được ghi lại.</h2>
        <p>Trợ lý AI cá nhân giúp bạn quản lý công việc bằng giọng nói tiếng Việt, từ thêm việc, nhắc hạn đến xem tiến độ.</p>
        <ul>
          <li><IconSparkle size={18} />Hiểu "thứ Sáu tuần sau", "gấp", "8 giờ tối nay"</li>
          <li><IconBell size={18} />Nhắc nhở đúng lúc, đọc to bằng giọng của bạn</li>
          <li><IconCheck size={18} />Mọi thao tác xoá đều cần bạn xác nhận</li>
        </ul>
      </section>
      <section className="auth-form-wrap">
        <form className="auth-form" onSubmit={submit}>
          <h1>{isLogin ? "Chào mừng trở lại" : "Tạo tài khoản"}</h1>
          <p className="muted" style={{ marginTop: 0, marginBottom: "1.4rem" }}>{isLogin ? "Đăng nhập để tiếp tục." : "Chỉ mất một phút để bắt đầu."}</p>
          {!isLogin && (
            <label>Họ và tên
              <input required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
            </label>
          )}
          <label>Email
            <input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </label>
          <label>Mật khẩu
            <input type="password" required minLength={6} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </label>
          {error && <div className="error">{error}</div>}
          <button className="primary" disabled={busy}>{busy ? "Đang xử lý…" : isLogin ? "Đăng nhập" : "Đăng ký"}</button>
          <p className="muted small" style={{ textAlign: "center", marginTop: "1rem" }}>
            {isLogin ? <>Chưa có tài khoản? <Link to="/register">Đăng ký</Link></> : <>Đã có tài khoản? <Link to="/login">Đăng nhập</Link></>}
          </p>
        </form>
      </section>
    </div>
  );
}
