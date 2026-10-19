#!/usr/bin/env python3
"""Higgsfield 适配（本 harness 唯一的后端）：中性分段 → higgsfield 命令行任务；提交、登记、限流、轮询、下载、续跑；另管出图、产品图、音频、估价、余额、对账。
前提：本机装了 higgsfield 命令行、已登录（higgsfield auth login）、已选工作区（higgsfield workspace set <id>）。凭证由命令行自己存在 ~/.config/higgsfield：不读、不拷、不打印。
单跑：
  python3 .claude/tools/adapters/higgsfield.py check                                      查命令行、登录、工作区、余额（不打印账户原文：里面有邮箱）
  python3 .claude/tools/adapters/higgsfield.py params MODEL                               这个模型收哪些参数、枚举、互斥规则（第一次用先看）
  python3 .claude/tools/adapters/higgsfield.py video --jobs 生成/jobs.json [--poll 15] [--max 4]   跑视频任务（segments.py run 调的就是它）
  python3 .claude/tools/adapters/higgsfield.py image MODEL --prompt "…" --out 素材库/x.png [--ref a.png ...] [--aspect 9:16] [--res 2k] [--n 2] [--param k=v ...]
  python3 .claude/tools/adapters/higgsfield.py photoshoot MODE --prompt "…" --image 素材库/产品/x.png --out 素材库/关键帧/x.png [--count 3]
  python3 .claude/tools/adapters/higgsfield.py audio MODEL --prompt "…" --out 剪辑/音效/x.wav [--duration 8] [--param k=v ...]
  python3 .claude/tools/adapters/higgsfield.py cost MODEL --prompt "…" [--param k=v ...]    估价，不花钱
  python3 .claude/tools/adapters/higgsfield.py fetch JOB_ID --out 路径                     按任务号补下载
  python3 .claude/tools/adapters/higgsfield.py ledger [--size 20]                          最近的扣费流水（花完对账）
所有命令加 --dry 只打印要执行的命令，不调用（自检用）。环境变量 HF_DRY=1 等同 --dry。
提示词原样发出，不加任何默认块：段里写了 prompt 就发 prompt；没写就把 rules、参考说明（按挂图顺序 @image1…，带段里写的 note）、camera、shots、imperfections、台词、sound 按顺序拼起来。段里的 params 原样透传给命令行（模型能做的，这里不拦）。
"""
import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import common as C  # noqa: E402

TAG = "higgsfield"
DRY = os.environ.get("HF_DRY") == "1"
DONE = {"completed", "succeeded", "success", "done", "finished"}
FAILED = {"failed", "error", "errored", "canceled", "cancelled", "rejected", "nsfw", "expired", "ip_detected"}  # ip_detected：生成中被知识产权检测拦下（2026-10-16 实测）
RUNNING = {"", "queued", "pending", "in_progress", "processing", "running", "waiting", "submitted", "starting", "created"}  # 别的状态一律按失败记下来，不干等
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

