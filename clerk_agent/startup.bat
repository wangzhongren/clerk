@echo off
REM Clerk Agent 一键启动脚本 (Windows)
REM 功能：检查Python环境，自动安装依赖，创建虚拟环境，启动服务

setlocal enabledelayedexpansion

REM 设置变量
set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%"
set "VENV_DIR=%PROJECT_DIR%.venv"
set "REQUIREMENTS_FILE=%PROJECT_DIR%requirements.txt"

REM 颜色定义（简化版）
set "RED=31"
set "GREEN=32"
set "YELLOW=33"
set "BLUE=34"

:main
call :log "开始 Clerk Agent 一键启动流程..."

REM 检查 Python 3.10
call :check_python

REM 创建目录结构
call :create_directory_structure

REM 创建 requirements 文件
call :create_requirements_file

REM 设置虚拟环境
call :setup_virtual_environment

REM 启动应用
call :start_application

goto :eof

:log
echo [INFO] %~1
exit /b

:warn
echo [WARN] %~1
exit /b

:error
echo [ERROR] %~1
pause
exit /b 1

:success
echo [SUCCESS] %~1
exit /b

:check_python
call :log "检查 Python 3.10 安装状态..."

REM 尝试查找 python3.10
where python3.10 >nul 2>&1
if %errorlevel% == 0 (
    set "PYTHON_CMD=python3.10"
    call :log "Python 3.10 已安装"
    goto :eof
)

REM 尝试查找 python3
where python3 >nul 2>&1
if %errorlevel% == 0 (
    for /f "tokens=2" %%i in ('python3 --version') do set "PY_VERSION=%%i"
    if "!PY_VERSION:~0,4!"=="3.10" (
        set "PYTHON_CMD=python3"
        call :log "检测到 Python !PY_VERSION!"
        goto :eof
    )
)

REM 尝试查找 python
where python >nul 2>&1
if %errorlevel% == 0 (
    for /f "tokens=2" %%i in ('python --version 2^>^&1') do set "PY_VERSION=%%i"
    if "!PY_VERSION:~0,4!"=="3.10" (
        set "PYTHON_CMD=python"
        call :log "检测到 Python !PY_VERSION!"
        goto :eof
    )
)

REM 未找到 Python 3.10，提示用户安装
call :warn "未找到 Python 3.10，请手动安装 Python 3.10"
call :warn "下载地址: https://www.python.org/downloads/release/python-31012/"
call :warn "安装时请勾选 'Add Python to PATH' 选项"
pause
call :error "Python 3.10 未安装，无法继续"

:eof

:create_directory_structure
call :log "创建项目目录结构..."
if not exist "%PROJECT_DIR%skills" mkdir "%PROJECT_DIR%skills"
if not exist "%PROJECT_DIR%scripts" mkdir "%PROJECT_DIR%scripts"
if not exist "%PROJECT_DIR%tasks" mkdir "%PROJECT_DIR%tasks"
if not exist "%PROJECT_DIR%workspace" mkdir "%PROJECT_DIR%workspace"

REM 创建默认的 self.md
if not exist "%PROJECT_DIR%self.md" (
    echo # Clerk 自我设定 > "%PROJECT_DIR%self.md"
    echo. >> "%PROJECT_DIR%self.md"
    echo - 工作空间: %PROJECT_DIR%workspace >> "%PROJECT_DIR%self.md"
    echo - 当前环境: Windows >> "%PROJECT_DIR%self.md"
)

REM 创建默认的 user.md
if not exist "%PROJECT_DIR%user.md" (
    echo # 用户画像 > "%PROJECT_DIR%user.md"
    echo. >> "%PROJECT_DIR%user.md"
    echo - 姓名: 未设置 >> "%PROJECT_DIR%user.md"
    echo - 偏好: 未设置 >> "%PROJECT_DIR%user.md"
)

REM 创建默认的 config.yaml
if not exist "%PROJECT_DIR%config.yaml" (
    echo api_key: "" > "%PROJECT_DIR%config.yaml"
    echo base_url: "https://api.openai.com/v1" >> "%PROJECT_DIR%config.yaml"
    echo model: "gpt-4o-mini" >> "%PROJECT_DIR%config.yaml"
    echo dangerous_commands: >> "%PROJECT_DIR%config.yaml"
    echo   - "rm -rf /" >> "%PROJECT_DIR%config.yaml"
    echo   - "format" >> "%PROJECT_DIR%config.yaml"
    echo   - "mkfs" >> "%PROJECT_DIR%config.yaml"
    echo   - "fdisk" >> "%PROJECT_DIR%config.yaml"
    echo metadata: >> "%PROJECT_DIR%config.yaml"
    echo   name: "Clerk" >> "%PROJECT_DIR%config.yaml"
    echo   version: "3.0.0" >> "%PROJECT_DIR%config.yaml"
    echo   description: "办公自动化智能体" >> "%PROJECT_DIR%config.yaml"
    echo skills_dir: "./skills" >> "%PROJECT_DIR%config.yaml"
    echo tasks_dir: "./tasks" >> "%PROJECT_DIR%config.yaml"
    echo temp_scripts_dir: "./temp_scripts" >> "%PROJECT_DIR%config.yaml"
    echo workspace_root: "./workspace" >> "%PROJECT_DIR%config.yaml"
)

:eof

:create_requirements_file
if not exist "%REQUIREMENTS_FILE%" (
    call :log "创建默认的 requirements.txt..."
    echo Flask==2.3.3 > "%REQUIREMENTS_FILE%"
    echo Flask-CORS==4.0.0 >> "%REQUIREMENTS_FILE%"
    echo PyYAML==6.0.1 >> "%REQUIREMENTS_FILE%"
    echo openai==1.12.0 >> "%REQUIREMENTS_FILE%"
    echo markdown==3.4.4 >> "%REQUIREMENTS_FILE%"
)

:eof

:setup_virtual_environment
call :log "设置虚拟环境..."

if not exist "%VENV_DIR%" (
    call :log "创建虚拟环境..."
    %PYTHON_CMD% -m venv "%VENV_DIR%"
)

call :log "激活虚拟环境并安装依赖..."
call "%VENV_DIR%\Scripts\activate.bat"
python -m pip install --upgrade pip

if exist "%REQUIREMENTS_FILE%" (
    call :log "安装项目依赖..."
    pip install -r "%REQUIREMENTS_FILE%"
) else (
    call :warn "未找到 requirements.txt 文件，跳过依赖安装"
)

:eof

:start_application
call :log "启动 Clerk Agent 服务..."
echo.
echo 🚀 Clerk Agent 3.0 WebUI 启动中...
echo ========================================
echo 🔧 访问地址: http://localhost:5000
echo 📁 项目目录: %PROJECT_DIR%
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set "PY_VER=%%i"
echo 🐍 Python 版本: %PY_VER%
echo ========================================
echo.

REM 在虚拟环境中运行应用
call "%VENV_DIR%\Scripts\activate.bat"
python "%PROJECT_DIR%app.py"

:eof