#!/usr/bin/env python3
"""总装（默认做法，参数可改；"按整帧截、声音按实际帧数摆"这一条是门禁的前提，别动）。
python3 .claude/tools/assemble.py --edl 剪辑/剪辑表.py --out final/片名_主版.mp4 [--draft] [--frame 16:9|none] [--size 1920x1080] [--target -14]
剪辑表的写法见同目录的 剪辑表示例.py。画幅、响度目标都写在剪辑表顶上（SIZE、FRAME、TARGET_I，按需求文档定）：SIZE 不写就跟第一条视频素材走，FRAME 不写就不留黑边，TARGET_I 必填；
命令行参数能临时覆盖画幅和响度（多个交付规格用同一份剪辑表出各版时就这么用）。24fps。
视频素材的入点送给 ffmpeg 前对齐到"离它最近的整帧前 1/4 帧"（seek_in），滤镜链里再把第一帧时间归零：直接拿入点 -ss 再 fps=24，入点刚过一帧时首帧会重复一次。剪辑表里对齐过的入点再算一遍不变，帧数仍按剪辑表的入点、出点算。
画面处理链 LOOK：none（默认，不加处理）/ hero（广告：轻去噪、柔和压高光、细颗粒；不柔化、不动饱和度，产品颜色和纹理不变）/ doc（纪实花絮：更轻的去噪、更重的颗粒，同样不动颜色）/ film（胶片感：柔化、降饱和、暗角）/ clean / none / 自定义滤镜串；颗粒强度 GRAIN 可在剪辑表里改。
片尾品牌卡：v("CARD:logo 图路径|slogan|小字", 0, 2.5)，程序渲染，字体用 common.font_path() 找到的中文字体（FEICAI_FONT 可指定）。
声音：片段原声走对白链（去齿音，不提高频）；额外音轨按类型归一（music -20 / amb -40 / sfx -22 / voice -18 LUFS，最多提 10 dB）并走柔化链；
对白时段自动压配乐（DUCK_DB）；env 包络、hits 多次落点；rev=(room|courtyard|hall, 湿声 dB) 给原声或音轨加一点空间感（台词太干时用）；母带 alimiter + 两遍 loudnorm 到 TARGET_I。
剪辑表引用的文件缺一个就停，音轨解不出声音也停，不悄悄当成无声。每条画面查源片里的切镜点（场景检测，算一次存缓存）：入点、出点落在切镜点前后 2 帧以内会闪进别的镜头，标 ⚠ 并写进 sync.json。
写 剪辑/sync_<成片名>.json（同时覆盖一份 剪辑/sync.json：名义时长 vs 实际帧数、响度目标、画幅、切点警告）和 剪辑/audio_report.txt（每条音轨的落点和增益），给门禁和自审看。
"""
import argparse
import hashlib
import json
import importlib.util
import math
import os
import re
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

