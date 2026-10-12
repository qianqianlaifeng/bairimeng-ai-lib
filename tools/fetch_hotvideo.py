#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
抓取「热门视频」板块（真视频 + 提示词）。

与图片流是同一个接口，只是带 tab=HotVideo 参数。
结果写到 .cache/hotvideo.json，供 build_gal.py 合并进站点。
"""
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import refresh  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.environ.get("GAL_RAW_DIR") or os.path.join(HERE, ".cache")
OUT = os.path.join(RAW_DIR, "hotvideo.json")
LIMIT = 600


def crawl(token):
    seen, items, last = set(), [], None
    for page in range(10):
        params = {"limit": LIMIT, "tab": "HotVideo"}
        if last is not None:
            params["lastScore"] = last
        d = refresh.curl([refresh.BASE + "/v1/jobs/discovery?" + urllib.parse.urlencode(params),
                          "-H", "Authorization: Bearer " + token], timeout=120)
        if d.get("code") != 200:
            print("  第%d页失败: %s" % (page + 1, str(d)[:120]))
            break
        data = d.get("data") or {}
        lst = data.get("list") or []
        if not lst:
            break
        new = 0
        for x in lst:
            if x.get("id") not in seen:
                seen.add(x["id"])
                items.append(x)
                new += 1
        last = lst[-1].get("score")
        print("  第%d页: +%d (累计 %d)" % (page + 1, new, len(items)), flush=True)
        if not data.get("hasMore"):
            break
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(items, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    nv = sum(1 for x in items if x.get("videoUrl"))
    print("视频抓取完成: %d 条 (含 videoUrl: %d) -> %s" % (len(items), nv, OUT))
    return len(items)


if __name__ == "__main__":
    crawl(refresh.fetch_token())
