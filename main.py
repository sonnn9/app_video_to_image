import sys
import os

# Fix for PyInstaller windowed mode: stdout/stderr are None
# which crashes libraries (torch, whisper) that try to print/log
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import json
import re
import customtkinter as ctk
import cv2
import numpy as np
import whisper
import subprocess
import threading
import shutil
from deep_translator import GoogleTranslator
from datetime import datetime
from tkinter import filedialog, messagebox
from pathlib import Path


# Supported translation languages: code -> display name
LANGUAGES = {
    "none": "-- Không dịch --",
    "vi": "Tiếng Việt",
    "en": "English",
    "zh-CN": "Chinese (Simplified)",
    "zh-TW": "Chinese (Traditional)",
    "ja": "Japanese",
    "ko": "Korean",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "th": "Thai",
    "id": "Indonesian",
    "ru": "Russian",
    "pt": "Portuguese",
    "ar": "Arabic",
    "hi": "Hindi",
}

LANG_DISPLAY = list(LANGUAGES.values())
LANG_CODES = list(LANGUAGES.keys())

VIDEO_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".mpeg", ".mpg"}

ELEVENLABS_MODELS = [
    "eleven_multilingual_v2",
    "eleven_turbo_v2_5",
    "eleven_v3",
    "eleven_flash_v2_5",
]

# Preset tuning for TTS: (stability, similarity, style, speed, speaker_boost)
TTS_PRESETS = {
    "📣 Viral / Hook (TikTok, Shorts)":     (0.35, 0.80, 0.50, 1.10, True),
    "⚡ Năng lượng cao (Ads, Hype)":         (0.25, 0.80, 0.60, 1.15, True),
    "🎬 Kể chuyện (Storytelling, Vlog)":    (0.55, 0.75, 0.35, 1.00, True),
    "📰 Tin tức / Chuyên nghiệp":           (0.70, 0.75, 0.15, 1.00, True),
    "📖 Đọc sách (Audiobook)":              (0.80, 0.75, 0.10, 0.95, True),
    "🎯 Mặc định ElevenLabs":               (0.50, 0.75, 0.00, 1.00, True),
    "⚙  Tùy chỉnh":                         None,
}
TTS_PRESET_NAMES = list(TTS_PRESETS.keys())

TTS_CHUNK_MAX_CHARS = 4500

CONFIG_PATH = Path.home() / ".tach_anh_tu_video.json"


def load_config():
    try:
        if CONFIG_PATH.is_file():
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_config(data):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def chunk_text_for_tts(text, max_chars=TTS_CHUNK_MAX_CHARS):
    """Split text into chunks <= max_chars, preferring sentence/line boundaries."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    # Split by sentence-ending punctuation while keeping delimiters
    sentences = re.split(r"(?<=[\.\?\!\。\？\！])\s+|\n+", text)
    sentences = [s.strip() for s in sentences if s and s.strip()]

    chunks = []
    current = ""
    for s in sentences:
        # If single sentence is itself too long, hard-split it
        if len(s) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            for i in range(0, len(s), max_chars):
                chunks.append(s[i:i + max_chars])
            continue
        if len(current) + len(s) + 1 > max_chars:
            if current:
                chunks.append(current)
            current = s
        else:
            current = current + " " + s if current else s
    if current:
        chunks.append(current)
    return chunks


def concat_mp3_files(ffmpeg_bin, input_files, output_file):
    """Concatenate MP3 files into one using ffmpeg concat demuxer."""
    if len(input_files) == 1:
        shutil.copyfile(input_files[0], output_file)
        return

    list_path = output_file + ".concat.txt"
    with open(list_path, "w", encoding="utf-8") as f:
        for p in input_files:
            safe = p.replace("\\", "/").replace("'", "'\\''")
            f.write(f"file '{safe}'\n")

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    try:
        subprocess.run(
            [ffmpeg_bin, "-f", "concat", "-safe", "0", "-i", list_path,
             "-c", "copy", output_file, "-y"],
            capture_output=True, text=True, check=True, startupinfo=startupinfo,
        )
    finally:
        try:
            os.remove(list_path)
        except OSError:
            pass


def get_base_path():
    """Get base path for bundled resources (PyInstaller or dev)."""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def get_ffmpeg_path():
    """Find ffmpeg: bundled first, then system PATH."""
    if getattr(sys, 'frozen', False):
        for base in [sys._MEIPASS, os.path.dirname(sys.executable)]:
            bundled = os.path.join(base, "ffmpeg.exe")
            if os.path.isfile(bundled):
                return bundled
    found = shutil.which("ffmpeg")
    if found:
        return found
    return None


def get_ffprobe_path():
    """Find ffprobe: bundled first, then system PATH, then sibling of ffmpeg."""
    if getattr(sys, 'frozen', False):
        for base in [sys._MEIPASS, os.path.dirname(sys.executable)]:
            bundled = os.path.join(base, "ffprobe.exe")
            if os.path.isfile(bundled):
                return bundled
    found = shutil.which("ffprobe")
    if found:
        return found
    ffmpeg_bin = get_ffmpeg_path()
    if ffmpeg_bin:
        sibling = os.path.join(os.path.dirname(ffmpeg_bin), "ffprobe.exe")
        if os.path.isfile(sibling):
            return sibling
    return None


def _ffmpeg_startupinfo():
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return si


def probe_duration_sec(ffprobe_bin, path):
    """Return audio/video file duration in seconds, or 0.0 on failure."""
    if not ffprobe_bin:
        return 0.0
    try:
        result = subprocess.run(
            [ffprobe_bin, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, startupinfo=_ffmpeg_startupinfo(),
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def make_silence_mp3(ffmpeg_bin, duration_sec, output_path):
    """Generate a silent MP3 matching ElevenLabs' mp3_44100_128 format."""
    dur = max(float(duration_sec), 0.02)
    subprocess.run(
        [ffmpeg_bin, "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
         "-t", f"{dur:.3f}",
         "-c:a", "libmp3lame", "-b:a", "128k", output_path, "-y"],
        capture_output=True, check=True, startupinfo=_ffmpeg_startupinfo(),
    )


def mux_video_with_audio(ffmpeg_bin, video_path, audio_path, output_path):
    """Merge video (audio stripped) with external audio into a new MP4.

    - Copies video stream losslessly when compatible, else re-encodes to H.264.
    - Pads audio with silence (apad) so it covers the full video duration,
      and caps at video duration via -shortest.
    """
    def _run(video_codec_args):
        cmd = [
            ffmpeg_bin,
            "-i", video_path,
            "-i", audio_path,
            "-map", "0:v:0",
            "-map", "1:a:0",
            *video_codec_args,
            "-c:a", "aac", "-b:a", "192k",
            "-af", "apad",
            "-shortest",
            "-movflags", "+faststart",
            output_path, "-y",
        ]
        return subprocess.run(
            cmd, capture_output=True, text=True, startupinfo=_ffmpeg_startupinfo(),
        )

    # Try stream copy first (fast, lossless)
    result = _run(["-c:v", "copy"])
    if result.returncode == 0:
        return
    # Fallback: re-encode video
    result = _run(["-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p"])
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg mux lỗi: {result.stderr[-300:]}")


def apply_atempo(ffmpeg_bin, input_path, tempo, output_path):
    """Time-stretch MP3 by `tempo` factor. Chains atempo filter to cover 0.25–4.0x."""
    if abs(tempo - 1.0) < 0.01:
        shutil.copyfile(input_path, output_path)
        return
    parts = []
    t = float(tempo)
    while t > 2.0:
        parts.append("atempo=2.0")
        t /= 2.0
    while t < 0.5:
        parts.append("atempo=0.5")
        t *= 2.0
    parts.append(f"atempo={t:.4f}")
    filter_str = ",".join(parts)
    subprocess.run(
        [ffmpeg_bin, "-i", input_path, "-filter:a", filter_str,
         "-c:a", "libmp3lame", "-b:a", "128k", output_path, "-y"],
        capture_output=True, check=True, startupinfo=_ffmpeg_startupinfo(),
    )


def cv2_open_video(path):
    """Open video with Unicode path support on Windows."""
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(500)
            ctypes.windll.kernel32.GetShortPathNameW(path, buf, 500)
            if buf.value:
                cap = cv2.VideoCapture(buf.value)
        except Exception:
            pass
    return cap


def cv2_save_image(filepath, frame, params=None):
    """Save image with Unicode path support on Windows."""
    ext = os.path.splitext(filepath)[1]
    result, buf = cv2.imencode(ext, frame, params or [])
    if result:
        with open(filepath, "wb") as f:
            f.write(buf.tobytes())
        return True
    return False


def pick_representative_frames(frames_dir, n=5):
    """Return up to n frame paths evenly spaced from a frames folder."""
    def _frame_key(p):
        try:
            return (0, int(p.stem))
        except ValueError:
            return (1, p.name)
    frames = sorted(Path(frames_dir).glob("*.jpg"), key=_frame_key)
    if not frames:
        return []
    if len(frames) <= n:
        return [str(p) for p in frames]
    step = (len(frames) - 1) / (n - 1)
    indices = [round(i * step) for i in range(n)]
    return [str(frames[i]) for i in indices]


def rewrite_transcript_viral(vi_transcript, frame_paths, product_info,
                             log_fn=None, timeout=600):
    """Use Codex CLI (codex exec -i ...) to rewrite VN transcript as viral sales script.

    Returns the rewritten script as a plain string. Raises RuntimeError on failure.
    """
    codex_exe = shutil.which("codex") or shutil.which("codex.cmd")
    if not codex_exe:
        raise RuntimeError("Không tìm thấy lệnh 'codex' trong PATH. Cài Codex CLI rồi thử lại.")

    info = (product_info or "").strip() or "(không có thông tin bổ sung)"

    prompt = f"""Bạn là chuyên gia copywriter viral cho TikTok/Reels/Shorts (thị trường Việt Nam).

Dưới đây là transcript của một video sản phẩm (có thể bằng tiếng Việt, tiếng Anh, hoặc trộn nhiều ngôn ngữ) và các ảnh chụp sản phẩm trích từ chính video đó.

THÔNG TIN SẢN PHẨM (do người dùng cung cấp):
{info}

TRANSCRIPT GỐC (giữ nguyên ngôn ngữ — có thể không phải tiếng Việt):
{vi_transcript.strip()}

YÊU CẦU:
1. Viết lại thành KỊCH BẢN VIRAL khoảng 60-90 giây cho TikTok / Reels / Shorts, BẰNG TIẾNG VIỆT.
2. Nếu transcript gốc không phải tiếng Việt, tự hiểu nội dung và Việt hóa — không cần giữ nguyên cấu trúc câu gốc.
3. 3-5 giây ĐẦU phải có HOOK CỰC MẠNH: câu hỏi gây tò mò, con số shock, hoặc vấn đề đau đầu của khách hàng.
4. Highlight 2-3 USP của sản phẩm dựa trên những gì BẠN THẤY trong ảnh (màu sắc, thiết kế, công dụng, chi tiết nổi bật...).
5. Văn phong nói chuyện tự nhiên kiểu người Việt trẻ. Tránh từ Hán-Việt nặng nề và lối viết sáo rỗng.
6. CTA cuối rõ ràng: "comment", "follow", "click link bio", "mua ngay"...
7. CHỈ in ra phần script thuần text TIẾNG VIỆT — KHÔNG thêm lời giải thích, tiêu đề, markdown hay liệt kê đánh số.
8. Output sẵn sàng để đọc trực tiếp bằng TTS."""

    cmd = [codex_exe, "exec"]
    for fp in frame_paths:
        cmd.extend(["-i", fp])
    # Prompt qua stdin để tránh `-i <FILE>...` variadic nuốt mất prompt.

    if log_fn:
        log_fn(f"Gọi Codex CLI với {len(frame_paths)} ảnh tham chiếu...")

    startupinfo = None
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    result = subprocess.run(
        cmd,
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        startupinfo=startupinfo,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Codex CLI thất bại (exit {result.returncode}): "
            f"{(result.stderr or result.stdout)[:500]}"
        )

    return result.stdout.strip()


