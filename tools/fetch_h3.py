#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓取 MiniMax H3 视频案例 -> h3 原始行缓存。

数据源(公开、MIT): SkyNotSilent/awesome-MiniMax-H3-cases
  - 站点索引接口  /api/catalog         分页(36 条/页, nextCursor 游标)
  - 单条详情      /data/cases/<id>.json 仅 hasPrompt=true 的条目带完整 prompt
  - 媒体全部自托管: /media/<id>.mp4 (307 -> 对象存储预签名, 浏览器自动跟随)
                   /posters/x/<num>.jpg 封面
  该库 hostedVideos == total, 即**每一条都是可播视频**(2026-10-17 起取代旧源:
  旧源 274 条里仅 7 条自托管可播, 其余视频在 X 图床、国内不可达)。

产物: <GAL_RAW_DIR>/h3_raw.json  {rows, cats, total, videos, prompts}
行格式(14 字段, 与 Vibe 行一致, 尾缀 media_type):
  [id, 标题, prompt, cat, desc, cover, videoUrl, model, author, lang, source, bodyLang, refs, media_type]

域名/路径均可被环境变量覆盖, 便于换源。
注意: cover/videoUrl 写**相对路径**(/media/...、/posters/...), 域名不进数据分片 ——
      由前端 config.js 的 H3_MEDIA(案例媒体基址) 拼接, 与 IMG_BASE 同款思路。
