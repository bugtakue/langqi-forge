#!/bin/sh
# arc.sh — 把任意 agent 提交到 ARC-Bench 评测。
#
# 用法:
#   sh arc.sh submit [题目] [模型] [agent来源]
#   sh arc.sh check  [run-id]           省略时查最近一次提交
#   sh arc.sh pack   [agent来源]        只打包不上传(验证用)
#
# agent来源(也可用 ARC_AGENT 环境变量),必填,三种写法:
#   https://github.com/org/repo                              整个仓库
#   https://github.com/org/repo/tree/分支/子目录              仓库里的某个目录
#   /本地/目录  或  /本地/文件.zip                            本地打包好的
#
# 例:
#   sh arc.sh submit ticketbooking gpt-5.5 https://github.com/octos-org/arc-adapter
#
# 仓库/目录里需要是一个 ARC-Bench 适配包:含 main.py(平台入口)。
# 想自己写适配包,照这个标准参考包来:github.com/octos-org/arc-adapter
#
# 同目录下需要一个文件:
#   account.txt    第一行 ARC-Bench 注册邮箱,第二行密码
#
# 依赖:curl + tar + zip(系统自带);python3 有则用、没有也能跑。

set -e
BASE=http://arc-bench.com/api
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ACCOUNT=${ARC_ACCOUNT:-"$DIR/account.txt"}
ZIP=${ARC_ZIP:-"$DIR/agent-bundle.zip"}
JAR="$DIR/.arc-cookies"

login() {
  EMAIL=$(sed -n '1p' "$ACCOUNT" | tr -d '[:space:]')
  PASS=$(sed -n '2p' "$ACCOUNT" | tr -d '[:space:]')
  [ -n "$EMAIL" ] && [ -n "$PASS" ] || { echo "account.txt 需要两行:邮箱、密码"; exit 1; }
  curl -fsS -c "$JAR" -H 'Content-Type: application/json' \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" "$BASE/auth/login" >/dev/null
}

json_id() { sed -n 's/.*"id":"\([0-9a-fA-F]*\)".*/\1/p' | head -1; }

pretty() {
  if command -v python3 >/dev/null 2>&1; then python3 -m json.tool; else cat; fi
}

# 把 GitHub 链接/org缩写 拆成 "org/repo 分支 子目录"
parse_github() {
  u=${1#https://}; u=${u#http://}; u=${u#github.com/}; u=${u%.git}
  case "$u" in
    */tree/*)
      repo=${u%%/tree/*}; rest=${u#*/tree/}
      branch=${rest%%/*}; sub=${rest#*/}; [ "$sub" = "$rest" ] && sub=
      ;;
    *) repo=$u; branch=main; sub= ;;
  esac
  echo "$repo $branch $sub"
}

# $1=agent来源;把适配包打进 $ZIP
pack_agent() {
  src=$1
  case "$src" in
    *.zip)
      [ -f "$src" ] || { echo "找不到 $src"; exit 1; }
      [ "$src" != "$ZIP" ] && cp "$src" "$ZIP"
      echo "[$(date +%H:%M:%S)] using zip: $src"
      return ;;
  esac
  if [ -d "$src" ]; then
    [ -f "$src/main.py" ] || { echo "$src 里没有 main.py,不是 ARC-Bench 适配包"; exit 1; }
    (cd "$src" && zip -qr "$ZIP" . -x '.*' '*__pycache__*')
    echo "[$(date +%H:%M:%S)] packed from local dir: $src"
    return
  fi
  if [ -z "$src" ]; then
    echo "缺少 agent 来源。例:"
    echo "  sh $0 submit ticketbooking gpt-5.5 https://github.com/octos-org/arc-adapter"
    echo "来源可以是 GitHub 链接(可带 /tree/分支/子目录)、本地目录或本地 zip。"
    exit 1
  fi
  set -- $(parse_github "$src"); repo=$1; branch=$2; sub=$3
  echo "[$(date +%H:%M:%S)] fetching github.com/$repo (branch $branch) ..."
  TMP=$(mktemp -d)
  curl -fsSL "https://codeload.github.com/$repo/tar.gz/refs/heads/$branch" \
    | tar -xz -C "$TMP" 2>/dev/null \
    || { branch=master
         curl -fsSL "https://codeload.github.com/$repo/tar.gz/refs/heads/master" \
           | tar -xz -C "$TMP"; }
  ROOT=$(find "$TMP" -maxdepth 1 -mindepth 1 -type d | head -1)
  if [ -n "$sub" ]; then
    SRC=$ROOT/$sub
  else
    # 自动找适配包:优先 bundle/ 或 reference-implementations/,其次任何含 main.py 的浅层目录
    SRC=$(find "$ROOT" -maxdepth 3 -type d -name bundle | head -1)
    [ -n "$SRC" ] || SRC=$(dirname "$(find "$ROOT" -maxdepth 3 -path '*reference-implementations*' -name main.py | head -1)")
    [ "$SRC" != "." ] || SRC=
    [ -n "$SRC" ] || SRC=$(dirname "$(find "$ROOT" -maxdepth 3 -name main.py | head -1)")
  fi
  [ -f "$SRC/main.py" ] || { echo "在 $repo${sub:+/$sub} 里找不到 main.py"; rm -rf "$TMP"; exit 1; }
  (cd "$SRC" && zip -qr "$ZIP" . -x '.*' '*__pycache__*')
  rm -rf "$TMP"
  echo "[$(date +%H:%M:%S)] packed from github.com/$repo${sub:+/$sub}"
}

cmd=${1:-help}
case "$cmd" in
  pack)
    pack_agent "${2:-${ARC_AGENT:-}}"
    ls -l "$ZIP"
    ;;

  submit)
    TASK=${2:-ticketbooking}
    MODEL=${3:-gpt-5.5}
    pack_agent "${4:-${ARC_AGENT:-}}"
    login && echo "[$(date +%H:%M:%S)] logged in"

    snap_id=$(curl -fsS -b "$JAR" \
      -F "requirement_id=$TASK" -F "runtime=python" -F "catalog=playground" \
      -F "agent_source=upload" -F "display_name=ARC Agent" \
      -F "model_name=$MODEL" \
      -F "file=@$ZIP;type=application/zip" \
      "$BASE/submissions" | json_id)
    [ -n "$snap_id" ] || { echo "上传失败"; exit 1; }
    echo "[$(date +%H:%M:%S)] snapshot: $snap_id"

    run_id=$(curl -fsS -b "$JAR" \
      -F "submission_id=$snap_id" -F "requirement_id=$TASK" \
      "$BASE/runs" | json_id)
    [ -n "$run_id" ] || { echo "创建评测任务失败"; exit 1; }
    echo "[$(date +%H:%M:%S)] run: $run_id"

    curl -fsS -b "$JAR" -X POST "$BASE/runs/$run_id/start" >/dev/null
    echo "$run_id" > "$DIR/last-run.txt"
    echo "[$(date +%H:%M:%S)] started: $run_id"
    echo "过一会儿用  sh $0 check  查看结果"
    ;;

  check)
    login
    RID=${2:-$(cat "$DIR/last-run.txt" 2>/dev/null)}
    [ -n "$RID" ] || { echo "没有可查的评测,先 submit 或手动给 run-id"; exit 1; }
    curl -fsS -b "$JAR" "$BASE/runs/$RID" | pretty
    ;;

  *)
    sed -n '2,24p' "$0"
    ;;
esac
exit 0
