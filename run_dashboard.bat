@echo off
setlocal enabledelayedexpansion

REM Navigate to project root (current directory of this script)
cd /d "%~dp0"

echo.
echo === Django Dashboard Launcher ===
echo.

REM Optional virtual environment activation (if exists)
if exist "venv\Scripts\activate.bat" (
    echo Активируем виртуальное окружение...
    call "venv\Scripts\activate.bat"
) else (
    echo Виртуальное окружение не найдено, используется системный Python.
)

echo.
echo Применяем миграции (на случай новых зависимостей)...
python manage.py migrate
if errorlevel 1 (
    echo Ошибка при выполнении миграций. Программа остановлена.
    goto :eof
)

echo.
echo Запускаем сервер разработки. Нажмите CTRL+C для остановки.
python manage.py runserver





