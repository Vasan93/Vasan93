@echo off
REM GrandmasterAI - double-click this file to start the app.
REM It only bypasses the execution policy for this one script, and changes nothing
REM about your machine's settings.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
