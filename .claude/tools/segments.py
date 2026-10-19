#!/usr/bin/env python3
"""分段表 → 任务。分段表是 markdown（进度表 + 每段一个 json 块）；这里读 json 块交给适配拼成任务（提示词原样发出），读进度表报"现在到哪了"。
  python3 .claude/tools/segments.py list    [--file 脚本/分段表.md]
  python3 .claude/tools/segments.py status  [--file 脚本/分段表.md]               从表里数"现在到哪了"（按表头认列，改了列顺序也不会算错）
  python3 .claude/tools/segments.py jobs    [--ids S01,S02] [--res 1080p] [--model 模型名] [--n 1] [--draft] --out 生成/jobs.json [--no-estimate]
                                            查缺素材、按 Higgsfield 现查的价格估这一批、报余额；--draft 时按低清草稿出（模型支持才有），--res 记成升级的目标
  python3 .claude/tools/segments.py upgrade S03_v2 S05_v1 [--res 1080p] --out 生成/upgrade.json    选中的草稿升到目标分辨率（输出 生成/<段>_vK_hd.mp4）
  python3 .claude/tools/segments.py run     --jobs 生成/jobs.json [--poll 15] [--max 4]          提交、轮询、下载；能续跑
所有命令可加 --adapter（默认 higgsfield，在 tools/adapters/ 里）。

每段 json 块的字段（写法见 skills/ad-script/templates/分段表.md 的示例）：
  id ✓          段号，S01、S02…
  dur ✓         秒，整数，在模型的时长范围内
  shots ✓       [{at, text, lines}]：段内每个镜头从第几秒开始、画面写什么；lines 是台词 [{speaker, text, vo, delivery}]（vo=true 画外音）
  beat          这段在片子里的作用，给人看的
  mode          t2v 纯文字 / first_frame 首帧 / first_last 首尾帧 / ref 参考。不写：有 refs 就是 ref，没有就是 t2v
  model、res    这段单独指定模型或分辨率；不写就用命令行给的
  ratio         画幅：16:9、9:16、1:1、4:3、3:4、21:9
  refs          [{file, role, note}]。role：product 产品、identity 人物、location 场景、plate 某机位背景、prop 道具、frame 构图参考、look 质感参考；note 原样进提示词
  first_frame、last_frame   首帧、尾帧图的路径（或任务号）
  video_refs    [{file, note}]，参考视频（比如参考片剪出的镜头），note 写要它怎么用
  audio_refs    [{file, note}]
  cast          出镜的人，列名字
  camera        机位、镜头、运镜、光（原样进提示词）
  sound         现场声（原样进提示词；不写就不提）
  music         false 才加 "No music."；不写不加
  voices        false 且没台词才加 "No voices, no dialogue."；不写不加
  prompt        直接写整段提示词：原样发，连参考说明和自动句都不加
  params        {参数名: 值}，原样透传给命令行，覆盖适配给的默认值，值写 null 就去掉这个参数
  generate_audio   默认 true；整段要静音时写 false
  imperfections 故意的效果和瑕疵，审片员据此标"设计如此"
  rules         这一段写死的规矩（谁朝哪边、产品哪面朝镜头、不出现什么）
输出命名：候选 生成/<段>_vK.mp4（单条也是 _v1），草稿升级后 生成/<段>_vK_hd.mp4；证据脚本和放映室都按这个认。"""
import argparse, importlib, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

COLS = ["脚本", "参考", "生成", "过审", "入片", "验收"]


def load(path):
    p = C.abspath(path)
    if not os.path.exists(p):
        raise SystemExit(f"找不到分段表：{path}")
    text = open(p, encoding="utf-8").read()
    segs = []
    for block in re.findall(r"```json\s*(\{.*?\})\s*```", text, re.S):
        try:
            segs.append(json.loads(block))
        except json.JSONDecodeError as e:
            raise SystemExit(f"分段表里有一段 json 写错了：{e}\n{block[:200]}")
    return [s for s in segs if not str(s.get("id", "")).startswith("示例")]


def table(path):
    """进度表：按表头认列。返回 (表头, [每行的 dict])；示例行和分隔行跳过。"""
    text = open(C.abspath(path), encoding="utf-8").read()
    header, rows = None, []
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            if header and rows:
                break  # 只读第一张以"段"开头的表
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            if cells and cells[0] == "段":
                header = cells
            continue
        if not cells[0] or set(cells[0]) <= set("-: ") or cells[0].startswith("示例"):
            continue
        rows.append(dict(zip(header, cells + [""] * (len(header) - len(cells)))))
    return header, rows


def filled(v):
    return v.strip() not in ("", "○", "-") and "✗" not in v  # 带 ✗ 的格子是被反馈划掉的，不算


def adapter(name):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "adapters"))
    return importlib.import_module(name)


def report_cost(A, jobs, no_estimate=False):
    secs = sum(j["duration"] * (1 if j.get("single") else j.get("n", 1)) for j in jobs)
    print(f"{len(jobs)} 条任务，合计 {secs} 秒视频")
    if no_estimate or not hasattr(A, "estimate"):
        return
    total, unknown, rows = A.estimate(jobs)
    for jid, model, res, dur, n, v in rows:
        print(f"  {jid:<10} {model:<14} {res:<6} {dur:>3}s ×{n}  {'估不出' if v is None else f'{v:g} 积分/条'}")
    bal = A.balance() if hasattr(A, "balance") else None
    print(f"估算 {total:g} 积分" + (f"（另有 {unknown} 条估不出价，第一次先跑一条看流水）" if unknown else "") + (f"；余额 {bal:g} 积分" if bal is not None else ""))
    if bal is not None and total > bal:
        print("⚠ 余额不够：先出最关键的段（--ids），或请用户充值")


