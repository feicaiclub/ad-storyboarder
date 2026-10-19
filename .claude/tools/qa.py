#!/usr/bin/env python3
"""质检：抽帧拼图、局部对比表（产品、人脸）、本地听写、音高、逐秒响度、亮度。审片员和主 Agent 都用它。
  sheet  FILE [--fps N] [--cols 6] [--out x.jpg]            抽帧拼一张图（看产品、脸、手、虚影、闪烁）。默认按画面动静自动定密度：静 2、动 4、猛动和切镜 8 帧/秒，标题里写出哪几秒；--fps 改成固定帧率
  crops  SPEC.json [--out x.jpg]                           局部对比表（别名 faces、product）：把视频某一帧或某张图的一块裁出来并排。
                                                           SPEC=[{"file","t"(图片写 null),"cx","cy","r" 或 "w"+"h","label"}]，cx cy 是中心、r 是半径、w h 是宽高，都是相对画面宽的比例；
                                                           产品对比表：第一格放产品图，后面放这段里产品最清楚的几帧
  stt    FILE [--model large-v3] [--expect 台词] [--from s] [--to s]   本地 whisper 听写（有 whisper 用 whisper，没有用 mlx_whisper；忽略它在静音上幻听的字）
  pitch  FILE [--from s] [--to s]                          音高中位数和起伏（同一个人各段比，差 >25% 不收）
  levels FILE                                              逐秒响度、无声洞、爆音、响度、2～8kHz 占比、150Hz 以下占比
  bright FILE t1,t2,...                                    每个时间点的亮度均值和暗部占比"""
import argparse, glob, json, os, re, shutil, subprocess, sys, tempfile
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import measure as M
import common as C
font = C.font
MOTION_RATE, LEVELS = 8, ((90.0, 8), (30.0, 4), (-1.0, 2))   # 自动密度：先按 8 帧/秒抽，看每秒里"最动的那一块"（6x6 像素块）的灰度差：>90 猛动或切镜留 8 帧，>30 动留 4 帧，其余静留 2 帧
LABEL = {2: (255, 255, 0), 4: (255, 190, 0), 8: (255, 110, 0)}


def grab(src, t):
    p = os.path.join(tempfile.mkdtemp(), "f.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", src, "-frames:v", "1", p])
    return Image.open(p).convert("RGB")


