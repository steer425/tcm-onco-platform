@echo off
setlocal enabledelayedexpansion

rem =====================================================================
rem  Purpose: One-stop release script for D:\tcm_backend.
rem
rem           Runs the whole checklist from rules.md chapter 9 in order:
rem             pre-flight checks -> add / commit / push -> verify
rem
rem           Why the extra blocks: this project has twice shipped a
rem           version that looked fine locally but never reached GitHub,
rem           and has bumped the version in only some of the five places
rem           that must agree. Both failures are silent - git status is
rem           clean, the files are on disk, nothing errors. This script
rem           makes them loud instead.
rem
rem  Usage:
rem   1. Just double-click it -> uses the DEFAULT_MSG below
rem      this default message is updated each time a new version is
rem      delivered, to match that version's summary
rem   2. Or run it from a command prompt with your own message:
rem      git_push.bat "your custom commit message"
rem
rem  Note: all messages are English on purpose. The Windows console
rem        defaults to cp950 and Chinese text inside a .bat usually
rem        renders as garbage, which would make a failed check
rem        unreadable at exactly the moment it matters.
rem
rem  Note: This always switches to D:\tcm_backend before running git
rem        commands. If your project folder is somewhere else, edit
rem        the PROJECT_DIR value below.
rem =====================================================================

rem ---- update these two lines every release ----------------------------
set "EXPECTED_VER=1.41.1"
set "DEFAULT_MSG=v1.41.1 add a DepMap sanity check that quantifies how much of the dependency table is just common essential genes, and turn ginseng targets into named cell lines worth testing"
rem ----------------------------------------------------------------------

set "PROJECT_DIR=D:\tcm_backend"
set "BACKEND_DOCS=https://tcm-onco-backend.onrender.com/docs"
set "WORKFLOW=.github/workflows/daily-news.yml"

rem Ad-hoc outputs from the analysis scripts. They land in the project
rem root, so "git add ." grabs them unless .gitignore stops it.
set "JUNK=ginseng_step2.md mw mw.md"

set "FAILED="

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
echo   Release check and push
echo ============================================
echo   Folder:           %PROJECT_DIR%
echo   Expected version: v%EXPECTED_VER%
echo   Commit message:   %MSG%
echo ============================================
echo.

rem =====================================================================
rem  PRE-FLIGHT - nothing is committed until every check passes
rem =====================================================================

echo [1/8] Version number must match in all five places
echo.
call :checkver "app\main.py"                 "version=.%EXPECTED_VER%"
call :checkver "app\routers\project_info.py" "APP_VERSION = .%EXPECTED_VER%"
call :checkver "README.md"                   "v%EXPECTED_VER%"
call :checkver "CHANGELOG.md"                "## v%EXPECTED_VER%"
call :checkver "git_push.bat"                "DEFAULT_MSG=v%EXPECTED_VER%"
echo.

echo [2/8] CI and schedule config must NOT be ignored
echo.
rem The v1.40.1 bug: .gitignore contained .github/workflows/, so the
rem daily news schedule existed on disk but never reached GitHub.
rem GitHub Actions only runs workflows that exist in the repo, and
rem nothing anywhere reports this - the schedule just never fires.
git check-ignore -q "%WORKFLOW%"
if not errorlevel 1 (
    echo   FAIL  %WORKFLOW% is ignored by .gitignore
    echo         GitHub Actions only runs workflows that exist in the repo.
    set "FAILED=1"
) else (
    echo   OK    %WORKFLOW% is not ignored
)
echo.

echo [3/8] Script output files must stay out of version control
echo.
for %%F in (%JUNK%) do (
    if exist "%%F" (
        git check-ignore -q "%%F"
        if errorlevel 1 (
            echo   FAIL  %%F exists and is NOT ignored - it would be committed
            set "FAILED=1"
        ) else (
            echo   OK    %%F is ignored
        )
    ) else (
        echo   OK    %%F not present
    )
)
echo.

echo [4/8] Working tree status
echo.
git status --short
echo.

if defined FAILED (
    echo ============================================
    echo   PRE-FLIGHT FAILED. Nothing was committed.
    echo   Fix every line marked FAIL above, then run
    echo   this script again.
    echo ============================================
    pause
    exit /b 1
)

