#!/bin/bash

# Clerk Agent 一键启动脚本 (Linux/macOS)
# 功能：检查Python环境，自动安装依赖，创建虚拟环境，启动服务

set -e  # 遇到错误立即退出

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
VENV_DIR="$PROJECT_DIR/.venv"
REQUIREMENTS_FILE="$PROJECT_DIR/requirements.txt"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# 检查系统类型
check_system() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        SYSTEM="linux"
        if command -v apt-get &> /dev/null; then
            PKG_MANAGER="apt"
        elif command -v yum &> /dev/null; then
            PKG_MANAGER="yum"
        elif command -v dnf &> /dev/null; then
            PKG_MANAGER="dnf"
        else
            PKG_MANAGER="unknown"
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        SYSTEM="macos"
        if ! command -v brew &> /dev/null; then
            error "macOS 系统需要先安装 Homebrew: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
        fi
    else
        error "不支持的操作系统: $OSTYPE"
    fi
}

# 检查并安装 Python 3.10
install_python310() {
    log "检查 Python 3.10 安装状态..."
    
    if command -v python3.10 &> /dev/null; then
        log "Python 3.10 已安装"
        PYTHON_CMD="python3.10"
    elif command -v python3 &> /dev/null; then
        # 检查现有 Python 3 版本
        PY_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
        if [[ "$PY_VERSION" == 3.10* ]]; then
            log "检测到 Python $PY_VERSION"
            PYTHON_CMD="python3"
        else
            warn "检测到 Python $PY_VERSION，但需要 Python 3.10"
            install_python310_from_source
        fi
    else
        log "未找到 Python 3，开始安装 Python 3.10..."
        install_python310_from_source
    fi
}

# 从源码编译安装 Python 3.10
install_python310_from_source() {
    if [[ "$SYSTEM" == "linux" ]]; then
        log "在 Linux 系统上安装 Python 3.10 依赖..."
        case "$PKG_MANAGER" in
            "apt")
                sudo apt-get update
                sudo apt-get install -y build-essential zlib1g-dev libncurses5-dev libgdbm-dev libnss3-dev libssl-dev libreadline-dev libffi-dev libsqlite3-dev wget libbz2-dev
                ;;
            "yum"|"dnf")
                sudo ${PKG_MANAGER} groupinstall -y "Development Tools"
                sudo ${PKG_MANAGER} install -y gcc openssl-devel bzip2-devel libffi-devel zlib-devel
                ;;
            *)
                warn "无法自动安装编译依赖，请手动安装必要的开发包"
                ;;
        esac
        
        log "下载并编译 Python 3.10.12..."
        cd /tmp
        wget https://www.python.org/ftp/python/3.10.12/Python-3.10.12.tgz
        tar -xzf Python-3.10.12.tgz
        cd Python-3.10.12
        ./configure --enable-optimizations --prefix=/usr/local
        make -j$(nproc)
        sudo make altinstall
        PYTHON_CMD="python3.10"
        
    elif [[ "$SYSTEM" == "macos" ]]; then
        log "在 macOS 上通过 Homebrew 安装 Python 3.10..."
        brew install python@3.10
        PYTHON_CMD="python3.10"
    fi
}

# 创建和配置虚拟环境
setup_virtual_environment() {
    log "设置虚拟环境..."
    
    if [ ! -d "$VENV_DIR" ]; then
        log "创建虚拟环境..."
        "$PYTHON_CMD" -m venv "$VENV_DIR"
    fi
    
    log "激活虚拟环境..."
    source "$VENV_DIR/bin/activate"
    
    # 升级 pip
    python -m pip install --upgrade pip
    
    # 安装项目依赖
    if [ -f "$REQUIREMENTS_FILE" ]; then
        log "安装项目依赖..."
        pip install -r "$REQUIREMENTS_FILE"
    else
        warn "未找到 requirements.txt 文件，跳过依赖安装"
    fi
}

# 创建默认的 requirements.txt（如果不存在）
create_requirements_file() {
    if [ ! -f "$REQUIREMENTS_FILE" ]; then
        log "创建默认的 requirements.txt..."
        cat > "$REQUIREMENTS_FILE" << EOF
Flask==2.3.3
Flask-CORS==4.0.0
PyYAML==6.0.1
openai==1.12.0
markdown==3.4.4
EOF
    fi
}

# 创建必要的目录结构
create_directory_structure() {
    log "创建项目目录结构..."
    mkdir -p "$PROJECT_DIR/skills"
    mkdir -p "$PROJECT_DIR/scripts"
    mkdir -p "$PROJECT_DIR/tasks"
    mkdir -p "$PROJECT_DIR/workspace"
    
    # 创建默认的 self.md 和 user.md
    if [ ! -f "$PROJECT_DIR/self.md" ]; then
        echo "# Clerk 自我设定" > "$PROJECT_DIR/self.md"
        echo "" >> "$PROJECT_DIR/self.md"
        echo "- 工作空间: $PROJECT_DIR/workspace" >> "$PROJECT_DIR/self.md"
        echo "- 当前环境: $(uname -s)" >> "$PROJECT_DIR/self.md"
    fi
    
    if [ ! -f "$PROJECT_DIR/user.md" ]; then
        echo "# 用户画像" > "$PROJECT_DIR/user.md"
        echo "" >> "$PROJECT_DIR/user.md"
        echo "- 姓名: 未设置" >> "$PROJECT_DIR/user.md"
        echo "- 偏好: 未设置" >> "$PROJECT_DIR/user.md"
    fi
    
    # 创建默认的 config.yaml
    if [ ! -f "$PROJECT_DIR/config.yaml" ]; then
        cat > "$PROJECT_DIR/config.yaml" << EOF
api_key: ""
base_url: "https://api.openai.com/v1"
model: "gpt-4o-mini"
dangerous_commands:
  - "rm -rf /"
  - "format"
  - "mkfs"
  - "fdisk"
metadata:
  name: "Clerk"
  version: "3.0.0"
  description: "办公自动化智能体"
skills_dir: "./skills"
tasks_dir: "./tasks"
temp_scripts_dir: "./temp_scripts"
workspace_root: "./workspace"
EOF
    fi
}

# 启动应用
start_application() {
    log "启动 Clerk Agent 服务..."
    echo ""
    echo "🚀 Clerk Agent 3.0 WebUI 启动中..."
    echo "========================================"
    echo "🔧 访问地址: http://localhost:5000"
    echo "📁 项目目录: $PROJECT_DIR"
    echo "🐍 Python 版本: $($PYTHON_CMD --version)"
    echo "========================================"
    echo ""
    
    # 在虚拟环境中运行应用
    source "$VENV_DIR/bin/activate"
    python "$PROJECT_DIR/app.py"
}

# 主函数
main() {
    log "开始 Clerk Agent 一键启动流程..."
    
    # 检查系统
    check_system
    
    # 安装 Python 3.10
    install_python310
    
    # 创建目录结构
    create_directory_structure
    
    # 创建 requirements 文件
    create_requirements_file
    
    # 设置虚拟环境
    setup_virtual_environment
    
    # 启动应用
    start_application
}

# 运行主函数
main "$@"