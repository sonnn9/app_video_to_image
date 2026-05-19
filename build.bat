@echo off
cd /d "%~dp0"
echo ============================================
echo   DANG DONG GOI APP - Tach Anh Tu Video
echo   (Co the mat 5-10 phut...)
echo ============================================
echo.

python -m PyInstaller build.spec --noconfirm --clean

echo.
if exist "dist\TachAnhTuVideo\TachAnhTuVideo.exe" (
    echo ============================================
    echo   DONG GOI THANH CONG!
    echo   File: dist\TachAnhTuVideo\TachAnhTuVideo.exe
    echo   Copy TOAN BO thu muc dist\TachAnhTuVideo\
    echo   de su dung tren may khac.
    echo ============================================
) else (
    echo   LOI: Dong goi that bai!
)
echo.
pause
