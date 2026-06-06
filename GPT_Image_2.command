#!/bin/bash
# ============================================================
#  GPT-Image-2 图片生成器 - macOS 启动脚本 (Web 版)
#  双击此文件即可启动，自动在浏览器中打开界面
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ---------- 加载用户环境变量 ----------
for rc in "$HOME/.zshrc" "$HOME/.zprofile" "$HOME/.bash_profile" "$HOME/.bashrc"; do
    [ -f "$rc" ] && source "$rc" 2>/dev/null
done

# 从 launchd 环境继承
export OPENAI_API_KEY="${OPENAI_API_KEY:-$(launchctl getenv OPENAI_API_KEY 2>/dev/null)}"
export AZURE_OPENAI_IMAGE_ENDPOINT="${AZURE_OPENAI_IMAGE_ENDPOINT:-$(launchctl getenv AZURE_OPENAI_IMAGE_ENDPOINT 2>/dev/null)}"

# ---------- 检查 Python3 ----------
if ! command -v python3 &>/dev/null; then
    osascript -e 'display dialog "未找到 python3，请先安装 Python3。\n可从 https://www.python.org/downloads/ 下载" buttons {"确定"} default button "确定" with icon stop'
    exit 1
fi

# ---------- 检查环境变量 ----------
if [ -z "$OPENAI_API_KEY" ]; then
    osascript -e 'display dialog "未检测到环境变量 OPENAI_API_KEY。\n\n请在终端中执行：\n  launchctl setenv OPENAI_API_KEY \"your-key-here\"\n\n然后重新启动本应用。" buttons {"确定"} default button "确定" with icon caution'
    exit 1
fi

if [ -z "$AZURE_OPENAI_IMAGE_ENDPOINT" ]; then
    osascript -e 'display dialog "未检测到环境变量 AZURE_OPENAI_IMAGE_ENDPOINT。\n\n请在终端中执行：\n  launchctl setenv AZURE_OPENAI_IMAGE_ENDPOINT \"your-endpoint\"\n\n然后重新启动本应用。" buttons {"确定"} default button "确定" with icon caution'
    exit 1
fi

# ---------- 创建保存目录 ----------
mkdir -p "/Users/jingchen/Documents/GPT_IMAGE_2"

# ---------- 启动应用 ----------
cd "$SCRIPT_DIR"
python3 "$SCRIPT_DIR/gpt_image_app.py" 2>&1

# 异常退出时暂停
EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "⚠️  应用异常退出（退出码: $EXIT_CODE）"
    read -r -p "按任意键关闭窗口..." -n 1
fi