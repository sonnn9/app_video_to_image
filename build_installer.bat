@echo off
cd /d "%~dp0"

echo ============================================
echo   BUOC 1/2: DANG DONG GOI APP (PyInstaller)
echo ============================================
echo.

python -m PyInstaller build.spec --noconfirm --clean
if errorlevel 1 (
    echo.
    echo [LOI] PyInstaller that bai.
    pause
    exit /b 1
)

if not exist "dist\TachAnhTuVideo\TachAnhTuVideo.exe" (
    echo.
    echo [LOI] Khong tim thay dist\TachAnhTuVideo\TachAnhTuVideo.exe
    pause
    exit /b 1
)

echo.
echo ============================================
echo   BUOC 2/2: DANG TAO BO CAI (Inno Setup)
echo ============================================
echo.

set "ISCC1=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
set "ISCC2=%ProgramFiles%\Inno Setup 6\ISCC.exe"
set "ISCC3=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
set "ISCC="

if exist "%ISCC1%" set "ISCC=%ISCC1%"
if not defined ISCC if exist "%ISCC2%" set "ISCC=%ISCC2%"
if not defined ISCC if exist "%ISCC3%" set "ISCC=%ISCC3%"

if not defined ISCC (
    echo [LOI] Khong tim thay Inno Setup ISCC.exe
    echo Cai bang: winget install JRSoftware.InnoSetup
    pause
    exit /b 1
)

echo Dung ISCC: %ISCC%
echo.

"%ISCC%" installer.iss
if errorlevel 1 (
    echo.
    echo [LOI] Inno Setup bien dich that bai.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   DONG GOI THANH CONG!
echo   File: installer\TachAnhTuVideo_Setup_v1.0.0.exe
echo   -^> Copy file nay di cai tren bat ky may Win 10/11 nao.
echo ============================================
echo.
pause
