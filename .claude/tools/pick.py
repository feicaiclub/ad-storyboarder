#!/usr/bin/env python3
"""候选的指标表（只报数，不替你选）。指标只用来筛掉不合格的；合格的候选谁更好，看抽帧、按画面和创意的需要定。
  takes FILES... [--ref 参考片.mp4]  镜头候选：清晰度（中位数，糊的低）、最糊那一秒、亮度、动作（均值 / 中位数：中位数去掉了切点，明显低于参考片或其他段就是画面没动）、原声峰值、时长；--ref 把参考片的数放在第一行
  cues  FILES... [--pick]            单条配乐候选：2～8kHz 占比、>5kHz 占比、峰均比、每 3 秒能量曲线；--pick 选高频最低的
  score --dir D --cands a,b,c --sections intro,build,hero,ending [--rise build] [--build hero] [--audible intro] [--pick]
                                     整条分段配乐候选：每段的开场可闻、推进段起点和升幅、高潮段峰值位置和推进、整条高频占比；--pick 时拷成 D/sel_<段>.mp3 并写 selection.json"""
import argparse, json, os, shutil, subprocess, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import measure as M


def curve(x, step=3):
    n = M.SR * step
    return [20 * np.log10(np.sqrt(np.mean(x[i:i + n] ** 2)) + 1e-9) for i in range(0, len(x) - n // 2, n)]


def frames(p, fps=4, w=320):
    """按 fps 抽灰度帧，返回 (帧数组 N×H×W, fps)。"""
    info = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", p], capture_output=True, text=True).stdout.strip().split(",")
    if len(info) < 2 or not info[0]:
        return np.zeros((0, 1, 1)), fps
    h = int(round(int(info[1]) * w / int(info[0]) / 2) * 2)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-vf", f"fps={fps},scale={w}:{h},format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    n = len(raw) // (w * h)
    return np.frombuffer(raw[: n * w * h], dtype=np.uint8).reshape(n, h, w).astype(np.float32), fps


def sharpness(f):
    """拉普拉斯方差：越大越清楚。"""
    lap = -4 * f[1:-1, 1:-1] + f[:-2, 1:-1] + f[2:, 1:-1] + f[1:-1, :-2] + f[1:-1, 2:]
    return float(lap.var())


def motion_stats(fr):
    """逐帧差的均值和中位数：中位数不受切点和闪光影响，反映单镜头里东西动不动。"""
    if len(fr) < 2:
        return 0.0, 0.0
    d = np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2))
    return float(np.mean(d)), float(np.median(d))


def takes(a):
    if getattr(a, "ref", None):
        fr, fps = frames(a.ref)
        mm, md = motion_stats(fr)
        print(f"{'参考片 ' + os.path.basename(a.ref):<26} 动作 均值 {mm:4.1f} 中位 {md:4.1f}  时长 {len(fr) / fps:4.1f}s")
    for p in a.files:
        fr, fps = frames(p)
        if not len(fr):
            print(f"{os.path.basename(p):<26} 读不出画面"); continue
        sh = [sharpness(f) for f in fr]
        per_sec = [float(np.median(sh[i:i + fps])) for i in range(0, len(sh), fps)]
        worst = int(np.argmin(per_sec)) if per_sec else 0
        mm, md = motion_stats(fr)
        x = M.decode(p)
        if len(x) > M.SR // 2:
            win = int(0.3 * M.SR)
            rms = [20 * np.log10(np.sqrt(np.mean(x[i:i + win] ** 2)) + 1e-9) for i in range(0, len(x) - win, win // 2)]
            peak, tp = max(rms), int(np.argmax(rms)) * win // 2 / M.SR
            snd = f"原声峰值 {peak:6.1f} dB @ {tp:4.1f}s"
        else:
            snd = "无原声"
        print(f"{os.path.basename(p):<26} 清晰度 {np.median(sh):7.0f}（最糊在第 {worst} 秒 {per_sec[worst] if per_sec else 0:6.0f}）  亮度 {fr.mean():5.1f}  动作 均值 {mm:4.1f} 中位 {md:4.1f}  {snd}  时长 {len(fr) / fps:4.1f}s")


def cues(a):
    rows = []
    for p in a.files:
        x = M.decode(p); h, vh = M.band_ratio_db(x, 2000, 8000), M.band_ratio_db(x, 5000, 8000)
        crest = 20 * np.log10(np.max(np.abs(x)) / (np.sqrt(np.mean(x ** 2)) + 1e-9))
        rows.append((p, h + 0.5 * vh))
        print(f"{os.path.basename(p):<24} 2-8k {h:6.1f} dB  >5k {vh:6.1f} dB  峰均比 {crest:4.1f}  每3秒 {' '.join(f'{v:4.0f}' for v in curve(x))}")
    if a.pick and rows:
        print("→ 自动选（高频最低）：", min(rows, key=lambda r: r[1])[0])


def score(a):
    secs = a.sections.split(","); rows = []
    for c in a.cands.split(","):
        files = {s: os.path.join(a.dir, f"score_{c}_{s}.mp3") for s in secs}
        if not all(os.path.exists(f) for f in files.values()):
            continue
        whole = os.path.join(a.dir, f"score_{c}.mp3"); h = M.band_ratio_db(M.decode(whole if os.path.exists(whole) else files[secs[0]]), 2000, 8000)
        sc, notes, peak_t = -0.5 * h, [], None
        if a.audible and a.audible in files:
            lvl = float(np.mean(curve(M.decode(files[a.audible])) or [-99])); ok = lvl > -45; sc += 3 if ok else -4; notes.append(f"{a.audible} {'可闻' if ok else '静音 ✗'}")
        if a.rise and a.rise in files:
            cm = curve(M.decode(files[a.rise])); start = float(np.mean(cm[:2])); rise = float(np.mean(cm[-2:]) - start); sc += 0.6 * rise + (2 if start > -34 else -3); notes.append(f"{a.rise} 起 {start:.0f} 升 {rise:+.1f}")
        if a.build and a.build in files:
            ch = curve(M.decode(files[a.build])); i = int(np.argmax(ch)); peak_t = 3 * i; build = float(ch[i] - np.mean(ch[:2])); sc += 0.6 * build; notes.append(f"{a.build} 峰 {peak_t}s 推进 {build:+.1f}")
        rows.append((sc, c, peak_t, files)); print(f"score_{c}: 2-8k {h:5.1f} | {' | '.join(notes)} | 打分 {sc:5.1f}")
    if a.pick and rows:
        sc, c, peak_t, files = max(rows, key=lambda r: r[0])
        for s, f in files.items():
            shutil.copy(f, os.path.join(a.dir, f"sel_{s}.mp3"))
        json.dump({"score": f"score_{c}", "build_peak_t": peak_t}, open(os.path.join(a.dir, "selection.json"), "w"), ensure_ascii=False, indent=1); print("→ 自动选：", f"score_{c}")


ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
p = sp.add_parser("takes"); p.add_argument("files", nargs="+"); p.add_argument("--ref"); p.set_defaults(f=takes)
p = sp.add_parser("cues"); p.add_argument("files", nargs="+"); p.add_argument("--pick", action="store_true"); p.set_defaults(f=cues)
p = sp.add_parser("score"); p.add_argument("--dir", required=True); p.add_argument("--cands", required=True); p.add_argument("--sections", required=True); p.add_argument("--rise"); p.add_argument("--build"); p.add_argument("--audible"); p.add_argument("--pick", action="store_true"); p.set_defaults(f=score)
a = ap.parse_args(); a.f(a)
