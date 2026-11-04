import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";

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
      <form className="card" onSubmit={submit}>
        <h1>{isLogin ? "Đăng nhập" : "Tạo tài khoản"}</h1>
        <p className="muted">Trợ lý AI cá nhân hỗ trợ công việc bằng giọng nói</p>
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
        <p className="muted small">
          {isLogin ? <>Chưa có tài khoản? <Link to="/register">Đăng ký</Link></> : <>Đã có tài khoản? <Link to="/login">Đăng nhập</Link></>}
        </p>
      </form>
    </div>
  );
}
