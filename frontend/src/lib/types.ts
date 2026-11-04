export type Priority = "low" | "medium" | "high";
export type Status = "todo" | "in_progress" | "done";

export interface Task {
  id: number;
  title: string;
  description: string | null;
  due_at: string | null;
  priority: Priority;
  status: Status;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface VoiceSettings {
  voice: string | null;
  rate: number;
  pitch: number;
  auto_speak: boolean;
}

export interface User {
  id: number;
  email: string;
  full_name: string;
  voice_settings: Partial<VoiceSettings>;
}

export interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  text: string;
  input_mode: "text" | "voice";
  actions: Array<Record<string, unknown> & { type: string }>;
  created_at: string;
}

export interface PendingAction {
  id: number;
  kind: string;
  summary: string;
}

export interface Reminder {
  id: number;
  task_id: number | null;
  message: string;
  remind_at: string;
  fired_at: string | null;
  seen: boolean;
}

export interface Stats {
  total: number;
  todo: number;
  in_progress: number;
  done: number;
  overdue: number;
  due_today: number;
  due_this_week: number;
  by_priority: Record<Priority, number>;
  completion_rate: number;
  completed_last_7_days: { date: string; count: number }[];
}

export const PRIORITY_LABEL: Record<Priority, string> = { low: "Thấp", medium: "Trung bình", high: "Cao" };
export const STATUS_LABEL: Record<Status, string> = { todo: "Cần làm", in_progress: "Đang làm", done: "Hoàn thành" };
