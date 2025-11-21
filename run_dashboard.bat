@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

REM Navigate to project root (current directory of this script)
cd /d "%~dp0"
if errorlevel 1 (
    echo Ошибка: Не удалось перейти в директорию скрипта.
    pause
    exit /b 1
)

echo.
echo === Django Dashboard Launcher ===
echo.

REM Optional virtual environment activation (if exists)
if exist "venv\Scripts\activate.bat" (
    echo Активируем виртуальное окружение...
    call "venv\Scripts\activate.bat"
) else (
    echo Виртуальное окружение не найдено, используется системный Python.
    echo.
    echo Проверяем установленные зависимости...
    python -c "import django" >nul 2>&1
    if errorlevel 1 (
        echo Django не найден. Устанавливаем зависимости из requirements.txt...
        python -m pip install -r requirements.txt
        if errorlevel 1 (
            echo ОШИБКА: Не удалось установить зависимости!
            pause
            exit /b 1
        )
        echo Зависимости успешно установлены.
    )
)

echo.
echo Проверяем наличие Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ОШИБКА: Python не найден! Убедитесь, что Python установлен и добавлен в PATH.
    pause
    exit /b 1
)

echo.
echo Применяем миграции (на случай новых зависимостей)...
python manage.py migrate
if errorlevel 1 (
    echo Ошибка при выполнении миграций. Программа остановлена.
    pause
    exit /b 1
)

echo.
echo Запускаем сервер разработки. Нажмите CTRL+C для остановки.
echo.

REM Получаем IP-адрес для подключения из локальной сети
echo ========================================
echo Сервер будет доступен по адресам:
echo   - Локально: http://127.0.0.1:8000
echo.
echo Определяем IP-адрес в локальной сети...

for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    set "IP_ADDRESS=%%a"
    set "IP_ADDRESS=!IP_ADDRESS:~1!"
    if not "!IP_ADDRESS!"=="" (
        echo   - В локальной сети: http://!IP_ADDRESS!:8000
        goto :ip_found
    )
)

:ip_found
echo.
echo Для подключения с другого компьютера используйте IP-адрес
echo из вывода выше (например, http://192.168.1.100:8000)
echo ========================================
echo.
echo Запуск сервера...
echo.

REM Запускаем сервер на всех интерфейсах (0.0.0.0) для доступа из локальной сети
python manage.py runserver 0.0.0.0:8000