# 能力声明（2026-10-15 用 `higgsfield model get` 核过 seedance_2_5、minimax_h3；其余标了"先 model get"的没核）。
# 价格不写在这里（会变）：估价一律现查 `higgsfield generate cost`，参考价在 Higgsfield 实测.md。
CAPABILITIES = {
    "video_models": {
        "seedance_2_5": {"res": ["480p", "720p", "1080p"], "dur": (4, 30), "draft": True, "draft_res": "480p", "audio": True, "max_images": 30, "max_media": 50,
                         "mix_frames_and_refs": True,
                         "note": "默认视频模型。纯文字 t2v；首帧、首尾帧、参考都走 omni_reference；默认自带声音；草稿 draft=true，选中后 draft_job_id 升级"},
        "minimax_h3": {"res": ["2K"], "dur": (4, 15), "draft": False, "audio": True, "max_images": 9, "max_media": 12,
                       "mix_frames_and_refs": False,
                       "note": "只出 2K。首帧、首尾帧（尾帧要先有首帧）不能和参考素材混用；音频参考要配至少一张图或视频参考。时长上限没核，先 model get"},
        "seedance_2_0": {"res": ["480p", "720p", "1080p", "4K"], "dur": (4, 15), "draft": False, "audio": True, "max_images": 9, "max_media": 12,
                         "mix_frames_and_refs": True, "unverified": True,
                         "note": "要原生 4K 时用（官方文档说支持，没实测）。参数和 2.5 不同，第一次用先 params seedance_2_0 核对，再先出一条看看"},
        "kling3_0": {"res": ["std", "pro", "4K"], "dur": (3, 15), "draft": False, "audio": True, "max_images": 4, "max_media": 4,
                     "mix_frames_and_refs": False, "unverified": True,
                     "note": "便宜，动作不大的单场景；分辨率是 mode 档位。没核参数，第一次用先 params kling3_0"},
    },
    # 作者要的分辨率 → 默认模型（拷问时问清分辨率，按这张表选；作者点名模型的优先）
    "res_default": {"480p": "seedance_2_5", "720p": "seedance_2_5", "1080p": "seedance_2_5", "2K": "minimax_h3", "4K": "seedance_2_0"},
    "ratios": ["auto", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"],
    "modes": {"t2v": "纯文字，不挂任何素材", "first_frame": "首帧（start_image）", "first_last": "首尾帧（start_image + end_image）",
              "ref": "参考（image / video / audio references）"},
    "image_models": {
        "gpt_image_2_5": "默认高保真；产品、带字、关键帧；可挂多张参考；quality low→max，resolution 1k/2k/4k；background=transparent 出透明底",
        "seedream_v5_pro": "人物设定表、带脸的改图；最多 10 张参考；1k/1.5k/2k",
        "text2image_soul_v2": "人像、时尚；便宜（2k 一张 0.12）；最多 1 张参考；不给 style_id 会自动套 General 风格；style_id 不能和参考图同用",
        "soul_location": "无人场景，只吃文字",
    },
    "photoshoot_modes": ["product_shot", "lifestyle_scene", "closeup_product_with_person", "moodboard_pin", "hero_banner", "social_carousel",
                         "ad_creative_pack", "virtual_model_tryout", "conceptual_product", "restyle"],
    "audio_models": {"seed_audio": "音效、环境声、可选音色配音（默认 wav 24kHz，一段约 16 秒）", "sonilo_music": "配乐，要给 duration",
                     "elevenlabs_v4": "多人对话式配音（dialogue 数组）"},
}

# 参考按挂图顺序用 @image1、@image2… 指代（2026-10-16 实测能认）。每条只说它是什么、带段里写的 note；要它怎么用，段里自己写。
ROLE_TEXT = {
    "product": "@{tag} is the product{note}.",
    "identity": "@{tag} is {note}.",
    "location": "@{tag} is the location{note}.",
    "plate": "@{tag} is the background plate for this camera position{note}.",
    "prop": "@{tag} is a prop{note}.",
    "frame": "@{tag} is a composition reference only{note}.",
    "look": "@{tag} is a look reference only{note}.",
}


def hf_bin():
    for b in ("higgsfield", "hf", "higgs"):
        p = shutil.which(b)
        if p:
            return p
    return None


def _fmt(cmd):
    return " ".join(a if re.fullmatch(r"[\w@./:=,+-]+", a) else json.dumps(a, ensure_ascii=False) for a in cmd)


def cli(args, timeout=1800, dry=None):
    """跑一条 higgsfield 命令，返回解析后的 JSON（解析不了就返回原文）。登录、工作区的问题给人话。"""
    dry = DRY if dry is None else dry
    cmd = [hf_bin() or "higgsfield"] + [str(a) for a in args] + ["--json"]
    if dry:
        print("[dry] " + _fmt(cmd))
        return {"dry": True, "cmd": cmd}
    if not hf_bin():
        sys.exit("找不到 higgsfield 命令行：先按官方说明安装并登录（npm i -g @higgsfield/cli；higgsfield auth login；higgsfield workspace set <id>）")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    out, err = r.stdout.strip(), r.stderr.strip()
    msg = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "<邮箱>", (err or out)[-600:])
    if r.returncode != 0:
        low = msg.lower()
        if "no workspace selected" in low:
            raise RuntimeError("还没选工作区：让用户运行 `higgsfield workspace list` 再 `higgsfield workspace set <id>`")
        if "not authenticated" in low or "session expired" in low or ("login" in low and "auth" in low):
            raise RuntimeError("Higgsfield 没登录或登录过期：让用户自己运行 `higgsfield auth login`（浏览器里授权）")
        raise RuntimeError(f"higgsfield {' '.join(map(str, args[:3]))} 失败：{msg}")
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return out


def _is_dry(d):
    return isinstance(d, dict) and d.get("dry")


def _walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from _walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v)


def job_objects(parsed):
    """从命令行的 JSON 里找出任务对象（带 id 的 dict）；找不到就从原文里抠 UUID。"""
    objs = [d for d in _walk(parsed) if isinstance(d, dict) and d.get("id") and ("status" in d or "job_type" in d or "result_url" in d)]
    if objs:
        return objs
    text = parsed if isinstance(parsed, str) else json.dumps(parsed)
    return [{"id": u} for u in dict.fromkeys(re.findall(UUID, text))]


