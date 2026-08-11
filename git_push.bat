@echo off
setlocal

rem =====================================================================
rem  Purpose: Run "git add ." / "git commit -m ..." / "git push" in
rem           sequence, instead of typing three commands every time.
rem
rem  Usage:
rem   1. Just double-click it -> uses the DEFAULT_MSG below
rem      (this default message is updated each time a new version is
rem      delivered, to match that version's summary)
rem   2. Or run it from a command prompt with your own message:
rem      git_push.bat "your custom commit message"
rem
rem  Note: This always switches to D:\tcm_backend before running git
rem        commands. If your project folder is somewhere else, edit
rem        the PROJECT_DIR value below.
rem =====================================================================

set "PROJECT_DIR=D:\tcm_backend"
set "DEFAULT_MSG=v1.32.1 add disease-centric GenCC query station, rename herb-centric page, fix unlimited list bug"

if not exist "%PROJECT_DIR%" (
    echo Folder not found: %PROJECT_DIR%
    echo Please check the path, or edit PROJECT_DIR at the top of this file.
    pause
    exit /b 1
)

cd /d "%PROJECT_DIR%"

set "MSG=%~1"
if "%MSG%"=="" set "MSG=%DEFAULT_MSG%"

echo ============================================
echo   Git commit and push
echo ============================================
echo   Folder: %PROJECT_DIR%
echo   Commit message: %MSG%
echo ============================================
echo.
set /p CONFIRM="Continue? Type Y to proceed, anything else to cancel: "
if /i not "%CONFIRM%"=="Y" (
    echo.
    echo Cancelled. Nothing was changed.
    pause
    exit /b 0
)

echo.
echo [1/3] git add .
git add .
if errorlevel 1 goto :error

echo.
echo [2/3] git commit -m "%MSG%"
git commit -m "%MSG%"
if errorlevel 1 (
    echo.
    echo Note: if the message above says "nothing to commit", it means
    echo git did not detect any file changes -- check whether you ran
    echo update_local_folder.bat first, or this version was already
    echo committed before.
    echo.
    echo Still trying git push below, in case there is an earlier
    echo commit that has not been pushed yet...
)

echo.
echo [3/3] git push
git push
if errorlevel 1 goto :error

echo.
echo ============================================
echo   Done! Pushed to the remote repository.
echo   Render (backend) and Cloudflare Pages (frontend)
echo   will detect the update on the main branch and
echo   start deploying automatically.
echo ============================================
pause
exit /b 0

:error
echo.
echo ============================================
echo   Something failed. Please check the error
echo   message above to see which step failed.
echo   Common causes: git credentials not set up,
echo   network issues, or someone else pushed to
echo   the remote repo first (conflict).
echo ============================================
pause
exit /b 1
