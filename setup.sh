#!/usr/bin/env bash
# ============================================================
#  AxonFlow — macOS / Linux 一键安装脚本
#  用法:  chmod +x setup.sh && ./setup.sh
# ============================================================

set -euo pipefail

# ---- 颜色输出 ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

info()  { printf "${BLUE}[INFO]${NC}  %s\n" "$*"; }
ok()    { printf "${GREEN}[  OK]${NC}  %s\n" "$*"; }
warn()  { printf "${YELLOW}[WARN]${NC}  %s\n" "$*"; }
fail()  { printf "${RED}[FAIL]${NC}  %s\n" "$*"; exit 1; }

# ---- 标题 ----
echo ""
printf "${BOLD}========================================${NC}\n"
printf "${BOLD}  AxonFlow 一键安装${NC}\n"
printf "${BOLD}  多智能体自治工作流引擎${NC}\n"
printf "${BOLD}========================================${NC}\n"
echo ""

# ---- 检查是否在项目根目录 ----
if [ ! -f "pyproject.toml" ]; then
    fail "请在 AxonFlow 项目根目录下运行此脚本"
fi

# ============================================================
#  第 1 步：检查系统依赖
# ============================================================
info "检查系统依赖..."

# Python >= 3.11
if command -v python3 &>/dev/null; then
    PY_CMD="python3"
elif command -v python &>/dev/null; then
    PY_CMD="python"
else
    fail "未找到 Python，请先安装 Python >= 3.11"
fi

PY_VERSION=$($PY_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$($PY_CMD -c 'import sys; print(sys.version_info.major)')
PY_MINOR=$($PY_CMD -c 'import sys; print(sys.version_info.minor)')

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; }; then
    fail "Python 版本 $PY_VERSION 过低，需要 >= 3.11（当前: $PY_VERSION）"
fi
ok "Python $PY_VERSION"

# Node.js >= 18
if command -v node &>/dev/null; then
    NODE_VERSION=$(node -v | sed 's/v//')
    NODE_MAJOR=$(echo "$NODE_VERSION" | cut -d. -f1)
    if [ "$NODE_MAJOR" -lt 18 ]; then
        fail "Node.js 版本过低，需要 >= 18（当前: $NODE_VERSION）"
    fi
    ok "Node.js $NODE_VERSION"
else
    fail "未找到 Node.js，请先安装 Node.js >= 18（推荐 20 LTS）"
fi

# npm
if command -v npm &>/dev/null; then
    NPM_VERSION=$(npm -v)
    ok "npm $NPM_VERSION"
else
    fail "未找到 npm，请先安装 Node.js（npm 随附安装）"
fi

# git
if command -v git &>/dev/null; then
    GIT_VERSION=$(git --version | sed 's/git version //')
    ok "Git $GIT_VERSION"
else
    fail "未找到 Git，请先安装 Git >= 2.0"
fi

# Redis (可选)
if command -v redis-cli &>/dev/null; then
    ok "Redis 已安装（可选依赖）"
else
    warn "未检测到 Redis — 将自动降级为内存消息总线（不影响使用）"
fi

echo ""

# ============================================================
#  第 2 步：创建 Python 虚拟环境
# ============================================================
info "创建 Python 虚拟环境..."

if [ -d ".venv" ]; then
    warn "虚拟环境 .venv 已存在，跳过创建"
else
    $PY_CMD -m venv .venv
    ok "虚拟环境已创建: .venv/"
fi

# 激活虚拟环境
# shellcheck disable=SC1091
source .venv/bin/activate
ok "虚拟环境已激活"

echo ""

# ============================================================
#  第 3 步：安装 Python 后端依赖
# ============================================================
info "安装 Python 后端依赖（含开发依赖）..."

pip install --upgrade pip -q
pip install -e ".[dev]" -q

ok "Python 依赖安装完成"
echo ""

# ============================================================
#  第 4 步：安装前端依赖
# ============================================================
info "安装前端依赖..."

if [ -d "frontend" ]; then
    (cd frontend && npm install --no-fund --no-audit)
    ok "前端依赖安装完成"
else
    warn "未找到 frontend/ 目录，跳过前端安装"
fi

echo ""

# ============================================================
#  第 5 步：构建前端（生产模式）
# ============================================================
info "构建前端..."

if [ -d "frontend" ]; then
    (cd frontend && npm run build)
    ok "前端构建完成: frontend/dist/"
else
    warn "跳过前端构建"
fi

echo ""

# ============================================================
#  第 6 步：配置环境变量
# ============================================================
info "配置环境变量..."

if [ -f "config/.env" ]; then
    warn "config/.env 已存在，跳过（不覆盖已有配置）"
else
    if [ -f "config/.env.example" ]; then
        cp config/.env.example config/.env
        ok "已从 .env.example 创建 config/.env"
        warn "请编辑 config/.env 填入你的 OPENAI_API_KEY"
    else
        warn "未找到 config/.env.example，请手动创建 config/.env 或设置环境变量"
    fi
fi

echo ""

# ============================================================
#  第 7 步：创建工作目录
# ============================================================
info "创建工作目录..."

mkdir -p workspace
ok "workspace/ 目录已就绪"

echo ""

# ============================================================
#  第 8 步：验证安装
# ============================================================
info "验证安装..."

# 快速测试 import
$PY_CMD -c "import axonflow; print(f'axonflow {axonflow.__version__ if hasattr(axonflow, \"__version__\") else \"0.1.0\"}')" 2>/dev/null \
    && ok "axonflow 模块导入正常" \
    || warn "axonflow 模块导入失败，请检查安装"

echo ""

# ============================================================
#  完成
# ============================================================
printf "${GREEN}${BOLD}========================================${NC}\n"
printf "${GREEN}${BOLD}  安装完成!${NC}\n"
printf "${GREEN}${BOLD}========================================${NC}\n"
echo ""
echo "接下来："
echo ""
echo "  1. 设置 API Key:"
echo "     export OPENAI_API_KEY=\"your-api-key-here\""
echo ""
echo "  2. 启动后端 API (终端 1):"
echo "     source .venv/bin/activate"
echo "     python -m uvicorn axonflow.api.app:app --port 8000 --reload"
echo ""
echo "  3. 启动前端 dev server (终端 2):"
echo "     cd frontend && npm run dev"
echo ""
echo "  4. 打开浏览器访问: http://localhost:5173"
echo ""
echo "  或使用 CLI 模式:"
echo "     source .venv/bin/activate"
echo "     axonflow status"
echo "     axonflow run dev-pipeline --input \"你的任务描述\""
echo ""
