@echo off
set PATH=D:\Git\cmd;%PATH%
cd /d D:\discord-gemini-bot
echo =========================================================
echo Pushing debate updates to GitHub (Naraito-ai/discord-gemini-bot)...
echo =========================================================
git push origin main
echo.
if %errorlevel% equ 0 (
    echo [SUCCESS] Pushed to GitHub successfully!
    echo Render will automatically begin deploying the update.
) else (
    echo [NOTICE] If prompted above, please complete the GitHub sign-in.
)
echo.
pause
