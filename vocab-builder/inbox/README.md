# 收件箱

把管理员导出的备份 JSON（`mimi-vocab-backup-YYYY-MM-DD.json`）放进这个目录，
然后回到项目根目录执行：

```bash
PY=/Users/H.Sheng/.workbuddy/binaries/python/envs/default/bin/python
$PY vocab-builder/merge_backup.py vocab-builder/inbox/mimi-vocab-backup-*.json --dry-run
```

确认无误后去掉 `--dry-run` 再跑一次，接着构建、净化、推送。
详见 `工作内容.md` 第七节。
