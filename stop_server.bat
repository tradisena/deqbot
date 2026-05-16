@echo off
echo [*] Sending shutdown signal to control server...
echo [*] This will save all settings before closing.

curl -X POST http://localhost:5000/shutdown

echo.
echo [*] Shutdown signal sent.
echo [*] Please check the server window to confirm it has closed.
pause
