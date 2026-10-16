#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 h3_video_* 分片并入 manifest(幂等)。仿 build_wf.py。
  h3_video_*  -> 「海螺 H3」独立页签(MiniMax H3 视频案例, 尾字段区分视频卡/图卡)
"""
import glob
import json
import os
import re as _re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.environ.get("GAL_OUTDIR") or os.path.join(ROOT, "app", "data")
CACHE = os.environ.get("GAL_RAW_DIR") or os.path.join(ROOT, ".cache")
MANI = os.path.join(DATA, "manifest.json")

SOURCE_LABEL = ["海螺 H3 社区案例", ""]   # 对外中性名


def re_num(p):
    m = _re.search(r"_(\d+)\.json$", p)
    return int(m.group(1)) if m else 0


def load_rows(pattern):
    rows = []
    for f in sorted(glob.glob(os.path.join(DATA, pattern)), key=re_num):
        try:
            rows.extend(json.load(open(f, encoding="utf-8")))
        except Exception:
            pass
    return rows


def nfiles(pattern):
    return len(glob.glob(os.path.join(DATA, pattern)))


def main():
    rows = load_rows("h3_video_*.json")
    if not rows:
        print("[h3] 无 h3 分片, 跳过")
        return

    labels = {}
    rp = os.path.join(CACHE, "h3_raw.json")
    if os.path.exists(rp):
        try:
            labels = (json.load(open(rp, encoding="utf-8")) or {}).get("cats") or {}
        except Exception:
            labels = {}

    m = json.load(open(MANI, encoding="utf-8"))

    # ---- 分类标签 + 分类计数 ----
    ccnt = {}
    for r in rows:
        ccnt[r[3]] = ccnt.get(r[3], 0) + 1
    h3Cats = dict(m.get("h3Cats") or {})
    for k, n in ccnt.items():
        h3Cats[k] = labels.get(k, ["H3 案例", "⚡"])
        m.setdefault("catCounts", {}).setdefault("h3", {})[k] = n
    m["h3Cats"] = h3Cats

    # ---- 计数(绝对赋值, 与 vibeCount 同模式) ----
    n_all = len(rows)
    n_video = sum(1 for r in rows if (r[13] if len(r) > 13 else "video") != "image")
    m["h3Count"] = n_all
    m["h3Video"] = n_video
    m["h3Playable"] = n_video

    # ---- 分片数 ----
    ch = m.setdefault("chunks", {})
    ch["h3_video"] = nfiles("h3_video_*.json")

    # ---- 来源(中性名) ----
    m.setdefault("sources", {})["h3"] = SOURCE_LABEL

    json.dump(m, open(MANI, "w", encoding="utf-8"), ensure_ascii=False)
    print("[h3] manifest: 行 %d (可播 %d) | h3Count=%s | chunks h3_video=%d | cats=%d" %
          (n_all, n_video, m["h3Count"], ch["h3_video"], len(h3Cats)))


if __name__ == "__main__":
    main()
