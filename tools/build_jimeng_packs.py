# -*- coding: utf-8 -*-
"""只重建「即梦」相关的分类首屏包，不动其他分类。

为什么单独一个脚本：
  build_catpack.py 会整体覆盖 manifest.galCatPack，连 reorg 加进去的「人像全部」
  一起丢掉；而每 2 小时跑一次的即梦同步只需要更新即梦自己的几个包。
  这里按分类重切 jimeng-* 的 cp_*.json，并保证 jimeng_portrait 索引在位，
  其他分类的包和索引原样保留。

用法: python tools/build_jimeng_packs.py [数据目录]
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(HERE), "data")
CAT_LIMIT = 150     # 即梦单个分类条数不多, 一次给够

# 首屏包瘦身（与 build_catpack.py 同口径）：正文留 90 字摘要(带 …)，
# 点开卡片时前端按 id 去大分片取全文。注意保留第 9/10 字段(人像/性别)。
EXCERPT_MAX = 90
TITLE_MAX = 40


def slim(r):
    row = list(r[:8])
    row[1] = (r[1] or "")[:TITLE_MAX]
    body = (r[2] or "")
    row[2] = body[:EXCERPT_MAX] + ("…" if len(body) > EXCERPT_MAX else "")
    if len(r) > 8:
        row.append(r[8])
    if len(r) > 9:
        row.append(r[9])
    return row


def slug(cat):
    return "cp_" + hashlib.md5(cat.encode("utf-8")).hexdigest()[:10]


def main():
    rows = []
    i = 0
    while True:
        fp = os.path.join(DATA, "jimeng_gal_%d.json" % i)
        if not os.path.exists(fp):
            break
        rows.extend(json.load(open(fp, encoding="utf-8")))
        i += 1
    if not rows:
        print("无 jimeng 分片, 跳过")
        return

    by_cat = {}
    for r in rows:
        by_cat.setdefault(r[3], []).append(r)

    mp = os.path.join(DATA, "manifest.json")
    man = json.load(open(mp, encoding="utf-8"))
    pack = man.setdefault("galCatPack", {})

    written = 0
    for cat, items in by_cat.items():
        name = slug(cat)
        with open(os.path.join(DATA, name + ".json"), "w", encoding="utf-8") as f:
            json.dump([slim(r) for r in items[:CAT_LIMIT]], f, ensure_ascii=False, separators=(",", ":"))
        pack[cat] = name
        written += 1

    # 人像包由 build_jimeng.py 产出，这里只确保索引在
    if os.path.exists(os.path.join(DATA, "jimeng_portrait.json")):
        man["jimengPortraitPack"] = "jimeng_portrait"

    with open(mp, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, separators=(",", ":"))

    pn = sum(1 for r in rows if len(r) > 8 and r[8])
    print("即梦分类首屏包: %d 个 / %d 条 (人像 %d 条)" % (written, len(rows), pn))


if __name__ == "__main__":
    main()
