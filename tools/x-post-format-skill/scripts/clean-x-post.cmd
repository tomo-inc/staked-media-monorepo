@echo off
setlocal

if "%~1"=="" (
  echo Usage: scripts\clean-x-post.cmd ^<input.md^> [output.md]
  exit /b 1
)

set INPUT=%~1
set OUTPUT=%~2

if "%OUTPUT%"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0clean-x-post.ps1" -InputPath "%INPUT%"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0clean-x-post.ps1" -InputPath "%INPUT%" -OutputPath "%OUTPUT%"
)