def calc_reference_frame_count(viral_chars):
    """Heuristic: more frames for longer scripts so Codex has enough visual context."""
    if viral_chars < 600:
        return 3
    if viral_chars < 1200:
        return 5
    if viral_chars < 2000:
        return 8
    if viral_chars < 3000:
        return 10
    return 12


SCENE_OUTPUT_FILES = [
    "character_bible.txt",
    "visual_bible.txt",
    "story_breakdown.txt",
    "all_image_prompts.txt",
    "all_grok_video_prompts.txt",
    "all_veo3_video_prompts.txt",
    "production_notes.txt",
]

CHARACTER_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def character_name_from_filename(path):
    """father.png -> 'Father', ong_noi.png -> 'Ong Noi'."""
    stem = Path(path).stem
    cleaned = re.sub(r"[_\-]+", " ", stem).strip()
    return cleaned.title() if cleaned else stem


def collect_character_refs(folder):
    """Return sorted list of (filename, character_name, abs_path) for images in folder."""
    if not folder or not os.path.isdir(folder):
        return []
    refs = []
    for p in sorted(Path(folder).iterdir(), key=lambda x: x.name.lower()):
        if p.is_file() and p.suffix.lower() in CHARACTER_IMAGE_EXTS:
            refs.append((p.name, character_name_from_filename(p), str(p)))
    return refs


def generate_scene_prompts(viral_script, frame_paths, product_info,
                           character_refs=None, log_fn=None, timeout=1200):
    """Use Codex CLI to produce a full scene breakdown + image/video prompts.

    Output is one big string with `===FILE: <name>===` markers separating each
    target file. Caller is responsible for splitting and writing to disk.
    """
    codex_exe = shutil.which("codex") or shutil.which("codex.cmd")
    if not codex_exe:
        raise RuntimeError("Không tìm thấy lệnh 'codex' trong PATH. Cài Codex CLI rồi thử lại.")

    info = (product_info or "").strip() or "(không có thông tin bổ sung)"
    files_list = ", ".join(SCENE_OUTPUT_FILES)

    character_refs = character_refs or []
    n_keyframes = len(frame_paths)
    n_characters = len(character_refs)

    if character_refs:
        char_lines = []
        for fname, cname, _ in character_refs:
            char_lines.append(f"  • {fname}  →  nhân vật \"{cname}\"")
        characters_block = (
            "DANH SÁCH NHÂN VẬT CỐ ĐỊNH (BẮT BUỘC BÁM SÁT):\n"
            + "\n".join(char_lines)
            + "\n\n"
            f"QUAN TRỌNG: Tổng số ảnh đính kèm là {n_characters + n_keyframes}. "
            f"{n_characters} ảnh ĐẦU là ảnh nhân vật (theo thứ tự trên), "
            f"{n_keyframes} ảnh SAU là keyframe trích từ video gốc.\n"
        )
        characters_image_rule = (
            "BẮT BUỘC: Mỗi prompt ảnh PHẢI có dòng tham chiếu file nhân vật, vd:\n"
            "  Use the uploaded character reference images: father.png as Father, "
            "mother.png as Mother. Keep their faces, hairstyles and outfits EXACTLY "
            "consistent with these references across every scene.\n"
            "Liệt kê đúng các file nhân vật xuất hiện trong cảnh đó."
        )
        characters_video_rule = (
            "Trong từng Grok/Veo3 prompt cũng phải nhắc lại file nhân vật xuất hiện trong cảnh "
            "(vd: \"Characters must match father.png and mother.png exactly — no face, hair, or outfit drift\")."
        )
    else:
        characters_block = "DANH SÁCH NHÂN VẬT CỐ ĐỊNH: (không có — tự suy từ keyframe / kịch bản)\n"
        characters_image_rule = "(không có ảnh nhân vật cố định — chỉ mô tả bằng text)"
        characters_video_rule = "(không có ảnh nhân vật cố định)"

    prompt = f"""Bạn là trợ lý sản xuất video dài bằng AI, chuyên phân tích kịch bản, chia cảnh, tạo prompt ảnh ChatGPT Image và tạo prompt video Grok + Veo 3 từ các ảnh keyframe.

Bạn nhận: (a) một kịch bản viral tiếng Việt, (b) các ảnh nhân vật cố định (nếu có) + các ảnh keyframe trích từ video sản phẩm gốc đính kèm, (c) thông tin sản phẩm.

{characters_block}

NGUYÊN TẮC CHIA CẢNH:
- KHÔNG chia số cố định. Phân tích nhịp kể chuyện, lời thoại, sự thay đổi của hành động/bối cảnh/cảm xúc.
- Mỗi cảnh có 1 ý chính duy nhất.
- Tạo cảnh mới khi: nhân vật chuyển hành động, bối cảnh đổi, cảm xúc đổi rõ, có câu thoại mới, hoặc cần điểm nhấn.
- Không chia quá nhỏ nếu hành động liên tục; không gộp quá nhiều ý vì Grok/Veo3 khó render chuyển động rõ.

QUY TẮC OUTPUT (CỰC KỲ QUAN TRỌNG):
- Output chia thành nhiều block. Mỗi block bắt đầu bằng dòng marker đúng định dạng: `===FILE: <tên_file>===`
- Đúng các tên file sau (theo thứ tự): {files_list}
- Sau marker là nội dung file (text thuần, KHÔNG markdown bao quanh, KHÔNG dấu ```).
- KHÔNG thêm lời giải thích bên ngoài các block.
- Nếu thiếu thông tin, TỰ ĐƯA RA GIẢ ĐỊNH HỢP LÝ rồi tiếp tục — KHÔNG được hỏi lại (chế độ non-interactive).

═══════════════════════════════════════════════
NỘI DUNG TỪNG FILE
═══════════════════════════════════════════════

[character_bible.txt]
NẾU có danh sách nhân vật cố định ở trên: PHẢI dùng đúng tên đó và mô tả theo đúng ngoại hình thấy trong ảnh nhân vật (KHÔNG bịa khác). Mỗi nhân vật có dòng đầu: `Tên (file_nhân_vật.ext)` rồi mới đến mô tả.
Với mỗi nhân vật: Tên (file) | Tuổi | Giới tính | Ngoại hình | Kiểu tóc | Trang phục | Tính cách | Biểu cảm điển hình | Quy tắc giữ đồng nhất xuyên suốt video.
Nếu video không có nhân vật người (chỉ sản phẩm) VÀ không có file nhân vật, ghi rõ "Không có nhân vật người" và mô tả "nhân vật chính" là sản phẩm.

[visual_bible.txt]
Phong cách hình ảnh | Tỷ lệ khung (9:16 / 16:9 / 1:1) | Tông màu | Ánh sáng | Bối cảnh chính | Camera style | Mức realistic/cartoon/3D/cinematic | Những điều TUYỆT ĐỐI không thay đổi xuyên video.

[story_breakdown.txt]
PHẦN A — PHÂN TÍCH KỊCH BẢN (trả lời 12 câu, mỗi câu 1 dòng):
1. Chủ đề chính:
2. Đối tượng người xem:
3. Phong cách phù hợp:
4. Nhân vật chính/phụ:
5. Bối cảnh chính:
6. Mạch nội dung:
7. Cảm xúc cần tạo:
8. Có cần voiceover không:
9. Có cần subtitle không:
10. Video nên dài bao lâu:
11. Số cảnh đề xuất:
12. Vì sao chia số cảnh như vậy:

PHẦN B — BẢNG CẢNH (mỗi cảnh 1 block, ngăn cách bằng dòng `---`):
Cảnh <số>:
- Thời lượng: <X giây>
- Nội dung chính: <...>
- Hành động nhân vật: <...>
- Bối cảnh: <...>
- Góc máy: <...>
- Voiceover/Lời thoại: <...>
- Ghi chú chuyển cảnh: <...>

[all_image_prompts.txt]
{characters_image_rule}

Mỗi cảnh = 1 prompt. Theo đúng cấu trúc:

Image Prompt 01:
Create a [style] [aspect ratio] keyframe image for a long-form AI video.
Character references (uploaded by user): [liệt kê đúng các file nhân vật xuất hiện cảnh này, vd: father.png as Father, mother.png as Mother — hoặc "none" nếu chỉ sản phẩm]
Keep the same characters throughout the entire series:
[short character description theo Character Bible — bám sát ảnh ref nếu có]
Scene 01:
[describe the scene clearly]
Show [main action, emotion, composition].
Use [lighting, color tone, camera angle].
No text, no subtitles, no letters, no watermark, no logo.

(Lặp lại cho từng cảnh, đánh số 01, 02, 03...)

[all_grok_video_prompts.txt]
{characters_video_rule}

Nếu có N ảnh, tạo N-1 prompt (mỗi cặp ảnh liên tiếp). Cộng thêm Outro Prompt nếu cần.

Grok Video Prompt 01 — Image 01 to Image 02:

Use the uploaded Image 01 as the exact starting frame and Image 02 as the exact ending frame.
Create a smooth [duration]-second video transition from Image 01 to Image 02.

Character references (must match exactly): [liệt kê đúng các file nhân vật trong cảnh, vd: father.png, mother.png — hoặc "none"]
Preserve the same characters exactly:
[character consistency rules — không thay đổi mặt, tóc, trang phục]

At 0-1s:
[describe starting action]

From 1-[middle time]s:
[describe natural movement]

From [middle time]-[end time]s:
Smoothly arrive at the exact composition of Image 02.

Voiceover:
[voiceover text tiếng Việt]

Voice accent:
Vietnamese [Northern/Southern/Central] accent, warm, clear, natural.

Camera motion:
[gentle / cinematic / stable / handheld / slow zoom]

Important restrictions:
Do not change the characters' faces.
Do not change hairstyles or outfits.
Do not add text, subtitles, watermark, logo, random objects, or new people.

[all_veo3_video_prompts.txt]
Cùng N-1 prompt nhưng dùng cú pháp Veo 3:

Veo 3 Video Prompt 01 — Scene 01 to Scene 02:
Duration: 8 seconds
Starting frame: Image 01 (exact composition)
Ending frame: Image 02 (exact composition)
Character references: [liệt kê đúng file nhân vật xuất hiện trong cảnh, vd: father.png, mother.png — hoặc "none"]
Subject: [character/product description, giữ đồng nhất theo ảnh ref]
Action timeline:
- 0-2s: [opening motion]
- 2-6s: [main movement]
- 6-8s: [resolve to ending frame]
Camera: [shot type, movement — e.g., slow dolly in, static medium shot]
Lighting: [theo Visual Bible]
Audio:
- Voiceover (vi-VN, [Northern/Southern/Central] accent, [tone]): "[lời thoại]"
- Ambient: [sound design hint]
Style: [cinematic / commercial / realistic / cinematic 3D]
Negative: no text overlay, no watermark, no logo, no extra people, no face/outfit changes.

[production_notes.txt]
Ghi chú sản xuất tổng thể: lưu ý kỹ thuật khi render, gợi ý nhạc nền, các điểm cần A/B test, cảnh có rủi ro AI render khó, gợi ý điều chỉnh cho từng nền tảng (TikTok/Reels/Shorts).

═══════════════════════════════════════════════
DỮ LIỆU ĐẦU VÀO
═══════════════════════════════════════════════

THÔNG TIN SẢN PHẨM:
{info}

KỊCH BẢN VIRAL TIẾNG VIỆT:
{viral_script.strip()}

═══════════════════════════════════════════════
Bắt đầu output ngay (block đầu tiên `===FILE: character_bible.txt===`). KHÔNG thêm lời mở đầu."""

    cmd = [codex_exe, "exec"]
    # Ảnh nhân vật trước (để Codex bám), keyframe sau
    for _, _, fp in character_refs:
        cmd.extend(["-i", fp])
    for fp in frame_paths:
        cmd.extend(["-i", fp])
    # Prompt qua stdin để tránh `-i <FILE>...` variadic nuốt mất prompt.

    if log_fn:
        log_fn(
            f"Gọi Codex CLI cho scene breakdown "
            f"({n_characters} ảnh nhân vật + {n_keyframes} keyframe, có thể mất 3-10 phút)..."
        )

    startupinfo = None
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    result = subprocess.run(
        cmd, input=prompt,
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        timeout=timeout, startupinfo=startupinfo,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Codex CLI thất bại (exit {result.returncode}): "
            f"{(result.stderr or result.stdout)[:500]}"
        )
    return result.stdout


