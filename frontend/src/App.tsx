import { Navigate, NavLink, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./lib/auth";
import { useTheme } from "./lib/theme";
import ReminderWatcher from "./components/ReminderWatcher";
import { IconChart, IconLogout, IconMic, IconMoon, IconSettings, IconSun, IconTasks } from "./components/Icons";
import AuthPage from "./pages/AuthPage";
import Dashboard from "./pages/Dashboard";
import Tasks from "./pages/Tasks";
import Assistant from "./pages/Assistant";
import Settings from "./pages/Settings";

function ThemeButton() {
  const { theme, toggle } = useTheme();
  return (
    <button className="icon-btn" onClick={toggle} title={theme === "dark" ? "Chế độ sáng" : "Chế độ tối"} aria-label="Đổi giao diện sáng/tối">
      {theme === "dark" ? <IconSun /> : <IconMoon />}
    </button>
  );
}

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
  const initial = (user.full_name || user.email).trim().charAt(0).toUpperCase();
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand"><span className="logo"><IconMic size={18} /></span>Trợ lý AI</div>
        <nav className="nav">
          <NavLink to="/" end><IconMic />Trợ lý</NavLink>
          <NavLink to="/tasks"><IconTasks />Công việc</NavLink>
          <NavLink to="/dashboard"><IconChart />Thống kê</NavLink>
          <NavLink to="/settings"><IconSettings />Cài đặt</NavLink>
        </nav>
        <div className="side-foot">
          <div className="user-chip" title={user.email}>
            <span className="avatar">{initial}</span>
            <span className="name">{user.full_name}</span>
          </div>
          <div className="row">
            <ThemeButton />
            <button className="ghost" onClick={logout} style={{ flex: 1 }}><IconLogout size={18} />Đăng xuất</button>
          </div>
        </div>
      </aside>
      <div className="content">
        <div className="mobile-top">
          <div className="brand"><span className="logo"><IconMic size={18} /></span>Trợ lý AI</div>
          <div className="row" style={{ gap: 0 }}>
            <ThemeButton />
            <button className="icon-btn" onClick={logout} aria-label="Đăng xuất"><IconLogout /></button>
          </div>
        </div>
        <main>
          <Routes>
            <Route path="/" element={<Assistant />} />
            <Route path="/tasks" element={<Tasks />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </main>
      </div>
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
