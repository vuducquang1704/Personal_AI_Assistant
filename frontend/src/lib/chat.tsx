import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "./api";
import { useAuth } from "./auth";

export interface Conv { id: number; title: string; created_at: string }

interface ChatCtx {
  convs: Conv[];
  convId: number | null;
  setConvId: (id: number | null) => void;
  reload: () => Promise<void>;
  /** Tăng mỗi lần bấm "Trò chuyện mới" để trang Trợ lý xoá khung chat dù convId vốn đã là null. */
  newChatTick: number;
  startNew: () => void;
}

const Ctx = createContext<ChatCtx>(null!);
export const useChat = () => useContext(Ctx);

/** Giữ danh sách và cuộc trò chuyện đang mở ở cấp ứng dụng để thanh bên và trang Trợ lý dùng chung. */
export function ChatProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [convs, setConvs] = useState<Conv[]>([]);
  const [convId, setConvId] = useState<number | null>(null);
  const [newChatTick, setTick] = useState(0);

  const reload = useCallback(async () => {
    try { setConvs(await api<Conv[]>("/api/chat/conversations")); } catch { /* bỏ qua */ }
  }, []);
  useEffect(() => { if (user) reload(); }, [user, reload]);

  const startNew = useCallback(() => { setConvId(null); setTick((t) => t + 1); }, []);
  return <Ctx.Provider value={{ convs, convId, setConvId, reload, newChatTick, startNew }}>{children}</Ctx.Provider>;
}
