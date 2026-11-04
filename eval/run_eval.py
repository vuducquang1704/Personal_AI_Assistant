"""Đánh giá khả năng hiểu câu lệnh tiếng Việt của trợ lý (nhận dạng ý định + trích xuất thông tin).

Chạy: (trong thư mục backend, đã đặt ANTHROPIC_API_KEY)
    python ../eval/run_eval.py [--cases ../eval/commands_vi.jsonl] [--only 1,2,3]

Mỗi ca kiểm thử chạy trên một người dùng mới trong CSDL SQLite riêng, với "thời điểm hiện tại" cố định
là Thứ Tư 2026-11-04 09:00 (giờ Việt Nam) để kết quả lặp lại được. Kết quả ghi ra eval/results/.
"""
import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{ROOT / 'eval.db'}")

from app import timeutil  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import Conversation, Priority, TaskStatus, User  # noqa: E402
from app.services import ai_tools, assistant, task_service  # noqa: E402

VN = ZoneInfo("Asia/Ho_Chi_Minh")
FIXED_NOW = datetime(2026, 11, 4, 9, 0, tzinfo=VN)
for mod in (timeutil, assistant, task_service, ai_tools):
    if hasattr(mod, "now_utc"):
        mod.now_utc = lambda: FIXED_NOW.astimezone(ZoneInfo("UTC"))


def norm(s: str | None) -> str:
    return (s or "").lower()


def grade(case: dict, actions: list[dict], reply: str, db, user) -> dict:
    exp = case["expect"]
    types = [a["type"].replace("_requested", "") for a in actions]
    mutating = [t for t in types if t not in ("list_tasks", "get_statistics")]
    checks: dict[str, bool] = {}

    # 1) Ý định
    if "tool_any" in exp:
        checks["intent"] = any(t in types for t in exp["tool_any"])
    elif exp.get("tool") is None:
        checks["intent"] = not mutating
    else:
        checks["intent"] = exp["tool"] in types
    tool = exp.get("tool") or next((t for t in exp.get("tool_any", []) if t in types), None)
    hits = [a for a in actions if a["type"].replace("_requested", "") == tool]
    act = hits[-1] if hits else {}
    obj = act.get("task") or act.get("reminder") or {}

    # 2) Trích xuất thông tin
    if "title_contains" in exp:
        checks["title"] = bool(obj) and all(norm(k) in norm(obj.get("title")) for k in exp["title_contains"])
    if "priority" in exp:
        checks["priority"] = obj.get("priority") == exp["priority"]
    if "status" in exp and "targets_all" not in exp:
        checks["status"] = obj.get("status") == exp["status"]
    if "due_at" in exp:
        want = exp["due_at"].replace("T", " ") if exp["due_at"] else None
        checks["due_at"] = obj.get("due_at") == want
    if "due_date" in exp:
        checks["due_date"] = (obj.get("due_at") or "")[:10] == exp["due_date"]
    if "remind_at" in exp:
        got = obj.get("remind_at") or obj.get("due_at")
        checks["remind_at"] = got == exp["remind_at"].replace("T", " ")
    if "target" in exp:
        if tool == "set_reminder":
            target_id = obj.get("task_id")
            t = task_service.get_task(db, user, target_id) if target_id else None
            checks["target"] = bool(t) and t.title == exp["target"]
        else:
            checks["target"] = any((a.get("task") or {}).get("title") == exp["target"] for a in hits)
    if "count" in exp:
        checks["count"] = len(hits) == exp["count"]
    if "targets_all" in exp:
        tasks = {t.title: t for t in task_service.list_tasks(db, user, limit=100)}
        checks["targets_all"] = all(tasks[n].status == TaskStatus.done for n in exp["targets_all"])
        checks["not_target"] = tasks[exp["not_target"]].status != TaskStatus.done

    # 3) Nội dung câu trả lời (cho các câu hỏi tra cứu)
    if "reply_contains" in exp:
        f = any if exp.get("reply_any") else all
        checks["reply"] = f(norm(k) in norm(reply) for k in exp["reply_contains"])
    if "reply_not_contains" in exp:
        checks["reply_excludes"] = all(norm(k) not in norm(reply) for k in exp["reply_not_contains"])

    return {"checks": checks, "passed": all(checks.values()), "tools": types}


def seed(db, user, items):
    for it in items or []:
        due = datetime.fromisoformat(it["due_at"]) if it.get("due_at") else None
        task_service.create_task(db, user, title=it["title"], due_at=due,
                                 priority=Priority(it.get("priority", "medium")),
                                 status=TaskStatus(it.get("status", "todo")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=str(ROOT / "commands_vi.jsonl"))
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    cases = [json.loads(l) for l in open(args.cases, encoding="utf-8") if l.strip()]
    if args.only:
        ids = {int(x) for x in args.only.split(",")}
        cases = [c for c in cases if c["id"] in ids]

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    results = []
    for case in cases:
        with SessionLocal() as db:
            user = User(email=f"eval{case['id']}@test", full_name="Eval", password_hash="x", voice_settings={})
            db.add(user)
            db.commit()
            seed(db, user, case.get("seed"))
            conv = Conversation(user_id=user.id)
            db.add(conv)
            db.commit()
            t0 = time.perf_counter()
            try:
                msg, _ = assistant.chat(db, user, conv, case["text"])
                reply, actions, err = msg.text, msg.actions, None
            except Exception as e:  # ghi nhận lỗi, chạy tiếp
                reply, actions, err = "", [], str(e)
            latency = time.perf_counter() - t0
            g = grade(case, actions, reply, db, user) if not err else {"checks": {"error": False}, "passed": False, "tools": []}
            results.append({"id": case["id"], "text": case["text"], "reply": reply, "actions": actions,
                            "error": err, "latency_s": round(latency, 2), **g})
            mark = "✓" if g["passed"] else "✗"
            failed = [k for k, v in g["checks"].items() if not v]
            print(f"{mark} #{case['id']:>2} {latency:5.1f}s {case['text'][:60]:<60} {'' if g['passed'] else failed}")

    n = len(results)
    intent = sum(r["checks"].get("intent", False) for r in results)
    field_checks = [(k, v) for r in results for k, v in r["checks"].items() if k != "intent"]
    lat = [r["latency_s"] for r in results]
    summary = {
        "model": assistant.get_settings().llm_model,
        "effort": assistant.get_settings().llm_effort,
        "cases": n,
        "case_pass_rate": round(sum(r["passed"] for r in results) / n, 3),
        "intent_accuracy": round(intent / n, 3),
        "field_accuracy": round(sum(v for _, v in field_checks) / max(1, len(field_checks)), 3),
        "per_field": {k: f"{sum(v for kk, v in field_checks if kk == k)}/{sum(1 for kk, _ in field_checks if kk == k)}"
                      for k in sorted({k for k, _ in field_checks})},
        "latency_mean_s": round(statistics.mean(lat), 2),
        "latency_p90_s": round(sorted(lat)[int(0.9 * (n - 1))], 2),
    }
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (out / f"eval-{stamp}.json").write_text(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Chi tiết: {out / f'eval-{stamp}.json'}")


if __name__ == "__main__":
    main()