def credits_of(parsed):
    for d in _walk(parsed):
        for k in ("credits", "cost", "total_credits", "price", "amount"):
            if isinstance(d.get(k), (int, float)) and not isinstance(d.get(k), bool):
                return float(d[k])
    if isinstance(parsed, (int, float)):
        return float(parsed)
    return None


def download(url, out, tries=4):
    out = pathlib.Path(C.abspath(out))
    out.parent.mkdir(parents=True, exist_ok=True)
    last = None
    for k in range(tries):
        tmp = out.with_suffix(out.suffix + ".part")
        try:
            with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
            tmp.replace(out)
            return str(out)
        except Exception as e:  # 链接可能限时：失败就等一会再下；还不行用 fetch 按任务号重拿链接
            last = e
            C.log(TAG, f"下载第 {k + 1} 次失败：{str(e)[:120]}")
            time.sleep(5 * (k + 1))
    raise RuntimeError(f"下载失败：{last}")


def _ext_of(url, default):
    m = re.search(r"\.(png|jpe?g|webp|mp4|mov|wav|mp3|ogg|glb)(\?|$)", url or "", re.I)
    return "." + m.group(1).lower() if m else default


def _media(p):
    """素材参数：本地文件给绝对路径（命令行会自动上传）；任务号、上传号原样给。"""
    if re.fullmatch(UUID, str(p)):
        return p
    return C.abspath(p) if os.path.exists(C.abspath(p)) else p


# ---------------- 余额、估价、对账
def balance(dry=None):
    d = cli(["account", "status"], dry=dry)
    return None if _is_dry(d) else credits_of(d)


def ledger(size=20, dry=None):
    """扣费流水，只留时间、积分和看得懂的说明字段（不带账户信息）。"""
    d = cli(["account", "transactions", "--size", str(size)], dry=dry)
    if _is_dry(d):
        return []
    rows = d if isinstance(d, list) else next((v for v in (d.get("items"), d.get("transactions"), d.get("data")) if isinstance(v, list)), []) if isinstance(d, dict) else []
    keep = ("created_at", "credits", "type", "description", "job_type", "job_id", "reason")
    return [{k: r.get(k) for k in keep if k in r} for r in rows if isinstance(r, dict)]


_COST = {}


def cost(args, dry=None):
    """估一条任务要多少积分；估不出（有的模型、带草稿号的升级不支持估价）返回 None。args 可以直接给 video_args() 的结果（开头的 generate create 会去掉）。"""
    args = list(args)
    if args[:2] == ["generate", "create"]:
        args = args[2:]
    key = json.dumps(args, ensure_ascii=False)
    if key in _COST:
        return _COST[key]
    try:
        d = cli(["generate", "cost"] + args, timeout=180, dry=dry)
        v = None if _is_dry(d) else credits_of(d)
    except RuntimeError as e:
        C.log(TAG, f"估不出价：{str(e)[:160]}")
        v = None
    _COST[key] = v
    return v


def params(model, dry=None):
    """模型收哪些参数：名字、类型、默认值、枚举，加互斥规则。"""
    d = cli(["model", "get", model], timeout=120, dry=dry)
    if _is_dry(d) or not isinstance(d, dict):
        return str(d)
    lines = [f"{d.get('display_name', model)}（{d.get('job_type', model)}，{d.get('type', '')}）"]
    for p in d.get("params", []):
        enum = f" 可选 {p['enum']}" if p.get("enum") else ""
        lines.append(f"  --{p.get('name')}  {p.get('type')}  默认 {p.get('default')}{'  必填' if p.get('required') else ''}{enum}")
    for r in d.get("rules", []):
        lines.append(f"  规则：{r.get('message')}")
    return "\n".join(lines)


# ---------------- 视频：中性分段 → 任务
def pick_model(resolution, model=None):
    if model:
        return model
    return CAPABILITIES["res_default"].get(resolution, "seedance_2_5")


def _t(sec):
    return f"{sec:.1f}s"


