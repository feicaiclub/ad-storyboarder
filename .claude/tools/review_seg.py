#!/usr/bin/env python3
"""一段候选的质检证据一键出（默认做法，可改）：每条候选（含升级版 _hd）出抽帧拼图（密度由 qa.py 按画面动静自动定）、逐秒响度；这段有台词或旁白的再出听写（按分段表算字错率）；最后出一张候选指标表。
python3 .claude/tools/review_seg.py S03 [--fps N 固定帧率] [--model large-v3]
产出：生成/<段>_vK_sheet.jpg、生成/<段>_vK_stt.txt（有台词才有）、生成/<段>_报数.txt。产品对比表和人脸表另用 qa.py crops（要先看拼图定产品和脸的位置）。"""
import argparse, glob, json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

ap = argparse.ArgumentParser(); ap.add_argument("seg"); ap.add_argument("--fps", type=float); ap.add_argument("--model", default="large-v3")
a = ap.parse_args()
T = os.path.dirname(os.path.abspath(__file__))
text = open(C.abspath(C.SEG), encoding="utf-8").read()
seg = next((j for j in (json.loads(b) for b in re.findall(r"```json\s*(\{.*?\})\s*```", text, re.S)) if j.get("id") == a.seg), None)
if not seg:
    sys.exit(f"分段表里没有 {a.seg}")
lines = "".join(ln["text"] for sh in seg.get("shots", []) for ln in sh.get("lines", []))
files = sorted(f for f in glob.glob(C.abspath(f"{C.GEN}/{a.seg}_v*.mp4")) if re.search(r"_v\d+(_hd)?\.mp4$", f))
if not files:
    sys.exit(f"{C.GEN}/ 里没有 {a.seg} 的候选（{a.seg}_vK.mp4）")
products = [r["file"] for r in seg.get("refs", []) if r.get("role") == "product"]
report = [f"{a.seg}  期望台词：{lines or '（无）'}  候选 {len(files)} 条",
          f"故意的效果（设计如此，不算崩坏）：{seg.get('imperfections') or '（无）'}",
          f"产品图：{products or '（这段没挂产品图）'}"]
for f in files:
    stem = f[:-4]
    subprocess.run(["python3", os.path.join(T, "qa.py"), "sheet", f, "--cols", "4", "--out", stem + "_sheet.jpg"] + (["--fps", str(a.fps)] if a.fps else []), capture_output=True)
    stt = ""
    if lines:
        stt = subprocess.run(["python3", os.path.join(T, "qa.py"), "stt", f, "--model", a.model, "--expect", lines], capture_output=True, text=True).stdout.strip()
        open(stem + "_stt.txt", "w", encoding="utf-8").write(stt + "\n")
    lv = subprocess.run(["python3", os.path.join(T, "qa.py"), "levels", f], capture_output=True, text=True).stdout.strip().splitlines()
    info = C.ffprobe(f)
    report.append(f"\n== {os.path.basename(f)}  {info.get('width')}x{info.get('height')} {info.get('duration')}s 有声={info.get('has_audio', False)}"
                  + (f"\n听写：{stt or '（无）'}" if lines else "") + f"\n响度：{lv[-1] if lv else ''}")
tk = subprocess.run(["python3", os.path.join(T, "pick.py"), "takes"] + files, capture_output=True, text=True).stdout.strip()
report.append("\n指标：\n" + tk)
if products:
    report.append(f"\n下一步：看拼图挑出产品最清楚的几帧，写 spec（第一格放 {products[0]}），python3 .claude/tools/qa.py crops spec.json --out {C.GEN}/{a.seg}_product.jpg")
if seg.get("cast") or any(r.get("role") == "identity" for r in seg.get("refs", [])):
    report.append(f"有人出镜：人脸表 python3 .claude/tools/qa.py crops face_spec.json --out {C.GEN}/{a.seg}_faces.jpg（和他的照片或确认过的定稿图、其他段并排）")
open(C.abspath(f"{C.GEN}/{a.seg}_报数.txt"), "w", encoding="utf-8").write("\n".join(report) + "\n")
print("\n".join(report))
