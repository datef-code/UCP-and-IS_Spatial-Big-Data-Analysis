@echo off
rem ===========================================================================
rem  Web console (SDP) - one-click launcher for the local service on Windows.
rem
rem  Double-click this file. Optional args:  --no-browser   |   --port 9000
rem  Stop with Ctrl+C or by closing the window.
rem
rem  WHY THIS FILE IS PURE ASCII:
rem  cmd.exe parses batch files using the OEM code page (GBK on zh-CN), NOT the
rem  code page set by `chcp`. Non-ASCII bytes in a .bat therefore get mis-paired,
rem  which silently swallows the next line's prefix. All Chinese user-facing text
rem  is printed by python (serve.py), where encoding is under our control.
rem  Keep this file ASCII + CRLF; do not "prettify" it with Chinese comments.
rem ===========================================================================
setlocal EnableDelayedExpansion
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
chcp 65001 >nul
title SDP - Local Service
cd /d "%~dp0.."

echo.
echo ===========================================================================
echo   SDP  -  local service  (details below are printed by python)
echo ===========================================================================

rem ---------- 1/4 locate python (prefer the repo's own venv) ----------
set "PY="
for %%P in ("%CD%\datakit\.venv\Scripts\python.exe" "%CD%\.venv\Scripts\python.exe") do (
  if not defined PY if exist %%~P set "PY=%%~P"
)
if not defined PY ( where py     >nul 2>nul && set "PY=py" )
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
  echo   [x] Python not found.
  echo       Install Python 3.11+, or restore the repo venv at datakit\.venv
  echo.
  pause
  exit /b 1
)

rem ---------- 2/4 check required deps ----------
"%PY%" -c "import datakit,pandas,numpy" >nul 2>nul
if errorlevel 1 (
  echo   [x] Missing dependencies: datakit + pandas + numpy are required.
  echo.
  echo       Use the venv shipped with this repo:
  echo         datakit\.venv\Scripts\python.exe
  echo       If it is gone, rebuild it as described in datakit\README.md
  echo.
  pause
  exit /b 1
)
echo   [ok] Python : %PY%
echo   [ok] deps   : datakit + pandas + numpy
"%PY%" -c "import statsmodels,libpysal,esda,spreg" >nul 2>nul
if errorlevel 1 (
  echo   [warn] optional deps missing: statsmodels / libpysal / esda / spreg
  echo          -^> "refit on your own data" and "spatial" will be degraded.
) else (
  echo   [ok] optional : refit + spatial available
)

rem ---------- 3/4 pick a free port (skip if the user passed --port) ----------
set "PORTARG="
echo %*| findstr /i /c:"--port" >nul 2>nul && set "PORTARG=1"
set "PORT="
if not defined PORTARG (
  set "FREEPORT="
  for %%P in (8765 8766 8767 8768 8770 8771 8772 8773) do (
    if not defined FREEPORT (
      netstat -ano | findstr /r /c:"127\.0\.0\.1:%%P .*LISTENING" >nul 2>nul
      if errorlevel 1 set "FREEPORT=%%P"
    )
  )
  if defined FREEPORT ( set "PORT=!FREEPORT!" ) else ( set "PORT=8799" )
)

echo.
if defined PORTARG (
  echo   port : given by args
) else (
  echo   port : !PORT!   ^(first free port from 8765^)
)
echo   stop : Ctrl+C  or close this window
echo ---------------------------------------------------------------------------
echo.

rem ---------- 4/4 start ----------
if defined PORTARG (
  "%PY%" "portal\serve.py" %*
) else (
  "%PY%" "portal\serve.py" --port !PORT! %*
)
set "RC=%ERRORLEVEL%"

echo.
echo ---------------------------------------------------------------------------
if not "%RC%"=="0" (
  echo   [x] service exited with code %RC%  ^(port taken? blocked by AV?^)
) else (
  echo   service stopped.
)
echo.
pause
endlocal
