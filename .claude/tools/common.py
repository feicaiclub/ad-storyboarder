"""公共工具：项目路径、日志、ffprobe、JSON 落盘、中文字体。所有脚本共用。"""
import datetime
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent  # .claude/tools → 项目根
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 项目里的固定位置（CLAUDE.md 的文件结构）。改结构只改这里。
DOC = "需求文档.md"
SCRIPT_DIR = "脚本"
SEG = "脚本/分段表.md"
LIB = "素材库"
GEN = "生成"
EDIT = "剪辑"
EDL = "剪辑/剪辑表.py"
FINAL = "final"
FB = "反馈/待处理.md"
FB_FRAMES = "反馈/帧"

ENV_FILE = ROOT / ".env"  # 只给以后接需要密钥的别家用；Higgsfield 的凭证归它的命令行管，不走这里


def load_env(path=ENV_FILE):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()


def need(key):
    v = os.environ.get(key)
    if not v:
        sys.exit(f"[config] 缺少 {key}：写入 {ENV_FILE}（一行 {key}=xxx）或 export 后重试")
    return v


def log(tag, msg):
    line = f"{datetime.datetime.now().strftime('%H:%M:%S')} [{tag}] {msg}"
    print(line, flush=True)
    with open(LOG_DIR / f"{tag}.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def ffprobe(path):
    """返回 {duration, width, height, fps, has_audio}；失败返回 {}。"""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
            capture_output=True, text=True, timeout=60).stdout
        d = json.loads(out or "{}")
    except Exception:
        return {}
    info = {"duration": round(float(d.get("format", {}).get("duration", 0) or 0), 3)}
    for s in d.get("streams", []):
        if s.get("codec_type") == "video":
            info.update(width=s.get("width"), height=s.get("height"), fps=s.get("r_frame_rate"))
        if s.get("codec_type") == "audio":
            info.update(has_audio=True, sample_rate=s.get("sample_rate"), channels=s.get("channels"))
    return info


def write_json(path, obj):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def abspath(p):
    p = pathlib.Path(p)
    return str(p if p.is_absolute() else ROOT / p)


# 中文字体：环境变量 FEICAI_FONT 指定的优先，否则按系统找常见的几种。找不到返回 None（调用方退回默认字体，不报错）。
FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/Hiragino Sans GB.ttc", "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc", "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc", "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def font_path():
    env = os.environ.get("FEICAI_FONT")
    if env and os.path.exists(env):
        return env
    return next((f for f in FONT_CANDIDATES if os.path.exists(f)), None)


def font(size, path=None):
    """PIL 字体；找不到中文字体时用 PIL 自带的（中文会显示成方块，但不会崩）。"""
    from PIL import ImageFont
    p = path or font_path()
    if p:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()
