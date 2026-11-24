@echo off
cd /d "%~dp0"
rem 1) přibalený Python ve složce python\ (bez instalace), 2) Python v systému
if exist "%~dp0python\pythonw.exe" (start "" "%~dp0python\pythonw.exe" "%~dp0ActivitySheet.pyw" & exit /b)
where pythonw >nul 2>nul && (start "" pythonw "%~dp0ActivitySheet.pyw" & exit /b)
where pyw >nul 2>nul && (start "" pyw -3 "%~dp0ActivitySheet.pyw" & exit /b)
echo Python nebyl nalezen. Rozbal Python "embeddable" do slozky python\ (viz README.txt).
pause
