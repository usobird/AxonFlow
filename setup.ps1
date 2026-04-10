# ============================================================
#  AxonFlow — Windows PowerShell 一键安装脚本
#  用法:  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#         .\setup.ps1
# ============================================================

$ErrorActionPreference = "Stop"

# ---- 颜色输出 ----
function Write-Info  { Write-Host "[INFO]  $args" -ForegroundColor Cyan }
function Write-Ok    { Write-Host "[  OK]  $args" -ForegroundColor Green }
function Write-Warn  { Write-Host "[WARN]  $args" -ForegroundColor Yellow }
function Write-Fail  { Write-Host "[FAIL]  $args" -ForegroundColor Red; exit 1 }

# ---- 标题 ----
Write-Host ""
Write-Host "========================================" -ForegroundColor White
Write-Host "  AxonFlow 一键安装" -ForegroundColor White
Write-Host "  多智能体自治工作流引擎" -ForegroundColor White
Write-Host "========================================" -ForegroundColor White
Write-Host ""

# ---- 检查是否在项目根目录 ----
if (-not (Test-Path "pyproject.toml")) {
    Write-Fail "请在 AxonFlow 项目根目录下运行此脚本"
}

# ============================================================
#  第 1 步：检查系统依赖
# ============================================================
Write-Info "检查系统依赖..."

# Python >= 3.11
$pyCmd = $null
if (Get-Command "python" -ErrorAction SilentlyContinue) {
    $pyCmd = "python"
} elseif (Get-Command "python3" -ErrorAction SilentlyContinue) {
    $pyCmd = "python3"
} else {
    Write-Fail "未找到 Python，请先安装 Python >= 3.11 (https://www.python.org/downloads/)"
}

$pyVersion = & $pyCmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$pyMajor = & $pyCmd -c "import sys; print(sys.version_info.major)"
$pyMinor = & $pyCmd -c "import sys; print(sys.version_info.minor)"

if ([int]$pyMajor -lt 3 -or ([int]$pyMajor -eq 3 -and [int]$pyMinor -lt 11)) {
    Write-Fail "Python 版本 $pyVersion 过低，需要 >= 3.11"
}
Write-Ok "Python $pyVersion"

# Node.js >= 18
if (Get-Command "node" -ErrorAction SilentlyContinue) {
    $nodeVersion = (node -v).TrimStart("v")
    $nodeMajor = [int]($nodeVersion.Split(".")[0])
    if ($nodeMajor -lt 18) {
        Write-Fail "Node.js 版本过低，需要 >= 18（当前: $nodeVersion）"
    }
    Write-Ok "Node.js $nodeVersion"
} else {
    Write-Fail "未找到 Node.js，请先安装 Node.js >= 18（推荐 20 LTS, https://nodejs.org/）"
}

# npm
if (Get-Command "npm" -ErrorAction SilentlyContinue) {
    $npmVersion = npm -v
    Write-Ok "npm $npmVersion"
} else {
    Write-Fail "未找到 npm，请先安装 Node.js（npm 随附安装）"
}

# git
if (Get-Command "git" -ErrorAction SilentlyContinue) {
    $gitVersion = (git --version) -replace "git version ", ""
    Write-Ok "Git $gitVersion"
} else {
    Write-Fail "未找到 Git，请先安装 Git >= 2.0 (https://git-scm.com/)"
}

# Redis (可选)
if (Get-Command "redis-cli" -ErrorAction SilentlyContinue) {
    Write-Ok "Redis 已安装（可选依赖）"
} else {
    Write-Warn "未检测到 Redis — 将自动降级为内存消息总线（不影响使用）"
}

Write-Host ""

# ============================================================
#  第 2 步：创建 Python 虚拟环境
# ============================================================
Write-Info "创建 Python 虚拟环境..."