echo ============================================
echo   All pre-flight checks passed.
echo ============================================
echo.
set /p CONFIRM="Continue? Type Y to proceed, anything else to cancel: "
if /i not "%CONFIRM%"=="Y" (
    echo.
    echo Cancelled. Nothing was changed.
    pause
    exit /b 0
)

rem =====================================================================
rem  COMMIT AND PUSH
rem =====================================================================

echo.
echo [5/8] git add .
git add .
if errorlevel 1 goto :error

echo.
echo [6/8] git commit
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
echo [7/8] git push
git push
if errorlevel 1 goto :pushfail

rem =====================================================================
rem  VERIFY - the commit is not the deliverable, the push is
rem =====================================================================

echo.
echo [8/8] Verify what actually reached GitHub
echo.
git fetch origin
for /f %%h in ('git rev-parse HEAD') do set "LOCALSHA=%%h"
for /f %%h in ('git rev-parse origin/main') do set "REMOTESHA=%%h"

if not "!LOCALSHA!"=="!REMOTESHA!" (
    echo   FAIL  local HEAD and origin/main differ
    echo         local:  !LOCALSHA!
    echo         remote: !REMOTESHA!
    echo         The push did not land. Do NOT use --force.
    set "FAILED=1"
) else (
    echo   OK    origin/main matches local HEAD
    echo         !LOCALSHA!
)

for %%F in (%JUNK%) do (
    git ls-files --error-unmatch "%%F" >nul 2>&1
    if not errorlevel 1 (
        echo   FAIL  %%F is tracked by git
        echo         run: git rm --cached %%F
        set "FAILED=1"
    ) else (
        echo   OK    %%F is not tracked
    )
)

git ls-files --error-unmatch "%WORKFLOW%" >nul 2>&1
if errorlevel 1 (
    echo   FAIL  %WORKFLOW% is not tracked - the schedule will not run
    set "FAILED=1"
) else (
    echo   OK    %WORKFLOW% is tracked
)

echo.
if defined FAILED (
    echo ============================================
    echo   PUSHED, BUT VERIFY FAILED.
    echo   Read every FAIL line above before assuming
    echo   this version is live.
    echo ============================================
    pause
    exit /b 1
)

echo ============================================
echo   Done. v%EXPECTED_VER% is on GitHub.
echo.
echo   Render backend and Cloudflare Pages frontend
echo   deploy from main automatically.
echo.
echo   Manual step - confirm the deploy finished,
echo   usually 2 to 3 minutes:
echo     %BACKEND_DOCS%
echo   That page should show version %EXPECTED_VER%.
echo   If it still shows the old one it is simply
echo   still deploying - wait and reload.
echo ============================================
pause
exit /b 0

rem =====================================================================
rem  Helpers
rem =====================================================================

:checkver
rem  %1 = file path, %2 = findstr regex that must match
rem  The patterns deliberately use . where the source has a quote
rem  character, so no pattern here needs an embedded quote.
if not exist %1 (
    echo   FAIL  %~1 not found
    set "FAILED=1"
    goto :eof
)
findstr /r /c:%2 %1 >nul
if errorlevel 1 (
    echo   FAIL  %~1 does not contain: %~2
    set "FAILED=1"
) else (
    echo   OK    %~1
)
goto :eof

:pushfail
echo.
echo ============================================
echo   PUSH REJECTED.
echo.
echo   If the message above says non-fast-forward
echo   or says your branch is behind, the remote
echo   has commits you do not have - someone edited
echo   files on github.com, or another machine
echo   pushed first.
echo.
echo   Look before you merge:
echo     git log --oneline HEAD..origin/main
echo     git pull --no-rebase origin main
echo     git push
echo.
echo   NEVER use git push --force here. Those remote
echo   commits may exist only on GitHub, with no copy
echo   on this machine, and force would delete them.
echo ============================================
pause
exit /b 1

:error
echo.
echo ============================================
echo   Something failed. Check the error message
echo   above to see which step failed.
echo   Common causes: git credentials not set up,
echo   or network issues.
echo ============================================
pause
exit /b 1
