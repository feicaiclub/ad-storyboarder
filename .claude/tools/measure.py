"""量：声音和画面的客观数。gate.py、qa.py、pick.py 共用。只量，不判断。"""
import os, re, subprocess
import numpy as np

SR = 16000


def decode(path, start=0.0, dur=None, sr=SR):
    """解出单声道浮点采样。文件不存在或解不出来就报错，不悄悄当成无声；没有音轨的视频返回空数组。"""
    if not os.path.exists(str(path)):
        raise FileNotFoundError(f"找不到文件：{path}")
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}"] + (["-t", f"{dur:.3f}"] if dur else []) + ["-i", str(path), "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0 and b"does not contain any stream" not in r.stderr and b"Output file is empty" not in r.stderr:
        raise RuntimeError(f"解不出声音：{path}（{r.stderr.decode(errors='ignore').strip()[-200:]}）")
    return np.frombuffer(r.stdout, dtype=np.float32)


def per_second_db(x, sr=SR):
    return [20 * np.log10(np.sqrt(np.mean(x[i:i + sr] ** 2)) + 1e-9) for i in range(0, len(x) - sr, sr)]


def holes_and_peaks(vals, hole_db=-45.0, peak_db=-6.0, min_run=2):
    holes, run = [], []
    for i, v in enumerate(vals + [0]):
        if v < hole_db:
            run.append(i)
        else:
            if len(run) >= min_run:
                holes.append((run[0], run[-1]))
            run = []
    return holes, [i for i, v in enumerate(vals) if v > peak_db]


def loudness(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
    g = lambda p: (re.findall(p, r) or [None])[-1]
    return {"lufs": float(g(r"I:\s+(-?[\d.]+) LUFS") or -99), "tp": float(g(r"Peak:\s+(-?[\d.]+) dBFS") or 0), "lra": float(g(r"LRA:\s+([\d.]+) LU") or 0)}


def band_ratio_db(x, lo, hi, sr=SR):
    """某频段能量占全频的比例（dB）。2～8kHz 用来看刺耳度，<150Hz 用来看隆隆声。"""
    n = len(x) // 4 * 4
    f = np.fft.rfft(x[:n] * np.hanning(n)); p = np.abs(f) ** 2; fr = np.fft.rfftfreq(n, 1 / sr)
    return float(10 * np.log10(p[(fr >= lo) & (fr < hi)].sum() / (p.sum() + 1e-12) + 1e-12))


def f0_stats(x, sr=SR):
    frame, hop, lo, hi = int(0.04 * sr), int(0.01 * sr), sr // 400, sr // 60
    vals, rms_all = [], np.sqrt(np.mean(x ** 2)) + 1e-9
    for s in range(0, len(x) - frame, hop):
        w = x[s:s + frame] * np.hanning(frame)
        if np.sqrt(np.mean(w ** 2)) < 0.3 * rms_all:
            continue
        ac = np.correlate(w, w, mode="full")[frame - 1:]
        if ac[0] <= 0:
            continue
        ac = ac / ac[0]; seg = ac[lo:hi]
        if len(seg) and seg.max() > 0.45:
            vals.append(sr / (lo + int(np.argmax(seg))))
    if not vals:
        return {}
    v = np.array(vals)
    return {"f0_median": round(float(np.median(v)), 1), "f0_iqr": round(float(np.percentile(v, 75) - np.percentile(v, 25)), 1), "voiced": len(vals)}


def brightness(video, t):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=320:-1", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
    y = np.frombuffer(raw, dtype=np.uint8)
    return (float(y.mean()), float((y < 30).mean() * 100)) if len(y) else (None, None)


def frames_and_duration(video):
    n = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames,r_frame_rate", "-of", "csv=p=0", str(video)], capture_output=True, text=True).stdout.strip().split(",")
    fps = eval(n[0]) if "/" in n[0] else float(n[0]); nf = int(n[1]) if len(n) > 1 else 0
    d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)], capture_output=True, text=True).stdout or 0)
    return nf, fps, d
