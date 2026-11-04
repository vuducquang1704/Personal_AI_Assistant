import { Navigate, NavLink, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./lib/auth";
import ReminderWatcher from "./components/ReminderWatcher";
import AuthPage from "./pages/AuthPage";
import Dashboard from "./pages/Dashboard";
import Tasks from "./pages/Tasks";
import Assistant from "./pages/Assistant";
import Settings from "./pages/Settings";

function Shell() {
  const { user, loading, logout } = useAuth();
  if (loading) return <div className="center muted">Đang tải…</div>;
  if (!user)
    return (
      <Routes>
        <Route path="/register" element={<AuthPage mode="register" />} />
        <Route path="*" element={<AuthPage mode="login" />} />
      </Routes>
    );
  return (
    <div className="layout">
      <header className="topbar">
        <span className="brand">🎙️ Trợ lý AI</span>
        <nav>
          <NavLink to="/" end>Trợ lý</NavLink>
          <NavLink to="/tasks">Công việc</NavLink>
          <NavLink to="/dashboard">Thống kê</NavLink>
          <NavLink to="/settings">Cài đặt</NavLink>
        </nav>
        <button className="link" onClick={logout} title={user.email}>Đăng xuất</button>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Assistant />} />
          <Route path="/tasks" element={<Tasks />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </main>
      <ReminderWatcher />
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Shell />
    </AuthProvider>
  );
}
