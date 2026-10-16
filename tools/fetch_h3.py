#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取 MiniMax H3(海螺 H3) 视频案例 -> h3 原始行缓存。

数据源(公开、MIT):
  1) GitHub 开源仓库 xianyu110/awesome-minimax-h3-prompts 的 prompts/GALLERY.md
     (英文标题/分类) + GALLERY.zh-CN.md(中文标题/分类, 同一套 thumb id 可对齐)。
     每条含: 标题 / 分类 / 推特缩略图(amplify_video_thumb/<视频id>) / 原创者推文链接 / 完整提示词。
  2) 可播视频与本地封面由案例站自托管(同域媒体路径):
       /minimax/source-videos/<vid>.mp4        —— 成片(目前 7 条)
       /minimax/prompts/thumbs/<vid>-<name>.jpg —— 全部条目的本地封面
     逐个 HEAD 探测视频是否存在; 存在的渲染成视频卡, 其余渲染成图卡(封面+完整提示词)。

产物: <GAL_RAW_DIR>/h3_raw.json  {rows, cats, total, videos, images}
行格式(14 字段, 与 Vibe 行一致, 尾缀 media_type 区分视频卡/图卡):
  [id, 标题, prompt, cat, desc, cover, videoUrl, model, author, lang, source, bodyLang, refs, media_type]
