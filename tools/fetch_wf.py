#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
抓取外部灵感库(wf)的 图片 / 视频 / Vibe Coding 三类内容, 转成站点通用分片。

- 数据源接口根地址见 WF_API(环境变量/同目录 secrets.json), 代码不写死域名。
- 三类 = media_type:image | media_type:video | tag:"vibe coding"。
- 分类: **图片按「生成模型」分(wf-m-*, 2026-10-22 起)**, 视频按主题(wfv-*), vibe 单页签。
- 分页: cursor(响应 data.next_cursor)。列表不含 prompt, 只含 title/description/cover/media/model/tags...
- prompt: 按需再打详情接口 /api/prompts/{slug} 取(有 WF_PROMPT_CAP 上限, 控制构建耗时)。
- 隐私: 只保留媒体地址与展示字段, 剥掉 source_name/source_url/接口域名; 媒体主机不进仓库
         (图片由前端 coverUrl 走缩图代理, 视频走 /r/v 302 代理, 见 config.js / worker)。

输出(与 oi 同目录 app/data/):
  wf_image_*.json  (7 字段 gal 行, 折进「图库」页签)
  wf_video_*.json  (13 字段 video 行, 折进「视频」页签)
  wf_vibe_*.json   (14 字段 video 行 + 尾缀 media_type, 进「Vibe Coding」页签)
  .cache/wf_meta.json  (分类中文标签 + 轮播 hero 原料)
