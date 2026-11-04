# Trợ lý AI cá nhân hỗ trợ công việc thông qua giọng nói

Đồ án tốt nghiệp kỹ sư, Trường CNTT&TT, ĐHBK Hà Nội (kỳ 20261).

Ứng dụng web cho phép người dùng quản lý công việc bằng câu lệnh tiếng Việt, gõ hoặc nói. Trợ lý dùng mô hình
ngôn ngữ lớn (Claude) với cơ chế gọi công cụ (tool calling) để tạo, tra cứu, cập nhật, xoá công việc, đặt nhắc
nhở và báo cáo tiến độ, rồi trả lời lại bằng giọng nói tiếng Việt.

## Chức năng

| Yêu cầu trong phiếu giao nhiệm vụ | Đã làm |
|---|---|
| Đăng ký, đăng nhập, quản lý tài khoản | JWT, bcrypt, đổi tên, đổi mật khẩu, xoá tài khoản |
| Hội thoại với AI bằng giọng nói, lưu lịch sử | Nhiều cuộc trò chuyện, lưu từng tin nhắn kèm hành động AI đã làm |
| Quản lý công việc (tạo, xem, sửa, xoá, trạng thái) | Trang Công việc + qua trợ lý; lọc theo trạng thái, ưu tiên, từ khoá |
| Trích xuất tên việc, thời hạn, mức ưu tiên từ câu nói | LLM gọi công cụ với schema chặt (strict); hiểu "mai", "thứ Sáu tuần sau", "gấp"... |
| Tiếng Việt: STT và TTS, tuỳ chỉnh theo người dùng | Web Speech API (vi-VN); chọn giọng, tốc độ, cao độ, bật/tắt tự đọc |
| Nhắc nhở, theo dõi, thống kê tiến độ | Worker nền kích hoạt nhắc nhở, tự nhắc việc sắp đến hạn 1 giờ; dashboard thống kê |
| Bảo vệ dữ liệu, kiểm soát hành động | Mỗi người chỉ thấy dữ liệu của mình; thao tác xoá do AI đề xuất phải bấm xác nhận |
| Bộ dữ liệu kiểm thử, đánh giá thực nghiệm | 40 câu lệnh tiếng Việt có đáp án + script chấm tự động; script tính WER cho STT |
| (Mở rộng) Gmail | Chưa làm, để giai đoạn sau |

## Kiến trúc

```
Trình duyệt (React + TypeScript)
  ├─ Web Speech API: giọng nói -> văn bản (vi-VN), văn bản -> giọng nói
  └─ REST /api ──> FastAPI (Python)
                    ├─ auth, tasks, reminders, chat
                    ├─ services/assistant.py  : vòng lặp LLM <-> công cụ
                    ├─ services/ai_tools.py   : 6 công cụ: create/list/update/delete task, set_reminder, get_statistics
                    ├─ services/reminder_worker.py : tác vụ nền kiểm tra nhắc nhở
                    └─ PostgreSQL (users, tasks, reminders, conversations, chat_messages, pending_actions)
                    └─> Claude API (Anthropic)
```

Luồng xử lý một câu lệnh giọng nói:
1. Người dùng bấm micro, trình duyệt nhận dạng tiếng nói tiếng Việt thành văn bản.
2. Frontend gửi văn bản lên `POST /api/chat`.
3. Backend gửi cho LLM: lời nhắc hệ thống, lịch sử hội thoại gần nhất, thời điểm hiện tại (giờ Việt Nam) và câu lệnh.
4. LLM chọn công cụ (ví dụ `create_task` với `title`, `due_at`, `priority`); backend thực thi trên CSDL và trả kết quả về LLM.
5. LLM trả lời ngắn gọn; frontend hiển thị và đọc câu trả lời bằng giọng đã chọn.

## Chạy trên máy (phát triển)

Yêu cầu: Python 3.11+, Node 20+, PostgreSQL 14+ (hoặc Docker), khoá API Anthropic.

```bash
# 1. CSDL
docker run -d --name pg -e POSTGRES_USER=assistant -e POSTGRES_PASSWORD=assistant -e POSTGRES_DB=assistant -p 5432:5432 postgres:16-alpine

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env                                # rồi điền ANTHROPIC_API_KEY, JWT_SECRET
uvicorn app.main:app --reload                          # http://localhost:8000/docs

# 3. Frontend (cửa sổ khác)
cd frontend
npm install
npm run dev                                            # http://localhost:5173
```

Dùng Chrome hoặc Edge để có nhận dạng giọng nói tiếng Việt. Trình duyệt chỉ cho dùng micro trên `localhost` hoặc HTTPS.

