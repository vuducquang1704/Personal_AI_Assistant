import { Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./lib/auth";
import { ChatProvider, useChat } from "./lib/chat";
import { api } from "./lib/api";
import { useTheme } from "./lib/theme";
import ReminderWatcher from "./components/ReminderWatcher";
import { IconChart, IconLogout, IconMic, IconMoon, IconPlus, IconSettings, IconSun, IconTasks, IconTrash } from "./components/Icons";
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

/** Mục "Trợ lý" kèm nút trò chuyện mới và danh sách trò chuyện gần đây, nằm gọn trong thanh bên. */
function AssistantNav() {
  const { convs, convId, setConvId, startNew, reload } = useChat();
  const nav = useNavigate();
  const onAssistant = useLocation().pathname === "/";
  const open = (id: number | null) => { if (id === null) startNew(); else setConvId(id); nav("/"); };
  const remove = async (id: number, title: string) => {
    if (!confirm(`Xoá cuộc trò chuyện "${title}"? Việc này không thể hoàn tác.`)) return;
    try {
      await api(`/api/chat/conversations/${id}`, { method: "DELETE" });
      if (id === convId) startNew();
      await reload();
    } catch (e) {
      alert((e as Error).message);
    }
  };
  return (
    <div className="nav-group">
      <NavLink to="/" end><IconMic />Trợ lý</NavLink>
      <div className="subnav">
        <button className="new-chat" onClick={() => open(null)}><IconPlus size={16} />Trò chuyện mới</button>
        {convs.length > 0 && <h4>Gần đây</h4>}
        <div className="recent">
          {convs.map((c) => (
            <div key={c.id} className={`conv-row ${onAssistant && c.id === convId ? "active" : ""}`}>
              <button className="conv" onClick={() => open(c.id)} title={c.title}>{c.title}</button>
              <button className="conv-del" onClick={() => remove(c.id, c.title)} title="Xoá cuộc trò chuyện" aria-label={`Xoá cuộc trò chuyện ${c.title}`}><IconTrash size={14} /></button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function NewChatButton() {
  const { startNew } = useChat();
  const nav = useNavigate();
  return <button className="icon-btn" onClick={() => { startNew(); nav("/"); }} title="Trò chuyện mới" aria-label="Trò chuyện mới"><IconPlus /></button>;
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
          <AssistantNav />
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
            <NewChatButton />
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
      <ChatProvider>
        <Shell />
      </ChatProvider>
    </AuthProvider>
  );
}