def main():
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    for c in ("list", "status"):
        p = sp.add_parser(c); p.add_argument("--file", default=C.SEG)
    p = sp.add_parser("jobs"); p.add_argument("--file", default=C.SEG); p.add_argument("--adapter", default="higgsfield"); p.add_argument("--ids")
    p.add_argument("--res", default="1080p"); p.add_argument("--model"); p.add_argument("--n", type=int, default=1); p.add_argument("--draft", action="store_true")
    p.add_argument("--out", required=True); p.add_argument("--no-estimate", action="store_true")
    p = sp.add_parser("upgrade"); p.add_argument("cands", nargs="+"); p.add_argument("--adapter", default="higgsfield"); p.add_argument("--res", help="升到多少；不给就用出草稿时定的目标分辨率")
    p.add_argument("--out", required=True); p.add_argument("--no-estimate", action="store_true")
    p = sp.add_parser("run"); p.add_argument("--adapter", default="higgsfield"); p.add_argument("--jobs", required=True); p.add_argument("--poll", type=int, default=15); p.add_argument("--max", type=int, default=4)
    a = ap.parse_args()
    if a.cmd == "list":
        for s in load(a.file):
            refs = s.get("refs", [])
            roles = ",".join(sorted({r.get("role", "?") for r in refs})) or "-"
            print(f"{s['id']:<6} {s.get('beat', ''):<8} {s.get('dur', '?'):>3}s {s.get('mode', 'ref' if refs else 't2v'):<11} "
                  f"参考 {len(refs)}（{roles}）  镜头 {len(s.get('shots', []))}  台词 {sum(len(sh.get('lines', [])) for sh in s.get('shots', []))}"
                  + (f"  {s['model']}" if s.get("model") else "") + (f" {s['res']}" if s.get("res") else ""))
    elif a.cmd == "status":
        header, rows = table(a.file)
        if not header:
            sys.exit("分段表里没找到进度表（第一列表头要叫'段'）")
        miss = [c for c in COLS if c not in header]
        if miss:
            print(f"⚠ 进度表缺这几列：{miss}")
        counts = {c: sum(1 for r in rows if filled(r.get(c, ""))) for c in COLS}
        cand = sum(int(m.group(1)) if (m := re.search(r"候选\s*(\d+)", r.get("生成", ""))) else (1 if filled(r.get("生成", "")) else 0) for r in rows)
        print(f"{len(rows)} 段 · " + " · ".join(f"{c} {counts[c]}" + (f"（候选 {cand}）" if c == "生成" else "") for c in COLS))
    elif a.cmd == "jobs":
        A = adapter(a.adapter); want = set(a.ids.split(",")) if a.ids else None
        segs = [s for s in load(a.file) if not want or s["id"] in want]
        if want and len(segs) < len(want):
            print(f"⚠ 分段表里没有：{sorted(want - {s['id'] for s in segs})}")
        try:
            jobs = [A.build_job(s, a.res, n=a.n, model=a.model, draft=a.draft) for s in segs]
        except ValueError as e:
            sys.exit(f"分段表要改：{e}")
        missing = sorted({p for j in jobs for p in A.job_inputs(j) if not os.path.exists(C.abspath(p))})
        if missing:
            sys.exit(f"缺素材：{missing}")
        C.write_json(C.abspath(a.out), jobs)
        report_cost(A, jobs, a.no_estimate)
        print(f"→ {a.out}")
    elif a.cmd == "upgrade":
        A = adapter(a.adapter); jobs = []
        for c in a.cands:
            m = re.fullmatch(r"(.+)_v(\d+)", c)
            if not m:
                sys.exit(f"{c} 不是候选名（写成 S03_v2 这样）")
            reg = C.abspath(f"{C.GEN}/{c}.mp4.json")
            if not os.path.exists(reg):
                sys.exit(f"没有 {C.GEN}/{c}.mp4.json：这条不是适配跑出来的，或登记丢了，没法升级")
            r = C.read_json(reg)
            if r.get("status") != "done" or not r.get("job_id"):
                sys.exit(f"{c} 的任务还没完成（{r.get('status')}），等它出完再升级")
            j = dict(r["job"])
            if not j.get("draft"):
                print(f"⚠ {c} 不是草稿出的，升级不一定支持；照样生成任务，报错就改成直接出高清候选")
            j.update(resolution=a.res or j.get("target_res") or "1080p", draft=False, upgrade_from=r["job_id"], single=True, n=1, out=f"{C.GEN}/{c}_hd.mp4")
            jobs.append(j)
        C.write_json(C.abspath(a.out), jobs)
        report_cost(A, jobs, a.no_estimate)
        print(f"→ {a.out}（升级版输出 {', '.join(j['out'] for j in jobs)}）")
    else:
        A = adapter(a.adapter)
        res = A.run_jobs(C.read_json(C.abspath(a.jobs)), a.poll, max_parallel=a.max)
        print(json.dumps(res, ensure_ascii=False, indent=1))
        bad = [r for r in res if r["status"] not in ("done", "exists", "dry")]
        if bad:
            print(f"⚠ {len(bad)} 条没完成：{[(r['id'], r['status']) for r in bad]}（still_pending 的再跑同一条命令会接着等）")


if __name__ == "__main__":
    main()
