@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Запуск бота...
python bot.py
pause