def build_job(seg, resolution="1080p", n=1, model=None, draft=False):
    """中性分段 → 一条任务（提示词、参考、首尾帧、时长、输出路径）。段里写了 model / res 的以段为准；提示词不加任何默认块。"""
    resolution = seg.get("res", resolution)
    model = pick_model(resolution, seg.get("model") or model)
    caps = CAPABILITIES["video_models"].get(model)
    if caps is None:  # 没核过的模型：不按猜的范围拦，第一次用先出一条看看
        C.log(TAG, f"{seg['id']}：{model} 不在已核过的模型表里，不查时长和分辨率；第一次用先出一条看看（params {model}）")
        caps = {}
    refs = seg.get("refs", [])
    mode = seg.get("mode", "ref" if refs else "t2v")
    if mode not in CAPABILITIES["modes"]:
        raise ValueError(f"{seg['id']} 的 mode 写成了 {mode}：只能是 {'/'.join(CAPABILITIES['modes'])}")
    lo, hi = caps.get("dur", (1, 3600))
    dur = int(round(float(seg["dur"])))
    if not lo <= dur <= hi:
        raise ValueError(f"{seg['id']} 时长 {dur}s 超出 {model} 的 {lo}–{hi}s：拆段或换模型")
    if caps.get("res") and resolution not in caps["res"]:
        raise ValueError(f"{seg['id']} 要 {resolution}，{model} 只有 {caps['res']}：换分辨率或换模型")
    if mode == "t2v" and (refs or seg.get("video_refs") or seg.get("audio_refs") or seg.get("first_frame")):
        raise ValueError(f"{seg['id']} 是纯文字模式却挂了素材：改成 ref / first_frame，或删掉素材")
    if mode == "ref" and not (refs or seg.get("video_refs")):
        raise ValueError(f"{seg['id']} 是参考模式但没有参考图或参考视频")
    if mode in ("first_frame", "first_last") and not seg.get("first_frame"):
        raise ValueError(f"{seg['id']} 是首帧模式但没写 first_frame")
    if mode == "first_last" and not seg.get("last_frame"):
        raise ValueError(f"{seg['id']} 是首尾帧模式但没写 last_frame")
    if mode in ("first_frame", "first_last") and (refs or seg.get("video_refs") or seg.get("audio_refs")) and not caps.get("mix_frames_and_refs", True):
        raise ValueError(f"{seg['id']}：{model} 不能把首尾帧和参考素材混用，二选一，或换 seedance_2_5")
    if seg.get("audio_refs") and not (refs or seg.get("video_refs")) and model == "minimax_h3":
        raise ValueError(f"{seg['id']}：{model} 的音频参考要配至少一张参考图或参考视频")
    n_img = len(refs) + (1 if mode in ("first_frame", "first_last") else 0) + (1 if mode == "first_last" else 0)
    if n_img > caps.get("max_images", 30):
        raise ValueError(f"{seg['id']} 挂了 {n_img} 张图，{model} 最多 {caps.get('max_images')} 张")
    use_draft = bool(draft and caps.get("draft"))
    if draft and not use_draft:
        C.log(TAG, f"{seg['id']}：{model} 没有草稿模式，直接出 {resolution}")
    job = {"id": seg["id"], "out": f"生成/{seg['id']}.mp4", "model": model, "mode": mode, "duration": dur,
           "resolution": caps.get("draft_res", "480p") if use_draft else resolution, "target_res": resolution,
           "aspect_ratio": seg.get("ratio", "16:9"), "n": int(n),
           "draft": use_draft, "generate_audio": seg.get("generate_audio", True), "params": dict(seg.get("params") or {}),
           "image_refs": [], "video_refs": [], "audio_refs": []}  # 草稿按低清出（实测 480p 草稿），选中后按 target_res 升级
    head = ""
    roles = []
    if mode in ("first_frame", "first_last"):
        job["start_image"] = seg["first_frame"]
        if mode == "first_last":
            job["end_image"] = seg["last_frame"]
    for i, r in enumerate(refs, 1):
        job["image_refs"].append(r["file"])
        role, note = r.get("role", "frame"), r.get("note", "")
        note = (note or "the person") if role == "identity" else (f" ({note})" if note else "")
        roles.append(ROLE_TEXT.get(role, "@{tag}{note}").format(tag=f"image{i}", note=note))
    for k, v in enumerate(seg.get("video_refs", []), 1):  # 运镜参考视频
        job["video_refs"].append(v["file"])
        roles.append(f"@video{k}: {v.get('note') or 'reference video'}.")
    for k, a in enumerate(seg.get("audio_refs", []), 1):
        job["audio_refs"].append(a["file"])
        roles.append(f"@audio{k}: {a.get('note', 'audio reference')}.")
    if seg.get("prompt"):  # 段里直接写了提示词：原样发，连参考说明和自动句都不加
        job["prompt"] = seg["prompt"].strip()
        return job
    body = head + (seg.get("rules", "") + " " if seg.get("rules") else "")
    if roles:
        body += "References: " + " ".join(roles) + " "
    if seg.get("camera"):
        body += f"Camera: {seg['camera']}. "
    for k, sh in enumerate(seg.get("shots", []), 1):
        body += f"\n[Shot {k} | {'0.0s' if k == 1 else 'from ' + _t(sh.get('at', 0))}] {sh['text']}"
    if seg.get("imperfections"):
        body += f"\nDeliberate imperfections (intended, keep them): {seg['imperfections']}."
    lines = [ln for sh in seg.get("shots", []) for ln in sh.get("lines", [])]
    for ln in lines:
        body += f"\n{'Voice-over (off-screen, mouths do not move)' if ln.get('vo') else ln.get('speaker', 'Speaker') + ' says'}" \
                f"{(', ' + ln['delivery']) if ln.get('delivery') else ''}: \"{ln['text']}\""
    sound = seg.get("sound", "")
    if sound:
        body += f"\nSound: {sound}."
    if seg.get("music") is False:  # 段里明写了才加，不替它定
        body += " No music."
    if seg.get("voices") is False and not lines:
        body += " No voices, no dialogue."
    job["prompt"] = body.strip()
    return job


