@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

echo ============================================
echo   Vera Voice Assistant - Build Script
echo ============================================
echo.

:: Проверка Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python не найден! Установите Python 3.10+
    pause
    exit /b 1
)

:: Проверка наличия модели LLM
if not exist "Qwen3-1.7B-Q4_K_M.gguf" (
    echo [ERROR] Модель LLM не найдена: Qwen3-1.7B-Q4_K_M.gguf
    echo         Скачайте модель и положите в корень проекта
    pause
    exit /b 1
)

:: Проверка наличия модели Vosk
if not exist "vosk-model-small-ru-0.22" (
    echo [ERROR] Модель Vosk не найдена: vosk-model-small-ru-0.22
    echo         Скачайте модель с https://alphacephei.com/vosk/models
    pause
    exit /b 1
)

echo [1/6] Установка/обновление PyInstaller...
pip install --upgrade pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [WARN] Не удалось обновить PyInstaller, используем текущую версию
)

echo [2/6] Проверка llama-cpp-python...
python -c "import llama_cpp" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Устанавливаем llama-cpp-python prebuilt wheel...
    pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
    if errorlevel 1 (
        echo [ERROR] Не удалось установить llama-cpp-python
        pause
        exit /b 1
    )
) else (
    echo   llama-cpp-python OK
)

echo [3/6] Очистка предыдущей сборки...
if exist "build" rmdir /s /q "build" >nul 2>&1
if exist "dist" rmdir /s /q "dist" >nul 2>&1

echo [4/6] Сборка Vera.exe...
echo.
echo *** Это может занять 5-15 минут ***
echo *** Итоговый размер: ~1.5 GB (включая модели) ***
echo.

pyinstaller vera.spec --noconfirm

if errorlevel 1 (
    echo.
    echo [ERROR] Сборка PyInstaller завершилась с ошибкой!
    echo         Проверьте логи выше
    pause
    exit /b 1
)

echo.
echo [5/6] Копирование моделей в dist\Vera...

:: Копируем LLM модель
echo   - Копирование LLM модели (~1.1 GB)...
copy "Qwen3-1.7B-Q4_K_M.gguf" "dist\Vera\" >nul 2>&1
if errorlevel 1 (
    echo [WARN] Не удалось скопировать LLM модель
)

:: Копируем Vosk модель
echo   - Копирование Vosk модели (~45 MB)...
xcopy /E /I /Y "vosk-model-small-ru-0.22" "dist\Vera\vosk-model-small-ru-0.22" >nul 2>&1
if errorlevel 1 (
    echo [WARN] Не удалось скопировать Vosk модель
)

:: Создаём папку data (config.json создастся автоматически при первом запуске)
if not exist "dist\Vera\data" mkdir "dist\Vera\data"

echo [6/6] Создание README для пользователя...

:: Создаём README в папке dist
(
echo ============================================
echo   Vera Voice Assistant
echo ============================================
echo.
echo ЗАПУСК:
echo   Дважды кликните на Vera.exe
echo.
echo ТРЕБОВАНИЯ:
echo   - Windows 10/11 x64
echo   - Microsoft Visual C++ Redistributable
echo     https://aka.ms/vs/17/release/vc_redist.x64.exe
echo.
echo ФАЙЛЫ:
echo   - Vera.exe - главный файл
echo   - Qwen3-1.7B-Q4_K_M.gguf - модель AI (или любой .gguf)
echo   - vosk-model-small-ru-0.22/ - модель распознавания речи
echo   - data/config.json - настройки (можно редактировать)
echo   - data/ - данные пользователя
echo.
echo ИСПОЛЬЗОВАНИЕ:
echo   1. Скажите "Вера" для активации
echo   2. Дайте голосовую команду
echo   3. /help для списка команд
echo   4. /exit для выхода
) > "dist\Vera\README.txt"

echo.
echo ============================================
echo   СБОРКА ЗАВЕРШЕНА УСПЕШНО!
echo ============================================
echo.
echo Результат: dist\Vera\
echo.
echo Содержимое:
dir /b "dist\Vera\*.exe" "dist\Vera\*.gguf" 2>nul
echo   + vosk-model-small-ru-0.22\
echo   + data\
echo   + _internal\ (библиотеки)
echo.
echo Для запуска:
echo   cd dist\Vera
echo   Vera.exe
echo.
echo ============================================
echo ВАЖНО: Для работы на другом ПК нужен
echo Microsoft Visual C++ Redistributable:
echo https://aka.ms/vs/17/release/vc_redist.x64.exe
echo ============================================
echo.

pause
