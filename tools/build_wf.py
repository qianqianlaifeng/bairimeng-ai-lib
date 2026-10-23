#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
把 wf_* 分片并入 manifest(幂等)。仿 build_oi.py。
  wf_image_*  -> 「图库」gal 页(图片提示词)
  wf_video_*  -> 「视频」video 页
  wf_vibe_*   -> 「Vibe Coding」独立页(=tag: vibe coding)

数据/清单目录优先取 GAL_OUTDIR(Actions 每日刷新用), 否则退回 app/data。
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

SOURCE_LABEL = ["灵感画廊", ""]          # 对外只显示中性名, 不暴露来源
VIBE_LABEL = ["Vibe Coding", "⚡"]
IMGFB = ["灵感画廊", "🎨"]
VIDFB = ["灵感视频", "🎬"]


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
    gal = load_rows("wf_image_*.json")
    vid = load_rows("wf_video_*.json")
    vib = load_rows("wf_vibe_*.json")
    if not (gal or vid or vib):
        print("[wf] 无 wf 分片, 跳过")
        return

    labels = {}
    mp = os.path.join(CACHE, "wf_meta.json")
    if os.path.exists(mp):
        try:
            labels = (json.load(open(mp, encoding="utf-8")) or {}).get("cats") or {}
        except Exception:
            labels = {}

    m = json.load(open(MANI, encoding="utf-8"))

    # ---- 分类中文标签 + 分类计数 ----
    gcnt, vcnt = {}, {}
    for r in gal:
        gcnt[r[3]] = gcnt.get(r[3], 0) + 1
    for r in vid:
        vcnt[r[3]] = vcnt.get(r[3], 0) + 1

    galCats = dict(m.get("galCats") or {})
    videoCats = dict(m.get("videoCats") or {})
    for k, n in gcnt.items():
        galCats[k] = labels.get(k, IMGFB)
        m.setdefault("catCounts", {}).setdefault("gal", {})[k] = n
    for k, n in vcnt.items():
        videoCats[k] = labels.get(k, VIDFB)
        m.setdefault("catCounts", {}).setdefault("video", {})[k] = n
    m["galCats"] = galCats
    m["videoCats"] = videoCats

    # Vibe Coding 独立页签
    m["vibeCats"] = {"wf-vibe": VIBE_LABEL}
    m.setdefault("catCounts", {})["vibe"] = {"wf-vibe": len(vib)}

    # ---- 计数折入 ----
    # nightly 链路语义(2026-10-23 修正, 同 build_oi.py): refresh.py 已重置 galCount,
    # build_hotvideo 已重建 videoCount —— 直接加本轮量, 不扣上一轮。
    n_i, n_v, n_b = len(gal), len(vid), len(vib)
    m["galCount"] = (m.get("galCount") or 0) + n_i
    m["videoCount"] = (m.get("videoCount") or 0) + n_v
    m["videoPlayable"] = (m.get("videoPlayable") or 0) + n_v
    m["vibeCount"] = n_b
    m["wfImage"] = n_i
    m["wfVideo"] = n_v
    m["wfVibe"] = n_b

    # ---- 分片数 ----
    ch = m.setdefault("chunks", {})
    ch["wf_image"] = nfiles("wf_image_*.json")
    ch["wf_video"] = nfiles("wf_video_*.json")
    ch["wf_vibe"] = nfiles("wf_vibe_*.json")

    # ---- 来源(中性名) ----
    m.setdefault("sources", {})["wf"] = SOURCE_LABEL

    # ---- 黑金轮播: wf 精选 + 现有 oiHero 混排 ----
    hero = []
    if os.path.exists(mp):
        try:
            hero = (json.load(open(mp, encoding="utf-8")) or {}).get("hero") or []
        except Exception:
            hero = []
    ex = m.get("oiHero") or []
    m["oiHero"] = (hero[:9] + ex[:9])[:18]

    json.dump(m, open(MANI, "w", encoding="utf-8"), ensure_ascii=False)
    print("[wf] manifest: 图 %d / 视频 %d / Vibe %d | galCount=%s videoCount=%s vibeCount=%s | "
          "chunks wf_image=%d wf_video=%d wf_vibe=%d | oiHero=%d" %
          (n_i, n_v, n_b, m["galCount"], m["videoCount"], m["vibeCount"],
           ch["wf_image"], ch["wf_video"], ch["wf_vibe"], len(m["oiHero"])))


if __name__ == "__main__":
    main()
