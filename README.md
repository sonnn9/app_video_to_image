# Tách Ảnh Từ Video

Ứng dụng desktop (Windows) giúp:

- Trích xuất ảnh từ video theo khoảng cách thời gian tùy chỉnh
- Phiên âm nội dung video bằng Whisper (offline)
- Dịch transcript sang nhiều ngôn ngữ qua Google Translate
- (Tùy chọn) TTS bằng ElevenLabs và ghép lại thành video mới

## Cài đặt

### Cách 1 — Dùng file .exe đã đóng gói (khuyến nghị cho người dùng cuối)

1. Copy **toàn bộ thư mục** `dist/TachAnhTuVideo/` sang máy đích.
2. Chạy `TachAnhTuVideo.exe`.
3. **Lần đầu chạy cần Internet** để tự tải Whisper model (~150MB–3GB tùy mô hình) về `%USERPROFILE%\.cache\whisper\`.
4. Các lần sau chạy hoàn toàn offline (trừ khi dùng Dịch / TTS — cần mạng).

Yêu cầu: Windows 10/11 64-bit, ~3GB dung lượng trống.

### Cách 2 — Chạy từ mã nguồn (cho dev)

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Nếu máy có GPU NVIDIA và muốn tăng tốc Whisper, cài torch bản CUDA:

```powershell
pip uninstall torch torchvision
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
```

## Sử dụng

### 1. Chọn video

Bấm **Duyệt...** ở mục "Chọn video". Hỗ trợ `.mp4`, `.avi`, `.mkv`, `.mov`, `.wmv`, `.flv`, `.webm`, `.m4v`, `.mpeg`, `.mpg`.

App cũng hỗ trợ chọn **cả folder video** để xử lý hàng loạt.

### 2. Chọn thư mục lưu

Tự gợi ý thư mục `<tên_video>_frames` cạnh file video. Có thể đổi.

### 3. Tinh chỉnh tham số

- **Khoảng cách (giây)**: cứ X giây trích 1 ảnh. Mặc định 5.
- **Mô hình Whisper**: `tiny` → `turbo`. Càng to càng chính xác nhưng càng chậm. Mặc định `base`.
- **Trích xuất phiên âm**: bỏ tick nếu chỉ cần ảnh.

### 4. Dịch transcript (tùy chọn)

Chọn ngôn ngữ đích từ dropdown. App sẽ tạo thêm file `transcript_<lang>.txt` chứa bản dịch (giữ nguyên timestamp).

### 5. TTS + ghép video (tùy chọn)

Nếu có API key ElevenLabs, có thể:
- Chuyển transcript thành giọng nói (chọn voice, model, preset Viral/News/Audiobook…)
- Đồng bộ theo timestamp gốc
- Ghép audio mới với ảnh trích xuất thành video kết quả

### 6. Bắt đầu

Bấm **▶ BẮT ĐẦU XỬ LÝ**. Tiến trình hiển thị ở thanh progress + log dưới cùng. Có thể bấm **✖ HỦY** bất cứ lúc nào.

## Kết quả

Trong thư mục lưu:

- `frame_00001_00h00m05s.jpg`, `frame_00002_00h00m10s.jpg`, … — ảnh trích xuất
- `<tên_video>_audio.wav` — âm thanh gốc (nếu bật phiên âm)
- `transcript.txt` — phiên âm gốc kèm timestamp
- `transcript_<lang>.txt` — bản dịch (nếu bật)
- File audio TTS + video ghép (nếu bật TTS)

## Hiệu năng tham khảo

| Pipeline | CPU | GPU (NVIDIA) |
|---|---|---|
| Trích ảnh (Full HD) | <0.1s/ảnh | <0.1s/ảnh |
| Whisper `base` (video 10 phút) | ~3 phút | ~30s |

## Build lại file .exe

```powershell
venv\Scripts\activate
build.bat
```

File output: `dist/TachAnhTuVideo/TachAnhTuVideo.exe`. Quá trình mất 5-10 phút.

## Tech stack

- **UI**: customtkinter
- **Video**: OpenCV
- **Phiên âm**: OpenAI Whisper (PyTorch)
- **Dịch**: deep-translator (Google Translate)
- **TTS**: ElevenLabs
- **Audio/video**: ffmpeg + ffprobe (bundled)
- **Bundling**: PyInstaller

## Lưu ý

- File `.exe` khá to (~3GB) do bundle PyTorch (CUDA nếu có) + Whisper runtime. Đây là đánh đổi để chạy offline và tận dụng GPU.
- Whisper với GPU 2GB VRAM (như MX570) chạy được model tới `small`/`medium`; `large` có thể OOM.
- TTS/dịch yêu cầu Internet.
