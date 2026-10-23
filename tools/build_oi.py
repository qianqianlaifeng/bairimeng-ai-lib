#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
把 oi_* 分片并入 manifest(幂等, 每日刷新流程最后一步跑)。

- 扫 app/data 里的 oi_gal_*.json / oi_video_*.json 重建统计(不依赖 .cache)。
- chunks.oi_gal / chunks.oi_video = 分片数(前端把这两组分片排在最前 => 优先展示)。
- galCount / videoCount / videoPlayable 折入 oi 条数(保持页签计数一致)。
- galCats / videoCats 并入 oi 分类; sources 加 'oi'; catCounts 同步累加。
- manifest.oiHero = 黑金轮播精选(优先用 .cache/oi_meta.json 的 hero, 否则从分片现取)。
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "app", "data")
MANI = os.path.join(DATA, "manifest.json")

# 没抓到 .cache 时的分类兜底(与 fetch_openimg 的命名规则一致)
FALLBACK_CATS = {"oi-other": ["综合创作", "🎨"]}
SOURCE_LABEL = ["社区开放分享", ""]


def load_rows(pattern):
    rows = []
    for f in sorted(glob.glob(os.path.join(DATA, pattern)),
                    key=lambda p: int(re_num(p))):
        rows.extend(json.load(open(f, encoding="utf-8")))
    return rows


def re_num(p):
    import re
    m = re.search(r"_(\d+)\.json$", p)
    return m.group(1) if m else "0"


def main():
    gal = load_rows("oi_gal_*.json")
    vid = load_rows("oi_video_*.json")
    if not gal and not vid:
        print("无 oi 分片, 跳过")
        return

    m = json.load(open(MANI, encoding="utf-8"))

    # ---- 分类: 从分片现统计(键 -> 计数), 标签用 meta 里的, 没有就兜底 ----
    meta = {}
    mp = os.path.join(ROOT, ".cache", "oi_meta.json")
    if os.path.exists(mp):
        meta = json.load(open(mp, encoding="utf-8"))
    labels = meta.get("cats") or FALLBACK_CATS

    gcnt, vcnt = {}, {}
    for r in gal:
        gcnt[r[3]] = gcnt.get(r[3], 0) + 1
    for r in vid:
        vcnt[r[3]] = vcnt.get(r[3], 0) + 1

    galCats = dict(m.get("galCats") or {})
    videoCats = dict(m.get("videoCats") or {})
    for k, n in gcnt.items():
        galCats[k] = labels.get(k, ["开放精选", "🎨"])
        m.setdefault("catCounts", {}).setdefault("gal", {})[k] = n
    for k, n in vcnt.items():
        videoCats[k] = labels.get(k, ["开放精选", "🎬"])
        m.setdefault("catCounts", {}).setdefault("video", {})[k] = n
    m["galCats"] = galCats
    m["videoCats"] = videoCats

    # ---- 计数折入 ----
    # nightly 链路语义(2026-10-23 修正): refresh.py 已把 galCount 重置为纯 gal 量,
    # build_hotvideo 已重建 videoCount —— 这里直接加本轮量。旧版「先扣上一轮」
    # 会把刚重置的基数误当成本源旧量吞掉(源的量不变时增量全丢)。
    n_gal, n_vid = len(gal), len(vid)
    m["galCount"] = (m.get("galCount") or 0) + n_gal
    m["videoCount"] = (m.get("videoCount") or 0) + n_vid
    m["videoPlayable"] = (m.get("videoPlayable") or 0) + n_vid
    m["oiGalCount"] = n_gal
    m["oiVideoCount"] = n_vid

    # ---- 分片数 ----
    ch = m.setdefault("chunks", {})
    ch["oi_gal"] = len(glob.glob(os.path.join(DATA, "oi_gal_*.json")))
    ch["oi_video"] = len(glob.glob(os.path.join(DATA, "oi_video_*.json")))

    # ---- 来源 ----
    src = m.setdefault("sources", {})
    src["oi"] = SOURCE_LABEL

    # ---- 黑金轮播精选 ----
    hero = meta.get("hero") or []
    if not hero:
        hero = [{"id": r[0], "kind": "image", "cover": r[5], "title": r[1],
                 "desc": r[4], "cat": (galCats.get(r[3]) or ["精选"])[0]} for r in gal[:18]]
    m["oiHero"] = hero[:18]

    json.dump(m, open(MANI, "w", encoding="utf-8"), ensure_ascii=False)
    print("manifest 更新: oi 图 %d / 视频 %d | galCount=%s videoCount=%s | oiHero=%d" %
          (n_gal, n_vid, m["galCount"], m["videoCount"], len(m["oiHero"])))


if __name__ == "__main__":
    main()
