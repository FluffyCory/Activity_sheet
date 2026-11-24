@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "%~dp0python\python.exe" ("%~dp0python\python.exe" ActivitySheet.pyw --debug & pause & exit /b)
where python >nul 2>nul && (python ActivitySheet.pyw --debug) || (py -3 ActivitySheet.pyw --debug)
pause
