@echo off
setlocal

rem =====================================================================
rem  Purpose: Sync the contents of THIS folder (the newly extracted
rem           version) over D:\tcm_backend, keeping the .git folder
rem           untouched (so your git history / remote link is not
rem           affected).
rem
rem  Usage:   1. FULLY EXTRACT the zip file to a real folder first
rem              (right-click the zip -> Extract All... -> choose a
rem              destination). Do NOT double-click files while just
rem              browsing the zip in Windows Explorer as a compressed
rem              folder -- that only extracts a single file to a
rem              temporary folder and this script would then be unable
rem              to find the other files it needs to copy.
rem           2. After extracting, open the extracted tcm_backend
rem              folder and double-click this file directly from there.
rem
rem  Note:    This uses robocopy /MIR (mirror). Any file that exists in
rem           D:\tcm_backend but NOT in this new version will be
rem           DELETED (except .git), so the destination folder ends up
rem           identical to this source folder. If you keep local-only
rem           files in D:\tcm_backend (e.g. a local .db file or .env),
rem           back them up first.
rem =====================================================================

set "SOURCE=%~dp0"
rem %~dp0 always ends with a trailing backslash. If we keep that trailing
rem backslash and wrap the value in quotes like "%SOURCE%", the sequence
rem becomes ...\"  which Windows interprets as an ESCAPED quote character,
rem not a closing quote -- so the quoted string never actually closes and
rem everything after it (the destination path and all robocopy switches)
rem gets swallowed into one broken argument. Stripping the trailing
rem backslash here avoids that classic Windows quoting trap.
if "%SOURCE:~-1%"=="\" set "SOURCE=%SOURCE:~0,-1%"
set "DEST=D:\tcm_backend"

rem Safety check: if this script is running from a Windows temp folder,
rem it almost certainly means you double-clicked it while browsing the
rem zip file directly in Explorer, instead of fully extracting the zip
rem first. In that case only this .bat file was extracted to a temp
rem folder by Windows -- the other project files (frontend, app, etc.)
rem are NOT there, so syncing from here would copy little or nothing
rem useful, with no error message to warn you. Stop and tell the user.
echo "%SOURCE%" | findstr /i "AppData\Local\Temp" >nul
if not errorlevel 1 (
    echo ============================================
    echo   STOP: This looks like a temporary folder.
    echo ============================================
    echo   Detected source folder:
    echo     %SOURCE%
    echo.
    echo   This usually happens when you double-click a file while
    echo   just BROWSING the zip in Windows Explorer, without fully
    echo   extracting it first. Windows only extracts the single file
    echo   you clicked into a temp folder -- the rest of the project
    echo   files are not there, so this script cannot safely continue.
    echo.
    echo   Please do this instead:
    echo     1. Right-click the zip file -^> Extract All...
    echo     2. Choose a real destination folder and extract everything
    echo     3. Open the extracted tcm_backend folder
    echo     4. Double-click update_local_folder.bat from there
    echo ============================================
    pause
    exit /b 1
)

echo ============================================
echo   Update local folder
echo ============================================
echo   Source (this newly extracted version):
echo     %SOURCE%
echo   Destination (folder that will be overwritten):
echo     %DEST%
echo.
echo   The .git folder will be kept as-is (git history is safe).
echo   Any file under %DEST% that does NOT exist in the new
echo   version will be DELETED.
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
echo Syncing now...
echo.

robocopy "%SOURCE%" "%DEST%" /MIR /XD ".git" /R:2 /W:2 /NFL /NDL

rem robocopy exit codes 0-7 mean success (not an error), 8+ means real failure
if %ERRORLEVEL% GEQ 8 (
    echo.
    echo Sync failed. robocopy exit code: %ERRORLEVEL%
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Done! %DEST% now matches this new version.
echo   Next step: run git_push.bat to push to GitHub.
echo ============================================
pause