def sheet(a):
    dur = M.frames_and_duration(a.file)[2]; tmp = tempfile.mkdtemp(); tw = 2400 // a.cols
    if a.fps:  # 固定帧率
        n = max(4, int(dur * a.fps))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.file, "-vf", f"fps={n / dur:.4f},scale={tw}:-2", os.path.join(tmp, "%04d.jpg")])
        ims = [Image.open(os.path.join(tmp, f)).convert("RGB") for f in sorted(os.listdir(tmp))]
        picks = [((i + 0.5) * dur / len(ims), im, 2) for i, im in enumerate(ims)]; note = f"固定每格 {dur / len(ims):.2f}s"
    else:  # 自动密度
        R = MOTION_RATE
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.file, "-vf", f"fps={R},scale={tw}:-2", os.path.join(tmp, "%04d.jpg")])
        ims = [Image.open(os.path.join(tmp, f)).convert("RGB") for f in sorted(os.listdir(tmp))]
        g = [np.asarray(im.convert("L").resize((96, 54)), dtype=np.float32) for im in ims]
        local = lambda p, q: float(np.abs(p - q).reshape(9, 6, 16, 6).mean(axis=(1, 3)).max())   # 最动的那一块的平均差
        score = [0.0] + [local(g[i], g[i - 1]) for i in range(1, len(g))]
        secs = (len(ims) + R - 1) // R
        rate = [next(n for thr, n in LEVELS if max(score[s * R:(s + 1) * R]) > thr) for s in range(secs)]
        step = lambda s: R // rate[s]
        picks = [((i + 0.5) / R, im, rate[i // R]) for i, im in enumerate(ims) if (i % R) % step(i // R) == step(i // R) // 2]
        def runs(n):
            out = []
            for s, r in enumerate(rate):
                if r == n and out and out[-1][1] == s: out[-1][1] = s + 1
                elif r == n: out.append([s, s + 1])
            return "、".join(f"{p}～{q}" for p, q in out)
        note = "静 2 · 动 4 · 猛动 8 帧/秒" + (f"，猛动 {runs(8)} 秒" if 8 in rate else "") + (f"，动 {runs(4)} 秒" if 4 in rate else "")
    if not picks:
        sys.exit(f"抽不出帧：{a.file}")
    w, h = ims[0].size; rows = (len(picks) + a.cols - 1) // a.cols
    sh = Image.new("RGB", (w * a.cols, h * rows + 40), (15, 15, 15)); d = ImageDraw.Draw(sh)
    d.text((8, 8), f"{os.path.basename(a.file)}  {dur:.2f}s  {len(picks)} 格  {note}", fill=(240, 200, 120), font=font(24))
    for i, (t, im, n) in enumerate(picks):
        x, y = (i % a.cols) * w, 40 + (i // a.cols) * h; sh.paste(im, (x, y))
        d.text((x + 4, y + 2), f"{t:.1f}" if n == 2 else f"{t:.2f}", fill=LABEL[n], font=font(18))   # 黄 2 帧/秒、橙 4、深橙 8
    out = a.out or a.file.rsplit(".", 1)[0] + "_sheet.jpg"; sh.save(out, quality=86); print(out)


def crops(a):
    spec = json.load(open(a.spec)); size, cols = 440, 6
    rows = (len(spec) + cols - 1) // cols; sh = Image.new("RGB", (cols * size, rows * (size + 36)), (15, 15, 15)); d = ImageDraw.Draw(sh)
    for i, it in enumerate(spec):
        im = Image.open(it["file"]).convert("RGB") if it.get("t") is None else grab(it["file"], it["t"])
        W, H = im.size; cx, cy = it.get("cx", 0.5) * W, it.get("cy", 0.4) * H
        if it.get("w") and it.get("h"):
            hw, hh = it["w"] * W / 2, it["h"] * W / 2
        else:
            hw = hh = it.get("r", 0.1) * W
        crop = im.crop((int(max(0, cx - hw)), int(max(0, cy - hh)), int(min(W, cx + hw)), int(min(H, cy + hh))))
        crop.thumbnail((size, size))   # 保持比例放进格子里，不拉伸（产品比例要能看）
        cell = Image.new("RGB", (size, size), (15, 15, 15)); cell.paste(crop, ((size - crop.width) // 2, (size - crop.height) // 2))
        x, y = (i % cols) * size, (i // cols) * (size + 36); sh.paste(cell, (x, y + 36)); d.text((x + 6, y + 4), it.get("label", ""), fill=(255, 220, 120), font=font(24))
    out = a.out or "crops.jpg"; sh.save(out, quality=90); print(out)


def _whisper(wav, model, lang, tmp):
    """返回 whisper 的 segments。先找 openai-whisper 的 whisper 命令，再找 mlx_whisper（Apple 芯片）。"""
    w = shutil.which("whisper")
    if w:
        subprocess.run([w, wav, "--model", model, "--language", lang, "--output_format", "json", "--output_dir", tmp, "--fp16", "False", "--word_timestamps", "True"], capture_output=True)
    else:
        mw = shutil.which("mlx_whisper") or next(iter(glob.glob(os.path.expanduser("~/Library/Python/*/bin/mlx_whisper"))), None)
        if not mw:
            sys.exit("没有本地 whisper：pip install -U openai-whisper（Apple 芯片可装 mlx-whisper），装完再听写")
        repo = model if "/" in model else f"mlx-community/whisper-{model}-mlx"
        subprocess.run([mw, wav, "--model", repo, "--language", lang, "--output-format", "json", "--output-dir", tmp, "--output-name", "a", "--word-timestamps", "True"], capture_output=True)
    js = os.path.join(tmp, "a.json")
    if not os.path.exists(js):
        sys.exit("听写失败：whisper 没有产出（模型没下载好或音频是空的）")
    return json.load(open(js)).get("segments", [])


def stt(a):
    tmp = tempfile.mkdtemp(); wav = os.path.join(tmp, "a.wav")
    cmd = ["ffmpeg", "-v", "error", "-y"] + (["-ss", str(a.frm)] if a.frm else []) + (["-t", str(a.to - (a.frm or 0))] if a.to else []) + ["-i", a.file, "-vn", "-ac", "1", "-ar", "16000", wav]
    subprocess.run(cmd)
    segs = [s for s in _whisper(wav, a.model, a.lang, tmp) if s["text"].strip()]
    for s in segs:
        print(f"{(a.frm or 0) + s['start']:7.2f}-{(a.frm or 0) + s['end']:7.2f}  {s['text'].strip()}")
    if a.expect:
        strip = lambda t: re.sub(r"[\s，。、！？；：,.!?;:“”\"'‘’…—\-（）()《》\[\]【】]", "", t)
        ref, hyp = strip(a.expect), strip("".join(s["text"] for s in segs))
        dp = list(range(len(hyp) + 1))
        for i in range(1, len(ref) + 1):
            prev, dp[0] = dp[0], i
            for j in range(1, len(hyp) + 1):
                cur = dp[j]; dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + (ref[i - 1] != hyp[j - 1])); prev = cur
        print(f"字错率 {dp[len(hyp)] / max(1, len(ref)):.3f}  期望：{a.expect}")


def pitch(a):
    x = M.decode(a.file, a.frm or 0, (a.to - (a.frm or 0)) if a.to else None); print(M.f0_stats(x))


def levels(a):
    x = M.decode(a.file); vals = M.per_second_db(x); holes, peaks = M.holes_and_peaks(vals)
    for k in range(0, len(vals), 10):
        print(f"{k // 60}:{k % 60:02d} " + " ".join(f"{v:6.1f}" for v in vals[k:k + 10]))
    if not len(x):
        print("没有音轨"); return
    print("无声洞:", holes, " 爆音:", peaks, " ", M.loudness(a.file), f" 2-8kHz {M.band_ratio_db(x, 2000, 8000):.1f} dB  <150Hz {M.band_ratio_db(x, 20, 150):.1f} dB")


def bright(a):
    for t in a.times.split(","):
        m, dark = M.brightness(a.file, float(t)); print(f"{float(t):7.2f}s 亮度均值 {m:5.1f} 暗部占比 {dark:4.0f}%")


ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
p = sp.add_parser("sheet"); p.add_argument("file"); p.add_argument("--fps", type=float); p.add_argument("--cols", type=int, default=6); p.add_argument("--out"); p.set_defaults(f=sheet)
for name in ("crops", "faces", "product"):
    p = sp.add_parser(name); p.add_argument("spec"); p.add_argument("--out"); p.set_defaults(f=crops)
p = sp.add_parser("stt"); p.add_argument("file"); p.add_argument("--model", default="large-v3"); p.add_argument("--lang", default="zh"); p.add_argument("--expect"); p.add_argument("--from", dest="frm", type=float); p.add_argument("--to", type=float); p.set_defaults(f=stt)
p = sp.add_parser("pitch"); p.add_argument("file"); p.add_argument("--from", dest="frm", type=float); p.add_argument("--to", type=float); p.set_defaults(f=pitch)
p = sp.add_parser("levels"); p.add_argument("file"); p.set_defaults(f=levels)
p = sp.add_parser("bright"); p.add_argument("file"); p.add_argument("times"); p.set_defaults(f=bright)
a = ap.parse_args(); a.f(a)