"""
import glob
import json
import os
import ssl
import sys
import time
import urllib.request
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.environ.get("GAL_OUTDIR") or os.path.join(ROOT, "app", "data")
CACHE = os.environ.get("GAL_RAW_DIR") or os.path.join(ROOT, ".cache")
MANI = os.path.join(DATA, "manifest.json")


def cfg_api():
    """域名只从 环境变量 WF_API / 同目录 secrets.json(gitignored) 取, 代码不写死任何来源域名。"""
    p = os.path.join(HERE, "secrets.json")
    if os.path.exists(p):
        try:
            import json
            v = (json.load(open(p, encoding="utf-8")) or {}).get("WF_API")
            if v:
                return str(v).rstrip("/")
        except Exception:
            pass
    return (os.environ.get("WF_API") or "").strip().rstrip("/")


API = cfg_api()
PAGE = int(os.environ.get("WF_PAGE") or "60")
# 每类最多抓多少条(列表+详情), 本地构建可调小。
# 2026-10-22: 图片源已 4497 条, 上限调到 6000 保证全量接入(改为按模型分类后不再只取前 600)。
IMG_CAP = int(os.environ.get("WF_IMG_CAP") or "6000")
VID_CAP = int(os.environ.get("WF_VID_CAP") or "400")
VIBE_CAP = int(os.environ.get("WF_VIBE_CAP") or "200")
# 每类对前 N 条抓详情取完整 prompt, 其余用 description 兜底。
# 详情接口有严格限流(429), 串行约 1.2~2.5s/条; 默认 1500 条 ≈ 30~60 分钟,
# 再大手动跑会失控(nightly 由 workflow 的 WF_PROMPT_CAP 另行覆盖)。
PROMPT_CAP = int(os.environ.get("WF_PROMPT_CAP") or "1500")

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def http_json(url, tries=4):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; refresh-bot)",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=25, context=_CTX) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            time.sleep(1.5 + i)
    raise last


def list_page(extra):
    """翻一页。extra 里已含 limit/sort; cursor 由调用方追加。返回 (items, next_cursor, total)。"""
    q = urllib.parse.urlencode(extra)
    j = http_json(API + "/api/prompts?" + q)
    d = (j or {}).get("data") or {}
    return d.get("items") or [], d.get("next_cursor"), d.get("total") or 0


def detail(slug):
    try:
        j = http_json(API + "/api/prompts/" + urllib.parse.quote(slug), tries=3)
        return (j or {}).get("data") or {}
    except Exception:
        return {}


def zh(item, short=True):
    t = (item.get("title") or "").strip()
    if not t:
        tr = item.get("title_translations") or {}
        t = tr.get("zh") or tr.get("en") or ""
    return t


def zhdesc(item):
    d = (item.get("description") or "").strip()
    return d


def clean_refs(_):
    return []


# 画廊来源的 model 字段 -> 站点分类键/中文标签。
# 2026-10-22 起画廊图片改按「生成模型」分类(用户要求), 不再按主题(character/portrait...)。
# 模型名清洗: 统一大小写变体/脏数据; 中文模型名 slug 化会空, 用 md5 短码兜底(标签仍显示中文原名)。
import hashlib
import re as _re


def model_key(m):
    m = (m or "").strip()
    low = m.lower()
    # 已知脏数据/变体归一。注意: 归一后必须重算 low, 否则 slug 仍按旧名生成,
    # 会产出 wf-m-image-2-5 这种 1 条幽灵分类(2026-10-22 实测踩坑)。
    if low in ("image 2.5", "gpt-image-2.5", "gpt image2.5"):
        m = "GPT Image 2.5"
        low = m.lower()
    elif low in ("gpt-image-2", "gpt image2"):
        m = "GPT Image 2"
        low = m.lower()
    if not m:
        return "wf-m-other", "其它模型"
    slug = _re.sub(r"[^a-z0-9]+", "-", low).strip("-")
    if not slug:                      # 纯中文模型名
        slug = hashlib.md5(m.encode("utf-8")).hexdigest()[:8]
    return "wf-m-" + slug, m


def img_row(item, prompt):
    cat, _label = model_key(item.get("model"))
    return [
        "wf-" + item["slug"],
        zh(item),
        prompt or zhdesc(item) or zh(item),
        cat,
        zhdesc(item) or zh(item),
        item.get("cover_url") or item.get("media_url") or "",
        [],
    ]


def media_row(item, prompt, kind):
    """kind: 'video' | 'vibe' -> 13(14) 字段。"""
    cover = item.get("cover_url") or ""
    media = item.get("media_url") or ""
    row = [
        "wf-" + item["slug"],
        zh(item),
        prompt or zhdesc(item) or zh(item),
        "wfv-" + (item.get("category") or "") if kind == "video" else "wf-vibe",
        zhdesc(item) or zh(item),
        cover,
        media,
        item.get("model") or "",
        "",                       # author: 不暴露原作者账号
        "zh",                     # lang
        "wf",                     # source key
        "zh",                     # bodyLang
        [],                       # refs
    ]
    if kind == "vibe":
        row.append(item.get("media_type") or "video")
    return row


def fetch_group(extra, cap, prompt_cap, kind):
    seen, items, cursor = set(), [], ""
    total = 0
    while len(items) < cap:
        q = dict(extra)
        q["limit"] = PAGE
        q["sort"] = "latest"
        page, nxt, total = list_page(q) if not cursor else list_page({**q, "cursor": cursor})
        if not page:
            break
        for it in page:
            if it.get("id") in seen:
                continue
            seen.add(it.get("id"))
            items.append(it)
            if len(items) >= cap:
                break
        cursor = nxt
        if not cursor:
            break
    # 详情取 prompt(有上限)
    rows = []
    for i, it in enumerate(items[:cap]):
        p = ""
        if i < prompt_cap:
            d = detail(it.get("slug") or "")
            p = (d.get("prompt") or "").strip()
        if kind == "image":
            rows.append(img_row(it, p))
        else:
            rows.append(media_row(it, p, kind))
    return rows, items, total


def write_shards(prefix, rows, per=100):
    per = int(os.environ.get("WF_SHARD") or str(per))
    old = glob.glob(os.path.join(DATA, prefix + "_*.json"))
    for f in old:
        os.remove(f)
    n = 0
    for i in range(0, len(rows), per):
        json.dump(rows[i:i + per], open(os.path.join(DATA, "%s_%d.json" % (prefix, i // per)), "w", encoding="utf-8"),
                  ensure_ascii=False)
        n += 1
    return n


def main():
    os.makedirs(CACHE, exist_ok=True)
    t0 = time.time()
    if not API:
        print("[wf] 未配置 WF_API(来源接口根地址), 跳过。请在 secret/环境变量/secrets.json 提供。")
        return
    print("[wf] API 已配置, 开始抓取…")

    imgs, img_items, i_total = fetch_group({"media_type": "image"}, IMG_CAP, PROMPT_CAP, "image")
    print("[wf] 图片", len(imgs), "/ total~", i_total, "(%.0fs)" % (time.time() - t0))
    vids, vid_items, v_total = fetch_group({"media_type": "video"}, VID_CAP, PROMPT_CAP, "video")
    print("[wf] 视频", len(vids), "/ total~", v_total, "(%.0fs)" % (time.time() - t0))
    vibs, vibe_items, b_total = fetch_group({"tag": "vibe coding"}, VIBE_CAP, PROMPT_CAP, "vibe")
    print("[wf] Vibe", len(vibs), "/ total~", b_total, "(%.0fs)" % (time.time() - t0))

    n_img = write_shards("wf_image", imgs)
    n_vid = write_shards("wf_video", vids)
    n_vib = write_shards("wf_vibe", vibs)
    print("[wf] 分片: wf_image=%d wf_video=%d wf_vibe=%d" % (n_img, n_vid, n_vib))

    # meta: 分类中文标签 + 聚合分类 + hero 原料
    # 图片按「生成模型」分类(2026-10-22 起, 用户要求); 视频仍按主题(wfv-*); vibe 单页签
    cats = {}
    for it in img_items:
        k, label = model_key(it.get("model"))
        cats[k] = [label, "🎨"]
    for it in vid_items:
        k = "wfv-" + (it.get("category") or "")
        cats[k] = ["灵感视频", "🎬"]
    cats["wf-vibe"] = ["Vibe Coding", "⚡"]
    hero = []
    for it in (vibe_items + vid_items + img_items):
        _k, _label = model_key(it.get("model")) if it.get("media_type") == "image" else ("", "灵感画廊")
        hero.append({
            "id": "wf-" + it["slug"],
            "kind": "image" if it.get("media_type") == "image" else "image",
            "cover": it.get("cover_url") or "",
            "title": zh(it),
            "desc": zhdesc(it),
            "cat": _label or "灵感画廊",
        })
        if len(hero) >= 18:
            break
    json.dump({"cats": cats, "hero": hero, "api_marker": "wf"},
              open(os.path.join(CACHE, "wf_meta.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print("[wf] 完成, 共 %.0fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