"""
import glob
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from concurrent import futures

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.environ.get("GAL_OUTDIR") or os.path.join(ROOT, "app", "data")
OUTDIR = os.environ.get("GAL_RAW_DIR") or os.path.join(ROOT, ".cache")

BASE = (os.environ.get("H3_BASE") or "https://awesome-minimax-h3-cases.zzskysilent.com").rstrip("/")
CATALOG = BASE + "/api/catalog"
CASE_URL = BASE + "/data/cases/%s.json"

CAP = int(os.environ.get("H3_CAP") or "3000")          # 行数上限(全量 2764)
PAGE_CAP = int(os.environ.get("H3_PAGE_CAP") or "120")  # 最多翻多少页
PROMPT_CAP = int(os.environ.get("H3_PROMPT_CAP") or "900")  # 最多抓多少条详情
TIMEOUT = int(os.environ.get("H3_TIMEOUT") or "30")
WORKERS = int(os.environ.get("H3_WORKERS") or "12")
PER = int(os.environ.get("H3_SHARD") or "100")

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept": "application/json"}

# 源分类 -> (cat key, 中文标签, 图标)
CAT_MAP = {
    "cinematic": ("h3-cinematic", "电影与叙事", "🎬"),
    "action-vfx": ("h3-action", "动作与特效", "💥"),
    "dialogue": ("h3-dialogue", "对白与音效", "🎙️"),
    "music": ("h3-music", "音乐与节奏", "🎵"),
    "dance": ("h3-dance", "舞蹈与表演", "💃"),
    "advertising": ("h3-product", "广告与产品", "📦"),
    "comparison": ("h3-compare", "模型对比", "🔬"),
    "animation": ("h3-animation", "动画与二次元", "🎨"),
    "workflow": ("h3-workflow", "工作流与编辑", "⚙️"),
    "showcase": ("h3-showcase", "精选展示", "⭐"),
}
CAT_FALLBACK = ("h3-misc", "H3 案例", "⚡")


def http_get(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def fetch_catalog():
    """翻页抓全量索引。"""
    out, seen, cursor, pages = [], set(), None, 0
    while pages < PAGE_CAP:
        url = CATALOG if not cursor else CATALOG + "?cursor=" + urllib.parse.quote(cursor)
        try:
            d = http_get(url)
        except Exception as e:
            print("[h3] catalog 第 %d 页失败: %s" % (pages + 1, e))
            break
        items = d.get("cases") or []
        for c in items:
            cid = c.get("id")
            if cid and cid not in seen:
                seen.add(cid)
                out.append(c)
        pages += 1
        cursor = d.get("nextCursor")
        if not cursor:
            break
        if pages % 10 == 0:
            print("[h3] catalog %d 页 / %d 条" % (pages, len(out)))
    print("[h3] catalog 完成: %d 页, %d 条" % (pages, len(out)))
    return out


def fetch_detail(cid):
    try:
        return cid, http_get(CASE_URL % cid, tries=2)
    except Exception:
        return cid, None


def main():
    t0 = time.time()
    cases = fetch_catalog()
    if not cases:
        print("!! catalog 为空, 放弃(保留旧缓存)")
        return 1

    # ---- 抓详情: 有 prompt 的优先, 最多 PROMPT_CAP 条 ----
    need = [c["id"] for c in cases if c.get("hasPrompt")][:PROMPT_CAP]
    print("[h3] 需抓详情(prompt) %d 条 ..." % len(need))
    details = {}
    with futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for cid, d in ex.map(fetch_detail, need):
            if d:
                details[cid] = d
    print("[h3] 详情到手 %d/%d (%.0fs)" % (len(details), len(need), time.time() - t0))

    # ---- 排序: 有 prompt -> 精选 -> 新增时间新 ----
    def rank(c):
        return (
            0 if c.get("hasPrompt") else 1,
            0 if c.get("isFeatured") else 1,
            _neg_time(c.get("addedAt") or ""),
        )
    cases.sort(key=rank)

    rows, cats = [], {}
    for c in cases:
        if len(rows) >= CAP:
            break
        cid = c["id"]
        det = details.get(cid) or {}
        cat = c.get("category") or ""
        key, label, icon = CAT_MAP.get(cat, CAT_FALLBACK)
        cats[key] = [label, icon]

        title = c.get("title") or c.get("titleEn") or cid
        prompt = det.get("prompt") or ""
        author = c.get("author") or ""
        if author and not author.startswith("@"):
            author = "@" + author

        # desc: 中文摘要 + 时长/分辨率规格
        desc = det.get("summary") or ""
        dur = c.get("duration")
        spec = []
        if isinstance(dur, (int, float)) and dur > 0:
            spec.append("%ds" % int(dur))
        if det.get("resolution"):
            spec.append(det["resolution"])
        if spec:
            desc = (desc + " · " if desc else "") + " · ".join(spec)
        # 摘要缺失(只剩 "10s" 这类规格)时, 用 分类 · 作者 · 规格 兜底, 卡片上不至于太空
        if len(desc) < 22:
            parts = [label]
            if author:
                parts.append(author)
            if desc:
                parts.append(desc)
            desc = " · ".join(parts)

        rows.append([
            "h3-" + cid,
            title,
            prompt,
            key,
            desc,
            c.get("posterUrl") or "",      # 相对路径 /posters/x/<num>.jpg
            c.get("mediaUrl") or "",       # 相对路径 /media/<id>.mp4
            "MiniMax H3",
            author,
            "zh",
            "h3",
            "en",
            [c["sourceUrl"]] if c.get("sourceUrl") else [],
            "video",
        ])

    # ---- 落盘: 原始缓存 + 站点分片 ----
    os.makedirs(OUTDIR, exist_ok=True)
    out = os.path.join(OUTDIR, "h3_raw.json")
    json.dump({"rows": rows, "cats": cats}, open(out, "w", encoding="utf-8"), ensure_ascii=False)

    os.makedirs(DATA, exist_ok=True)
    for f in glob.glob(os.path.join(DATA, "h3_video_*.json")):
        os.remove(f)
    for i in range(0, len(rows), PER):
        json.dump(rows[i:i + PER],
                  open(os.path.join(DATA, "h3_video_%d.json" % (i // PER)), "w", encoding="utf-8"),
                  ensure_ascii=False)

    n_prompt = sum(1 for r in rows if r[2])
    print("[h3] 行: %d (带完整 prompt %d) -> %s + %d 个分片 (%.0fs)" %
          (len(rows), n_prompt, out, (len(rows) + PER - 1) // PER if rows else 0, time.time() - t0))
    return 0


def _neg_time(s):
    """addedAt 降序用的排序键(字符串取负不便, 转成时间戳取负)。"""
    try:
        return -time.mktime(time.strptime(s[:19], "%Y-%m-%dT%H:%M:%S"))
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
