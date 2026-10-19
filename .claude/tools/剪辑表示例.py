"""剪辑表示例（给 assemble.py 用；真的剪辑表放 剪辑/剪辑表.py，竖版另写就叫 剪辑表_竖版.py）。画面按顺序首尾相接；额外音轨按落点摆；SUBS 只用来算旁白时段（压配乐），不烧字幕。

整片开关：LOOK = "none"（默认，不加处理）| "hero"（广告：轻去噪、柔和压高光、细颗粒；不柔化、不动饱和度）| "film"（胶片感：柔化、降饱和、暗角）| "clean" | 自定义 ffmpeg 滤镜串；
        GRAIN 颗粒强度（hero 默认 5，0 不加）；TARGET_I 成片响度（必填，按需求文档的平台定，如抖音、YouTube、B 站 -14）；
        SIZE、FRAME 画幅（SIZE 如 "1920x1080"、竖版 "1080x1920"，不写就跟第一条视频素材走；FRAME "16:9" 放进 16:9 画框上下留黑，"none" 原画幅）；DUCK_DB 旁白时配乐让多少；
        CARD_BG、CARD_FG 品牌卡的底色和字色。都按需求文档定。
V 里一条：dict(src=路径或 "BLACK"/"WHITE"/"TITLE:文字|副标题"/"CARD:logo 路径|slogan|小字" 或 .png（静态图，zoom=推镜比例）, in=秒, out=秒,
            grade="night2|day|warm2|cool2|call|none"（预设调色，想要别的写 fx=任意 ffmpeg 滤镜串）, matte=False（这一段不走 LOOK）,
            a=原声音量(0 不要), clarity=False（原声不走人声链）, fi/fo=淡入淡出秒, fcolor="white"（淡入淡出的颜色）, freeze=定格秒,
            crop=(左,上,宽比例), delogo=[(左,上,宽,高)], live=True/False（强制按生成画面或图文处理）, rev=("room"|"courtyard"|"hall", 湿声 dB), id=备注)
A 里一条：dict(src=路径, at=("V", 第几条, 偏移秒), in=源入点, dur=时长, gain=dB, fi/fo, loop=True,
            kind="music|amb|sfx|voice", norm=目标 LUFS(None 不归一), clarity=True, raw=True（不走柔化链，音乐要亮的时候用）,
            duck=True(旁白时让路), hits=[(偏移, dB), ...](同一样本落多次), env=[(秒, dB), ...](包络，把最强的一拍钉在产品时刻), rev=(空间, 湿声 dB))
"""
LOOK = "none"
V, A, SUBS, DUCK_EXTRA = [], [], [], []
DUCK_DB = -8.0      # 旁白时配乐让多少
TARGET_I = None     # 成片响度，必填：按需求文档的平台定，如 -14；不填总装不跑（或命令行 --target）
SIZE, FRAME = None, "none"   # 画幅：SIZE 不写就跟第一条视频素材走；FRAME "16:9" 留黑边，"none" 原画幅
GEN, BED, MU, FO, VO = "生成/", "剪辑/声音床/", "剪辑/配乐/", "剪辑/音效/", "剪辑/旁白/"


def v(src, i, o, **kw):
    V.append(dict(src=src, **{"in": i, "out": o}, **kw)); return len(V) - 1


def a(src, at, **kw):
    A.append(dict(src=src, at=at, **kw))


def sub(idx, s, e, text):
    SUBS.append(("V", idx, s, e, text))


def bed(name, at, dur, gain=0.0, fi=0.8, fo=1.0):
    a(BED + name + ".wav", at, dur=dur, loop=True, kind="amb", norm=-42, gain=gain, fi=fi, fo=fo)


def sfx(name, at, gain=0.0, **kw):
    a(FO + name + ".wav", at, kind="sfx", norm=-22, gain=gain, **kw)


# ---------------- 示例（虚构）：一条 30 秒香水广告的写法（VAUNE 是虚构品牌）。写真内容时删掉。
# TARGET_I, SIZE = -14, "1920x1080"
# x = v(GEN + "S01_v2_hd.mp4", 0.6, 2.4, a=0.6, id="钩子：黑里一道光")                      # 开头三秒内就有画面变化
# a(MU + "sel_main.wav", ("V", x, 0), dur=29.5, kind="music", norm=-18, fi=0.3, fo=1.2, duck=True,
#   env=[(0, -6), (8.8, -2), (9.6, 0), (12.5, -3), (29.5, -8)])                                 # 最强的一拍落在 9.6 秒：光扫到标签
# x = v(GEN + "S02_v1_hd.mp4", 1.0, 3.2, a=0.5, id="她在暗处转身")
# bed("studio_black", ("V", x, 0), dur=6.0, fi=0.5)
# x = v(GEN + "S03_v2_hd.mp4", 0.4, 4.0, a=0.0, matte=False, id="产品时刻：光扫过瓶身")      # 产品段不走处理链也行，以产品对比表为准
# sfx("光扫过_气声", ("V", x, 0.2), gain=-3)
# sfx("玻璃_共鸣", ("V", x, 2.9), gain=-6)
# x = v(GEN + "S05_v1_hd.mp4", 0.8, 3.6, a=0.7, id="天台：喷在手腕")
# bed("rooftop_dusk", ("V", x, 0), dur=6.5, fi=0.6)
# x = v(GEN + "S06_v3_hd.mp4", 0.5, 2.6, a=0.5, id="闭眼，笑")
# x = v("CARD:素材库/产品/logo.png|夜里的味道|VAUNE EAU DE PARFUM", 0, 2.6, fi=0.4, id="品牌卡")
