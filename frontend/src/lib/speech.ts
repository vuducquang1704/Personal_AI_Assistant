/**
 * Nhận dạng giọng nói (Speech-to-Text) và tổng hợp giọng nói (Text-to-Speech) tiếng Việt
 * dùng Web Speech API của trình duyệt (Chrome/Edge hỗ trợ vi-VN tốt nhất).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { VoiceSettings } from "./types";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyRecognition = any;

function getRecognitionCtor(): AnyRecognition | null {
  const w = window as unknown as Record<string, unknown>;
  return (w.SpeechRecognition || w.webkitSpeechRecognition || null) as AnyRecognition;
}

export const sttSupported = () => !!getRecognitionCtor();
export const ttsSupported = () => "speechSynthesis" in window;

export function useSpeechRecognition(onFinal: (text: string) => void) {
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const recRef = useRef<AnyRecognition>(null);
  const onFinalRef = useRef(onFinal);
  onFinalRef.current = onFinal;

  const start = useCallback(() => {
    const Ctor = getRecognitionCtor();
    if (!Ctor) {
      setError("Trình duyệt không hỗ trợ nhận dạng giọng nói. Hãy dùng Chrome hoặc Edge.");
      return;
    }
    window.speechSynthesis?.cancel(); // dừng trợ lý đang nói để nghe người dùng
    const rec = new Ctor();
    rec.lang = "vi-VN";
    rec.interimResults = true;
    rec.continuous = false;
    rec.maxAlternatives = 1;
    let finalText = "";
    rec.onresult = (e: AnyRecognition) => {
      let partial = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) finalText += r[0].transcript;
        else partial += r[0].transcript;
      }
      setInterim(finalText + partial);
    };
    rec.onerror = (e: AnyRecognition) => {
      const map: Record<string, string> = {
        "not-allowed": "Bạn chưa cho phép dùng micro.",
        "no-speech": "Không nghe thấy gì, bạn thử nói lại nhé.",
        network: "Lỗi mạng khi nhận dạng giọng nói.",
      };
      setError(map[e.error] ?? `Lỗi nhận dạng: ${e.error}`);
    };
    rec.onend = () => {
      setListening(false);
      setInterim("");
      if (finalText.trim()) onFinalRef.current(finalText.trim());
    };
    setError(null);
    recRef.current = rec;
    rec.start();
    setListening(true);
  }, []);

  const stop = useCallback(() => recRef.current?.stop(), []);
  useEffect(() => () => recRef.current?.abort?.(), []);
  return { listening, interim, error, start, stop };
}

export function useVietnameseVoices() {
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  useEffect(() => {
    if (!ttsSupported()) return;
    const load = () => {
      const all = window.speechSynthesis.getVoices();
      const vi = all.filter((v) => v.lang.toLowerCase().startsWith("vi"));
      setVoices(vi.length ? vi : all);
    };
    load();
    window.speechSynthesis.addEventListener("voiceschanged", load);
    return () => window.speechSynthesis.removeEventListener("voiceschanged", load);
  }, []);
  return voices;
}

export function speak(text: string, settings: Partial<VoiceSettings> = {}, onEnd?: () => void) {
  if (!ttsSupported() || !text) return;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "vi-VN";
  u.rate = settings.rate ?? 1;
  u.pitch = settings.pitch ?? 1;
  const voices = window.speechSynthesis.getVoices();
  const chosen =
    voices.find((v) => v.name === settings.voice) ?? voices.find((v) => v.lang.toLowerCase().startsWith("vi"));
  if (chosen) u.voice = chosen;
  if (onEnd) u.onend = onEnd;
  window.speechSynthesis.speak(u);
}

export const stopSpeaking = () => window.speechSynthesis?.cancel();
