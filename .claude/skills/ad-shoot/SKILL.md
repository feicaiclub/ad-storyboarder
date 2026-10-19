---
name: ad-shoot
description: 按分段表一段一段用 Higgsfield 生成，每段过三项质检才算过审；补拍、重出也用。参考齐了之后用。产出：生成/ 里每段选中的文件和质检证据，分段表"生成""过审"两格填满。
---

[任务]
    一段一次生成。怎么拍（模式、时长、挂几张图、提示词怎么写、出几条）按这一段的需要定；这里只管钱和质检。

[前置]
    分段表"参考"全填；Higgsfield 登录有效、余额够（python3 .claude/tools/doctor.py）。

[怎么跑]
    1. 出任务：python3 .claude/tools/segments.py jobs [--ids S01,S03] [--res 1080p] [--model 模型名] [--draft] --out 生成/jobs.json
       它查缺素材，按 Higgsfield 现查的价格估这一批要多少积分、报余额。超出需求文档的花钱上限就停下问。
    2. 跑：bash .claude/tools/bg.sh shoot python3 .claude/tools/segments.py run --jobs 生成/jobs.json
       后台跑，日志在 logs/shoot.out；断了再跑同一条会按登记接着等，不重复提交。
    3. 质检：python3 .claude/tools/review_seg.py S03（每条出抽帧拼图、响度、指标；有台词的出听写）；产品对比表和人脸表用 qa.py crops。
    4. 草稿选中的升高清：python3 .claude/tools/segments.py upgrade S03_v1 --res 1080p --out 生成/upgrade.json，再 run。升级版是 生成/S03_v1_hd.mp4，再过一遍质检。
    5. 花完对账：python3 .claude/tools/adapters/higgsfield.py ledger；估价和实扣差得多的写进 .claude/tools/adapters/Higgsfield 实测.md。

[钱的规矩]
    先一段再全部：一种做法第一次用，先出一段、一条、低清草稿，质检过了再铺开；没过就改做法，不靠多出几条碰运气。
    默认每段出一条；质检没过才重出或多出几条。
    草稿（480p）便宜，升级按目标分辨率全价收、画面不变（实测）：草稿用来看做法对不对，选中的再升级；只出一条的直接出目标分辨率。

[质检（每段必过）]
    抽帧看产品、脸、手、虚影、闪烁（qa.py sheet）；产品对比表：这段里产品最清楚的几帧和产品图并排（颜色、logo、字、结构、比例）；有人出镜的人脸表：和他的照片或他确认过的定稿图并排；有台词或旁白的听写一字不差。
    运动量：pick.py takes 报每条的单镜头运动量（可加 --ref 参考片一起报）；明显低于参考片或整片其他段的，当"画面不动"处理：不升级、不入片，改做法重出。
    imperfections 里写了的效果（光晕、运动模糊、虚焦）是设计如此，不算崩坏；没写的算。
    参考图里的背景、机位被整张搬进画面的，算崩坏。

[补拍]
    要补的段写进补拍表（和分段表同格式）；时长不足模型下限的出下限再剪。

[门禁]
    分段表每段"过审"打勾前，三项（同一个人、产品还原、无崩坏）都有证据文件放在 生成/：候选 <段>_vK.mp4（旁边同名 .json 是任务登记）、升级版 <段>_vK_hd.mp4、<段>_vK_sheet.jpg、<段>_product.jpg、<段>_faces.jpg（有人出镜才要）、<段>_vK_stt.txt（有台词才要）；选中哪条写在分段表"生成"格里。

[完成标准]
    每段有选中文件和证据；分段表"生成""过审"全填。

[文件结构]
    ad-shoot/
    └── SKILL.md