W, H, FPS, SR = 1920, 1080, 24, 48000
OUT_W, OUT_H = 1920, 1080  # --size / --frame 会改
CACHE = C.ROOT / C.EDIT / "cache"
CACHE.mkdir(parents=True, exist_ok=True)
SYNTH = ("BLACK", "WHITE", "TITLE:", "CARD:")  # 程序生成的画面，不是素材文件
CARD_BG, CARD_FG = (0, 0, 0), (236, 233, 226)  # 剪辑表里可改
GRADES = {
    "none": "",
    "night": "eq=contrast=1.04:saturation=0.86:gamma=0.98,colorbalance=bs=0.03:bm=0.02:rh=-0.01",
    # 夜戏提亮：抬中间调和暗部，脸看得清，仍保留夜的蓝
    "night2": "eq=contrast=1.02:saturation=0.86:gamma=1.14:brightness=0.025,curves=all='0/0 0.06/0.09 0.5/0.54 1/1',colorbalance=bs=0.035:bm=0.02:rh=-0.01",
    "day": "eq=contrast=1.02:saturation=0.88,colorbalance=rm=0.01:bm=-0.01",
    "warm": "eq=contrast=1.03:saturation=0.9,colorbalance=rs=0.03:rm=0.03:bs=-0.03:bm=-0.02",
    "warm2": "eq=contrast=1.02:saturation=0.9:gamma=1.06,colorbalance=rs=0.03:rm=0.03:bs=-0.03:bm=-0.02",
    "cool": "eq=contrast=1.05:saturation=0.8:gamma=0.97,colorbalance=bs=0.05:bm=0.03",
    "cool2": "eq=contrast=1.03:saturation=0.8:gamma=1.12:brightness=0.02,curves=all='0/0 0.06/0.085 0.5/0.53 1/1',colorbalance=bs=0.05:bm=0.03",
    "call": "eq=contrast=0.98:saturation=0.94:brightness=0.01",
}
GRAIN = "noise=alls=6:allf=t"
# 生成段的整片处理链：剪辑表里写 LOOK = "none"（默认，不加）| "hero" | "doc" | "film" | "clean"，单段用 matte=False 关掉
LOOKS = {
    "hero": "hqdn3d=2:1.5:3:2.5,curves=all='0/0 0.5/0.5 0.8/0.78 1/0.93'",  # 广告：轻去噪（压 AI 的细碎闪动）、柔和压高光；不柔化、不动饱和度
    "doc": "hqdn3d=1.5:1:2:2,curves=all='0/0.015 0.5/0.5 0.85/0.8 1/0.9'",  # 纪实花絮：去噪更轻、高光压得更多、黑位微抬，颗粒更重；同样不柔化、不动饱和度（产品颜色和面料纹理不能变）
    "film": "hqdn3d=4:3:6:4,gblur=sigma=1.3,unsharp=7:7:0.3:5:5:0,curves=all='0/0.02 0.45/0.47 0.7/0.64 0.85/0.74 1/0.82',eq=saturation=0.84,vignette=PI/4.6",  # 去噪、柔化、压高光、抬黑位、降饱和、暗角：电影胶片感（会动产品的颜色和纹理，产品段 matte=False）
    "clean": "hqdn3d=3:2:5:3,gblur=sigma=1.0,unsharp=5:5:0.25:5:5:0,curves=all='0/0.01 0.5/0.5 0.85/0.8 1/0.9'",  # 只防 AI 味：去噪、柔化、压高光，不动颜色
    "none": "",
}
MATTE = LOOKS["none"]
GRAIN_BY_LOOK = {"hero": 5, "doc": 8, "film": 9, "clean": 6, "none": 0}
GRAIN_LIVE = "noise=alls=5:allf=t"
CLARITY = ("highpass=f=70,equalizer=f=250:t=q:w=1.2:g=-2,deesser=i=0.35:m=0.5:f=0.5,equalizer=f=2600:t=q:w=1.4:g=1.2,"
           "acompressor=threshold=-24dB:ratio=2:attack=15:release=250,highshelf=f=9000:g=-2.5")
SOFT_SFX = "lowpass=f=7000,equalizer=f=3500:t=q:w=1.5:g=-3"
SOFT_BED = "lowpass=f=3800,equalizer=f=2800:t=q:w=1.5:g=-4,highpass=f=60"
SOFT_MUSIC = "highshelf=f=6000:g=-3,lowpass=f=12000"
PHONE = "highpass=f=320,lowpass=f=3000,aresample=8000,aresample=48000,acompressor=threshold=-22dB:ratio=3:attack=5:release=120,volume=1.6"
NORM_DEFAULT = {"music": -20.0, "amb": -40.0, "sfx": -22.0, "voice": -18.0}
MAX_BOOST = 10.0