def job_inputs(job):
    return [p for p in job.get("image_refs", []) + job.get("video_refs", []) + job.get("audio_refs", []) + [job.get("start_image"), job.get("end_image")]
            if p and not re.fullmatch(UUID, str(p))]


def video_args(job, draft_job_id=None):
    """任务 → `generate create` 的参数（不含 --wait / --json）。seedance_2_5 按 model get 写全；别的模型按常用参数传，第一次用先出一条、按 params 校对。"""
    m = job["model"]
    a = ["generate", "create", m, "--prompt", job["prompt"], "--duration", str(job["duration"]), "--aspect_ratio", job["aspect_ratio"]]
    if m == "seedance_2_5":
        a += ["--mode", "t2v" if job["mode"] == "t2v" else "omni_reference", "--resolution", job["resolution"],
              "--generate_audio", "true" if job.get("generate_audio", True) else "false"]
        if job.get("draft") and not draft_job_id:
            a += ["--draft", "true"]
        if draft_job_id:  # 升级必须显式写 --draft false，不然命令行自己的参数校验报 "Unsupported validation rules"（1.1.26 实测，2026-10-16）
            a += ["--draft", "false", "--draft_job_id", draft_job_id]
    elif m == "kling3_0":
        a += ["--mode", {"4K": "4k"}.get(job["resolution"], job["resolution"] if job["resolution"] in ("std", "pro") else "pro")]
    else:
        a += ["--resolution", {"4K": "4k"}.get(job["resolution"], job["resolution"]) if m != "minimax_h3" else "2K"]
    if job.get("start_image"):
        a += ["--start-image", _media(job["start_image"])]
    if job.get("end_image"):
        a += ["--end-image", _media(job["end_image"])]
    for flag, key in (("--image-references", "image_refs"), ("--video-references", "video_refs"), ("--audio-references", "audio_refs")):
        for p in job.get(key, []):
            a += [flag, _media(p)]
    for k, v in (job.get("params") or {}).items():  # 段里的 params 原样透传：覆盖上面的默认值，None 表示去掉这个参数
        flag = f"--{k}"
        v = ("true" if v else "false") if isinstance(v, bool) else v
        if flag in a:
            i = a.index(flag)
            if v is None:
                del a[i:i + 2]
            else:
                a[i + 1] = str(v)
        elif v is not None:
            a += [flag, str(v)]
    return a


def estimate(jobs, dry=None):
    """估一批任务：返回 (合计积分, 估不出的条数, 明细)。价格只跟模型、模式、分辨率、时长、草稿、声音、素材数有关，同类只估一次（估价也会上传本地素材）。候选 n 条按 n 倍算。"""
    total, unknown, rows, group = 0.0, 0, [], {}
    for j in jobs:
        key = (j["model"], j["mode"] == "t2v", j["resolution"], j["duration"], bool(j.get("draft")), bool(j.get("generate_audio", True)),
               len(j.get("image_refs", [])), len(j.get("video_refs", [])), len(j.get("audio_refs", [])), bool(j.get("start_image")), bool(j.get("end_image")),
               bool(j.get("upgrade_from")), json.dumps(j.get("params") or {}, sort_keys=True))
        if key not in group:
            group[key] = cost(video_args(j, draft_job_id=j.get("upgrade_from")), dry=dry)
        v, n = group[key], int(j.get("n", 1))
        rows.append((j["id"], j["model"], j["resolution"], j["duration"], n, v))
        if v is None:
            unknown += n
        else:
            total += v * n
    return total, unknown, rows


