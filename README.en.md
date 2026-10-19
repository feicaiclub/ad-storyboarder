<div align="center">

[简体中文](README.md) | **English**

<img src="assets/hero.gif" alt="A spec spot made by Ad Storyboarder: scissor doors swing open, the driver pulls on a helmet, a white car barrel-rolls over the pack trailing white vapor, ROADSTER end card" width="100%" />

# Ad Storyboarder

> *"You bring the idea. It shoots the ad."*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Opus%205.5-d97757)](https://claude.com/claude-code)
[![Higgsfield](https://img.shields.io/badge/Higgsfield-CLI%20%2B%20Skills-111111)](https://higgsfield.ai)
[![Feicai Club](https://img.shields.io/badge/author-Feicai%20Club-2B4CF5)](https://www.feicaiclub.cn)

**Drop Ad Storyboarder into a project folder, and Claude Code will make your commercial.**

Hand it product shots and a concept, and Opus 5.5 takes the director's chair. It pins down the brief, breaks the script into pieces it can generate,<br>
renders them one segment at a time on Higgsfield, has a read-only reviewer check each one, then cuts the spot, reviews it, and delivers.<br>
The 41-second Roadster spot above took it one afternoon. Studio, the screening room, is open source too.

[See it](#see-it) · [Install](#install) · [Where it fits](#where-it-fits-in-your-production) · [How it works](#how-it-works) · [Studio](#studio-the-screening-room) · [Limitations](#limitations) · [About the author](#about-the-author)

</div>

---

## See it

<!-- VIDEO -->

Ad Storyboarder made this 41-second spec spot. Turn the sound on. The whole process is a 20-minute tutorial (in Chinese) on [YouTube](https://www.youtube.com/@feicaiclub) and [Bilibili](https://space.bilibili.com/3546566589679687).

### What I actually did

<img src="assets/timeline.jpg" alt="Two tracks: mine has a few short ticks for handing over the script, answering questions, one nudge and a review session; the Opus 5.5 track runs from noon into the evening" width="100%" />

At 12:05 I handed over the script. By 12:19 I'd answered its questions. At 13:10 I chimed in once: "the car looks fake." At 15:30 it delivered the first cut. I reviewed it in Studio and added a few notes, and at 17:37 it delivered the second. The short ticks up top are me. The long bars below are Opus 5.5.

### Everything else, it did

<table><tr>
<td width="50%"><img src="assets/asset-wall.jpg" alt="Wall of art assets: track, rival cars, helmet, look tests, keyframes" width="100%" /><br/>Art assets: the track, rival cars, helmet, look tests and keyframes. It generated all of them on its own</td>
<td width="50%"><img src="assets/video-wall.jpg" alt="Wall of clips: 34 generated in total" width="100%" /><br/>34 clips in all. It test-shot the opening at 480p first and only rolled out the rest once that passed</td>
</tr></table>

Every image and clip has a prompt behind it, about 16,000 words of English in total, all written shot by shot and sent exactly as written. Across both cuts, the Higgsfield balance went from 1,753 credits to 1.82.

### From the first cut to the second

<table><tr>
<td width="50%"><img src="assets/inspector.jpg" alt="The reviewer's list of six must-fix issues" width="100%" /><br/>Before the first cut shipped, the reviewer flagged six must-fixes, each timecoded to the second</td>
<td width="50%"><img src="assets/two-versions.jpg" alt="Second cut and first cut side by side" width="100%" /><br/>The second cut (left) and the first (right), side by side at the same timecode</td>
</tr></table>

The on-screen text in these images is in Chinese.

---

## Install

### 1. Set up Higgsfield

The easy way: on the [Higgsfield](https://higgsfield.ai) site, open the MCP page, pick the **Claude Code** tab, copy the official setup prompt, and paste it into Claude Code. It installs the CLI, walks you through logging in (one click in the browser), and adds Higgsfield's 8 official Skills.

<details>
<summary>Rather run the commands yourself?</summary>

```sh
npm i -g @higgsfield/cli
higgsfield auth login                      # approve in the browser
higgsfield workspace set <your-workspace>  # skip this and you'll get "No workspace selected"
npx skills add higgsfield-ai/skills
```

</details>

### 2. Get Ad Storyboarder

Ad Storyboarder is just a `.claude` folder. Clone the repo and use it as your project folder:

```sh
git clone https://github.com/feicaiclub/ad-storyboarder.git my-first-spot
cd my-first-spot
claude
```

Already have a project folder? Copy `.claude` into it.

### 3. Start your first spot

Open the project folder in Claude Code and hand over what you have: product shots, your idea and requirements, and the shooting script if there is one. If anyone appears on camera, include their photos.

Before it starts, it runs a self-check: whether Higgsfield is installed, logged in and pointed at a workspace, how many credits you have left, and what's missing on your machine and how to install it. Give it a script and it reads it, takes stock of your references, and asks only what the script doesn't answer. No script, and it nails down the brief first, then pitches you a few concepts to choose from.

### Requirements

- Claude Code running Opus 5.5, the only model I've tested it with.
- A Higgsfield account with credits. I'm on the Ultra plan; both cuts of this spot used about 1,750 credits.
- ffmpeg, Python 3 (numpy, Pillow) and a CJK font. If the spot has dialogue or voiceover, a local whisper for transcription.
- Tested on macOS only. The self-check tells you what's missing, and you can just ask it to install things for you.
- The harness is written in Chinese and talks to you in Chinese by default. Ask it to work in English and it will, though folder and file names stay in Chinese.

---

## Where it fits in your production

This part is for people who make commercials. Ad Storyboarder can take a spot from brief to delivery, or just the stages you need: each of its six Skills owns one stage and works on its own.

| Stage | What it does for you |
|---|---|
| Pitching | Narrowed it down to two or three directions? Shoot a short spec segment for each and walk into the pitch with moving pictures instead of boards |
| Pre-production | Turns the script into a segment sheet (shots, duration, references and sound for each segment), writes a product bible (colors, logo, materials, construction), and logs every client note word for word, with a date, in the brief |
| Shots you can't get or can't afford | Flying cars, VFX, extreme weather, stunts, locations you'll never lock down. Each generated segment is its own video file, so you can cut it into live-action footage, too |
| Product and e-commerce spots | Product shots are a required input. If the color, logo, type or construction doesn't match the product, the shot doesn't make the cut, no matter how good it looks |
| Talent and spokespeople | Identity comes from real photos, used with the person's consent. Every segment is checked against those photos before it goes in, and a face that drifts gets re-rendered |
| Client revisions | Notes get pinned down first: which shot, what's wrong, what it should become, what can't change. Only the affected segments are re-rendered, and the delivery notes keep "what the client flagged" separate from "what we fixed on our own" |
| Multi-platform delivery | One spot, one version per deliverable (16:9, 9:16, different resolutions), and each version clears the gates on its own |
| Budget | Set a credit cap up front. It quotes the cost and reports your balance before spending, and asks before going over. A new approach gets one low-res test segment before it's rolled out, and afterward it reconciles against the transaction log |
| Review and versions | Frame-accurate notes and side-by-side version comparison in Studio. Your team reviews the whole cut once and hands it the full set of notes |

It will only stop to ask you about four things: going over budget, deleting your files, publishing anything, and touching your accounts. Everything else it decides for itself, and when it delivers, it lists the calls it made on your behalf.

---

## How it works

### One director, six end states

`CLAUDE.md` doesn't lay out a pipeline. It lists six things that have to be true when a spot is done: the brief is nailed down, the script is locked, the references are in place, every segment has passed review, the cut has passed the gates, and it's been delivered. Whichever one isn't true yet, with everything it depends on already true, is what it works on next. That lets it skip steps (no voiceover, no VO), go back (the product drifted, so strike the segment and re-render), or jump around (halfway through the edit and missing an insert, it goes back and shoots one).

### The segment sheet is the progress tracker

<img src="assets/segments.jpg" alt="The segment sheet: 14 segments" width="100%" />

The script becomes a segment sheet, basically a shot list grouped into chunks the model renders in one pass. One row per segment, six columns: script, references, generation, review, in the cut, sign-off. The first empty cell is the next task. When your notes point at a segment, its cells get struck out and it goes around again.

<img src="assets/requirements.jpg" alt="The brief: notes recorded word for word" width="100%" />

Everything you ask for goes into the brief word for word, with a date. When it edits and reviews later, it checks its work against what you actually said.

### A read-only reviewer

`agents/inspector.md` is an agent that finds problems and never touches a file. It pulls frames into contact sheets, lines up the product and faces against your references, transcribes, takes measurements, and checks ten things: product, people, glitches, AI tells, text and branding, sound, skin, set and screen direction, reference bleed, and motion. It hands back a timecoded list of issues. It runs before every segment goes into the cut, once more on the full cut, and again after fixes to verify them.

### The gates set a floor, not a ceiling

The measuring tools (`measure`, `qa`, `pick`, `review_seg`, `gate`, `doctor`) only measure and never change anything. It can't call something done without attaching the gate output, and if it didn't measure something, it says so. The rules cover the floor: the product is right, the people are right, nothing glitches, the sound passes, and every credit is accounted for. Prompts are written for each shot and sent exactly as written, with no default style block bolted on. Whatever the models and Higgsfield can do, the rules don't get in the way.

### The edit is the cheapest fix

<img src="assets/rescue-cut.jpg" alt="Saved in the edit: during the second the roof warps, a reaction shot of a side-eye inside the visor covers it" width="100%" />

In the finish-line shot, the roof balloons out of shape for about a second as the car rights itself and drops. Instead of re-rendering, it cuts away at the moment the car hangs upside down over a rival, to a reaction shot of the driver's side-eye inside the visor, and cuts back with the car already on the ground, right on the beat. The reviewer marks the usable stretch of every clip to the second, and the edit only uses those stretches.

### Lessons go back into the harness

`tools/adapters/Higgsfield 实测.md` (field notes on Higgsfield) records only what was observed in real runs, each entry dated. There are 36 in this release. A few of them:

- Use a studio product render as Seedance's product reference and the car comes out looking like CG. If a shot's framing resembles one of those renders, the model lifts its camera angle and studio floor wholesale.
- Upgrading a draft is billed at the 1080p rate, whether you upgrade to 720p or 1080p. For a 720p spot, render at 720p from the start.
- Seedance 2.5 in reference mode with a single set of references (one each of the location, the car's exterior, its rear, and the rival car) moves more convincingly, and keeps people and the car more consistent, than starting from a keyframe.

<img src="assets/before-after.jpg" alt="Before and after: the first batch looked like the official renders; with new references it looks shot on location" width="100%" />

---

## Studio, the screening room

Studio is open source too, in `.claude/tools/studio.py` and `studio.html`, with nothing extra to install. Say "open the screening room" or type `/ad-studio`, and it spins up a local page in Claude Code's built-in browser, right next to the chat.

### Frame-accurate notes

<img src="assets/studio-mark.gif" alt="Paused at 8.8 seconds in Studio, pressing M to drop a marker, typing that the shot doesn't match the one before it, pressing Enter to save" width="100%" />

Space to play, the arrow keys to step frame by frame, M to drop a marker. Type a line, hit Enter, and it's saved with the timecode and a frame grab to `反馈/待处理.md`, the feedback inbox. Review the whole cut, then hand it over in one go. It's far more precise than screenshots and long messages, and faster.

### Side-by-side versions

<img src="assets/studio-compare.gif" alt="The second and first cuts playing side by side; clicking the timeline jumps both to the same point" width="100%" />

New version on the left, old on the right, playing in sync. Click anywhere on the timeline and both jump there, so the differences are obvious at a glance.

### Self-review, progress and the asset library

<img src="assets/studio-pages.gif" alt="The self-review page is the report it writes before delivering; the progress page is the segment sheet, and opening a segment shows its prompt and every take" width="100%" />

The self-review page is the report it writes before delivering: how it handled your notes, what else it changed on its own, and what's still open. The progress page is the segment sheet; open a segment to see its prompt, every take, and the one it picked. The asset library holds the product shots, the people, and the looks it created.

The page binds to localhost only, reads only files inside the project, and writes nothing outside `反馈/`.

---

## What's inside

| | |
|---|---|
| The director's rules | `CLAUDE.md`: the six end states, the tracker, how it questions you, and when it has to check with you |
| 6 Skills | grill (pin down the brief) `/ad-grill` · script `/ad-script` · references `/ad-refs` · generation `/ad-shoot` · edit `/ad-edit` · self-review `/ad-review` |
| Reviewer | `agents/inspector.md`, read-only |
| Screening room | `/ad-studio`: `tools/studio.py` + `tools/studio.html` |
| Measuring tools | `measure` `qa` `pick` `review_seg` `gate` `doctor`, which measure and never modify |
| Backend | `tools/adapters/higgsfield.py`, the only backend, sends prompts exactly as written; the field notes in `Higgsfield 实测.md` sit right next to it |
| Guard | `hooks/secrets-guard.sh` blocks commands that would print login tokens, anything that looks like a key, and commits that contain one |

```
.claude/
├── CLAUDE.md                the director's rules
├── settings.json            wires up the credentials guard
├── skills/                  ad-grill · ad-script · ad-refs · ad-shoot · ad-edit · ad-review · ad-studio
├── agents/inspector.md      the reviewer
├── hooks/secrets-guard.sh   the credentials guard
└── tools/                   measuring tools, assembly, segment jobs, Studio, the Higgsfield backend and field notes
```

Once it's running, it creates these in your project folder:

```
需求文档.md  the brief          脚本/  scripts          素材库/  assets
生成/        renders            剪辑/  edit             final/   deliverables
反馈/        feedback inbox
```

---

## Limitations

- **The idea has to be yours.** In advertising, don't expect the model to bring the concept. It can execute your idea and get it on screen, but the idea itself has to come from you. For this Roadster spot, the two selling points (it flies, and it's fast) and every shot came from me. I worked them out after watching the launch event, wrote them into a creative script with Fable 5.1, and then handed it over.
- **Opus 5.5 is the director, not the author or the screenwriter.** It breaks your script into segments it can generate, drives the models, reviews, and edits. The image, video, music, and sound models it calls are all tools.
- **It needs a sharp eye on your end.** You have to be able to tell when a car looks fake or a cut doesn't match. The continuity break in the first cut was something I caught myself on a second look: the close-up after the driver steps out started from a separately generated keyframe, so his face changed. The fixes for the second cut were my calls, too.
- **Not every shot will land.** Physically complex moves deform (in the second the car rights itself after a barrel roll, the roof balloons), and here the fix was the edit. Faces and products drift. References and review catch most of it, and whatever can't be saved stays out of the cut.
- **It costs money.** Everything renders on Higgsfield and is billed in credits, and the first run of any new approach costs something to scout.
- **It can't hear, and it doesn't see perfectly.** It judges sound from transcripts and measurements and picture from frame grabs and contact sheets. The final call is still yours.
- Tested only on macOS with Claude Code and Opus 5.5. Higgsfield's models and prices change fast, so trust the field notes over this README.

---

## Getting help

If it won't run, or one of the rules doesn't fit your spot, open an issue and say which Skill and which step you got stuck on.

If you'd like to figure this stuff out alongside other people making AI video and building agents, [Feicai Club](https://www.feicaiclub.cn) has a members' community (in Chinese) where people share the workflows they're running and bail each other out. I'm in there every day.

---

## Credits

- Generation runs on [Higgsfield](https://higgsfield.ai)'s official CLI and Skills, with Seedance 2.5 doing most of the video.
- Studio's interface is built on the design system that ships with my Brutally Honest PM 6.0 (毒舌产品经理 6.0).
- The demo is an independent spec ad and isn't affiliated with Tesla.

---

## About the author

**Feicai (废才)**, founder of Feicai Club (废才俱乐部), is an AI builder and educator focused on AI agents, coding, and filmmaking. Every workflow gets proven on real work first; then the reusable parts get open-sourced.

- Author of *驱动 AI 提示词：指令入门与场景应用* (Tsinghua University Press), a book on prompting AI, from writing your first instructions to real-world use
- Creator of the Brutally Honest PM (毒舌产品经理) and Seedance Storyboarder (Seedance 分镜师) series
- Open source: [video-spec-builder](https://github.com/feicaiclub/video-spec-builder) (1,000+ ⭐) · [previz](https://github.com/feicaiclub/previz) · [script breakdown workflow](https://github.com/feicaiclub/script-breakdown-dsh) · [DeepSeek Harness white paper](https://github.com/feicaiclub/deepseek-harness-whitepaper)
- 114 episodes of hands-on AIGC tutorials, and counting

Ad Storyboarder is one piece of my AI video workflow. The rest, from breaking down scripts to shooting AI short dramas to how the Seedance Storyboarder series evolved version by version, lives at [Feicai Club](https://www.feicaiclub.cn) (in Chinese).

| | |
|:---|:---|
| 🌐 Website | [www.feicaiclub.cn](https://www.feicaiclub.cn) |
| 𝕏 | [@zhu185178](https://x.com/zhu185178) |
| ▶️ YouTube | [@feicaiclub](https://www.youtube.com/@feicaiclub) |
| 📺 Bilibili | [废才俱乐部Club](https://space.bilibili.com/3546566589679687) |
| 📕 Xiaohongshu (RED) | [废才俱乐部](https://www.xiaohongshu.com/user/profile/5c6ec0c20000000010032d24) |
| 🎵 Douyin | search for 废才俱乐部 |
| 💬 WeChat Official Account | search for 废才俱乐部 |

## License

Code and docs: MIT. Use it, change it, ship it.

One exception: the person in the demo film, GIFs, and screenshots is the author, and the Roadster's design belongs to Tesla. They're here for demonstration only and aren't covered by the MIT license.

---

<div align="center">

**[video-spec-builder](https://github.com/feicaiclub/video-spec-builder)** turns a vague video idea into a shot-by-shot spec. **[previz](https://github.com/feicaiclub/previz)** shows you a 3D blockout before you generate anything. **Ad Storyboarder** has Claude Code shoot the commercial.

MIT License © [Feicai Club](https://www.feicaiclub.cn)

</div>

---

<div align="center">
<sub>The author's community, and where these workflows come from</sub>

[![Feicai Club: a hands-on community for AI builders. No fluff, just what's useful.](assets/feicai-club.jpg)](https://www.feicaiclub.cn)

</div>
