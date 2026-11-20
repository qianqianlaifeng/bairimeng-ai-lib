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
    """按 app.js 里 shards('gal') 的顺序读: jimeng_gal -> wf_image -> oi_gal -> gal -> kook_image。"""
    out = []
    for prefix in ("jimeng_gal", "wf_image", "oi_gal", "gal", "kook_image"):
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


# 「日期最新」首屏排序：和 app.js itemDate 保持一致。
# 只认 ① 行尾 time 字段(KOOK 等) ② X/Twitter 雪花 ID ③ wf/oi/h3 编号里写死的日期。
# g-/lp-/hv- 老数据 ID 里的 6 位随机数字不当日期, 否则会被误读成 2035 年假日期霸占前排。
_SNOW_EPOCH = 1288834974657


def _item_date(r):
    import re as _re
    from datetime import datetime as _dt, timezone as _tz
    rid = str(r[0])
    t = str(r[7]) if len(r) > 7 else ""
    if _re.match(r"^\d{4}-\d{2}-\d{2}", t):
        try:
            return _dt.strptime(t[:10], "%Y-%m-%d").replace(tzinfo=_tz.utc).timestamp()
        except Exception:
            pass
    m = _re.search(r"(?:^|[^0-9])((?:1|2)[0-9]{18})(?:[^0-9]|$)", rid)
    if m:
        try:
            d = _dt.fromtimestamp((int(m.group(1)) / 4194304 + _SNOW_EPOCH) / 1000, tz=_tz.utc)
            if 2015 <= d.year <= 2035:
                return d.timestamp()
        except Exception:
            pass
    if _re.match(r"^(wf|kook|oi|h3)-", rid):
        m = _re.search(r"(?:^|[^0-9])(20[0-9]{6})(?:[^0-9]|$)", rid)
        if not m:
            m = _re.search(r"(?:^|[^0-9])([0-9]{2})([0-9]{2})([0-9]{2})(?:[^0-9]|$)", rid)
        if m:
            try:
                if len(m.group(1)) == 8:
                    y, mo, da = int(m.group(1)[:4]), int(m.group(1)[4:6]), int(m.group(1)[6:8])
                else:
                    y, mo, da = 2000 + int(m.group(1)), int(m.group(2)), int(m.group(3))
                if 2015 <= y <= 2035 and 1 <= mo <= 12 and 1 <= da <= 31:
                    return _dt(y, mo, da, tzinfo=_tz.utc).timestamp()
            except Exception:
                pass
    return 0


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

    # 「全部」首屏按发布日期倒序取最新的 ALL_LIMIT 条：
    # 让默认「日期最新」第一眼就是真正的新内容(11 月), 而不是来源顺序里的老 wf 数据(5 月)。
    # 无日期的行排在后面, 并保持原顺序不跳动。
    all_sorted = sorted(rows, key=_item_date, reverse=True)
    with open(os.path.join(DATA, "cp_all.json"), "w", encoding="utf-8") as f:
        json.dump(all_sorted[:ALL_LIMIT], f, ensure_ascii=False, separators=(",", ":"))

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
