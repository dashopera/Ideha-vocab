#!/usr/bin/env python3
"""
Merge an admin-exported backup JSON back into the source unit files.

  The admin console edits words in the browser; those edits live in that one
  browser's localStorage only. To make them official, the admin exports a
  backup (⚙ 管理 → 数据导出 / 导入 → 导出 JSON) and this script folds the
  `units` section back into `vocab-builder/units/TextN.json`.

Usage:
    python3 merge_backup.py <backup.json> [<more.json> ...] [options]

Options:
    --prune      actually delete words that are absent from the backup
                 (default: keep them and only report)
    --dry-run    show what would change, write nothing
    --no-backup  skip writing .bak copies of the unit files

Notes:
    * Words are matched by their headword (lowercased).
    * Text fields (pos/ph/def/note/ex) from the backup win.
    * `prompt` (illustration hint) is kept from the source when the backup
      does not carry one, so existing artwork descriptions survive.
    * `img` is never written - images are resolved at build time from
      images/<Unit>/NN_slug.png.
    * New words have no illustration yet; the script prints the exact
      filenames to create.
"""
import glob
import json
import os
import shutil
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
UNITS_DIR = os.path.join(ROOT, "units")
IMG_DIR = os.path.join(ROOT, "images")
BAK_DIR = os.path.join(UNITS_DIR, ".bak")

TEXT_FIELDS = ["w", "pos", "ph", "def", "note", "ex"]
WORD_ORDER = ["w", "pos", "ph", "def", "note", "ex", "prompt"]


def slugify(word):
    return word.replace("-", "_").replace(" ", "_").replace("/", "_").lower()


def load(path):
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        sys.exit("cannot read %s: %s" % (path, e))
    if not isinstance(d, dict) or d.get("app") != "mimi-vocab":
        sys.exit("%s is not a mimi-vocab backup (missing app='mimi-vocab')" % path)
    if not d.get("units"):
        sys.exit("%s contains no word-table changes "
                 "(units is empty - the admin never edited the word list "
                 "on that device)" % path)
    return d


def clean_word(w):
    """Keep only real data fields; drop img/_href and blanks."""
    out = {}
    for k in WORD_ORDER:
        v = w.get(k, "")
        if isinstance(v, str):
            v = v.strip()
        if v:
            out[k] = v
    if "w" in out:
        out["w"] = out["w"].lower()
    return out


def find_image(uid, word):
    cands = sorted(glob.glob(os.path.join(IMG_DIR, uid, "*_%s.png" % slugify(word))))
    return cands[0] if cands else None