域名/路径均可被环境变量覆盖, 便于换源。
"""
import glob
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent import futures

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.environ.get("GAL_OUTDIR") or os.path.join(ROOT, "app", "data")

REPO = os.environ.get("H3_REPO") or "xianyu110/awesome-minimax-h3-prompts"
BRANCH = os.environ.get("H3_BRANCH") or "main"
GAL_EN = os.environ.get("H3_GAL_EN") or (
    "https://raw.githubusercontent.com/%s/%s/prompts/GALLERY.md" % (REPO, BRANCH))
GAL_ZH = os.environ.get("H3_GAL_ZH") or (
    "https://raw.githubusercontent.com/%s/%s/prompts/GALLERY.zh-CN.md" % (REPO, BRANCH))
MEDIA = (os.environ.get("H3_MEDIA_BASE") or "https://tryminimax.asia").rstrip("/")
VIDEO_PATH = os.environ.get("H3_VIDEO_PATH") or "/minimax/source-videos/%s.mp4"
# thumb_name 已含 .jpg 后缀(取自 GALLERY 的 img 文件名), 这里不再拼
THUMB_PATH = os.environ.get("H3_THUMB_PATH") or "/minimax/prompts/thumbs/%s-%s"

OUTDIR = os.environ.get("GAL_RAW_DIR") or os.path.join(ROOT, ".cache")
CAP = int(os.environ.get("H3_CAP") or "300")
PROBE_CAP = int(os.environ.get("H3_PROBE_CAP") or "260")
TIMEOUT = int(os.environ.get("H3_TIMEOUT") or "12")

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# 中文分区 -> (cat key, 中文标签, 图标)
CAT_MAP = {
    "电影与叙事": ("h3-cinematic", "电影与叙事", "🎬"),
    "动画与二次元": ("h3-animation", "动画与二次元", "🎨"),
    "广告与产品": ("h3-product", "广告与产品", "📦"),
    "人物与表演": ("h3-character", "人物与表演", "🎭"),
    "特效与转场": ("h3-vfx", "特效与转场", "✨"),
    "运镜": ("h3-camera", "运镜", "🎥"),
    "参考图与一致性": ("h3-reference", "参考图与一致性", "🔗"),
    "视频编辑": ("h3-editing", "视频编辑", "✂️"),
    "对白与音效": ("h3-dialogue", "对白与音效", "🎙️"),
    "动物": ("h3-animal", "动物", "🐾"),
    "女性": ("h3-character", "人物与表演", "🎭"),
}
CAT_FALLBACK = ("h3-misc", "H3 案例", "⚡")


def http_get(url, binary=False):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = r.read()
    return data if binary else data.decode("utf-8", "replace")


def head_ok(url):
    """HEAD 探测; 某些 CDN 不支持 HEAD 时退化成 Range 小 GET。"""
    try:
        req = urllib.request.Request(url, headers=UA, method="HEAD")
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return 200 <= r.status < 300
    except urllib.error.HTTPError as e:
        if e.code == 405:  # Method Not Allowed -> 退化
            try:
                req = urllib.request.Request(url, headers={**UA, "Range": "bytes=0-0"})
                with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                    return r.status in (200, 206)
            except Exception:
                return False
        return False
    except Exception:
        return False


def parse_gallery(md):
    """解析 GALLERY markdown -> [{title, cat, vid, thumb_name, tweet, prompt}]"""
    out = []
    secs = re.split(r"\n## (?!#)", md)
    for sec in secs[1:]:
        cat = sec.split("\n", 1)[0].strip()
        for b in re.split(r"\n### ", sec)[1:]:
            title = re.sub(r"^\d+\.\s*", "", b.split("\n", 1)[0]).strip()
            if not title:
                continue
            img = re.search(r'<img src="https://pbs\.twimg\.com/amplify_video_thumb/([0-9]+)/img/([^"]+?\.jpg)"', b)
            if not img:
                continue
            vid, thumb_name = img.group(1), img.group(2)
            tweet = re.search(r"\((https://x\.com/[^)]+/status/[0-9]+)\)", b)
            pm = re.search(r"~{3,}[a-zA-Z]*\n([\s\S]*?)\n~{3,}", b)
            prompt = pm.group(1).strip() if pm else ""
            if len(prompt) < 80:
                continue
            out.append({
                "title": title, "cat": cat, "vid": vid, "thumb_name": thumb_name,
                "tweet": tweet.group(1) if tweet else "",
                "prompt": prompt,
            })
    return out


def main():
    t0 = time.time()
    print("[h3] 拉取 GALLERY(英文) ...")
    try:
        md_en = http_get(GAL_EN)
    except Exception as e:
        print("!! GALLERY 英文版拉取失败:", e)
        return
    print("[h3] 拉取 GALLERY(中文) ...")
    try:
        md_zh = http_get(GAL_ZH)
    except Exception as e:
        print("!! GALLERY 中文版拉取失败(标题回退英文):", e)
        md_zh = ""

    en = parse_gallery(md_en)
    zh = {}
    if md_zh:
        for e in parse_gallery(md_zh):
            if e["vid"]:
                zh[e["vid"]] = e
    # 以英文版为骨架(条目全), 中文版补标题/分类
    merged = []
    seen = set()
    for e in en:
        if e["vid"] in seen:
            continue
        seen.add(e["vid"])
        z = zh.get(e["vid"]) or {}
        merged.append({
            "vid": e["vid"],
            "title_en": e["title"], "title_zh": z.get("title", ""),
            "cat_en": e["cat"], "cat_zh": z.get("cat", ""),
            "thumb_name": e["thumb_name"], "tweet": e["tweet"],
            "prompt": e["prompt"],
        })
    # 中文版有而英文版没有的条目也补上
    for vid, z in zh.items():
        if vid not in seen:
            seen.add(vid)
            merged.append({
                "vid": vid, "title_en": z["title"], "title_zh": z["title"],
                "cat_en": z["cat"], "cat_zh": z["cat"],
                "thumb_name": z["thumb_name"], "tweet": z["tweet"], "prompt": z["prompt"],
            })
    print("[h3] 条目: %d (去重后)" % len(merged))

    # HEAD 探测本地可播视频(并发; 不存在的地址会挂到超时, 必须并发+短超时)
    local_videos, probed = [], 0
    todo = [e for e in merged[:PROBE_CAP]]
    def probe(e):
        return e["vid"] if head_ok(MEDIA + VIDEO_PATH % e["vid"]) else None
    with futures.ThreadPoolExecutor(max_workers=12) as ex:
        for res in ex.map(probe, todo):
            probed += 1
            if res:
                local_videos.append(res)
    print("[h3] 探测 %d 个视频地址, 可播 %d 个 (%.0fs)" % (probed, len(local_videos), time.time() - t0))
    lv = set(local_videos)

    rows, cats = [], {}
    for e in merged:
        if len(rows) >= CAP:
            break
        cat_src = e["cat_zh"] or e["cat_en"]
        key, label, icon = CAT_MAP.get(cat_src, CAT_FALLBACK)
        cats[key] = [label, icon]
        title = e["title_zh"] or e["title_en"]
        author = ""
        m = re.search(r"x\.com/([^/]+)/status/", e["tweet"] or "")
        if m:
            author = "@" + m.group(1)
        is_video = e["vid"] in lv
        rows.append([
            "h3-" + e["vid"],
            title,
            e["prompt"],
            key,
            "%s%s" % (label, (" · " + author) if author else ""),
            MEDIA + THUMB_PATH % (e["vid"], e["thumb_name"]),
            (MEDIA + VIDEO_PATH % e["vid"]) if is_video else "",
            "MiniMax H3",
            author,
            "en",
            "h3",
            "en",
            [e["tweet"]] if e["tweet"] else [],
            "video" if is_video else "image",
        ])

    # 原始行缓存 + 站点分片(100 条/片, 与其它来源一致)
    os.makedirs(OUTDIR, exist_ok=True)
    out = os.path.join(OUTDIR, "h3_raw.json")
    json.dump({"rows": rows, "cats": cats}, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    per = int(os.environ.get("H3_SHARD") or "100")
    for f in glob.glob(os.path.join(DATA, "h3_video_*.json")):
        os.remove(f)
    for i in range(0, len(rows), per):
        json.dump(rows[i:i + per],
                  open(os.path.join(DATA, "h3_video_%d.json" % (i // per)), "w", encoding="utf-8"),
                  ensure_ascii=False)
    nv = sum(1 for r in rows if r[13] == "video")
    print("[h3] 行: %d (视频 %d / 图卡 %d) -> %s + %d 个分片 (%.0fs)" %
          (len(rows), nv, len(rows) - nv, out,
           (len(rows) + per - 1) // per if rows else 0, time.time() - t0))


if __name__ == "__main__":
    sys.exit(main())
