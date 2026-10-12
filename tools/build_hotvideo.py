#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
把「热门视频」板块做成站点的一个视频分片。

输入: .cache/hotvideo.json (fetch_hotvideo.py 抓的)
输出: <OUTDIR>/video_<N>.json   + 更新 manifest 里的 video 计数

记录格式(与其它视频分片一致):
  [id,title,body,cat,desc,cover,videoUrl,model,author,lang,srcKey,bodyLang,refs?]
  refs 是风格参考图, 形如 [["ref","/m/v/x.png"]] (有才带这一位)
"""
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_gal import clean_prompt, has_leak, make_title, refs_of, url_path  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.environ.get("GAL_RAW_DIR") or os.path.join(HERE, ".cache")
RAW = os.environ.get("GAL_RAW_VIDEO") or os.path.join(RAW_DIR, "hotvideo.json")
OUTDIR = os.environ.get("GAL_OUTDIR") or os.path.join(HERE, "app", "data")
MANIFEST = os.path.join(OUTDIR, "manifest.json")
PER = 600
CAT = "hotvideo"
CAT_LABEL = "热门视频"

CJK = re.compile(r"[\u4e00-\u9fff]")


def model_of(job_type):
    j = (job_type or "").lower()
    if "i2v" in j:
        return "图生视频 1.1"
    return "视频生成"


def main():
    items = json.load(open(RAW, encoding="utf-8"))
    rows, seen, dropped, nref = [], set(), 0, 0
    for it in items:
        oid = it.get("id")
        if not oid or oid in seen:
            continue
        seen.add(oid)
        raw = it.get("fullCommand") or ""
        body = clean_prompt(raw)
        if not body or has_leak(body):
            dropped += 1
            continue
        tok, path = url_path(it.get("videoUrl"))
        if not tok:
            dropped += 1
            continue
        rec = ["hv-" + hashlib.md5(oid.encode()).hexdigest()[:12],
               make_title(body), body, CAT, "", "",
               "/m/%s/%s" % (tok, path), model_of(it.get("jobType")), "",
               "zh" if CJK.search(body) else "en", "hotvideo",
               "zh" if CJK.search(body) else "en"]
        refs = refs_of(raw)
        if refs:
            rec.append(refs)
            nref += 1
        rows.append(rec)

    os.makedirs(OUTDIR, exist_ok=True)
    man = json.load(open(MANIFEST, encoding="utf-8"))
    # 分片号固定: 首次接在现有视频分片之后, 之后每次覆盖同一个分片(可反复运行)
    idx = man.get("hotVideoChunk")
    if idx is None:
        idx = int(man.get("chunks", {}).get("video", 0))
    n = 0
    for i in range(0, len(rows), PER):
        json.dump(rows[i:i + PER],
                  open(os.path.join(OUTDIR, "video_%d.json" % (idx + n)), "w", encoding="utf-8"),
                  ensure_ascii=False, separators=(",", ":"))
        n += 1

    # 计数用差值更新, 反复运行不会累加
    prev = int(man.get("hotVideoCount", 0))
    man.setdefault("chunks", {})["video"] = idx + n
    man["videoCount"] = (man.get("videoCount") or 0) - prev + len(rows)
    man["videoPlayable"] = (man.get("videoPlayable") or 0) - prev + len(rows)
    man["hotVideoCount"] = len(rows)
    man["hotVideoChunk"] = idx
    man.setdefault("videoCats", {})[CAT] = [CAT_LABEL, "🎬"]
    cc = man.setdefault("catCounts", {}).setdefault("video", {})
    cc[CAT] = len(rows)
    man.setdefault("sources", {})["hotvideo"] = ["", ""]
    man["totalCats"] = (len(man.get("cats", {})) + len(man.get("imageCats", {}))
                        + len(man.get("videoCats", {})) + len(man.get("galCats", {})))
    json.dump(man, open(MANIFEST, "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))

    print("热门视频分片: %d 条 -> video_%d..%d.json | 带风格参考 %d | 剔除 %d"
          % (len(rows), idx, idx + n - 1, nref, dropped))
    print("manifest: videoCount=%d chunks.video=%d videoCats=%d"
          % (man["videoCount"], man["chunks"]["video"], len(man["videoCats"])))


if __name__ == "__main__":
    main()
