#!/bin/bash
# 凭证守门（不依赖 jq）。三件事：
# 一、Higgsfield 的登录凭证只归它的命令行管：拦 `higgsfield / hf / higgs auth token`（会把令牌打出来），拦任何碰 ~/.config/higgsfield 的命令。
# 二、命令里出现像密钥的字符串就拦（密钥不写进命令、日志、记录）。
# 三、git commit 时暂存区里有 .env 或像密钥的改动就拦。别的命令一律放行。
INPUT=$(cat 2>/dev/null)
if printf '%s' "$INPUT" | grep -qE '(higgsfield|higgs|(^|[^[:alnum:]_-])hf)[[:space:]]+auth[[:space:]]+token'; then
  echo "拦住了：higgsfield auth token 会把登录令牌打出来。查登录和余额用 python3 .claude/tools/adapters/higgsfield.py check。" >&2
  exit 2
fi
if printf '%s' "$INPUT" | grep -qE '\.config/higgsfield'; then
  echo "拦住了：~/.config/higgsfield 里是 Higgsfield 的登录凭证，只归它的命令行管，不读、不拷、不删。登录、登出请用户自己做。" >&2
  exit 2
fi
KEYPAT='sk-ant-[A-Za-z0-9_-]{8,}|sk-proj-[A-Za-z0-9_-]{8,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[bpsa]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{30,}|eyJ[A-Za-z0-9_-]{30,}\.[A-Za-z0-9_-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----'
if printf '%s' "$INPUT" | grep -qE "$KEYPAT"; then
  echo "拦住了：命令里有像密钥的字符串。密钥不写进命令、文件和日志。" >&2
  exit 2
fi
case "$INPUT" in *"git commit"*) ;; *) exit 0 ;; esac
ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"; cd "$ROOT" || exit 0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
STAGED=$(git diff --cached --name-only 2>/dev/null); [ -z "$STAGED" ] && exit 0
if printf '%s\n' "$STAGED" | grep -E '(^|/)\.env(\.|$)' | grep -vqE '\.env\.(example|sample|template)$'; then
  echo "提交被拦住：.env 在暂存区里。把它加进 .gitignore 再提交。" >&2; exit 2
fi
HIT=$(git diff --cached -U0 2>/dev/null | grep -E '^\+' | grep -vE '^\+\+\+' | grep -nE "$KEYPAT" | head -3)
if [ -n "$HIT" ]; then
  echo "提交被拦住：暂存的改动里像是有密钥：" >&2; printf '%s\n' "$HIT" | cut -c1-120 >&2; exit 2
fi
exit 0