def load_edl(path):
    spec = importlib.util.spec_from_file_location("edl", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _fit(d, text, size, maxw, tracking=0.0):
    """字号放不下就缩小，直到整行宽度不超过 maxw（竖屏画面窄，长字会顶到边上）。返回 (字体, 字号)。"""
    while True:
        f = C.font(size)
        w = sum(d.textlength(ch, font=f) for ch in text) + size * tracking * max(0, len(text) - 1)
        if w <= maxw or size <= 12:
            return f, size
        size = max(12, int(size * maxw / w * 0.98))


def title_png(text, path, size=78, sub=None, tracking=0.42):
    size = int(size * min(W, H) / 1080)
    im = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(im)
    f, size = _fit(d, text, size, W * 0.86, tracking)
    gap = size * tracking
    widths = [d.textlength(ch, font=f) for ch in text]
    tw = sum(widths) + gap * (len(text) - 1)
    x = (W - tw) / 2
    for ch, w in zip(text, widths):
        d.text((x, H / 2 - size * 0.62), ch, font=f, fill=(232, 228, 220))
        x += w + gap
    if sub:
        f2, _ = _fit(d, sub, int(size * 0.3), W * 0.86)
        sw = d.textlength(sub, font=f2)
        d.text(((W - sw) / 2, H / 2 + size * 0.6), sub, font=f2, fill=(150, 146, 140))
    im.save(path)


def card_png(spec, path):
    """片尾品牌卡：logo 居中偏上（横屏最宽 36% 画面、最高 30%；竖屏最宽 62%），slogan 在下面，小字再下面。spec = "logo 路径|slogan|小字"，后两项可省；logo 可以写 none。"""
    parts = (spec.split("|") + ["", ""])[:3]
    logo, slogan, small = parts[0].strip(), parts[1].strip(), parts[2].strip()
    im = Image.new("RGB", (W, H), CARD_BG)
    d = ImageDraw.Draw(im)
    y = H * 0.5
    if logo and logo.lower() != "none":
        p = C.abspath(logo)
        if not os.path.exists(p):
            raise FileNotFoundError(f"品牌卡的 logo 不存在：{logo}")
        lg = Image.open(p).convert("RGBA")
        lg.thumbnail((int(W * (0.36 if W >= H else 0.62)), int(H * (0.30 if W >= H else 0.18))), Image.LANCZOS)  # 竖屏画面窄，logo 占宽度的比例放大
        y0 = int(H * 0.5 - lg.height * (0.75 if slogan else 0.5))
        im.paste(lg, ((W - lg.width) // 2, y0), lg)
        y = y0 + lg.height + H * 0.06
    if slogan:
        f, _ = _fit(d, slogan, int(min(W, H) * 0.06), W * 0.86)
        sw = d.textlength(slogan, font=f)
        d.text(((W - sw) / 2, y), slogan, font=f, fill=CARD_FG)
        y += H * 0.07
    if small:
        f2, _ = _fit(d, small, int(min(W, H) * 0.028), W * 0.86)
        sw = d.textlength(small, font=f2)
        d.text(((W - sw) / 2, y), small, font=f2, fill=tuple(int(c * 0.6) for c in CARD_FG))
    im.save(path)


def seek_in(it):
    """视频素材送给 -ss 的入点：离入点最近的整帧 k 之前 1/4 帧，即 (k-0.25)/24；入点不到半帧（k=0）就从头截，不跳第 0 帧。
    直接用入点时，入点刚过一帧（0.30 秒在第 7 帧 0.2917 之后），seek 后第一帧离 0 超过半帧，fps 拿它补第 0 帧、第 1 帧又是它：
    首帧重复一次，两帧的闪切只剩一张静帧（2026-10-17 量到 24 处）。对齐后第一帧就是第 k 帧；已经是 (k-0.25)/24 的入点再算一遍不变。
    帧数仍按剪辑表的入点、出点算；声音仍从剪辑表的入点取，和画面差不到半帧。"""
    k = round(it["in"] * FPS)
    return (k - 0.25) / FPS if k >= 1 else 0.0


def item_key(it, draft):
    s = json.dumps({k: v for k, v in it.items() if k != "id"}, sort_keys=True, ensure_ascii=False, default=str) + ("d" if draft else "f")
    src = it["src"]
    dep = src[5:].split("|")[0].strip() if src.startswith("CARD:") else (None if src.startswith(SYNTH) else src)
    if dep:
        p = C.abspath(dep)
        if os.path.exists(p):
            s += str(os.path.getmtime(p))
    s += f"{W}x{H}"
    if not src.startswith(SYNTH) and not src.lower().endswith((".png", ".jpg")) and abs(seek_in(it) - it["in"]) > 1e-6:
        s += f"ss{seek_in(it):.6f}"  # 入点被对齐的条目换缓存键（旧缓存可能是首帧重复的版本）；本来就对齐的不变，缓存照用
    return hashlib.md5(s.encode()).hexdigest()[:12]


def render_item(i, it, draft):
    out = CACHE / f"v_{item_key(it, draft)}.mp4"
    dur = it["out"] - it["in"] + it.get("freeze", 0)
    nf = max(1, int(round(dur * FPS)))
    dur = nf / FPS
    if out.exists() and C.ffprobe(out).get("duration", 0) > 0:
        return out, dur
    src = it["src"]
    vf = []
    if src in ("BLACK", "WHITE"):
        color = "black" if src == "BLACK" else "white"
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={color}:s={W}x{H}:r={FPS}:d={dur + 0.5:.3f}"]
    elif src.startswith("TITLE:"):
        png = CACHE / f"title_{item_key(it, draft)}.png"
        txt = src[6:].split("|")
        title_png(txt[0], png, sub=txt[1] if len(txt) > 1 else None)
        cmd = ["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", str(FPS), "-t", f"{dur + 0.5:.3f}", "-i", str(png)]
    elif src.startswith("CARD:"):
        png = CACHE / f"card_{item_key(it, draft)}.png"
        card_png(src[5:], png)
        cmd = ["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", str(FPS), "-t", f"{dur + 0.5:.3f}", "-i", str(png)]
    elif src.lower().endswith((".png", ".jpg")):
        z = it.get("zoom", 0.05)
        frames = int(round(dur * FPS))
        cmd = ["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", str(FPS), "-t", f"{dur + 0.5:.3f}", "-i", C.abspath(src)]
        vf.append(f"scale={W * 2}:-2,zoompan=z='1+{z}*on/{max(frames, 1)}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS}")
    else:
        ss = seek_in(it)
        cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{ss:.3f}", "-t", f"{it['out'] - ss + 0.3:.3f}", "-i", C.abspath(src)]
    # 实拍段（模型生成的视频）走哑光处理链；程序渲染的图文（路径含"图文"或 gfx）和静态图不走。剪辑表里也可以写 live=True/False 指定
    live = it.get("live", src.lower().endswith((".mp4", ".mov")) and "图文" not in src and "gfx" not in src.lower())
    if not src.startswith(SYNTH) and not src.lower().endswith((".png", ".jpg")):
        if it.get("delogo"):
            info = C.ffprobe(C.abspath(src))
            sw, sh = int(info.get("width")), int(info.get("height"))
            for bx, by, bw, bh in it["delogo"]:
                vf.append(f"delogo=x={int(bx * sw)}:y={int(by * sh)}:w={int(bw * sw)}:h={int(bh * sh)}")
        if it.get("crop"):
            cx, cy, cw = it["crop"]
            vf.append(f"crop=iw*{cw}:iw*{cw}*{H}/{W}:iw*{cx}:ih*{cy}")
        # setpts 把第一帧归零，fps 就不会拿它补第 0 帧（源片不是 24fps 或有起始偏移时 seek_in 的对齐不够，这一步兜底）；
        # 先盖满画面再居中裁：比例不一样的素材（480p 草稿、横转竖）也不会报错
        vf.append(f"setpts=PTS-STARTPTS,fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H}")
        if it.get("freeze"):
            vf.append(f"tpad=stop_mode=clone:stop_duration={it['freeze']:.3f}")
    if live and it.get("matte", True) and MATTE:
        vf.append(MATTE)
    if it.get("fx"):
        vf.append(it["fx"])
    g = GRADES.get(it.get("grade", "none"), "")
    if g:
        vf.append(g)
    if not src.startswith(SYNTH) and it.get("grain", True) and (GRAIN_LIVE or not live):
        vf.append(GRAIN_LIVE if live else GRAIN)
    if it.get("fi"):
        vf.append(f"fade=t=in:st=0:d={it['fi']}:color={it.get('fcolor', 'black')}")
    if it.get("fo"):
        vf.append(f"fade=t=out:st={dur - it['fo']:.3f}:d={it['fo']}:color={it.get('fcolor', 'black')}")
    vf.append(f"scale={W}:{H},setsar=1,format=yuv420p")
    cmd += ["-vf", ",".join(vf), "-an", "-r", str(FPS), "-vsync", "cfr", "-c:v", "libx264", "-preset", "veryfast" if draft else "slow",
            "-crf", "20" if draft else "14", "-frames:v", str(nf), str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"第 {i} 条 {it.get('id', src)} 渲染失败：{r.stderr[-600:]}")
    return out, dur


# ---------------- 声音
_LOUD = {}
LOUD_DB = CACHE / "loudness.json"
if LOUD_DB.exists():
    _LOUD = json.loads(LOUD_DB.read_text())


def measure(path):
    """整合响度 LUFS 和真峰值 dBFS（缓存）。"""
    key = f"{path}:{os.path.getmtime(path)}"
    if key in _LOUD:
        return _LOUD[key]
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    i = re.findall(r"I:\s+(-?[\d.]+) LUFS", r)
    p = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", r)
    lufs = float(i[-1]) if i else None
    peak = float(p[-1]) if p else None
    if lufs is not None and lufs < -70:
        lufs = None
    _LOUD[key] = {"lufs": lufs, "peak": peak}
    LOUD_DB.write_text(json.dumps(_LOUD))
    return _LOUD[key]


def norm_gain(path, target):
    """把文件归一到目标响度要加的 dB：有整合响度用响度，太短或测不到用峰值（峰值对 -6 dBFS 再按目标偏移）。"""
    m = measure(path)
    dur = C.ffprobe(path).get("duration", 0)
    if m["lufs"] is not None and dur >= 0.8:
        return target - m["lufs"]
    if m["peak"] is not None:
        return (target + 12) - m["peak"]  # 短音效：峰值放到 目标+12 dBFS 左右
    return 0.0


def decode_audio(path, start=0.0, dur=None, af=None):
    if not os.path.exists(C.abspath(path)):
        raise FileNotFoundError(f"剪辑表引用的文件不存在：{path}")
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}"]
    if dur:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-i", C.abspath(path), "-vn"]
    if af:
        cmd += ["-af", af]
    cmd += ["-ac", "2", "-ar", str(SR), "-f", "f32le", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).copy()


_IR = {}


def impulse(kind):
    """合成的空间脉冲响应（默认做法，可改）：room 小屋 0.35 秒、courtyard 石头院子 0.75 秒、hall 大殿 1.4 秒。
    指数衰减噪声 + 几个早期反射，切掉 160Hz 以下和 8kHz 以上，能量归一。固定随机种子，每次一样。"""
    if kind in _IR:
        return _IR[kind]
    rt60 = {"room": 0.35, "courtyard": 0.75, "hall": 1.4}[kind]
    early = {"room": [(0.007, 0.5), (0.013, 0.35), (0.021, 0.25)],
             "courtyard": [(0.018, 0.45), (0.034, 0.3), (0.052, 0.22), (0.079, 0.15)],
             "hall": [(0.025, 0.4), (0.047, 0.3), (0.071, 0.2), (0.11, 0.12)]}[kind]
    rng = np.random.default_rng({"room": 7, "courtyard": 11, "hall": 13}[kind])
    n = int(rt60 * 1.2 * SR); tt = np.arange(n) / SR
    ir = rng.standard_normal((n, 2)) * np.exp(-6.91 * tt / rt60)[:, None]
    for d, g in early:
        ir[int(d * SR)] += g
    k = 5
    for _ in range(2):  # 低通：两次 5 点滑动平均
        ir = np.vstack([np.convolve(ir[:, c], np.ones(k) / k, mode="same") for c in range(2)]).T
    lo = 300  # 高通：减去约 160Hz 的慢变化
    ir = ir - np.vstack([np.convolve(ir[:, c], np.ones(lo) / lo, mode="same") for c in range(2)]).T
    ir[: int(0.003 * SR)] = 0
    ir /= np.sqrt((ir ** 2).sum()) + 1e-12
    _IR[kind] = ir.astype(np.float32)
    return _IR[kind]


def reverb(x, kind, wet_db, tail=0.0):
    """给一段声音加空间感：湿声能量 = 干声能量 × 10^(wet_db/20)，与干声相加；tail>0 时保留这么多秒尾巴（用于单独铺的音轨）。"""
    if not len(x):
        return x
    ir = impulse(kind)
    n = len(x) + len(ir) - 1
    N = 1 << (n - 1).bit_length()
    y = np.fft.irfft(np.fft.rfft(x, N, axis=0) * np.fft.rfft(ir, N, axis=0), N, axis=0)
    keep = len(x) + int(tail * SR)
    y = y[:keep]
    g = (np.sqrt((x ** 2).mean()) / (np.sqrt((y[:len(x)] ** 2).mean()) + 1e-9)) * 10 ** (wet_db / 20)
    out = np.zeros((keep, 2), dtype=np.float32)
    out[:len(x)] += x
    out += (y * g).astype(np.float32)
    return out


def fade(x, fi, fo):
    n = len(x)
    if fi:
        k = min(n, int(fi * SR))
        x[:k] *= np.linspace(0, 1, k)[:, None]
    if fo:
        k = min(n, int(fo * SR))
        x[n - k:] *= np.linspace(1, 0, k)[:, None]
    return x


def kind_of(src):
    """没写 kind 时按 harness 约定的文件夹猜：剪辑/配乐 → music，剪辑/声音床 或环境 → amb，旁白、配音 → voice，其余 sfx。"""
    s = src.lower()
    if "/music" in s or "配乐" in s:
        return "music"
    if "ambience" in s or s.endswith("_loop.mp3") or "/amb_" in s or "声音床" in s or "环境" in s:
        return "amb"
    if "/voice" in s or "/声音/" in s or "旁白" in s or "配音" in s:
        return "voice"
    return "sfx"


CUTS_DB = CACHE / "cuts.json"


def cuts_of(src):
    """源片里的切镜点（秒）：场景检测算一次，按文件和修改时间存缓存。"""
    p = C.abspath(src); key = f"{p}:{os.path.getmtime(p)}"
    db = json.loads(CUTS_DB.read_text()) if CUTS_DB.exists() else {}
    if key not in db:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", p, "-vf", "scale=320:-2,select='gt(scene,0.2)',showinfo", "-f", "null", "-"], capture_output=True, text=True).stderr
        db[key] = [round(float(x), 3) for x in re.findall(r"pts_time:\s*([\d.]+)", r)]
        CUTS_DB.write_text(json.dumps(db))
    return db[key]


def cut_check(items):
    """入点、出点落在源片切镜点前后 2 帧以内就会闪进别的镜头：打 ⚠，返回清单写进 sync.json 给门禁。"""
    warn = []
    for i, it in enumerate(items):
        src = it["src"]
        if not src.lower().endswith((".mp4", ".mov", ".mkv", ".webm")):
            continue
        for c in cuts_of(src):
            d_in, d_out = (c - it["in"]) * FPS, (it["out"] - c) * FPS
            if 0 < d_in <= 2.01:
                warn.append(f"第 {i} 条 {it.get('id', src)}：入点 {it['in']:.3f} 在片内切点 {c:.3f} 之前 {d_in:.1f} 帧，开头会闪上一镜")
            if 0 < d_out <= 2.01:
                warn.append(f"第 {i} 条 {it.get('id', src)}：出点 {it['out']:.3f} 在片内切点 {c:.3f} 之后 {d_out:.1f} 帧，结尾会闪下一镜")
    for w in warn:
        print("⚠ " + w)
    return warn


def duck_envelope(total, spans, depth_db=-7.0, attack=0.12, release=0.45, pre=0.08, post=0.2):
    n = int(total * SR) + SR
    env = np.ones(n, dtype=np.float32)
    g = 10 ** (depth_db / 20)
    for s0, s1 in spans:
        a0 = max(0, int((s0 - pre - attack) * SR)); a1 = max(0, int((s0 - pre) * SR))
        r0 = int((s1 + post) * SR); r1 = int((s1 + post + release) * SR)
        if a1 > a0:
            env[a0:a1] = np.minimum(env[a0:a1], np.linspace(1, g, a1 - a0))
        env[a1:min(r0, n)] = np.minimum(env[a1:min(r0, n)], g)
        if r1 > r0 and r0 < n:
            r1 = min(r1, n)
            env[r0:r1] = np.minimum(env[r0:r1], np.linspace(g, 1, r1 - r0))
    return env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--edl", default=C.EDL)
    ap.add_argument("--out", default="final/成片.mp4")
    ap.add_argument("--target", type=float, help="成片响度目标，覆盖剪辑表的 TARGET_I（多规格时用）")
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--frame", help="16:9 放进 16:9 画框上下留黑，或 none 原画幅；不给就读剪辑表的 FRAME，再没有就 none")
    ap.add_argument("--size", help="画面尺寸如 1920x1080 或 1080x1920；不给就读剪辑表的 SIZE，再没有就跟第一条视频素材走")
    a = ap.parse_args()
    E = load_edl(C.abspath(a.edl))
    TI = a.target if a.target is not None else getattr(E, "TARGET_I", None)
    if TI is None:
        sys.exit("剪辑表顶上没有 TARGET_I（成片响度目标）：按需求文档的平台定，例如抖音、YouTube、B 站 -14；或命令行给 --target")
    size = a.size or getattr(E, "SIZE", None)
    if not size:
        first = next((it["src"] for it in E.V if it["src"].lower().endswith((".mp4", ".mov", ".mkv", ".webm"))), None)
        if not first:
            sys.exit("剪辑表顶上没有 SIZE（画面尺寸），也没有视频素材可跟：填 SIZE，如 \"1920x1080\"")
        info = C.ffprobe(C.abspath(first)); size = f"{info.get('width')}x{info.get('height')}"
    frame = a.frame or getattr(E, "FRAME", None) or "none"
    global W, H, OUT_W, OUT_H
    W, H = [int(v) for v in size.split("x")]
    OUT_W, OUT_H = (W, W * 9 // 16) if frame == "16:9" else (W, H)
    global MATTE, GRAIN_LIVE, CARD_BG, CARD_FG
    look = getattr(E, "LOOK", "none")
    MATTE = LOOKS.get(look, look)  # 不在预设里的就当成自定义滤镜串
    g = getattr(E, "GRAIN", GRAIN_BY_LOOK.get(look, 6))
    GRAIN_LIVE = f"noise=alls={g}:allf=t" if g else ""
    CARD_BG, CARD_FG = tuple(getattr(E, "CARD_BG", CARD_BG)), tuple(getattr(E, "CARD_FG", CARD_FG))
    starts, parts, t = [], [], 0.0
    for i, it in enumerate(E.V):
        p, d = render_item(i, it, a.draft)
        starts.append(t)
        parts.append((p, d))
        t += d
    total = t
    cut_warn = cut_check(E.V)
    sync = {"out": a.out, "nominal": round(sum(it["out"] - it["in"] + it.get("freeze", 0) for it in E.V), 3), "actual": round(total, 3), "items": len(E.V),
            "target_i": TI, "size": size, "frame": frame, "look": look, "cut_warnings": cut_warn}
    C.write_json(C.ROOT / C.EDIT / "sync.json", sync)
    C.write_json(C.ROOT / C.EDIT / f"sync_{os.path.splitext(os.path.basename(a.out))[0]}.json", sync)
    lst = CACHE / "concat.txt"
    lst.write_text("".join(f"file '{p}'\n" for p, _ in parts))
    pic = CACHE / "picture.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(pic)], check=True)

    def at_of(x):
        if isinstance(x, tuple):
            return starts[x[1]] + x[2]
        return float(x)
    # 对白时段
    spans = []
    for s in getattr(E, "SUBS", []):
        if s[0] == "V":
            spans.append((starts[s[1]] + s[2], starts[s[1]] + s[3], s[4]))
        else:
            spans.append(s)
    duck_spans = [(s0, s1) for s0, s1, _ in spans]
    for s in getattr(E, "DUCK_EXTRA", []):
        duck_spans.append((starts[s[1]] + s[2], starts[s[1]] + s[3]) if s[0] == "V" else (s[0], s[1]))
    env = duck_envelope(total, duck_spans, depth_db=getattr(E, "DUCK_DB", -7.0))
    mix = np.zeros((int(total * SR) + SR, 2), dtype=np.float32)
    # 片段原声
    for i, it in enumerate(E.V):
        g = it.get("a", 1.0)
        if not g or it["src"].startswith(SYNTH) or it["src"].lower().endswith((".png", ".jpg")):
            continue
        x = decode_audio(it["src"], it["in"], it["out"] - it["in"], af=CLARITY if it.get("clarity", True) else None)
        if not len(x):
            continue
        if it.get("rev"):  # rev=(空间, 湿声 dB)：给这一条的原声加空间感（台词太干、像录音棚时用）
            x = reverb(x, *it["rev"])[:len(x)]
        x = fade(x * g, it.get("afi", 0.04), it.get("afo", 0.06))
        s0 = int(starts[i] * SR)
        mix[s0:s0 + len(x)] += x[:len(mix) - s0]
    # 额外音轨
    report = []
    for ev in getattr(E, "A", []):
        t0 = at_of(ev["at"])
        dur = ev.get("dur")
        kind = ev.get("kind") or kind_of(ev["src"])
        af = []
        if ev.get("clarity"):
            af.append(CLARITY)
        if ev.get("fx") == "phone":
            af.append(PHONE)
        elif not ev.get("raw"):
            af.append({"music": SOFT_MUSIC, "amb": SOFT_BED, "sfx": SOFT_SFX}.get(kind, ""))
        af = [x for x in af if x]
        x = decode_audio(ev["src"], ev.get("in", 0.0), None if ev.get("loop") else dur, af=",".join(af) if af else None)
        if not len(x):
            raise RuntimeError(f"音轨解不出声音：{ev['src']}（{kind}，落点 {t0:.2f}s）")
        if ev.get("loop") and dur:
            reps = int(math.ceil(dur * SR / max(len(x), 1)))
            # 循环接缝做 0.3 秒交叉淡化
            xf = int(0.3 * SR)
            seg = x.copy()
            pieces = [seg]
            for _ in range(reps - 1):
                nxt = x.copy()
                if xf < len(nxt) and xf < len(pieces[-1]):
                    pieces[-1][-xf:] = pieces[-1][-xf:] * np.linspace(1, 0, xf)[:, None] + nxt[:xf] * np.linspace(0, 1, xf)[:, None]
                    pieces.append(nxt[xf:])
                else:
                    pieces.append(nxt)
            x = np.concatenate(pieces)[:int(dur * SR)]
        elif dur:
            x = x[:int(dur * SR)]
        if ev.get("rev"):  # 单独铺的音轨也能加空间感，保留 0.5 秒尾巴
            x = reverb(x, *ev["rev"], tail=0.5)
        norm = ev.get("norm", NORM_DEFAULT.get(kind))
        g_db = ev.get("gain", 0) + (min(MAX_BOOST, norm_gain(C.abspath(ev["src"]), norm)) if norm is not None else 0)
        x = fade(x * (10 ** (g_db / 20)), ev.get("fi", 0.02), ev.get("fo", 0.05))
        if ev.get("env"):
            pts = ev["env"]
            tt = np.arange(len(x)) / SR
            g_env = np.interp(tt, [q[0] for q in pts], [q[1] for q in pts])
            x = x * (10 ** (g_env / 20))[:, None]
        hits = ev.get("hits") or [(0.0, 0.0)]
        for off, hg in hits:
            s0 = int((t0 + off) * SR)
            if s0 >= len(mix) or s0 < 0:
                continue
            y = x * (10 ** (hg / 20))
            seg_len = min(len(y), len(mix) - s0)
            y = y[:seg_len]
            if ev.get("duck"):
                y = y * env[s0:s0 + seg_len][:, None]
            mix[s0:s0 + seg_len] += y
        report.append(f"{t0:7.2f}s {kind:5} {os.path.basename(ev['src']):<28} gain {g_db:+5.1f} dB dur {dur or round(len(x) / SR, 2)} {'duck' if ev.get('duck') else ''} {ev.get('fx', '')}")
    peak = float(np.max(np.abs(mix)) or 1)
    if peak > 0.98:
        mix *= 0.98 / peak
    raw = CACHE / "mix_raw.wav"
    wav = CACHE / "mix.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-", "-c:a", "pcm_f32le", str(raw)], input=mix.tobytes(), check=True)
    pre = "alimiter=limit=0.9:attack=5:release=60:level=false"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(raw), "-af", f"{pre},loudnorm=I={TI}:TP=-2:LRA=12:print_format=json", "-f", "null", "-"], capture_output=True, text=True)
    js = json.loads(r.stderr[r.stderr.rindex("{"):r.stderr.rindex("}") + 1])
    ln = (f"{pre},loudnorm=I={TI}:TP=-2:LRA=12:measured_I={js['input_i']}:measured_TP={js['input_tp']}:measured_LRA={js['input_lra']}"
          f":measured_thresh={js['input_thresh']}:offset={js['target_offset']}:linear=true")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af", ln, "-ar", str(SR), str(wav)], check=True)
    (C.ROOT / C.EDIT / "audio_report.txt").write_text("\n".join(report), encoding="utf-8")
    # 字幕只存到缓存（不烧进片子）
    def ts(x, sep=","):
        h, m = int(x // 3600), int(x % 3600 // 60)
        return f"{h:02d}:{m:02d}:{x % 60:06.3f}".replace(".", sep)
    with open(CACHE / "subs.srt", "w", encoding="utf-8") as f:
        for k, (s0, s1, txt) in enumerate(spans, 1):
            f.write(f"{k}\n{ts(s0)} --> {ts(s1)}\n{txt}\n\n")
    out = C.abspath(a.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    enc = ["-c:v", "libx264", "-preset", "veryfast" if a.draft else "slow", "-crf", "20" if a.draft else "18",
           "-maxrate", "24M", "-bufsize", "48M", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", "-shortest", "-movflags", "+faststart"]
    vf = ["-vf", f"pad={OUT_W}:{OUT_H}:0:({OUT_H}-ih)/2:black"] if (OUT_W, OUT_H) != (W, H) else []
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(pic), "-i", str(wav)] + vf + enc + [out], check=True)
    C.log("assemble", f"成片 {out} 时长 {total:.1f}s（{size} {frame} LOOK={look}，无字幕，帧精确）")
    print(f"总时长 {total:.2f}s；音轨落点见 剪辑/audio_report.txt，同步见 剪辑/sync_{os.path.splitext(os.path.basename(a.out))[0]}.json")


if __name__ == "__main__":
    main()
