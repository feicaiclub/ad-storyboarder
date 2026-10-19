#!/bin/bash
# 用法：bash .claude/tools/bg.sh 日志名 命令 参数...   在项目根目录下后台跑，日志在 logs/日志名.out
# 用新会话（setsid）在后台启动长任务：Claude Code 掉线、退出都不会把它一起停掉。进度看 logs/日志名.out 和产出文件。
name="$1"; shift
cd "$(dirname "$0")/../.." || exit 1
mkdir -p logs
nohup python3 -c 'import os, sys; os.setsid(); os.execvp(sys.argv[1], sys.argv[1:])' "$@" > "logs/$name.out" 2>&1 < /dev/null &
echo "已启动 $name（pid $!），日志 logs/$name.out"