def merge_unit(src_path, b_unit, prune, do_backup, dry):
    uid = b_unit.get("id", "").strip()
    if not uid:
        return None, "backup unit without id - skipped"

    b_words = [clean_word(w) for w in b_unit.get("words", []) if w.get("w")]
    b_map = {w["w"]: w for w in b_words}

    exists = os.path.exists(src_path)
    cur = json.load(open(src_path, encoding="utf-8")) if exists else {
        "id": uid, "title": b_unit.get("title", uid), "note": "", "words": []}
    cur_map = {w["w"].lower(): w for w in cur["words"]}

    added, changed, removed = [], [], []

    # --- apply backup order & values -------------------------------------
    merged = []
    for w in b_words:
        old = cur_map.get(w["w"])
        if old is None:
            added.append(w["w"])
            merged.append(w)
            continue
        new = dict(old)
        for k in TEXT_FIELDS:
            if w.get(k):
                new[k] = w[k]
            elif k in new and k != "w":
                pass          # keep the source value when the backup is blank
        if not w.get("prompt") and old.get("prompt"):
            new["prompt"] = old["prompt"]      # artwork hint must survive
        elif w.get("prompt"):
            new["prompt"] = w["prompt"]
        new.pop("img", None)
        new.pop("_href", None)
        if new != old:
            changed.append(w["w"])
        merged.append(new)

    # --- words present locally but gone from the backup -------------------
    for w in cur["words"]:
        key = w["w"].lower()
        if key not in b_map:
            removed.append(w["w"])
            if not prune:
                merged.append(w)

    # --- scalar fields ----------------------------------------------------
    if b_unit.get("title"):
        cur["title"] = b_unit["title"]
    if b_unit.get("note"):
        cur["note"] = b_unit["note"]
    cur["words"] = merged

    if not dry and (added or changed or removed or not exists):
        if exists and do_backup:
            os.makedirs(BAK_DIR, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.copy2(src_path, os.path.join(
                BAK_DIR, "%s.%s.json" % (uid, stamp)))
        json.dump(cur, open(src_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        open(src_path, "a", encoding="utf-8").write("\n")

    missing_img = [w["w"] for w in merged if not find_image(uid, w["w"])]
    return {
        "id": uid,
        "title": cur.get("title", uid),
        "new_file": not exists,
        "added": added,
        "changed": changed,
        "removed": removed,
        "pruned": bool(prune),
        "total": len(merged),
        "missing_img": missing_img,
        "path": src_path,
    }, None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    prune = "--prune" in sys.argv
    dry = "--dry-run" in sys.argv
    do_backup = "--no-backup" not in sys.argv

    if not args:
        sys.exit(__doc__)

    print("=== 读取备份 ===")
    backups = []
    for p in args:
        d = load(p)
        backups.append(d)
        print("  %s" % os.path.basename(p))
        print("    导出时间: %s" % d.get("exportedAt", "?"))
        print("    账号: %s" % ", ".join(d.get("users", {}).keys()) or "—")
        print("    单元: %s" % ", ".join(
            "%s(%d词)" % (u.get("id", "?"), len(u.get("words", [])))
            for u in d["units"]))

    # later files win when the same unit appears twice
    units = {}
    for d in backups:
        for u in d["units"]:
            units[u["id"]] = u

    print("\n=== 合并结果 %s===" % ("（演练，未写入）" if dry else ""))
    reports, errs = [], []
    for uid, u in sorted(units.items()):
        rep, err = merge_unit(os.path.join(UNITS_DIR, "%s.json" % uid),
                              u, prune, do_backup, dry)
        if err:
            errs.append(err)
        else:
            reports.append(rep)

    for e in errs:
        print("  ! " + e)

    for r in reports:
        print("\n  [%s] %s  →  %d 词" % (r["id"], r["title"], r["total"]))
        print("     文件: %s%s" % (os.path.relpath(r["path"], ROOT),
                                   "（新建）" if r["new_file"] else ""))
        if r["added"]:
            print("     + 新增 %d: %s" % (len(r["added"]), ", ".join(r["added"])))
        if r["changed"]:
            print("     ~ 修改 %d: %s" % (len(r["changed"]), ", ".join(r["changed"])))
        if r["removed"]:
            verb = "已删除" if r["pruned"] else "备份中已删（本地保留，加 --prune 才真删）"
            print("     - %s %d: %s" % (verb, len(r["removed"]), ", ".join(r["removed"])))
        if not (r["added"] or r["changed"] or r["removed"] or r["new_file"]):
            print("     = 与现有源数据一致，无变化")

    # ---- illustrations -------------------------------------------------
    need = [(r["id"], w) for r in reports for w in r["missing_img"]]
    if need:
        print("\n=== 缺少插画的词（%d 个）===" % len(need))
        print("  这些词仍可正常拼写练习，只是卡片上没有图。")
        for uid, w in need:
            print("    images/%s/NN_%s.png   ← %s" % (uid, slugify(w), w))
        print("\n  补齐方式：把上表发给我，我按固定风格生成插画并放进目录，再重新构建。")

    print("\n=== 下一步 ===")
    if dry:
        print("  演练结束。确认无误后去掉 --dry-run 再跑一次。")
        return
    print("  PY=/Users/H.Sheng/.workbuddy/binaries/python/envs/default/bin/python")
    print("  1. $PY vocab-builder/build.py         # 重建成品")
    print("  2. $PY vocab-builder/sanitize.py      # 净化 + 一致性自检")
    print("  3. git add -A && git commit -m '词表更新' && git push")
    print("  推送后 GitHub Pages 约 1 分钟生效。")
    print("\n  提示：线上生效后，请在管理后台点一次「还原内置词表」，")
    print("        否则本机覆盖层会一直压住后续来自仓库的更新。")


if __name__ == "__main__":
    main()
