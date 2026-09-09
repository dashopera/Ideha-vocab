#!/bin/sh
# One-shot: merge admin backups -> rebuild -> sanitize -> commit -> push.
#
#   ./sync_from_backup.sh                  # commit message defaults to today's date
#   ./sync_from_backup.sh "新增 Text2 15 词"
#   ./sync_from_backup.sh --no-push "..."  # stop before commit/push (dry-ish)
#
# Backups are read from vocab-builder/inbox/ and archived to inbox/done/ on success.
set -e
cd "$(dirname "$0")/.."

PY=/Users/H.Sheng/.workbuddy/binaries/python/envs/default/bin/python
INBOX=vocab-builder/inbox
NO_PUSH=0
MSG=

for a in "$@"; do
  case "$a" in
    --no-push) NO_PUSH=1 ;;
    *)         MSG="$a" ;;
  esac
done
[ -z "$MSG" ] && MSG="词表更新 $(date '+%Y-%m-%d')"

ls "$INBOX"/*.json >/dev/null 2>&1 || {
  echo "inbox 里没有备份 JSON。先把 mimi-vocab-backup-*.json 放进 $INBOX/"
  exit 1
}

echo "=== 1/4 合并备份 ==="
"$PY" vocab-builder/merge_backup.py "$INBOX"/*.json

echo ""
echo "=== 2/4 构建 ==="
"$PY" vocab-builder/build.py

echo ""
echo "=== 3/4 净化自检 ==="
"$PY" vocab-builder/sanitize.py

if [ "$NO_PUSH" = "1" ]; then
  echo ""
  echo "(--no-push：已停在提交前。确认无误后手动 git commit && git push)"
  exit 0
fi

echo ""
echo "=== 4/4 提交推送 ==="
git add -A
git -c user.name="dashopera" \
    -c user.email="55913052+dashopera@users.noreply.github.com" \
    commit -q -m "$MSG"
GIT_SSH_COMMAND="ssh -o IdentitiesOnly=yes" git push origin main

mkdir -p "$INBOX/done"
mv "$INBOX"/*.json "$INBOX/done"/ 2>/dev/null || true

echo ""
echo "✓ 已推送：$MSG"
echo "  GitHub Pages 约 1 分钟后生效：https://dashopera.github.io/Ideha-vocab/"