## Kiểm thử

```bash
cd backend && pytest                  # 8 test: API, phân quyền, nhắc nhở, vòng lặp công cụ (LLM giả lập)
TEST_DATABASE_URL=postgresql+psycopg://assistant:assistant@localhost:5432/assistant pytest   # chạy trên PostgreSQL
```

## Đánh giá thực nghiệm

```bash
cd backend && source .venv/bin/activate
python ../eval/run_eval.py            # gọi LLM thật cho 40 câu lệnh, tốn một ít phí API
python ../eval/run_eval.py --only 1,2,3
```

Script cố định "thời điểm hiện tại" là 09:00 Thứ Tư 04/11/2026 để kết quả lặp lại được, và báo cáo:
- Độ chính xác nhận dạng ý định (gọi đúng công cụ).
- Độ chính xác trích xuất từng trường: tên việc, hạn chót, mức ưu tiên, trạng thái, đúng công việc cần sửa.
- Độ trễ trung bình và p90.
Kết quả chi tiết lưu ở `eval/results/`. Có thể chạy lại với `LLM_MODEL` hoặc `LLM_EFFORT` khác để so sánh.

Đánh giá nhận dạng giọng nói (WER): đọc các câu trong `eval/commands_vi.jsonl` vào micro, xuất các tin nhắn
`input_mode = 'voice'` từ bảng `chat_messages` thành CSV `reference,hypothesis` (xem `eval/stt_samples.example.csv`),
rồi chạy `python eval/wer.py file.csv`.

## Triển khai thực tế (Nội dung 6)

Trên một VPS có Docker (ví dụ Ubuntu 22.04):

```bash
git clone <repo> && cd <repo>
cp .env.example .env      # điền ANTHROPIC_API_KEY, JWT_SECRET (chuỗi ngẫu nhiên dài), POSTGRES_PASSWORD
docker compose up -d --build      # web chạy ở cổng 8080
```

Sau đó đặt tên miền và HTTPS (bắt buộc để dùng micro), ví dụ dùng Caddy: `caddy reverse-proxy --from tenmien.vn --to localhost:8080`.
Thu phản hồi người dùng: mời 10-20 bạn dùng thử trong 1-2 tuần, dữ liệu `chat_messages` (có `latency_ms`, `actions`)
dùng để phân tích, kết hợp phiếu khảo sát (Google Form) về độ hài lòng và độ chính xác.

## Kết nối Google Calendar

Khi người dùng kết nối, mọi công việc có hạn chót (tạo bằng giọng nói hay bằng tay) trở thành sự kiện
30 phút trên lịch chính của họ, kèm thông báo nhắc trước hạn (mặc định 30 phút, đổi được trong Cài đặt).
Sửa việc thì sự kiện được sửa theo, hoàn thành hoặc xoá việc thì sự kiện bị gỡ. Nhắc nhở độc lập
("nhắc tôi 8 giờ tối gọi mẹ") thành sự kiện có thông báo đúng giờ. Việc ưu tiên cao có màu đỏ.
Lỗi từ Google không làm hỏng thao tác chính, chỉ hiện cảnh báo ở trang Cài đặt.

Cấu hình một lần (miễn phí):

1. Vào https://console.cloud.google.com, tạo project mới (ví dụ `tro-ly-ai`).
2. **APIs & Services → Library**: tìm *Google Calendar API* và bấm **Enable**.
3. **Google Auth Platform → Branding** (hoặc *OAuth consent screen*): User type **External**, điền tên ứng dụng và email.
   Ở mục **Audience** giữ trạng thái *Testing* và thêm Gmail của bạn (và người dùng thử) vào **Test users**.
4. **Data Access**: thêm scope `.../auth/calendar.events`, `openid`, `email`.
5. **Clients → Create client**: loại **Web application**, mục *Authorized redirect URIs* thêm
   `http://localhost:5173/api/google/callback` (chạy Docker thì thêm `http://localhost:8080/api/google/callback`,
   triển khai thật thì `https://tenmien.vn/api/google/callback`).
