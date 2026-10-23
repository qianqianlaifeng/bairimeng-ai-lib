#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成「分类首屏包」——让点分类 1~2 秒就能看到图, 而不是等 79 个分片。

背景: 灵感画廊的数据切成 600 条/片(约 292KB, gzip 后 115KB), 国内访问
GitHub Pages 单分片要 3~6 秒。点一个分类时要把 95 个分片全拉一遍才知道
哪些条目属于它, 用户等半分钟还是 0 条。

做法: 按分类各切一个"首屏包"(前 N 条, 完整行格式), 点分类先拉这个包
(单文件, gzip 后 ~30KB), 秒出首屏; 之后照常按需补分片。
另外给「全部」也做一个混合首屏包, 让首页不用等 4 个分片。

输出:
  data/cp_all.json         全部的前 200 条(按原分片顺序: wf -> oi -> gal)
  data/cp_<hash>.json      每个分类的前 N 条
  data/manifest.json       增加 galCatPack / galAllPack 索引

用法: python tools/build_catpack.py [数据目录]
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(HERE), "data")

CAT_LIMIT = 120      # 每个分类首屏包条数
ALL_LIMIT = 120      # 「全部」首屏包条数


def load_shards():
    """按 app.js 里 shards('gal') 的顺序读: wf_image -> oi_gal -> gal -> kook_image。"""
    out = []
    for prefix in ("wf_image", "oi_gal", "gal", "kook_image"):
        i = 0
        while True:
            fp = os.path.join(DATA, "%s_%d.json" % (prefix, i))
            if not os.path.exists(fp):
                break
            with open(fp, encoding="utf-8") as f:
                out.extend(json.load(f))
            i += 1
    return out


def slug(cat):
    return "cp_" + hashlib.md5(cat.encode("utf-8")).hexdigest()[:10]


def main():
    rows = load_shards()
    if not rows:
        sys.exit("!! 没读到 gal 分片, 检查数据目录: %s" % DATA)

    by_cat = {}
    for r in rows:
        cat = r[3] if len(r) > 3 else ""
        by_cat.setdefault(cat, []).append(r)

    pack = {}
    written = 0
    for cat, items in by_cat.items():
        name = slug(cat)
        with open(os.path.join(DATA, name + ".json"), "w", encoding="utf-8") as f:
            json.dump(items[:CAT_LIMIT], f, ensure_ascii=False, separators=(",", ":"))
        pack[cat] = name
        written += 1

    with open(os.path.join(DATA, "cp_all.json"), "w", encoding="utf-8") as f:
        json.dump(rows[:ALL_LIMIT], f, ensure_ascii=False, separators=(",", ":"))

    mp = os.path.join(DATA, "manifest.json")
    with open(mp, encoding="utf-8") as f:
        man = json.load(f)
    man["galCatPack"] = pack
    man["galAllPack"] = "cp_all"
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, separators=(",", ":"))

    sizes = sum(os.path.getsize(os.path.join(DATA, slug(c) + ".json")) for c in by_cat) + \
        os.path.getsize(os.path.join(DATA, "cp_all.json"))
    print("分类首屏包: %d 类 + 全部 | 共 %d 条 | %.2f MB" %
          (written, sum(min(len(v), CAT_LIMIT) for v in by_cat.values()) + min(len(rows), ALL_LIMIT),
           sizes / 1048576))
    top = sorted(by_cat.items(), key=lambda kv: -len(kv[1]))[:5]
    print("  最大几类: " + " | ".join("%s %d" % (k, len(v)) for k, v in top))


if __name__ == "__main__":
    main()
