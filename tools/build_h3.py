#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 h3_video_* 分片并入 manifest(幂等)。仿 build_wf.py。
  h3_video_*  -> 「开源 MiniMax H3」独立页签
  用户要求(2026-10-17): 该页签**只要可播视频**, 图卡一律过滤。
  fetch 失败时本脚本会用旧缓存兜底重写分片, 保证图卡不会回流。
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

SOURCE_LABEL = ["开源 MiniMax H3", ""]   # 对外中性名


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
    # 只要可播视频(尾字段 media_type != 'image'); 图卡一律过滤, 防旧数据回流
    return [r for r in rows if (r[13] if len(r) > 13 else "video") != "image"]


def write_shards(rows, per=100):
    for f in glob.glob(os.path.join(DATA, "h3_video_*.json")):
        os.remove(f)
    for i in range(0, len(rows), per):
        json.dump(rows[i:i + per],
                  open(os.path.join(DATA, "h3_video_%d.json" % (i // per)), "w", encoding="utf-8"),
                  ensure_ascii=False)


def nfiles(pattern):
    return len(glob.glob(os.path.join(DATA, pattern)))


def main():
    rows = load_rows("h3_video_*.json")
    # 分片与过滤结果对齐: fetch 失败(旧缓存含图卡)时兜底重写, 图卡不会回流
    per = int(os.environ.get("H3_SHARD") or "100")
    write_shards(rows, per)
    if not rows:
        print("[h3] 无可播视频行, 页签为空")

    labels = {}
    rp = os.path.join(CACHE, "h3_raw.json")
    if os.path.exists(rp):
        try:
            labels = (json.load(open(rp, encoding="utf-8")) or {}).get("cats") or {}
        except Exception:
            labels = {}

    m = json.load(open(MANI, encoding="utf-8"))

    # ---- 分类标签 + 分类计数(整体替换, 不吃上一轮的残留) ----
    ccnt = {}
    for r in rows:
        ccnt[r[3]] = ccnt.get(r[3], 0) + 1
    m["h3Cats"] = {k: labels.get(k, ["H3 案例", "⚡"]) for k in ccnt}
    m.setdefault("catCounts", {})["h3"] = ccnt

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
          (n_all, n_video, m["h3Count"], ch["h3_video"], len(m["h3Cats"])))


if __name__ == "__main__":
    main()