def variant_path(job, k):
    """候选一律带 _vK（单条也是 _v1，证据脚本只认这种名字）；草稿升级的任务 out 已经写好（<段>_vK_hd.mp4），原样用。"""
    p = pathlib.Path(job["out"])
    if job.get("single"):
        return str(p)
    return str(p.with_name(f"{p.stem}_v{k + 1}{p.suffix}"))


def _meta_path(out):
    return C.abspath(out) + ".json"


def _poll(job_id, dry=None):
    d = cli(["generate", "get", job_id], timeout=120, dry=dry)
    objs = job_objects(d)
    o = next((x for x in objs if x.get("id") == job_id), objs[0] if objs else {})
    return str(o.get("status", "")).lower(), o.get("result_url"), o


def run_jobs(jobs, poll=15, force=False, dry=None, timeout_min=40, max_parallel=4):
    """提交 → 登记任务号（同名 .json）→ 轮询 → 下载。同时在跑的不超过 max_parallel 条。
    已有成片的跳过；登记里有任务号且没完成的接着等，不重复提交（能续跑）。"""
    dry = DRY if dry is None else dry
    queue, pending, results = [], {}, []
    for j in jobs:
        for k in range(1 if j.get("single") else int(j.get("n", 1))):
            out = variant_path(j, k)
            meta = _meta_path(out)
            if not force and os.path.exists(C.abspath(out)) and C.ffprobe(C.abspath(out)).get("duration", 0) > 0:
                results.append({"id": j["id"], "out": out, "status": "exists"})
                continue
            old = C.read_json(meta) if os.path.exists(meta) else {}
            if not force and old.get("job_id") and old.get("status") == "pending":
                pending[old["job_id"]] = {"job": j, "out": out, "t0": time.time()}
                C.log(TAG, f"{j['id']} 接着等之前提交的任务 {old['job_id']}")
                continue
            queue.append((j, out))

    def submit():
        while queue and len(pending) < max_parallel:
            j, out = queue.pop(0)
            try:
                d = cli(video_args(j, draft_job_id=j.get("upgrade_from")), dry=dry)
            except RuntimeError as e:
                C.log(TAG, f"{j['id']} 提交失败：{e}")
                results.append({"id": j["id"], "out": out, "status": "submit_failed", "error": str(e)})
                if "没登录" in str(e) or "工作区" in str(e):  # 账号问题不会自己好：剩下的都别提交了
                    results.extend({"id": q["id"], "out": o, "status": "not_submitted"} for q, o in queue)
                    queue.clear()
                continue
            if dry:
                results.append({"id": j["id"], "out": out, "status": "dry"})
                continue
            objs = job_objects(d)
            if not objs:
                results.append({"id": j["id"], "out": out, "status": "submit_failed", "error": f"没拿到任务号：{str(d)[:200]}"})
                continue
            jid = objs[0]["id"]
            C.write_json(_meta_path(out), {"job": j, "job_id": jid, "status": "pending", "submitted": time.strftime("%Y-%m-%d %H:%M:%S")})
            C.log(TAG, f"{j['id']} 已提交 {jid} → {out}")
            pending[jid] = {"job": j, "out": out, "t0": time.time()}
            time.sleep(1)

    submit()
    while pending:
        time.sleep(poll)
        for jid in list(pending):
            p = pending[jid]
            try:
                status, url, obj = _poll(jid, dry=dry)
            except RuntimeError as e:
                C.log(TAG, f"{p['job']['id']} 查询异常：{e}")
                continue
            meta = _meta_path(p["out"])
            if status in DONE and url:
                try:
                    path = download(url, p["out"])
                    info = C.ffprobe(path)
                    C.write_json(meta, {"job": p["job"], "job_id": jid, "status": "done", "result_url": url, "info": info, "raw": obj})
                    C.log(TAG, f"{p['job']['id']} ✓ {int(time.time() - p['t0'])}s {info.get('width')}x{info.get('height')} {info.get('duration')}s 有声={info.get('has_audio', False)} → {p['out']}")
                    results.append({"id": p["job"]["id"], "out": p["out"], "status": "done", "job_id": jid, "info": info})
                except Exception as e:
                    C.log(TAG, f"{p['job']['id']} 下载失败：{e}（可用 fetch {jid} 补下）")
                    results.append({"id": p["job"]["id"], "out": p["out"], "status": "download_failed", "job_id": jid})
                del pending[jid]
            elif status in FAILED or status not in RUNNING:
                C.write_json(meta, {"job": p["job"], "job_id": jid, "status": "failed", "reason": status, "raw": obj})
                C.log(TAG, f"{p['job']['id']} ✗ {status}（{'平台拦下' if status in FAILED else '没见过的状态，按失败记'}）：{json.dumps(obj, ensure_ascii=False)[:300]}")
                results.append({"id": p["job"]["id"], "out": p["out"], "status": "failed", "reason": status, "job_id": jid})
                del pending[jid]
            elif time.time() - p["t0"] > timeout_min * 60:
                C.log(TAG, f"{p['job']['id']} 等了 {timeout_min} 分钟还没好，先放着（登记里有任务号，下次 run 会接着等）")
                results.append({"id": p["job"]["id"], "out": p["out"], "status": "still_pending", "job_id": jid})
                del pending[jid]
            else:
                C.log(TAG, f"{p['job']['id']} {status or 'pending'} {int(time.time() - p['t0'])}s")
        submit()
    return results


