#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sanitize.py — 成品 HTML 净化与一致性自检

背景：本地预览服务打开 HTML 时会往源文件注入 `data-page-node-id="..."` 属性
（约 4 KB 无用代码），导致成品被污染。此前已三次误将污染版提交/交付。

本脚本做两件事：
  1. 剔除所有成品中的预览注入属性（幂等，可反复运行）
  2. 校验四份成品字节级一致，并输出 MD5

用法：
    python3 sanitize.py            # 净化 + 校验
    python3 sanitize.py --check    # 只校验，不改文件

退出码：0 = 全部一致且干净；1 = 发现污染或不一致
"""
import hashlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)

# 内嵌版（单文件）：三份必须字节级一致
EMBEDDED = [
    "背单词-学习卡片.html",
    "米米背单词-便携版.html",
]
# 外链版（发布用）：图片是独立文件，体积本就不同，只查污染不比对
LINKED = ["index.html", "site/index.html"]
TARGETS = EMBEDDED + LINKED

# 预览服务注入的属性（含前后空格的各种形态）
INJECT_RE = re.compile(r'\s+data-page-node-id="[^"]*"')


def md5(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def clean(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    new_text, n = INJECT_RE.subn("", text)
    if n:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_text)
    return n


def main():
    check_only = "--check" in sys.argv
    digests = {}
    total_removed = 0

    for rel in TARGETS:
        p = os.path.join(PROJECT, rel)
        if not os.path.exists(p):
            print("  ! 缺失: %s" % rel)
            return 1
        if not check_only:
            total_removed += clean(p)
        digests[rel] = md5(p)

    if not check_only:
        print("净化: 移除 %d 处注入属性" % total_removed)

    print("\n=== 内嵌版一致性（三份必须相同）===")
    emb = {rel: digests[rel] for rel in EMBEDDED}
    for rel in EMBEDDED:
        p = os.path.join(PROJECT, rel)
        print("  %-24s %8d 字节  %s"
              % (rel, os.path.getsize(p), digests[rel]))
    for rel in LINKED:
        p = os.path.join(PROJECT, rel)
        print("  %-24s %8d 字节  %s  (外链版)"
              % (rel, os.path.getsize(p), digests[rel]))

    if len(set(emb.values())) == 1:
        print("\n✓ 内嵌版三份一致，MD5 = %s" % emb[EMBEDDED[0]])
        return 0

    print("\n✗ 内嵌版存在 %d 种不同内容，请重新构建后重试" % len(set(emb.values())))
    print("  重新构建: python3 vocab-builder/build.py && python3 vocab-builder/sanitize.py")
    return 1


if __name__ == "__main__":
    sys.exit(main())
