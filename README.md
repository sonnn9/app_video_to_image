# Tách Ảnh Từ Video

Ứng dụng desktop (Windows) giúp:

- Trích xuất ảnh từ video theo khoảng cách thời gian tùy chỉnh
- Phiên âm nội dung video bằng Whisper (offline)
- Dịch transcript sang nhiều ngôn ngữ qua Google Translate
- **Xóa chữ trên ảnh** đã trích xuất bằng OCR (EasyOCR) + inpainting (OpenCV hoặc LaMa AI)

## Cài đặt

### Cách 1 — Dùng file .exe đã đóng gói (khuyến nghị cho người dùng cuối)

1. Copy **toàn bộ thư mục** `dist/TachAnhTuVideo/` sang máy đích.
2. Chạy `TachAnhTuVideo.exe`.
3. **Lần đầu chạy cần Internet** để tự tải các model:
   - Whisper (~150MB–3GB tùy mô hình) → `%USERPROFILE%\.cache\whisper\`
   - EasyOCR (~100MB) → `%USERPROFILE%\.EasyOCR\`
   - LaMa (~200MB, nếu dùng) → `%USERPROFILE%\.cache\torch\hub\`
4. Các lần sau chạy hoàn toàn offline.

Yêu cầu: Windows 10/11 64-bit, ~4GB dung lượng trống.

### Cách 2 — Chạy từ mã nguồn (cho dev)

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Nếu máy có GPU NVIDIA và muốn tăng tốc, cài torch bản CUDA:

```powershell
pip uninstall torch torchvision
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
```

## Sử dụng

### 1. Chọn video

Bấm **Duyệt...** ở mục "Chọn video". Hỗ trợ `.mp4`, `.avi`, `.mkv`, `.mov`, `.wmv`, `.flv`, `.webm`.

### 2. Chọn thư mục lưu

Tự gợi ý thư mục `<tên_video>_frames` cạnh file video. Có thể đổi.

### 3. Tinh chỉnh tham số

- **Khoảng cách (giây)**: cứ X giây trích 1 ảnh. Mặc định 5.
- **Mô hình Whisper**: `tiny` → `turbo`. Càng to càng chính xác nhưng càng chậm. Mặc định `base`.
- **Trích xuất phiên âm**: bỏ tick nếu chỉ cần ảnh.

### 4. Xóa chữ trên ảnh (tùy chọn)

- **Tick "Xóa tất cả chữ trên ảnh"**: bật pipeline OCR + inpaint.
- **Tick "Chất lượng cao (LaMa AI)"**: dùng deep learning inpainting, đẹp hơn rõ rệt nhưng chậm 3-5x.
- **Ô danh sách từ khóa**:
  - **Để trống** → xóa **mọi** chữ phát hiện được.
  - **Điền từ/cụm từ** (mỗi dòng 1 từ) → chỉ xóa các chữ chứa từ khóa đó (substring, không phân biệt hoa/thường).

Ví dụ — bạn muốn xóa logo "SHOPEE" và giá "₫" trên thumbnail:

```
shopee
₫
giảm giá
```

→ App sẽ giữ nguyên các chữ khác (tên sản phẩm, mô tả…) và chỉ inpaint những vùng khớp.

### 5. Dịch transcript (tùy chọn)

Chọn ngôn ngữ đích từ dropdown. App sẽ tạo thêm file `transcript_<lang>.txt` chứa bản dịch (giữ nguyên timestamp).

### 6. Bắt đầu

Bấm **▶ BẮT ĐẦU XỬ LÝ**. Tiến trình hiển thị ở thanh progress + log dưới cùng. Có thể bấm **✖ HỦY** bất cứ lúc nào.

## Kết quả

Trong thư mục lưu:

- `frame_00001_00h00m05s.jpg`, `frame_00002_00h00m10s.jpg`, … — ảnh đã trích (có thể đã xóa chữ nếu bật)
- `<tên_video>_audio.wav` — file âm thanh trung gian (nếu bật phiên âm)
- `transcript.txt` — phiên âm gốc kèm timestamp
- `transcript_<lang>.txt` — bản dịch (nếu bật)

## Hiệu năng tham khảo

Với 1 ảnh Full HD (1920×1080):

| Pipeline | CPU | GPU (NVIDIA) |
|---|---|---|
| Chỉ trích ảnh | <0.1s | <0.1s |
| + Xóa chữ (OpenCV TELEA) | ~3s | ~0.5s |
| + Xóa chữ (LaMa AI) | ~8s | ~1s |

Whisper `base` phiên âm video 10 phút mất ~30s (GPU) / ~3 phút (CPU).

## Build lại file .exe

```powershell
venv\Scripts\activate
build.bat
```

File output: `dist/TachAnhTuVideo/TachAnhTuVideo.exe`. Quá trình mất 5-15 phút.

## Tech stack

- **UI**: customtkinter
- **Video**: OpenCV
- **Phiên âm**: OpenAI Whisper (PyTorch)
- **Dịch**: deep-translator (Google Translate)
- **OCR**: EasyOCR
- **Inpainting**: OpenCV (TELEA) / LaMa (simple-lama-inpainting)
- **Bundling**: PyInstaller
- **Audio extract**: ffmpeg (bundled)

## Lưu ý

- File `.exe` rất to (~4GB) do bundle PyTorch CUDA + nhiều model deep learning. Đây là đánh đổi để chạy offline và tận dụng GPU.
- LaMa với GPU 2GB VRAM (như MX570) có thể OOM trên ảnh quá lớn — app sẽ tự fallback OpenCV TELEA cho ảnh đó, không crash.
- EasyOCR mặc định dùng tiếng Anh + tiếng Việt. Cần ngôn ngữ khác (Trung, Nhật, Hàn…) phải sửa trong `main.py`.