# ---------------- 出图、产品图、音频（一次一条，--wait 等结果）
def _kv(params):
    out = []
    for kv in params or []:
        k, v = kv.split("=", 1)
        out += [f"--{k}", v]
    return out


def _save_results(d, out, default_ext):
    objs = [o for o in job_objects(d) if o.get("result_url")]
    saved = []
    for i, o in enumerate(objs):
        stem = pathlib.Path(out)
        path = str(stem.with_suffix(_ext_of(o["result_url"], default_ext))) if len(objs) == 1 else str(stem.with_name(f"{stem.stem}_{i + 1}{_ext_of(o['result_url'], default_ext)}"))
        download(o["result_url"], path)
        C.write_json(C.abspath(path) + ".json", {"job_id": o.get("id"), "job_type": o.get("job_type"), "result_url": o["result_url"], "params": o.get("params")})
        saved.append(path)
    if not saved:
        raise RuntimeError(f"没拿到结果链接：{str(d)[:300]}")
    return saved


def image(model, prompt, out, refs=(), aspect=None, res=None, n=1, params=(), dry=None):
    """出图，提示词原样发。Soul 2.0 不指定 style_id 会自动套 General 风格，要控制风格就传 --param style_id=…（不能和参考图一起用）。
    出图词存一份在图旁边（同名 .prompt.txt），放映室的素材库里能看到。"""
    full = prompt
    saved = []
    for k in range(int(n)):
        a = ["generate", "create", model, "--prompt", full]
        if aspect:
            a += ["--aspect_ratio", aspect]
        if res:
            a += ["--quality" if model in ("text2image_soul_v2", "soul_cinematic") else "--resolution", res]
        for r in refs:
            a += ["--image-references", _media(r)]
        a += _kv(params) + ["--wait"]
        d = cli(a, dry=dry)
        if _is_dry(d):
            continue
        o = out if n == 1 else str(pathlib.Path(out).with_name(f"{pathlib.Path(out).stem}_{k + 1}{pathlib.Path(out).suffix}"))
        for p in _save_results(d, o, ".png"):
            pathlib.Path(C.abspath(p) + ".prompt.txt").write_text(prompt, encoding="utf-8")
            saved.append(p)
    return saved


def photoshoot(mode, prompt, images, out, count=1, params=(), dry=None):
    """品牌产品图（后台按模式自动拼提示词，跑在 GPT Image 2 上）：模式见 CAPABILITIES["photoshoot_modes"]。prompt 写意图，不写完整提示词。"""
    if mode not in CAPABILITIES["photoshoot_modes"]:
        C.log(TAG, f"⚠ {mode} 不在已知模式里（{', '.join(CAPABILITIES['photoshoot_modes'])}），照样提交，报错就换")
    a = ["product-photoshoot", "create", "--mode", mode, "--prompt", prompt, "--count", str(count)]
    for p in images:
        a += ["--image", _media(p)]
    d = cli(a + _kv(params), dry=dry)
    if _is_dry(d):
        return []
    objs = job_objects(d)
    if objs and not any(o.get("result_url") for o in objs):  # 没等结果就返回了任务号：逐个等
        for o in objs:
            cli(["generate", "wait", o["id"]], dry=dry)
        d = [cli(["generate", "get", o["id"]], dry=dry) for o in objs]
    saved = _save_results(d, out, ".png")
    for p in saved:
        pathlib.Path(C.abspath(p) + ".prompt.txt").write_text(f"[product-photoshoot {mode}] {prompt}", encoding="utf-8")
    return saved


def audio(model, prompt, out, duration=None, params=(), dry=None):
    a = ["generate", "create", model, "--prompt", prompt]
    if duration:
        a += ["--duration", str(int(duration)) if float(duration).is_integer() else str(duration)]
    if model == "seed_audio" and not any(p.startswith("format=") for p in params or []):
        a += ["--format", "wav"]
    d = cli(a + _kv(params) + ["--wait"], dry=dry)
    if _is_dry(d):
        return []
    return _save_results(d, out, ".wav")