if (Test-Path ".venv") {
    Write-Warn "虚拟环境 .venv 已存在，跳过创建"
} else {
    & $pyCmd -m venv .venv
    Write-Ok "虚拟环境已创建: .venv\"
}

# 激活虚拟环境
$activateScript = ".\.venv\Scripts\Activate.ps1"
if (Test-Path $activateScript) {
    & $activateScript
    Write-Ok "虚拟环境已激活"
} else {
    Write-Fail "无法激活虚拟环境，未找到 $activateScript"
}

Write-Host ""

# ============================================================
#  第 3 步：安装 Python 后端依赖
# ============================================================
Write-Info "安装 Python 后端依赖（含开发依赖）..."

pip install --upgrade pip -q
pip install -e ".[dev]" -q

Write-Ok "Python 依赖安装完成"
Write-Host ""

# ============================================================
#  第 4 步：安装前端依赖
# ============================================================
Write-Info "安装前端依赖..."

if (Test-Path "frontend") {
    Push-Location frontend
    npm install --no-fund --no-audit
    Pop-Location
    Write-Ok "前端依赖安装完成"
} else {
    Write-Warn "未找到 frontend/ 目录，跳过前端安装"
}

Write-Host ""

# ============================================================
#  第 5 步：构建前端（生产模式）
# ============================================================
Write-Info "构建前端..."

if (Test-Path "frontend") {
    Push-Location frontend
    npm run build
    Pop-Location
    Write-Ok "前端构建完成: frontend/dist/"
} else {
    Write-Warn "跳过前端构建"
}

Write-Host ""

# ============================================================
#  第 6 步：配置环境变量
# ============================================================
Write-Info "配置环境变量..."

if (Test-Path "config\.env") {
    Write-Warn "config\.env 已存在，跳过（不覆盖已有配置）"
} else {
    if (Test-Path "config\.env.example") {
        Copy-Item "config\.env.example" "config\.env"
        Write-Ok "已从 .env.example 创建 config\.env"
        Write-Warn "请编辑 config\.env 填入你的 OPENAI_API_KEY"
    } else {
        Write-Warn "未找到 config\.env.example，请手动创建 config\.env 或设置环境变量"
    }
}

Write-Host ""

# ============================================================
#  第 7 步：创建工作目录
# ============================================================
Write-Info "创建工作目录..."

if (-not (Test-Path "workspace")) {
    New-Item -ItemType Directory -Path "workspace" | Out-Null
}
Write-Ok "workspace/ 目录已就绪"

Write-Host ""

# ============================================================
#  第 8 步：验证安装
# ============================================================
Write-Info "验证安装..."

try {
    & $pyCmd -c "import axonflow; print(f'axonflow {getattr(axonflow, `"__version__`", `"0.1.0`")}')"
    Write-Ok "axonflow 模块导入正常"
} catch {
    Write-Warn "axonflow 模块导入失败，请检查安装"
}

Write-Host ""

# ============================================================
#  完成
# ============================================================
Write-Host "========================================" -ForegroundColor Green
Write-Host "  安装完成!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "接下来："
Write-Host ""
Write-Host '  1. 设置 API Key:'
Write-Host '     $env:OPENAI_API_KEY = "your-api-key-here"'
Write-Host ""
Write-Host "  2. 启动后端 API (终端 1):"
Write-Host '     .\.venv\Scripts\Activate.ps1'
Write-Host '     python -m uvicorn axonflow.api.app:app --port 8000 --reload'
Write-Host ""
Write-Host "  3. 启动前端 dev server (终端 2):"
Write-Host '     cd frontend; npm run dev'
Write-Host ""
Write-Host "  4. 打开浏览器访问: http://localhost:5173"
Write-Host ""
Write-Host "  或使用 CLI 模式:"
Write-Host '     .\.venv\Scripts\Activate.ps1'
Write-Host '     axonflow status'
Write-Host '     axonflow run dev-pipeline --input "你的任务描述"'
Write-Host ""
