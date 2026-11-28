#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成「首屏包」—— 只装封面和标题，不含完整提示词。

为什么改（2026-11-28）：
  原来的 cp_*.json / cp_all.json 是**整行复制**，把完整提示词一起塞进去。
  首屏 120 条 = 421KB（中位 1992 字/条，最长 1.8 万字）。国内直连 GitHub
  Pages 单请求 1~7 秒，421KB 光首屏数据就要拖好几秒，而首屏其实只需要
  「封面 + 标题 + 分类」。用户反馈"每次打开加载半天"主要就是这一块。

  新版: 首屏行只留
    [id, title(≤40字), '', cat, desc, cover, [], time, portrait, gender]
  body 置空；点开卡片时才按 id 去大分片里取全文（fetchFullBody）。

  体积: 120 条 ≈ 42KB，约为原来的 1/10。

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
TITLE_MAX = 40       # 首屏标题截断长度（卡片上本来就只显示一行）


def load_shards():
    """按 app.js 里 shards('gal') 的顺序读。"""
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


EXCERPT_MAX = 90      # 卡片上只显示 3 行摘要, 90 字足够


def slim(r):
    """首屏行：正文只留一小段摘要，标题截断，其余字段原样（含即梦的 portrait/gender）。

    为什么留摘要而不是全清空：卡片上本来就会显示一段提示词预览，清空的话
    首屏会变成"只有图 + 标题"，看着像数据没加载出来。90 字够 3 行，
    体积仍然很小（120 条 x 90 字 ≈ 11KB，原先是 421KB）。
    """
    row = list(r[:8])
    row[1] = (r[1] or "")[:TITLE_MAX]
    body = (r[2] or "")
    row[2] = body[:EXCERPT_MAX] + ("…" if len(body) > EXCERPT_MAX else "")
    if len(r) > 8:
        row.append(r[8])
    if len(r) > 9:
        row.append(r[9])
    return row


def main():
    rows = load_shards()
    if not rows:
        sys.exit("!! 没读到 gal 分片, 检查数据目录: %s" % DATA)

    by_cat = {}
    for r in rows:
        cat = r[3] if len(r) > 3 else ""
        by_cat.setdefault(cat, []).append(r)

    pack = {}
    wrote = 0
    raw_bytes = 0
    for cat, items in by_cat.items():
        name = slug(cat)
        part = [slim(r) for r in items[:CAT_LIMIT]]
        with open(os.path.join(DATA, name + ".json"), "w", encoding="utf-8") as f:
            json.dump(part, f, ensure_ascii=False, separators=(",", ":"))
        raw_bytes += os.path.getsize(os.path.join(DATA, name + ".json"))
        pack[cat] = name
        wrote += 1

    all_sorted = sorted(rows, key=_item_date, reverse=True)
    head = [slim(r) for r in all_sorted[:ALL_LIMIT]]
    with open(os.path.join(DATA, "cp_all.json"), "w", encoding="utf-8") as f:
        json.dump(head, f, ensure_ascii=False, separators=(",", ":"))
    raw_bytes += os.path.getsize(os.path.join(DATA, "cp_all.json"))

    mp = os.path.join(DATA, "manifest.json")
    with open(mp, encoding="utf-8") as f:
        man = json.load(f)
    man["galCatPack"] = pack
    man["galAllPack"] = "cp_all"
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, separators=(",", ":"))

    print("首屏包: %d 类 + 全部 | %.2f MB (已瘦身: 不含正文)"
          % (wrote, raw_bytes / 1048576))
    print("cp_all 体积: %.0f KB" % (os.path.getsize(os.path.join(DATA, "cp_all.json")) / 1024))


if __name__ == "__main__":
    main()