def fetch(job_id, out, dry=None):
    status, url, obj = _poll(job_id, dry=dry)
    if dry:
        return None
    if status not in DONE or not url:
        sys.exit(f"任务 {job_id} 状态是 {status or '未知'}，还不能下载")
    path = download(url, out)
    meta = C.abspath(out) + ".json"
    old = C.read_json(meta) if os.path.exists(meta) else {}
    old.update({"job_id": job_id, "status": "done", "result_url": url, "info": C.ffprobe(path), "raw": obj})
    C.write_json(meta, old)
    return path


def check(dry=None):
    """命令行、登录、工作区、余额。只打印积分和套餐，不打印账户原文（里面有邮箱）。返回 True / False。"""
    if not hf_bin() and not dry:
        print("✗ 没装 higgsfield 命令行：npm i -g @higgsfield/cli（装完让用户自己 higgsfield auth login）")
        return False
    print("✓ 命令行：" + (hf_bin() or "（演练）"))
    try:
        ws = cli(["workspace", "status"], dry=dry)
        if not _is_dry(ws):
            w = next((d for d in _walk(ws) if isinstance(d, dict) and d.get("id")), {})
            print(f"✓ 工作区：{w.get('id', '已选')}（套餐 {w.get('plan_type', '?')}）")
        st = cli(["account", "status"], dry=dry)
        if not _is_dry(st):
            plan = next((d.get("subscription_plan_type") for d in _walk(st) if isinstance(d, dict) and d.get("subscription_plan_type")), "?")
            print(f"✓ 余额：{credits_of(st)} 积分（套餐 {plan}）")
    except RuntimeError as e:
        print(f"✗ {e}")
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("check")
    p = sp.add_parser("params"); p.add_argument("model")
    p = sp.add_parser("video"); p.add_argument("--jobs", required=True); p.add_argument("--poll", type=int, default=15); p.add_argument("--force", action="store_true"); p.add_argument("--max", type=int, default=4)
    p = sp.add_parser("image"); p.add_argument("model"); p.add_argument("--prompt", required=True); p.add_argument("--out", required=True); p.add_argument("--ref", action="append", default=[])
    p.add_argument("--aspect"); p.add_argument("--res"); p.add_argument("--n", type=int, default=1); p.add_argument("--param", action="append", default=[])
    p = sp.add_parser("photoshoot"); p.add_argument("mode"); p.add_argument("--prompt", required=True); p.add_argument("--image", action="append", required=True); p.add_argument("--out", required=True)
    p.add_argument("--count", type=int, default=1); p.add_argument("--param", action="append", default=[])
    p = sp.add_parser("audio"); p.add_argument("model"); p.add_argument("--prompt", required=True); p.add_argument("--out", required=True); p.add_argument("--duration", type=float); p.add_argument("--param", action="append", default=[])
    p = sp.add_parser("cost"); p.add_argument("model"); p.add_argument("--prompt", required=True); p.add_argument("--param", action="append", default=[])
    p = sp.add_parser("fetch"); p.add_argument("job_id"); p.add_argument("--out", required=True)
    p = sp.add_parser("ledger"); p.add_argument("--size", type=int, default=20)
    a = ap.parse_args()
    dry = a.dry or DRY
    if a.cmd == "check":
        sys.exit(0 if check(dry=dry) else 1)
    elif a.cmd == "params":
        print(params(a.model, dry=dry))
    elif a.cmd == "video":
        res = run_jobs(C.read_json(C.abspath(a.jobs)), a.poll, a.force, dry=dry, max_parallel=a.max)
        print(json.dumps(res, ensure_ascii=False, indent=1))
    elif a.cmd == "image":
        print("\n".join(image(a.model, a.prompt, a.out, a.ref, a.aspect, a.res, a.n, a.param, dry=dry)))
    elif a.cmd == "photoshoot":
        print("\n".join(photoshoot(a.mode, a.prompt, a.image, a.out, a.count, a.param, dry=dry)))
    elif a.cmd == "audio":
        print("\n".join(audio(a.model, a.prompt, a.out, a.duration, a.param, dry=dry)))
    elif a.cmd == "cost":
        print(cost([a.model, "--prompt", a.prompt] + _kv(a.param), dry=dry))
    elif a.cmd == "fetch":
        print(fetch(a.job_id, a.out, dry=dry))
    elif a.cmd == "ledger":
        for r in ledger(a.size, dry=dry):
            print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()
