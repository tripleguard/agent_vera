# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for Vera Voice Assistant

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules
import os

block_cipher = None

# Корневая папка проекта
PROJECT_ROOT = os.path.abspath('.')

# Собираем все зависимости для llama_cpp
llama_datas, llama_binaries, llama_hiddenimports = collect_all('llama_cpp')

# Собираем все зависимости для vosk
vosk_datas, vosk_binaries, vosk_hiddenimports = collect_all('vosk')

# Собираем pyttsx3
pyttsx3_datas, pyttsx3_binaries, pyttsx3_hiddenimports = collect_all('pyttsx3')



# Hidden imports для всех модулей проекта
project_hiddenimports = [
    # pyttsx3 драйверы
    'pyttsx3.drivers',
    'pyttsx3.drivers.sapi5',
    'pyttsx3.drivers.dummy',
    # win32 модули
    'win32api',
    'win32con',
    'win32gui',
    'win32process',
    'win32com',
    'win32com.client',
    'pywintypes',
    'pythoncom',
    # pycaw
    'pycaw',
    'pycaw.pycaw',
    'comtypes',
    # другие
    'ctypes',
    'ctypes.wintypes',
    'sounddevice',
    'PIL',
    'PIL.Image',
    'PIL.ImageGrab',
    'aiohttp',
    'bs4',
    'requests',
    'psutil',
    'screen_brightness_control',
    'win11toast',
    # модули проекта
    'main',
    'main.agent',
    'main.config_manager',
    'main.lang_ru',
    'main.multitask',
    'main.commands',
    'main.commands.app_control',
    'main.commands.file_operations',
    'main.commands.power_manager',
    'main.commands.recyclebin_commands',
    'main.commands.system_control',
    'main.commands.time_commands',
    'main.commands.user_commands',
    'main.commands.web_commands',
    'main.commands.window_manager',
    'main.tray',
    'pystray',
    'six',
    'web',
    'web.async_fetch',
    'web.currency',
    'web.weather',
    'web.web_search',
    'web.web_utils',
    'user',
    'user.history_logger',
    'user.notifications',
    'user.tasks',
    'user.user_profile',
]

# Все hidden imports
all_hiddenimports = (
    llama_hiddenimports + 
    vosk_hiddenimports + 
    pyttsx3_hiddenimports + 
    project_hiddenimports
)

# Данные проекта
# config.json создаётся автоматически при первом запуске (см. config_manager.py)
project_datas = [
    # Ресурсы main
    ('main/system_prompt.txt', 'main'),
    ('main/lang_ru.py', 'main'),
]

# Модели будут скопированы отдельно (не в bundle) - см. build.bat
# - Qwen3-1.7B-Q4_K_M.gguf (~1.1GB)
# - vosk-model-small-ru-0.22/ (~45MB)

# Все данные
all_datas = llama_datas + vosk_datas + pyttsx3_datas + project_datas

# Все бинарники
all_binaries = llama_binaries + vosk_binaries + pyttsx3_binaries

a = Analysis(
    ['run_vera.py'],
    pathex=[PROJECT_ROOT],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=all_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Исключаем ненужные тяжелые пакеты
        'tensorflow',
        'torch',
        'torchvision',
        'torchaudio',
        'xformers',
        'triton',
        'cupy',
        'numba',
        'numpy.distutils',
        'matplotlib',
        'scipy',
        'pandas',
        'notebook',
        'IPython',
        'jupyter',
        'jupyterlab',
        'transformers',
        'accelerate',
        'bitsandbytes',
        'safetensors',
        'huggingface_hub',
        'tokenizers',
        'sentencepiece',
        'onnx',
        'onnxruntime',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Vera',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # Консольное приложение (для голосового ассистента)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='vera.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Vera',
)