6. Chép *Client ID* và *Client secret* vào `.env` (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`), khởi động lại backend.
7. Vào **Cài đặt → Google Calendar → Kết nối Google Calendar**, đăng nhập và đồng ý.
   Google sẽ cảnh báo "ứng dụng chưa được xác minh" vì đang ở chế độ Testing: bấm *Tiếp tục* là được.

Lưu ý: ở chế độ Testing, Google cho refresh token sống 7 ngày, hết hạn thì bấm *Kết nối lại*. Token được mã hoá
(Fernet, khoá suy ra từ `JWT_SECRET`) trước khi lưu vào bảng `google_accounts`; đổi `JWT_SECRET` thì phải kết nối lại.

### Lọc email và nhắc trả lời (Gmail)

Cùng kết nối Google, trợ lý đọc (chỉ đọc) email **chưa đọc trong 3 ngày gần đây** và chia thành 4 nhóm:
cần trả lời, đọc sau, thông báo (noreply, mạng xã hội) và quảng cáo. Phân loại dùng quy tắc nên không tốn lượt gọi AI:
email có câu hỏi hoặc cụm đề nghị phản hồi ("vui lòng", "xác nhận", "please", "let me know"...) được xếp vào *cần trả lời*.

- **Email quan trọng** = cần trả lời, hoặc Gmail đã đánh dấu quan trọng / gắn sao (trừ thư quảng cáo).
  AI đọc thân thư và **tóm tắt 1-2 câu** (chỉ cho email quan trọng, tối đa 8 thư mỗi lần, tóm tắt được lưu lại nên mỗi thư chỉ tốn một lượt gọi AI).
  Nội dung email được coi là dữ liệu, trợ lý không làm theo yêu cầu nằm trong thư (chống prompt injection).
- **Mỗi sáng 8 giờ** (giờ Việt Nam, **mặc định tắt**, bật bằng công tắc trong Cài đặt vì nội dung email quan trọng được gửi cho dịch vụ AI để tóm tắt), hệ thống tạo việc "Trả lời: tiêu đề" hạn 17:00 cùng ngày cho email cần trả lời
  (việc này cũng lên Google Calendar) và hiện nhắc nhở "Sáng nay có N email quan trọng: ..." kèm tóm tắt, được đọc to bằng giọng nói.
  Mỗi email chỉ tạo việc một lần.
- **Hỏi bằng giọng nói**: "Có email nào quan trọng không?" -> trợ lý gọi công cụ `check_emails`, nói tổng số thư chưa đọc và đọc tóm tắt các thư quan trọng.
- Trong **Cài đặt → Google Calendar và Gmail**: *Kiểm tra email* xem danh sách theo nhóm, *Tóm tắt email quan trọng* gọi AI, *Tạo việc trả lời* tạo việc bất cứ lúc nào.

Cấu hình thêm trên Google Cloud: bật **Gmail API** (APIs & Services → Library), thêm quyền
`https://www.googleapis.com/auth/gmail.readonly` ở **Data Access**, rồi ngắt kết nối và kết nối lại trong app,
tick ô quyền đọc email ở màn hình của Google.

## Cấu hình

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `DATABASE_URL` | postgresql+psycopg://assistant:assistant@localhost:5432/assistant | Chuỗi kết nối CSDL |
| `LLM_PROVIDER` | auto | `anthropic`, `gemini` hoặc `auto` (Gemini nếu chỉ có `GEMINI_API_KEY`) |
| `ANTHROPIC_API_KEY` | | Khoá API Claude |
| `GEMINI_API_KEY` | | Khoá API Gemini (lấy ở aistudio.google.com, có gói miễn phí) |
| `LLM_MODEL` | (theo nhà cung cấp) | Mặc định `gemini-3.5-flash-lite` hoặc `claude-opus-5-5` |
| `LLM_EFFORT` | low | Mức suy luận (low/medium/high); low cho phản hồi nhanh |
| `JWT_SECRET` | | Khoá ký token, bắt buộc đổi khi triển khai |
| `CORS_ORIGINS` | http://localhost:5173 | Các origin được gọi API |
| `TIMEZONE` | Asia/Ho_Chi_Minh | Múi giờ để hiểu "hôm nay", "mai"... |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | | OAuth client cho Google Calendar; để trống thì tắt tính năng |
| `GOOGLE_REDIRECT_URI` | http://localhost:5173/api/google/callback | Địa chỉ Google gọi lại, phải khớp với Google Cloud Console |
| `FRONTEND_URL` | http://localhost:5173 | Trang giao diện để quay về sau khi kết nối Google |

## Cấu trúc thư mục

```
backend/app/        main.py, config.py, models.py, schemas.py, security.py, routers/, services/
backend/tests/      kiểm thử tự động
frontend/src/       pages/ (Assistant, Tasks, Dashboard, Settings, AuthPage), lib/ (api, auth, speech)
eval/               commands_vi.jsonl, run_eval.py, wer.py
docker-compose.yml  db + backend + frontend (nginx)
```
