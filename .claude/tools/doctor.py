#!/usr/bin/env python3
"""本机自检（尺子）：开工前一次查完，缺什么、怎么装说清楚。只查不装。
python3 .claude/tools/doctor.py [--no-hf]
必需：ffmpeg、ffprobe、Python 3.9+、numpy、Pillow、Higgsfield 命令行已登录且选了工作区（--no-hf 跳过这一项）。
可选：中文字体（片名卡、拼图的字）、本地 whisper（有台词或旁白时听写用）。"""
import argparse
import importlib
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--no-hf", action="store_true", help="不查 Higgsfield（只查本机工具）")
a = ap.parse_args()
bad = []


def ok(msg):
    print("✓ " + msg)


def fail(msg, fix):
    print(f"✗ {msg}：{fix}")
    bad.append(msg)


def opt(msg):
    print("· " + msg)


for b in ("ffmpeg", "ffprobe"):
    p = shutil.which(b)
    if p:
        v = subprocess.run([b, "-version"], capture_output=True, text=True).stdout.split("\n")[0]
        ok(f"{b}：{' '.join(v.split()[:3])}")
    else:
        fail(f"没有 {b}", "macOS 用 brew install ffmpeg；Linux 用 apt install ffmpeg；Windows 从 ffmpeg.org 下载并加进 PATH")
if sys.version_info >= (3, 9):
    ok(f"Python {sys.version.split()[0]}")
else:
    fail(f"Python {sys.version.split()[0]} 太旧", "装 Python 3.9 以上")
for mod, pip in (("numpy", "numpy"), ("PIL", "Pillow")):
    try:
        m = importlib.import_module(mod)
        ok(f"{pip} {getattr(m, '__version__', '')}")
    except ImportError:
        fail(f"没有 {pip}", f"python3 -m pip install --user {pip}")
f = C.font_path()
if f:
    ok(f"中文字体：{f}")
else:
    opt("没找到中文字体：片名卡、拼图上的中文会变方块。装一个（如 Noto Sans CJK），或设环境变量 FEICAI_FONT=字体路径")
w = shutil.which("whisper") or shutil.which("mlx_whisper")
if w:
    ok(f"本地听写：{w}")
else:
    opt("没有本地 whisper：有台词或旁白的片子要听写，pip install -U openai-whisper（Apple 芯片可装 mlx-whisper）；没有台词可以不装")
if not a.no_hf:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "adapters"))
    import higgsfield as HF  # noqa: E402
    if not HF.check():
        bad.append("Higgsfield")
        print("  装好、登录、选工作区这三步请用户自己做：npm i -g @higgsfield/cli → higgsfield auth login（浏览器里点授权）→ higgsfield workspace list → higgsfield workspace set <id>")
print("自检通过" if not bad else f"自检没过：{len(bad)} 项要处理")
sys.exit(0 if not bad else 1)
