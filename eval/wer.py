"""Tính tỉ lệ lỗi từ (WER) cho nhận dạng giọng nói tiếng Việt.

Đầu vào: file CSV có 2 cột `reference,hypothesis` (câu đọc chuẩn và văn bản hệ thống nhận dạng được).
Cách thu thập: đọc các câu trong commands_vi.jsonl vào micro trong ứng dụng, rồi xuất các tin nhắn có
input_mode='voice' từ bảng chat_messages (xem README).
Chạy: python eval/wer.py stt_samples.csv
"""
import csv
import re
import sys
import unicodedata


def tokens(s: str) -> list[str]:
    s = unicodedata.normalize("NFC", s.lower())
    s = re.sub(r"[^\w\s]", " ", s)
    return s.split()


def edit_distance(a: list[str], b: list[str]) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def main(path: str):
    errors = words = exact = n = 0
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ref, hyp = tokens(row["reference"]), tokens(row["hypothesis"])
            e = edit_distance(ref, hyp)
            errors += e
            words += len(ref)
            exact += e == 0
            n += 1
            if e:
                print(f"[{e} lỗi] {row['reference']}  ->  {row['hypothesis']}")
    print(f"\nSố câu: {n}\nWER: {errors / max(1, words):.2%}\nTỉ lệ câu đúng hoàn toàn: {exact / max(1, n):.2%}")


if __name__ == "__main__":
    main(sys.argv[1])