def split_scene_output(raw_output, scenes_dir):
    """Split Codex output by `===FILE: <name>===` markers and write each section.

    Always writes the raw output to `_raw_codex_output.txt` for debugging.
    Returns the list of file paths actually written (besides the raw dump).
    """
    os.makedirs(scenes_dir, exist_ok=True)
    raw_path = os.path.join(scenes_dir, "_raw_codex_output.txt")
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(raw_output)

    pattern = re.compile(r"^={3,}\s*FILE:\s*(\S+?)\s*={3,}\s*$", re.MULTILINE)
    matches = list(pattern.finditer(raw_output))
    if not matches:
        return []

    written = []
    for i, m in enumerate(matches):
        fname = m.group(1).strip().strip(".")
        if not fname:
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_output)
        content = raw_output[start:end].strip()
        # Sanitize file name to avoid path traversal
        fname = os.path.basename(fname)
        fpath = os.path.join(scenes_dir, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content + "\n")
        written.append(fpath)
    return written


def translate_text(text, target_lang, log_fn=None):
    """Translate text using Google Translate. Splits into chunks if too long."""
    if not text.strip():
        return ""
    try:
        # Google Translate has a ~5000 char limit per request
        max_chunk = 4500
        if len(text) <= max_chunk:
            return GoogleTranslator(source="auto", target=target_lang).translate(text)

        # Split by lines, translate in chunks
        lines = text.split("\n")
        chunks = []
        current_chunk = ""
        for line in lines:
            if len(current_chunk) + len(line) + 1 > max_chunk:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = line
            else:
                current_chunk = current_chunk + "\n" + line if current_chunk else line
        if current_chunk:
            chunks.append(current_chunk)

        translated_parts = []
        translator = GoogleTranslator(source="auto", target=target_lang)
        for i, chunk in enumerate(chunks):
            if log_fn:
                log_fn(f"Đang dịch phần {i + 1}/{len(chunks)}...")
            translated_parts.append(translator.translate(chunk))

        return "\n".join(translated_parts)
    except Exception as e:
        if log_fn:
            log_fn(f"Lỗi dịch: {e}")
        return None


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Tách Ảnh Từ Video (Batch)")
        self.geometry("820x1180")
        self.minsize(760, 900)
        self.resizable(True, True)

        self._cancel_flag = threading.Event()
        self._processing = False
        self._config = load_config()
        self._voices_cache = []  # list of dicts: {id, name, labels, display}

        # Variables
        self.videos_dir_var = ctk.StringVar()
        self.output_dir_var = ctk.StringVar()
        self.character_dir_var = ctk.StringVar(value=self._config.get("character_ref_dir", ""))
        self.interval_var = ctk.StringVar(value="5")
        self.model_var = ctk.StringVar(value="base")
        self.do_extract_frames_var = ctk.BooleanVar(value=True)
        self.do_transcript_var = ctk.BooleanVar(value=True)
        self.do_translate_var = ctk.BooleanVar(value=False)
        self.translate_var = ctk.StringVar(value=LANGUAGES["vi"])
        self.do_viral_rewrite_var = ctk.BooleanVar(value=False)
        self.do_scene_prompts_var = ctk.BooleanVar(value=False)

        # ElevenLabs TTS
        self.do_tts_var = ctk.BooleanVar(value=False)
        self.tts_api_key_var = ctk.StringVar(value=self._config.get("elevenlabs_api_key", ""))
        self.tts_voice_var = ctk.StringVar(value="(Chưa tải giọng)")
        self.tts_model_var = ctk.StringVar(
            value=self._config.get("elevenlabs_model", ELEVENLABS_MODELS[0])
        )
        self.tts_only_vi_var = ctk.BooleanVar(
            value=self._config.get("elevenlabs_only_vi", True)
        )
        self.tts_sync_timestamps_var = ctk.BooleanVar(
            value=self._config.get("tts_sync_timestamps", True)
        )
        self.do_merge_video_var = ctk.BooleanVar(
            value=self._config.get("merge_video_with_tts", False)
        )
        self.tts_max_tempo_var = ctk.StringVar(
            value=str(self._config.get("tts_max_tempo", "1.6"))
        )

        # TTS voice tuning (preset + individual values)
        default_preset = self._config.get("tts_preset", TTS_PRESET_NAMES[0])
        if default_preset not in TTS_PRESETS:
            default_preset = TTS_PRESET_NAMES[0]
        preset_vals = TTS_PRESETS[default_preset] or (
            self._config.get("tts_stability", 0.5),
            self._config.get("tts_similarity", 0.75),
            self._config.get("tts_style", 0.0),
            self._config.get("tts_speed", 1.0),
            self._config.get("tts_speaker_boost", True),
        )
        self.tts_preset_var = ctk.StringVar(value=default_preset)
        self.tts_stability_var = ctk.DoubleVar(value=preset_vals[0])
        self.tts_similarity_var = ctk.DoubleVar(value=preset_vals[1])
        self.tts_style_var = ctk.DoubleVar(value=preset_vals[2])
        self.tts_speed_var = ctk.DoubleVar(value=preset_vals[3])
        self.tts_boost_var = ctk.BooleanVar(value=preset_vals[4])

        self._build_ui()
        self._center_window()

    def _center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        # ── Header ──
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(18, 5))

        ctk.CTkLabel(
            header, text="🎬  TÁCH ẢNH TỪ VIDEO (BATCH)",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack()
        ctk.CTkLabel(
            header,
            text="Chọn folder chứa video — xử lý hàng loạt, mỗi video xuất vào folder _frames riêng",
            font=ctk.CTkFont(size=13),
            text_color="gray",
        ).pack(pady=(2, 0))

        # ── Videos folder selection ──
        vid_frame = ctk.CTkFrame(self)
        vid_frame.pack(fill="x", padx=20, pady=(12, 6))

        ctk.CTkLabel(vid_frame, text="📁  Folder chứa video:", font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=12, pady=(10, 4))
        row = ctk.CTkFrame(vid_frame, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 10))
        ctk.CTkEntry(row, textvariable=self.videos_dir_var, state="readonly").pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row, text="Duyệt...", width=90, command=self._browse_videos_dir).pack(side="right", padx=(8, 0))

        # ── Output folder (optional override) ──
        out_frame = ctk.CTkFrame(self)
        out_frame.pack(fill="x", padx=20, pady=6)

        ctk.CTkLabel(
            out_frame,
            text="💾  Thư mục output (tùy chọn — để trống = cùng folder video):",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(10, 4))
        row2 = ctk.CTkFrame(out_frame, fg_color="transparent")
        row2.pack(fill="x", padx=12, pady=(0, 10))
        ctk.CTkEntry(row2, textvariable=self.output_dir_var, state="readonly").pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row2, text="Duyệt...", width=90, command=self._browse_output).pack(side="right", padx=(8, 0))
        ctk.CTkButton(row2, text="Xóa", width=60, command=lambda: self.output_dir_var.set("")).pack(side="right", padx=(8, 0))

        # ── Character reference folder (for scene prompts) ──
        char_frame = ctk.CTkFrame(self)
        char_frame.pack(fill="x", padx=20, pady=6)

        ctk.CTkLabel(
            char_frame,
            text="👥  Folder ảnh nhân vật (cho scene prompts — vd: father.png, mother.png):",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(10, 4))
        row_char = ctk.CTkFrame(char_frame, fg_color="transparent")
        row_char.pack(fill="x", padx=12, pady=(0, 10))
        ctk.CTkEntry(row_char, textvariable=self.character_dir_var, state="readonly").pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row_char, text="Duyệt...", width=90, command=self._browse_character_dir).pack(side="right", padx=(8, 0))
        ctk.CTkButton(row_char, text="Xóa", width=60, command=lambda: self.character_dir_var.set("")).pack(side="right", padx=(8, 0))

        # ── Main options (checkboxes) ──
        opts_frame = ctk.CTkFrame(self)
        opts_frame.pack(fill="x", padx=20, pady=6)

        ctk.CTkLabel(
            opts_frame,
            text="✅  Tùy chọn xử lý:",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(10, 4))

        opts_inner = ctk.CTkFrame(opts_frame, fg_color="transparent")
        opts_inner.pack(fill="x", padx=12, pady=(0, 10))

        ctk.CTkCheckBox(
            opts_inner, text="🖼  Tách video thành ảnh", variable=self.do_extract_frames_var,
            font=ctk.CTkFont(size=13),
        ).pack(side="left", padx=(0, 16))
        ctk.CTkCheckBox(
            opts_inner, text="🎙  Trích xuất phiên âm", variable=self.do_transcript_var,
            font=ctk.CTkFont(size=13),
        ).pack(side="left", padx=(0, 16))
        ctk.CTkCheckBox(
            opts_inner, text="🌐  Dịch phiên âm", variable=self.do_translate_var,
            font=ctk.CTkFont(size=13),
        ).pack(side="left", padx=(0, 16))
        ctk.CTkCheckBox(
            opts_inner, text="🔥  Viết lại viral (Codex)", variable=self.do_viral_rewrite_var,
            font=ctk.CTkFont(size=13),
        ).pack(side="left", padx=(0, 16))
        ctk.CTkCheckBox(
            opts_inner, text="🎬  Tạo scene prompts (Image + Grok/Veo3)", variable=self.do_scene_prompts_var,
            font=ctk.CTkFont(size=13),
        ).pack(side="left", padx=(0, 16))
        ctk.CTkCheckBox(
            opts_inner, text="🔊  Đọc transcript (ElevenLabs)", variable=self.do_tts_var,
            font=ctk.CTkFont(size=13),
        ).pack(side="left", padx=(0, 16))
        ctk.CTkCheckBox(
            opts_inner, text="🎞  Ghép video lồng tiếng", variable=self.do_merge_video_var,
            font=ctk.CTkFont(size=13),
        ).pack(side="left")

        # ── ElevenLabs TTS settings ──
        tts_frame = ctk.CTkFrame(self)
        tts_frame.pack(fill="x", padx=20, pady=6)

        ctk.CTkLabel(
            tts_frame, text="🔊  ElevenLabs TTS:",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(10, 4))

        # Row 1: API key
        tts_row1 = ctk.CTkFrame(tts_frame, fg_color="transparent")
        tts_row1.pack(fill="x", padx=12, pady=(0, 6))
        ctk.CTkLabel(tts_row1, text="API key:", font=ctk.CTkFont(size=12), width=80).pack(side="left")
        ctk.CTkEntry(tts_row1, textvariable=self.tts_api_key_var, show="•").pack(side="left", fill="x", expand=True, padx=(6, 0))
        ctk.CTkButton(
            tts_row1, text="Tải giọng", width=110, command=self._load_voices,
        ).pack(side="right", padx=(8, 0))

        # Row 2: Voice + model + filter
        tts_row2 = ctk.CTkFrame(tts_frame, fg_color="transparent")
        tts_row2.pack(fill="x", padx=12, pady=(0, 10))

        ctk.CTkLabel(tts_row2, text="Giọng:", font=ctk.CTkFont(size=12), width=80).pack(side="left")
        self.voice_menu = ctk.CTkOptionMenu(
            tts_row2, variable=self.tts_voice_var, values=["(Chưa tải giọng)"], width=260,
        )
        self.voice_menu.pack(side="left", padx=(6, 10))

        ctk.CTkCheckBox(
            tts_row2, text="Chỉ giọng tiếng Việt",
            variable=self.tts_only_vi_var,
            font=ctk.CTkFont(size=12),
            command=self._refresh_voice_menu,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkLabel(tts_row2, text="Model:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(4, 4))
        ctk.CTkOptionMenu(
            tts_row2, variable=self.tts_model_var, values=ELEVENLABS_MODELS, width=180,
        ).pack(side="left")

        # Row 2b: Sync timestamps
        tts_row_sync = ctk.CTkFrame(tts_frame, fg_color="transparent")
        tts_row_sync.pack(fill="x", padx=12, pady=(0, 6))
        ctk.CTkCheckBox(
            tts_row_sync, text="🎯  Khớp timestamp với video (đồng bộ từng đoạn, nén/giãn tự động)",
            variable=self.tts_sync_timestamps_var,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            tts_row_sync, text="Max tempo:", font=ctk.CTkFont(size=11), text_color="gray",
        ).pack(side="left", padx=(16, 4))
        ctk.CTkOptionMenu(
            tts_row_sync,
            variable=self.tts_max_tempo_var,
            values=["1.3", "1.5", "1.6", "1.8", "2.0"], width=70,
        ).pack(side="left")
        ctk.CTkLabel(
            tts_row_sync,
            text="(cap khi nén cho khớp — càng cao càng biến giọng)",
            font=ctk.CTkFont(size=10), text_color="gray",
        ).pack(side="left", padx=(6, 0))

        # Row 3: Preset
        tts_row3 = ctk.CTkFrame(tts_frame, fg_color="transparent")
        tts_row3.pack(fill="x", padx=12, pady=(0, 6))
        ctk.CTkLabel(
            tts_row3, text="Preset nhịp điệu:", font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left")
        ctk.CTkOptionMenu(
            tts_row3, variable=self.tts_preset_var, values=TTS_PRESET_NAMES, width=320,
            command=self._on_preset_changed,
        ).pack(side="left", padx=(6, 10))
        ctk.CTkCheckBox(
            tts_row3, text="Speaker boost",
            variable=self.tts_boost_var,
            font=ctk.CTkFont(size=12),
            command=self._on_slider_changed,
        ).pack(side="left")

        # Row 4-7: Sliders
        self._tts_slider_labels = {}
        self._build_tts_slider(
            tts_frame, "stability", self.tts_stability_var,
            "Stability", "Thấp = biểu cảm, dao động — Cao = ổn định, đều",
            0.0, 1.0,
        )
        self._build_tts_slider(
            tts_frame, "similarity", self.tts_similarity_var,
            "Similarity", "Độ giống giọng gốc (0.7–0.85 thường tốt nhất)",
            0.0, 1.0,
        )
        self._build_tts_slider(
            tts_frame, "style", self.tts_style_var,
            "Style", "Độ kịch tính / phóng đại (v2/v3). Cao = drama hơn",
            0.0, 1.0,
        )
        self._build_tts_slider(
            tts_frame, "speed", self.tts_speed_var,
            "Speed", "Tốc độ đọc (0.7–1.2). Viral TikTok thường 1.08–1.15",
            0.7, 1.2,
            pady_bottom=10,
        )

        # ── Frame extraction settings ──
        settings_frame = ctk.CTkFrame(self)
        settings_frame.pack(fill="x", padx=20, pady=6)

        settings_inner = ctk.CTkFrame(settings_frame, fg_color="transparent")
        settings_inner.pack(fill="x", padx=12, pady=10)

        # Interval
        left = ctk.CTkFrame(settings_inner, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(left, text="⏱  Khoảng cách (giây):", font=ctk.CTkFont(size=13)).pack(anchor="w")
        ctk.CTkEntry(left, textvariable=self.interval_var, width=100, placeholder_text="5").pack(anchor="w", pady=(4, 0))

        # Whisper model
        mid = ctk.CTkFrame(settings_inner, fg_color="transparent")
        mid.pack(side="left", fill="x", expand=True, padx=20)
        ctk.CTkLabel(mid, text="🤖  Mô hình Whisper:", font=ctk.CTkFont(size=13)).pack(anchor="w")
        ctk.CTkOptionMenu(
            mid, variable=self.model_var, width=150,
            values=["tiny", "base", "small", "medium", "large", "turbo"],
        ).pack(anchor="w", pady=(4, 0))

        # Translation language
        right = ctk.CTkFrame(settings_inner, fg_color="transparent")
        right.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(right, text="🌐  Dịch sang:", font=ctk.CTkFont(size=13)).pack(anchor="w")
        ctk.CTkOptionMenu(
            right, variable=self.translate_var, width=180,
            values=[v for k, v in LANGUAGES.items() if k != "none"],
        ).pack(anchor="w", pady=(4, 0))

        # ── Viral rewrite — product info ──
        viral_frame = ctk.CTkFrame(self)
        viral_frame.pack(fill="x", padx=20, pady=6)

        ctk.CTkLabel(
            viral_frame,
            text="🔥  Thông tin sản phẩm cho viết viral (chỉ dùng khi tick \"Viết lại viral\"):",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(
            viral_frame,
            text="Ví dụ: tên SP, giá, USP, mã giảm giá, link bio... — để trống Codex sẽ chỉ dựa vào ảnh + transcript.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).pack(anchor="w", padx=12, pady=(0, 4))

        self.viral_product_info_textbox = ctk.CTkTextbox(
            viral_frame, height=70, font=ctk.CTkFont(size=12),
        )
        self.viral_product_info_textbox.pack(fill="x", padx=12, pady=(0, 10))

        # ── Buttons ──
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=10)

        self.start_btn = ctk.CTkButton(
            btn_frame, text="▶  BẮT ĐẦU XỬ LÝ", width=220, height=42,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#2ecc71", hover_color="#27ae60",
            command=self._start_processing,
        )
        self.start_btn.pack(side="left", expand=True)

        self.cancel_btn = ctk.CTkButton(
            btn_frame, text="✖  HỦY", width=120, height=42,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#e74c3c", hover_color="#c0392b",
            state="disabled",
            command=self._cancel_processing,
        )
        self.cancel_btn.pack(side="right", expand=True)

        # ── Progress ──
        prog_frame = ctk.CTkFrame(self)
        prog_frame.pack(fill="x", padx=20, pady=(6, 4))

        self.status_label = ctk.CTkLabel(
            prog_frame, text="Sẵn sàng", font=ctk.CTkFont(size=13),
            text_color="#3498db",
        )
        self.status_label.pack(anchor="w", padx=12, pady=(10, 4))

        self.progress_bar = ctk.CTkProgressBar(prog_frame, height=14)
        self.progress_bar.pack(fill="x", padx=12, pady=(0, 10))
        self.progress_bar.set(0)

        # ── Log ──
        self.log_textbox = ctk.CTkTextbox(self, height=140, font=ctk.CTkFont(size=12))
        self.log_textbox.pack(fill="both", padx=20, pady=(4, 16), expand=True)
        self.log_textbox.configure(state="disabled")

    # ── TTS tuning ──
    def _build_tts_slider(self, parent, key, var, label, hint, from_, to_, pady_bottom=4):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, pady_bottom))
        ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=12, weight="bold"), width=90).pack(side="left")
        value_lbl = ctk.CTkLabel(row, text=f"{var.get():.2f}", font=ctk.CTkFont(size=12), width=50)
        value_lbl.pack(side="right")
        slider = ctk.CTkSlider(
            row, variable=var, from_=from_, to=to_,
            number_of_steps=int((to_ - from_) * 100),
            command=lambda v, k=key: self._on_slider_changed(),
        )
        slider.pack(side="right", fill="x", expand=True, padx=(10, 6))
        ctk.CTkLabel(row, text=hint, font=ctk.CTkFont(size=11), text_color="gray").pack(side="right", padx=(8, 0))
        self._tts_slider_labels[key] = value_lbl

    def _update_slider_labels(self):
        mapping = {
            "stability": self.tts_stability_var,
            "similarity": self.tts_similarity_var,
            "style": self.tts_style_var,
            "speed": self.tts_speed_var,
        }
        for key, var in mapping.items():
            lbl = self._tts_slider_labels.get(key)
            if lbl is not None:
                lbl.configure(text=f"{var.get():.2f}")

    def _on_preset_changed(self, preset_name=None):
        preset_name = preset_name or self.tts_preset_var.get()
        vals = TTS_PRESETS.get(preset_name)
        if vals is None:
            # "Tùy chỉnh" — don't overwrite current values
            return
        stab, sim, style, speed, boost = vals
        self.tts_stability_var.set(stab)
        self.tts_similarity_var.set(sim)
        self.tts_style_var.set(style)
        self.tts_speed_var.set(speed)
        self.tts_boost_var.set(boost)
        self._update_slider_labels()

    def _on_slider_changed(self):
        # Switch to "Tùy chỉnh" when user manually tweaks a slider/boost
        current = self.tts_preset_var.get()
        vals = TTS_PRESETS.get(current)
        if vals is not None:
            stab, sim, style, speed, boost = vals
            if (abs(self.tts_stability_var.get() - stab) > 0.005
                or abs(self.tts_similarity_var.get() - sim) > 0.005
                or abs(self.tts_style_var.get() - style) > 0.005
                or abs(self.tts_speed_var.get() - speed) > 0.005
                or self.tts_boost_var.get() != boost):
                self.tts_preset_var.set("⚙  Tùy chỉnh")
        self._update_slider_labels()

    # ── ElevenLabs voices ──
    def _normalize_voice(self, v):
        vid = getattr(v, "voice_id", None) or (v.get("voice_id") if isinstance(v, dict) else None)
        name = getattr(v, "name", None) or (v.get("name") if isinstance(v, dict) else None) or "?"
        labels = getattr(v, "labels", None) or (v.get("labels") if isinstance(v, dict) else None) or {}
        if hasattr(labels, "model_dump"):
            labels = labels.model_dump()
        elif hasattr(labels, "dict"):
            labels = labels.dict()
        desc = getattr(v, "description", None) or (v.get("description") if isinstance(v, dict) else "") or ""
        category = getattr(v, "category", None) or (v.get("category") if isinstance(v, dict) else "") or ""
        fine = getattr(v, "fine_tuning", None) or (v.get("fine_tuning") if isinstance(v, dict) else None)
        verified_langs = []
        if fine is not None:
            vl = getattr(fine, "verified_languages", None) or (fine.get("verified_languages") if isinstance(fine, dict) else None) or []
            for item in vl:
                lang = getattr(item, "language", None) or (item.get("language") if isinstance(item, dict) else None)
                if lang:
                    verified_langs.append(str(lang).lower())

        label_parts = []
        if isinstance(labels, dict):
            for key in ("gender", "accent", "age", "use_case", "descriptive", "language"):
                val = labels.get(key)
                if val:
                    label_parts.append(str(val))
        label_str = ", ".join(label_parts)
        display = f"{name}" + (f"  ({label_str})" if label_str else "")
        if category and category != "premade":
            display += f"  [{category}]"

        return {
            "id": vid,
            "name": name,
            "labels": labels if isinstance(labels, dict) else {},
            "verified_langs": verified_langs,
            "description": desc,
            "category": category,
            "display": display,
        }

    def _load_voices(self):
        api_key = self.tts_api_key_var.get().strip()
        if not api_key:
            messagebox.showerror("Lỗi", "Vui lòng nhập API key ElevenLabs.")
            return

        self._log("Đang gọi ElevenLabs API để lấy danh sách giọng...")

        def _fetch():
            import traceback
            try:
                from elevenlabs.client import ElevenLabs
                client = ElevenLabs(api_key=api_key)

                collected = []
                # Try get_all first (user's voice library incl. premade defaults)
                try:
                    resp = client.voices.get_all(show_legacy=True)
                    voices_raw = getattr(resp, "voices", resp) or []
                    self.after(0, lambda n=len(voices_raw): self._log(f"get_all trả về {n} giọng."))
                    for v in voices_raw:
                        collected.append(self._normalize_voice(v))
                except Exception as e_get:
                    self.after(0, lambda msg=str(e_get): self._log(f"get_all lỗi: {msg}"))

                # If nothing (or as supplement), paginate through voices.search
                if len(collected) < 5:
                    try:
                        seen_ids = {v["id"] for v in collected if v["id"]}
                        next_token = None
                        pages = 0
                        while pages < 10:  # safety cap
                            kwargs = {"page_size": 100}
                            if next_token:
                                kwargs["next_page_token"] = next_token
                            resp2 = client.voices.search(**kwargs)
                            voices_raw = getattr(resp2, "voices", None) or []
                            for v in voices_raw:
                                norm = self._normalize_voice(v)
                                if norm["id"] and norm["id"] not in seen_ids:
                                    collected.append(norm)
                                    seen_ids.add(norm["id"])
                            next_token = getattr(resp2, "next_page_token", None)
                            has_more = getattr(resp2, "has_more", False)
                            pages += 1
                            if not next_token or not has_more:
                                break
                        self.after(0, lambda n=len(collected): self._log(f"search đã tổng hợp: {n} giọng."))
                    except Exception as e_search:
                        tb = traceback.format_exc()
                        self.after(0, lambda msg=str(e_search): self._log(f"search lỗi: {msg}"))
                        self.after(0, lambda tb=tb: self._log(tb.splitlines()[-1] if tb else ""))

                if not collected:
                    self.after(0, lambda: messagebox.showerror(
                        "Lỗi",
                        "Không lấy được giọng nào. Kiểm tra:\n"
                        "• API key đúng chưa?\n"
                        "• Tài khoản có quota không?\n"
                        "• Có giọng nào trong My Voices / Library không?\n\n"
                        "Xem log trong app để biết chi tiết lỗi.",
                    ))
                    return

                self.after(0, lambda: self._on_voices_loaded(collected))
            except Exception as e:
                tb = traceback.format_exc()
                self.after(0, lambda tb=tb: self._log(f"_load_voices lỗi:\n{tb}"))
                self.after(0, lambda msg=str(e): messagebox.showerror(
                    "Lỗi", f"Không tải được danh sách giọng:\n{msg}"
                ))

        threading.Thread(target=_fetch, daemon=True).start()

    def _on_voices_loaded(self, voices):
        self._voices_cache = voices
        # Persist API key
        self._config["elevenlabs_api_key"] = self.tts_api_key_var.get().strip()
        save_config(self._config)
        self._refresh_voice_menu()
        self._log(f"Đã tải {len(voices)} giọng từ ElevenLabs.")

    def _voice_matches_vietnamese(self, v):
        """Heuristic: voice supports Vietnamese based on labels/description/verified_languages."""
        if "vi" in v.get("verified_langs", []):
            return True
        hay = " ".join([
            str(v.get("name", "")),
            str(v.get("description", "")),
            " ".join(str(x) for x in (v.get("labels") or {}).values()),
        ]).lower()
        keywords = ["vietnam", "việt", "viet ", " viet"]
        return any(k in hay for k in keywords)

    def _refresh_voice_menu(self):
        if not self._voices_cache:
            self.voice_menu.configure(values=["(Chưa tải giọng)"])
            self.tts_voice_var.set("(Chưa tải giọng)")
            return

        if self.tts_only_vi_var.get():
            filtered = [v for v in self._voices_cache if self._voice_matches_vietnamese(v)]
            if not filtered:
                filtered = list(self._voices_cache)  # fallback: show all
        else:
            filtered = list(self._voices_cache)

        displays = [v["display"] for v in filtered]
        self.voice_menu.configure(values=displays)
        current = self.tts_voice_var.get()
        if current not in displays:
            self.tts_voice_var.set(displays[0])

    def _resolve_voice_id(self):
        display = self.tts_voice_var.get()
        for v in self._voices_cache:
            if v["display"] == display:
                return v["id"], v["name"]
        return None, None

    # ── Browsing ──
    def _browse_videos_dir(self):
        path = filedialog.askdirectory(title="Chọn folder chứa video")
        if path:
            self.videos_dir_var.set(path)

    def _browse_output(self):
        path = filedialog.askdirectory(title="Chọn thư mục output (tùy chọn)")
        if path:
            self.output_dir_var.set(path)

    def _browse_character_dir(self):
        path = filedialog.askdirectory(title="Chọn folder ảnh nhân vật tham chiếu")
        if path:
            self.character_dir_var.set(path)

    # ── Logging ──
    def _log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}\n"

        def _append():
            self.log_textbox.configure(state="normal")
            self.log_textbox.insert("end", line)
            self.log_textbox.see("end")
            self.log_textbox.configure(state="disabled")

        self.after(0, _append)

    def _update_progress(self, value, status_text=None):
        def _upd():
            self.progress_bar.set(value)
            if status_text:
                self.status_label.configure(text=status_text)

        self.after(0, _upd)

    def _find_videos(self, folder):
        """Return sorted list of video file Paths directly inside folder (non-recursive)."""
        folder_path = Path(folder)
        videos = [
            p for p in folder_path.iterdir()
            if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
        ]
        return sorted(videos, key=lambda p: p.name.lower())

    # ── Processing ──
    def _start_processing(self):
        if self._processing:
            return

        videos_dir = self.videos_dir_var.get().strip()
        output_root = self.output_dir_var.get().strip()
        interval_str = self.interval_var.get().strip()

        if not videos_dir or not os.path.isdir(videos_dir):
            messagebox.showerror("Lỗi", "Vui lòng chọn folder chứa video hợp lệ.")
            return

        videos = self._find_videos(videos_dir)
        if not videos:
            messagebox.showerror("Lỗi", "Không tìm thấy video nào trong folder đã chọn.")
            return

        do_extract = self.do_extract_frames_var.get()
        do_transcript = self.do_transcript_var.get()
        do_translate = self.do_translate_var.get()
        do_viral_rewrite = self.do_viral_rewrite_var.get()
        do_scene_prompts = self.do_scene_prompts_var.get()
        do_tts = self.do_tts_var.get()

        if not (do_extract or do_transcript):
            messagebox.showerror(
                "Lỗi",
                "Hãy tick ít nhất một trong các tùy chọn: 'Tách video thành ảnh' hoặc 'Trích xuất phiên âm'.",
            )
            return

        if do_tts and not do_transcript:
            messagebox.showerror(
                "Lỗi",
                "Muốn đọc transcript thì phải tick 'Trích xuất phiên âm' trước.",
            )
            return

        if do_viral_rewrite:
            if not do_transcript:
                messagebox.showerror(
                    "Lỗi",
                    "Viết lại viral cần bật 'Trích xuất phiên âm' để lấy nội dung gốc làm nguồn.",
                )
                return
            if not do_extract:
                messagebox.showerror(
                    "Lỗi",
                    "Viết lại viral cần ảnh sản phẩm — hãy tick 'Tách video thành ảnh'.",
                )
                return
            if not (shutil.which("codex") or shutil.which("codex.cmd")):
                messagebox.showerror(
                    "Lỗi",
                    "Không tìm thấy lệnh 'codex' trong PATH. Cài Codex CLI rồi thử lại.",
                )
                return

        viral_product_info = (
            self.viral_product_info_textbox.get("1.0", "end").strip()
            if (do_viral_rewrite or do_scene_prompts) else ""
        )

        character_dir = self.character_dir_var.get().strip()
        character_refs = []
        if do_scene_prompts and character_dir:
            if not os.path.isdir(character_dir):
                messagebox.showerror("Lỗi", f"Folder ảnh nhân vật không tồn tại:\n{character_dir}")
                return
            character_refs = collect_character_refs(character_dir)
            if not character_refs:
                messagebox.showerror(
                    "Lỗi",
                    "Folder ảnh nhân vật không có file ảnh hợp lệ (jpg/png/webp/bmp).",
                )
                return
            self._config["character_ref_dir"] = character_dir
            save_config(self._config)

        if do_scene_prompts:
            if not do_viral_rewrite and not do_transcript:
                messagebox.showerror(
                    "Lỗi",
                    "Tạo scene prompts cần có kịch bản nguồn — hãy bật 'Viết lại viral (Codex)' hoặc 'Trích xuất phiên âm'.",
                )
                return
            if not do_extract:
                messagebox.showerror(
                    "Lỗi",
                    "Tạo scene prompts cần ảnh tham chiếu — hãy tick 'Tách video thành ảnh'.",
                )
                return
            if not (shutil.which("codex") or shutil.which("codex.cmd")):
                messagebox.showerror(
                    "Lỗi",
                    "Không tìm thấy lệnh 'codex' trong PATH. Cài Codex CLI rồi thử lại.",
                )
                return

        do_merge_video = self.do_merge_video_var.get()
        if do_merge_video and not do_tts:
            messagebox.showerror(
                "Lỗi",
                "Ghép video lồng tiếng cần bật 'Đọc transcript (ElevenLabs)' để có audio mới.",
            )
            return

        tts_api_key = ""
        tts_voice_id = None
        tts_voice_name = None
        tts_model = self.tts_model_var.get()
        if do_tts:
            tts_api_key = self.tts_api_key_var.get().strip()
            if not tts_api_key:
                messagebox.showerror("Lỗi", "Vui lòng nhập API key ElevenLabs.")
                return
            tts_voice_id, tts_voice_name = self._resolve_voice_id()
            if not tts_voice_id:
                messagebox.showerror(
                    "Lỗi",
                    "Vui lòng bấm 'Tải giọng' rồi chọn một giọng đọc.",
                )
                return
            # Persist selections
            self._config["elevenlabs_api_key"] = tts_api_key
            self._config["elevenlabs_model"] = tts_model
            self._config["elevenlabs_only_vi"] = self.tts_only_vi_var.get()
            self._config["tts_preset"] = self.tts_preset_var.get()
            self._config["tts_stability"] = self.tts_stability_var.get()
            self._config["tts_similarity"] = self.tts_similarity_var.get()
            self._config["tts_style"] = self.tts_style_var.get()
            self._config["tts_speed"] = self.tts_speed_var.get()
            self._config["tts_speaker_boost"] = self.tts_boost_var.get()
            self._config["tts_sync_timestamps"] = self.tts_sync_timestamps_var.get()
            self._config["tts_max_tempo"] = self.tts_max_tempo_var.get()
            save_config(self._config)

        self._config["merge_video_with_tts"] = do_merge_video
        save_config(self._config)

        tts_settings = {
            "stability": self.tts_stability_var.get(),
            "similarity_boost": self.tts_similarity_var.get(),
            "style": self.tts_style_var.get(),
            "speed": self.tts_speed_var.get(),
            "use_speaker_boost": self.tts_boost_var.get(),
        }
        tts_sync = self.tts_sync_timestamps_var.get()
        try:
            tts_max_tempo = float(self.tts_max_tempo_var.get())
        except (TypeError, ValueError):
            tts_max_tempo = 1.6

        try:
            interval = float(interval_str)
            if interval <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Lỗi", "Khoảng cách giây phải là số dương.")
            return

        if do_transcript:
            if not get_ffmpeg_path():
                messagebox.showerror(
                    "Lỗi",
                    "Không tìm thấy ffmpeg. Vui lòng cài đặt ffmpeg và thêm vào PATH.",
                )
                return

        if output_root:
            os.makedirs(output_root, exist_ok=True)

        # Get translate language code
        translate_lang = "none"
        if do_translate:
            translate_display = self.translate_var.get()
            for code, name in LANGUAGES.items():
                if name == translate_display and code != "none":
                    translate_lang = code
                    break
            if translate_lang == "none":
                messagebox.showerror("Lỗi", "Vui lòng chọn ngôn ngữ để dịch.")
                return

        if do_viral_rewrite and do_translate and translate_lang != "vi":
            messagebox.showerror(
                "Lỗi",
                "Viết lại viral chỉ xuất ra tiếng Việt. Nếu có bật dịch, hãy chọn 'Tiếng Việt' ở mục 'Dịch sang' (hoặc bỏ tick 'Dịch phiên âm' để Codex tự xử lý transcript gốc).",
            )
            return

        self._processing = True
        self._cancel_flag.clear()
        self.start_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")

        # Clear log
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", "end")
        self.log_textbox.configure(state="disabled")

        self.progress_bar.set(0)
        self.status_label.configure(text="Đang bắt đầu...", text_color="#3498db")

        thread = threading.Thread(
            target=self._batch_worker,
            args=(videos, videos_dir, output_root, interval, translate_lang,
                  do_extract, do_transcript, do_translate,
                  do_viral_rewrite, viral_product_info, do_scene_prompts, character_refs,
                  do_tts, tts_api_key, tts_voice_id, tts_voice_name, tts_model, tts_settings,
                  tts_sync, tts_max_tempo, do_merge_video),
            daemon=True,
        )
        thread.start()

    def _cancel_processing(self):
        self._cancel_flag.set()
        self._log("Đang hủy... Vui lòng chờ.")

    def _on_complete(self, success, message):
        self._processing = False
        self.start_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        if success:
            self.status_label.configure(text="Hoàn thành!", text_color="#2ecc71")
            self._log(f"Hoàn thành! {message}")
            messagebox.showinfo("Thành công", message)
        else:
            self.status_label.configure(text="Lỗi / Đã hủy", text_color="#e74c3c")
            self._log(f"Lỗi: {message}")
            messagebox.showerror("Lỗi", message)

    def _batch_worker(self, videos, videos_dir, output_root, interval, translate_lang,
                      do_extract, do_transcript, do_translate,
                      do_viral_rewrite, viral_product_info, do_scene_prompts, character_refs,
                      do_tts, tts_api_key, tts_voice_id, tts_voice_name, tts_model, tts_settings,
                      tts_sync, tts_max_tempo, do_merge_video):
        """Process every video in the folder sequentially."""
        try:
            total = len(videos)
            self._log(f"Tìm thấy {total} video trong folder.")

            # Load heavy models ONCE for the whole batch
            whisper_model = None
            tts_client = None

            if do_tts:
                try:
                    from elevenlabs.client import ElevenLabs
                    tts_client = ElevenLabs(api_key=tts_api_key)
                    self._log(f"ElevenLabs sẵn sàng. Giọng: {tts_voice_name} | Model: {tts_model}")
                    self._log(
                        f"Voice settings: stability={tts_settings['stability']:.2f}, "
                        f"similarity={tts_settings['similarity_boost']:.2f}, "
                        f"style={tts_settings['style']:.2f}, "
                        f"speed={tts_settings['speed']:.2f}, "
                        f"boost={tts_settings['use_speaker_boost']}"
                    )
                except Exception as e:
                    self._log(f"Không khởi tạo được ElevenLabs: {e}")
                    self.after(0, self._on_complete, False, f"Không khởi tạo được ElevenLabs: {e}")
                    return
            if do_transcript:
                model_name = self.model_var.get()
                self._update_progress(0, f"Đang tải mô hình Whisper ({model_name})...")
                self._log(f"Đang tải mô hình Whisper '{model_name}'...")
                whisper_model = whisper.load_model(model_name)
                self._log("Đã tải Whisper.")

                ffmpeg_bin = get_ffmpeg_path()
                ffmpeg_dir = os.path.dirname(os.path.abspath(ffmpeg_bin))
                if ffmpeg_dir not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")

            processed = 0
            failed_videos = []

            for idx, video_path in enumerate(videos):
                if self._cancel_flag.is_set():
                    self.after(0, self._on_complete, False, "Đã hủy bởi người dùng.")
                    return

                stem = video_path.stem
                if output_root:
                    out_dir = os.path.join(output_root, f"{stem}_frames")
                else:
                    out_dir = os.path.join(str(video_path.parent), f"{stem}_frames")
                os.makedirs(out_dir, exist_ok=True)

                self._log("")
                self._log(f"━━━ [{idx + 1}/{total}] {video_path.name} ━━━")
                self._log(f"Output: {out_dir}")

                base_progress = idx / total
                per_video_span = 1.0 / total

                def video_progress_cb(local_frac, status):
                    self._update_progress(
                        base_progress + local_frac * per_video_span,
                        f"[{idx + 1}/{total}] {status}",
                    )

                try:
                    self._process_single_video(
                        video_path=str(video_path),
                        output_dir=out_dir,
                        interval=interval,
                        translate_lang=translate_lang,
                        do_extract=do_extract,
                        do_transcript=do_transcript,
                        do_translate=do_translate,
                        do_viral_rewrite=do_viral_rewrite,
                        viral_product_info=viral_product_info,
                        do_scene_prompts=do_scene_prompts,
                        character_refs=character_refs,
                        whisper_model=whisper_model,
                        do_tts=do_tts,
                        tts_client=tts_client,
                        tts_voice_id=tts_voice_id,
                        tts_model=tts_model,
                        tts_settings=tts_settings,
                        tts_sync=tts_sync,
                        tts_max_tempo=tts_max_tempo,
                        do_merge_video=do_merge_video,
                        progress_cb=video_progress_cb,
                    )
                    processed += 1
                except Exception as e:
                    self._log(f"✖ Lỗi xử lý {video_path.name}: {e}")
                    failed_videos.append(video_path.name)

            self._update_progress(1.0, "Hoàn thành!")

            summary = f"Đã xử lý {processed}/{total} video."
            if failed_videos:
                summary += f"\nLỗi: {len(failed_videos)} video: " + ", ".join(failed_videos[:5])
                if len(failed_videos) > 5:
                    summary += f" (+{len(failed_videos) - 5} video khác)"
            summary += f"\nFolder nguồn: {videos_dir}"
            if output_root:
                summary += f"\nFolder output: {output_root}"

            self.after(0, self._on_complete, True, summary)

        except Exception as e:
            self.after(0, self._on_complete, False, str(e))

    def _process_single_video(self, video_path, output_dir, interval, translate_lang,
                              do_extract, do_transcript, do_translate,
                              do_viral_rewrite, viral_product_info, do_scene_prompts,
                              character_refs,
                              whisper_model,
                              do_tts, tts_client, tts_voice_id, tts_model, tts_settings,
                              tts_sync, tts_max_tempo,
                              do_merge_video,
                              progress_cb):
        """Run the extraction/transcript/translate/TTS pipeline for one video."""
        # Progress weights within this video — split remaining budget when TTS is enabled
        weights = {"frame": 0.0, "transcript": 0.0, "translate": 0.0, "tts": 0.0}
        if do_extract:
            weights["frame"] = 1.0
        if do_transcript:
            weights["transcript"] = 1.0
        if do_translate and do_transcript:
            weights["translate"] = 0.7
        if do_tts and do_transcript:
            weights["tts"] = 0.8
        total_w = sum(weights.values()) or 1.0
        w_frame = weights["frame"] / total_w
        w_transcript = weights["transcript"] / total_w
        w_translate = weights["translate"] / total_w
        w_tts = weights["tts"] / total_w

        count = 0

        # ── Phase 1: Frame extraction ──
        if do_extract:
            self._log(f"Mở video: {Path(video_path).name}")
            cap = cv2_open_video(video_path)
            if not cap.isOpened():
                raise RuntimeError(f"Không thể mở video: {video_path}")

            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration_sec = total_frames / fps if fps > 0 else 0
            frame_interval = max(1, int(fps * interval))
            total_extractions = max(1, total_frames // frame_interval)

            self._log(f"FPS: {fps:.1f} | Tổng frame: {total_frames} | Thời lượng: {duration_sec:.0f}s")
            self._log(f"Sẽ trích xuất ~{total_extractions} ảnh (mỗi {interval}s)")

            frame_index = 0
            while frame_index < total_frames:
                if self._cancel_flag.is_set():
                    cap.release()
                    raise RuntimeError("Đã hủy bởi người dùng.")

                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                ret, frame = cap.read()
                if not ret:
                    break

                filename = f"{count + 1}.jpg"
                filepath = os.path.join(output_dir, filename)

                cv2_save_image(filepath, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])

                count += 1
                local_prog = (count / total_extractions) * w_frame
                progress_cb(min(local_prog, w_frame), f"Đang trích xuất ảnh... ({count}/{total_extractions})")

                frame_index += frame_interval

            cap.release()
            self._log(f"Đã trích xuất {count} ảnh.")

        # ── Phase 2: Transcription ──
        segments = []
        full_text = ""

        if do_transcript:
            if self._cancel_flag.is_set():
                raise RuntimeError("Đã hủy bởi người dùng.")

            progress_cb(w_frame, "Đang trích xuất âm thanh...")
            self._log("Đang trích xuất âm thanh bằng ffmpeg...")

            audio_filename = Path(video_path).stem + "_audio.wav"
            audio_path = os.path.join(output_dir, audio_filename)
            ffmpeg_bin = get_ffmpeg_path()
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            result = subprocess.run(
                [
                    ffmpeg_bin, "-i", video_path,
                    "-vn", "-acodec", "pcm_s16le",
                    "-ar", "16000", "-ac", "1",
                    audio_path, "-y",
                ],
                capture_output=True, text=True,
                startupinfo=startupinfo,
            )

            if result.returncode != 0:
                raise RuntimeError(f"ffmpeg lỗi: {result.stderr[:200]}")

            if self._cancel_flag.is_set():
                raise RuntimeError("Đã hủy bởi người dùng.")

            progress_cb(w_frame + 0.05 * w_transcript, "Đang phiên âm... (có thể mất vài phút)")
            self._log("Đang phiên âm...")

            transcription = whisper_model.transcribe(audio_path, verbose=False)
            segments = transcription.get("segments", [])
            full_text = transcription.get("text", "").strip()

            # Save original transcript
            transcript_path = os.path.join(output_dir, "transcript.txt")
            self._save_transcript(
                transcript_path, video_path, self.model_var.get(),
                segments, full_text, lang_label="Gốc",
            )

            self._log(f"Đã lưu audio: {audio_filename}")
            self._log("Đã lưu phiên âm: transcript.txt")
            progress_cb(w_frame + w_transcript, "Phiên âm xong!")

        translated_full = None
        translated_segments = []
        tts_source_text = full_text
        tts_source_label = "gốc"
        tts_source_segments = segments  # default; switched to translated_segments if translation runs

        # ── Phase 3: Translation ──
        if do_translate and do_transcript and segments:
            if self._cancel_flag.is_set():
                raise RuntimeError("Đã hủy bởi người dùng.")

            lang_name = LANGUAGES.get(translate_lang, translate_lang)
            progress_cb(w_frame + w_transcript, f"Đang dịch sang {lang_name}...")
            self._log(f"Đang dịch transcript sang {lang_name}...")

            translated_segments = []
            total_segs = len(segments)
            for i, seg in enumerate(segments):
                if self._cancel_flag.is_set():
                    raise RuntimeError("Đã hủy bởi người dùng.")

                text = seg["text"].strip()
                if text:
                    translated = translate_text(text, translate_lang)
                    if translated is None:
                        translated = text
                else:
                    translated = ""

                translated_segments.append({
                    "start": seg["start"],
                    "end": seg["end"],
                    "text": translated,
                })

                if (i + 1) % 10 == 0 or i == total_segs - 1:
                    prog = w_frame + w_transcript + ((i + 1) / total_segs) * w_translate
                    progress_cb(prog, f"Đang dịch... ({i + 1}/{total_segs} đoạn)")

            self._log("Đang dịch toàn bộ nội dung...")
            translated_full = translate_text(full_text, translate_lang, log_fn=self._log)
            if translated_full is None:
                translated_full = "(Lỗi dịch toàn bộ nội dung)"

            translated_path = os.path.join(output_dir, f"transcript_{translate_lang}.txt")
            self._save_transcript(
                translated_path, video_path, self.model_var.get(),
                translated_segments, translated_full,
                lang_label=lang_name,
            )

            self._log(f"Đã lưu bản dịch: transcript_{translate_lang}.txt")
            tts_source_text = translated_full
            tts_source_label = f"dịch ({lang_name})"
            tts_source_segments = translated_segments

        # ── Phase 3.5: Viral rewrite via Codex CLI ──
        # Ưu tiên bản dịch tiếng Việt nếu có; nếu không, dùng thẳng transcript gốc
        # (Codex sẽ tự viết lại sang tiếng Việt dù gốc là tiếng Anh / hội thoại trộn).
        viral_script = None
        if do_viral_rewrite and do_transcript and full_text:
            source_text = translated_full if (translated_full) else full_text
            source_label = "bản dịch (vi)" if translated_full else "transcript gốc"

            if self._cancel_flag.is_set():
                raise RuntimeError("Đã hủy bởi người dùng.")

            self._log(f"Đang chọn ảnh tham chiếu cho Codex (nguồn: {source_label})...")
            viral_frames = pick_representative_frames(output_dir, n=5)
            if not viral_frames:
                self._log("⚠ Không tìm thấy ảnh frame để gửi Codex — bỏ qua viết lại viral.")
            else:
                self._log(f"Đã chọn {len(viral_frames)} ảnh: {[Path(p).name for p in viral_frames]}")
                progress_cb(w_frame + w_transcript + w_translate, "Đang viết lại viral bằng Codex CLI...")
                try:
                    viral_script = rewrite_transcript_viral(
                        vi_transcript=source_text,
                        frame_paths=viral_frames,
                        product_info=viral_product_info,
                        log_fn=self._log,
                    )
                    viral_path = os.path.join(output_dir, "transcript_viral.txt")
                    with open(viral_path, "w", encoding="utf-8") as f:
                        f.write(viral_script + "\n")
                    self._log(f"Đã lưu bản viral: transcript_viral.txt ({len(viral_script)} ký tự)")
                    tts_source_text = viral_script
                    tts_source_label = "viral (Codex)"
                    tts_source_segments = []  # viral script không có timestamp gốc
                except Exception as e:
                    self._log(f"✖ Lỗi viết lại viral: {e} — giữ nguyên nguồn cho TTS.")
                    viral_script = None

        # ── Phase 3.7: Scene breakdown + image/video prompts via Codex CLI ──
        # Ưu tiên viral script; nếu không có thì dùng transcript (dịch nếu có, không thì gốc).
        if do_scene_prompts:
            if viral_script:
                scene_source_text = viral_script
                scene_source_label = "viral (Codex)"
            elif translated_full:
                scene_source_text = translated_full
                scene_source_label = "bản dịch"
            elif full_text:
                scene_source_text = full_text
                scene_source_label = "transcript gốc"
            else:
                scene_source_text = ""
                scene_source_label = ""

            if not scene_source_text:
                self._log("⚠ Không có kịch bản nguồn cho scene prompts — bỏ qua.")
            else:
                if self._cancel_flag.is_set():
                    raise RuntimeError("Đã hủy bởi người dùng.")

                n_frames = calc_reference_frame_count(len(scene_source_text))
                self._log(f"Đang chọn {n_frames} ảnh tham chiếu cho scene breakdown (nguồn: {scene_source_label})...")
                scene_frames = pick_representative_frames(output_dir, n=n_frames)
                if not scene_frames:
                    self._log("⚠ Không có ảnh để tạo scene prompts — bỏ qua.")
                else:
                    self._log(f"Đã chọn {len(scene_frames)} ảnh: {[Path(p).name for p in scene_frames]}")
                    progress_cb(w_frame + w_transcript + w_translate, "Đang tạo scene prompts bằng Codex (3-10 phút)...")
                    try:
                        if character_refs:
                            self._log(
                                f"Dùng {len(character_refs)} ảnh nhân vật: "
                                + ", ".join(c[0] for c in character_refs)
                            )
                        raw = generate_scene_prompts(
                            viral_script=scene_source_text,
                            frame_paths=scene_frames,
                            product_info=viral_product_info,
                            character_refs=character_refs,
                            log_fn=self._log,
                        )
                        scenes_dir = os.path.join(output_dir, "scene_prompts")
                        written = split_scene_output(raw, scenes_dir)
                        if written:
                            self._log(f"Đã lưu {len(written)} file scene prompts vào: scene_prompts/")
                            for p in written:
                                self._log(f"  • {Path(p).name}")
                        else:
                            self._log("⚠ Codex output không có marker `===FILE: ...===` — chỉ lưu _raw_codex_output.txt.")
                    except Exception as e:
                        self._log(f"✖ Lỗi tạo scene prompts: {e}")

        # ── Phase 4: TTS via ElevenLabs ──
        if do_tts and do_transcript and tts_client is not None:
            if self._cancel_flag.is_set():
                raise RuntimeError("Đã hủy bởi người dùng.")

            base_prog = w_frame + w_transcript + w_translate
            progress_cb(base_prog, "Đang tạo giọng đọc (ElevenLabs)...")
            self._log(f"Đang TTS từ bản {tts_source_label}, model={tts_model}...")

            # Build VoiceSettings from tuning params (shared across both modes)
            voice_settings_obj = None
            try:
                from elevenlabs import VoiceSettings
                voice_settings_obj = VoiceSettings(
                    stability=float(tts_settings["stability"]),
                    similarity_boost=float(tts_settings["similarity_boost"]),
                    style=float(tts_settings["style"]),
                    use_speaker_boost=bool(tts_settings["use_speaker_boost"]),
                    speed=float(tts_settings["speed"]),
                )
            except Exception as e:
                self._log(f"Không tạo được VoiceSettings ({e}) — dùng mặc định của giọng.")

            if tts_sync and tts_source_segments:
                self._run_tts_sync(
                    output_dir=output_dir,
                    video_path=video_path,
                    segments=tts_source_segments,
                    tts_client=tts_client,
                    tts_voice_id=tts_voice_id,
                    tts_model=tts_model,
                    voice_settings_obj=voice_settings_obj,
                    max_tempo=tts_max_tempo,
                    progress_cb=progress_cb,
                    base_prog=base_prog,
                    w_tts=w_tts,
                )
            elif not tts_source_text.strip():
                self._log("Transcript rỗng — bỏ qua TTS.")
            else:
                self._run_tts_chunks(
                    output_dir=output_dir,
                    video_path=video_path,
                    tts_source_text=tts_source_text,
                    tts_client=tts_client,
                    tts_voice_id=tts_voice_id,
                    tts_model=tts_model,
                    voice_settings_obj=voice_settings_obj,
                    progress_cb=progress_cb,
                    base_prog=base_prog,
                    w_tts=w_tts,
                )

        # ── Phase 5: Mux video + TTS audio (dubbed video) ──
        if do_merge_video and do_tts:
            if self._cancel_flag.is_set():
                raise RuntimeError("Đã hủy bởi người dùng.")
            stem = Path(video_path).stem
            tts_audio = os.path.join(output_dir, f"{stem}_tts.mp3")
            if not os.path.isfile(tts_audio):
                self._log("Không tìm thấy file TTS — bỏ qua ghép video lồng tiếng.")
            else:
                dubbed_path = os.path.join(output_dir, f"{stem}_dubbed.mp4")
                progress_cb(1.0, "Đang ghép video + audio...")
                self._log(f"Đang ghép video gốc (đã tắt tiếng) + {Path(tts_audio).name}...")
                ffmpeg_bin = get_ffmpeg_path()
                try:
                    mux_video_with_audio(ffmpeg_bin, video_path, tts_audio, dubbed_path)
                    self._log(f"Đã lưu video lồng tiếng: {Path(dubbed_path).name}")
                except Exception as e:
                    self._log(f"Lỗi ghép video: {e}")

        progress_cb(1.0, "Xong video.")
        return

    def _run_tts_chunks(self, output_dir, video_path, tts_source_text,
                        tts_client, tts_voice_id, tts_model, voice_settings_obj,
                        progress_cb, base_prog, w_tts):
        """Non-sync TTS: chunk the whole text and concat chunks into one MP3."""
        chunks = chunk_text_for_tts(tts_source_text)
        self._log(f"Chia thành {len(chunks)} đoạn để gửi ElevenLabs.")

        stem = Path(video_path).stem
        part_files = []
        for i, chunk in enumerate(chunks):
            if self._cancel_flag.is_set():
                raise RuntimeError("Đã hủy bởi người dùng.")
            part_path = os.path.join(output_dir, f"{stem}_tts_part{i + 1:03d}.mp3")
            try:
                convert_kwargs = dict(
                    voice_id=tts_voice_id,
                    text=chunk,
                    model_id=tts_model,
                    output_format="mp3_44100_128",
                )
                if voice_settings_obj is not None:
                    convert_kwargs["voice_settings"] = voice_settings_obj
                audio_iter = tts_client.text_to_speech.convert(**convert_kwargs)
                with open(part_path, "wb") as f:
                    for piece in audio_iter:
                        if piece:
                            f.write(piece)
            except Exception as e:
                raise RuntimeError(f"ElevenLabs lỗi ở đoạn {i + 1}/{len(chunks)}: {e}")
            part_files.append(part_path)
            prog = base_prog + ((i + 1) / len(chunks)) * w_tts
            progress_cb(prog, f"TTS... ({i + 1}/{len(chunks)} đoạn)")

        final_path = os.path.join(output_dir, f"{stem}_tts.mp3")
        ffmpeg_bin = get_ffmpeg_path()
        merged = False
        if len(part_files) == 1:
            shutil.move(part_files[0], final_path)
            merged = True
            self._log(f"Đã lưu TTS: {Path(final_path).name}")
        elif ffmpeg_bin:
            try:
                concat_mp3_files(ffmpeg_bin, part_files, final_path)
                merged = True
                self._log(f"Đã ghép {len(part_files)} đoạn TTS -> {Path(final_path).name}")
            except Exception as e:
                self._log(f"Lỗi ghép MP3 ({e}); giữ lại các file part.")
        else:
            self._log("Không có ffmpeg để ghép — giữ lại các file part.")

        if merged:
            for p in part_files:
                if os.path.abspath(p) != os.path.abspath(final_path) and os.path.isfile(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass

    def _run_tts_sync(self, output_dir, video_path, segments,
                      tts_client, tts_voice_id, tts_model, voice_settings_obj,
                      max_tempo, progress_cb, base_prog, w_tts):
        """Generate per-segment TTS and assemble on a timeline matching original timestamps."""
        ffmpeg_bin = get_ffmpeg_path()
        ffprobe_bin = get_ffprobe_path()
        if not ffmpeg_bin:
            raise RuntimeError("Thiếu ffmpeg — không thể đồng bộ timestamp.")
        if not ffprobe_bin:
            self._log("Không tìm thấy ffprobe — sẽ giả định duration = target (có thể drift).")

        stem = Path(video_path).stem
        parts_dir = os.path.join(output_dir, f"{stem}_tts_parts")
        os.makedirs(parts_dir, exist_ok=True)

        timeline_files = []
        current_time = 0.0
        total = len(segments)
        produced = 0

        self._log(f"Chế độ sync timestamp: {total} segment, max_tempo={max_tempo:.2f}")

        for i, seg in enumerate(segments):
            if self._cancel_flag.is_set():
                raise RuntimeError("Đã hủy bởi người dùng.")

            seg_start = float(seg.get("start", 0.0) or 0.0)
            seg_end = float(seg.get("end", seg_start) or seg_start)
            seg_text = (seg.get("text") or "").strip()
            target_dur = max(seg_end - seg_start, 0.0)

            # Silence before segment start
            gap = seg_start - current_time
            if gap > 0.02:
                silence_path = os.path.join(parts_dir, f"gap_{i:04d}.mp3")
                make_silence_mp3(ffmpeg_bin, gap, silence_path)
                timeline_files.append(silence_path)
                current_time += gap

            if not seg_text:
                # Empty segment: just pad through end
                if target_dur > 0.02:
                    pad_path = os.path.join(parts_dir, f"empty_{i:04d}.mp3")
                    make_silence_mp3(ffmpeg_bin, target_dur, pad_path)
                    timeline_files.append(pad_path)
                    current_time = seg_end
                continue

            # Generate TTS for this segment
            raw_path = os.path.join(parts_dir, f"seg_{i:04d}_raw.mp3")
            try:
                convert_kwargs = dict(
                    voice_id=tts_voice_id,
                    text=seg_text,
                    model_id=tts_model,
                    output_format="mp3_44100_128",
                )
                if voice_settings_obj is not None:
                    convert_kwargs["voice_settings"] = voice_settings_obj
                audio_iter = tts_client.text_to_speech.convert(**convert_kwargs)
                with open(raw_path, "wb") as f:
                    for piece in audio_iter:
                        if piece:
                            f.write(piece)
            except Exception as e:
                raise RuntimeError(f"ElevenLabs lỗi ở segment {i + 1}/{total}: {e}")

            raw_dur = probe_duration_sec(ffprobe_bin, raw_path) if ffprobe_bin else target_dur

            # Fit into target duration (nén nếu quá dài)
            fitted_path = os.path.join(parts_dir, f"seg_{i:04d}.mp3")
            actual_dur = raw_dur
            if raw_dur > 0 and target_dur > 0.3 and raw_dur > target_dur * 1.03:
                tempo = min(raw_dur / target_dur, max(max_tempo, 1.01))
                try:
                    apply_atempo(ffmpeg_bin, raw_path, tempo, fitted_path)
                    actual_dur = raw_dur / tempo
                    if tempo >= max_tempo - 0.005 and raw_dur / tempo > target_dur * 1.05:
                        self._log(f"  seg {i + 1}: nén {tempo:.2f}x vẫn dài hơn target ({raw_dur:.2f}s > {target_dur:.2f}s) — timeline sẽ drift")
                except Exception as e:
                    self._log(f"  seg {i + 1}: atempo lỗi ({e}) — giữ nguyên")
                    shutil.copyfile(raw_path, fitted_path)
                    actual_dur = raw_dur
            else:
                shutil.copyfile(raw_path, fitted_path)

            # Remove raw
            try:
                os.remove(raw_path)
            except OSError:
                pass

            timeline_files.append(fitted_path)
            current_time += actual_dur

            # Pad with silence if TTS shorter than segment duration
            remaining = seg_end - current_time
            if remaining > 0.02:
                pad_path = os.path.join(parts_dir, f"pad_{i:04d}.mp3")
                make_silence_mp3(ffmpeg_bin, remaining, pad_path)
                timeline_files.append(pad_path)
                current_time = seg_end

            produced += 1
            prog = base_prog + ((i + 1) / total) * w_tts
            progress_cb(prog, f"TTS sync... ({i + 1}/{total} segment)")

        # Concat whole timeline
        final_path = os.path.join(output_dir, f"{stem}_tts.mp3")
        try:
            concat_mp3_files(ffmpeg_bin, timeline_files, final_path)
            self._log(f"Đã lưu TTS đồng bộ timestamp: {Path(final_path).name} ({produced}/{total} segment có TTS)")
        except Exception as e:
            self._log(f"Lỗi ghép timeline: {e} — giữ lại các file tại {parts_dir}")
            return

        # Cleanup parts folder
        try:
            shutil.rmtree(parts_dir)
        except OSError:
            pass

    def _save_transcript(self, filepath, video_path, model_name, segments, full_text, lang_label=""):
        """Save transcript file with timestamps and full content."""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"Phiên âm video: {Path(video_path).name}\n")
            f.write(f"Ngày tạo: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Mô hình: {model_name}\n")
            if lang_label:
                f.write(f"Ngôn ngữ: {lang_label}\n")
            f.write("=" * 60 + "\n\n")

            for seg in segments:
                start = seg["start"]
                end = seg["end"]
                text = seg["text"].strip()
                sh, sm, ss = int(start // 3600), int((start % 3600) // 60), start % 60
                eh, em, es = int(end // 3600), int((end % 3600) // 60), end % 60
                f.write(f"[{sh:02d}:{sm:02d}:{ss:05.2f} --> {eh:02d}:{em:02d}:{es:05.2f}]  {text}\n")

            f.write("\n" + "=" * 60 + "\n")
            f.write("TOÀN BỘ NỘI DUNG:\n\n")
            f.write(full_text + "\n")


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = App()
    app.mainloop()
