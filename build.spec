# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Paths
# Auto-detect paths from the venv
SPEC_DIR = os.path.dirname(os.path.abspath('build.spec'))
VENV_SITE = os.path.join(SPEC_DIR, 'venv', 'Lib', 'site-packages')
CTK_PATH = os.path.join(VENV_SITE, 'customtkinter')
WHISPER_PATH = os.path.join(VENV_SITE, 'whisper')
FFMPEG_PATH = os.path.join(os.environ['LOCALAPPDATA'], 'Microsoft', 'WinGet', 'Packages',
    'Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe', 'ffmpeg-8.1-full_build', 'bin', 'ffmpeg.exe')
FFPROBE_PATH = os.path.join(os.environ['LOCALAPPDATA'], 'Microsoft', 'WinGet', 'Packages',
    'Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe', 'ffmpeg-8.1-full_build', 'bin', 'ffprobe.exe')

# EasyOCR + LaMa need data files and hidden submodules
easyocr_datas = collect_data_files('easyocr')
easyocr_hidden = collect_submodules('easyocr')
lama_datas = collect_data_files('simple_lama_inpainting')
lama_hidden = collect_submodules('simple_lama_inpainting')
elevenlabs_hidden = collect_submodules('elevenlabs')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[
        (FFMPEG_PATH, '.'),   # Bundle ffmpeg.exe at root
        (FFPROBE_PATH, '.'),  # Bundle ffprobe.exe at root (used for TTS timestamp sync)
    ],
    datas=[
        (CTK_PATH, 'customtkinter'),
        (os.path.join(WHISPER_PATH, 'assets'), os.path.join('whisper', 'assets')),
    ] + easyocr_datas + lama_datas,
    hiddenimports=[
        'tiktoken',
        'tiktoken_ext',
        'tiktoken_ext.openai_public',
        'torch',
        'torchvision',
        'numpy',
        'whisper',
        'whisper.model',
        'whisper.transcribe',
        'whisper.audio',
        'whisper.decoding',
        'whisper.tokenizer',
        'deep_translator',
        'deep_translator.google',
        'easyocr',
        'skimage',
        'scipy',
        'shapely',
        'pyclipper',
        'PIL',
        'simple_lama_inpainting',
        'elevenlabs',
        'httpx',
        'httpcore',
        'h11',
        'anyio',
        'pydantic',
        'pydantic_core',
        'websockets',
    ] + easyocr_hidden + lama_hidden + elevenlabs_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'IPython',
        'jupyter',
        'notebook',
        'pytest',
        'sphinx',
        'docutils',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TachAnhTuVideo',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TachAnhTuVideo',
)
