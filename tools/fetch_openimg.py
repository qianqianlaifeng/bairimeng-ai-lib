#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
抓取「开放精选」图/视频提示词源, 映射成站点分片。

- 接口地址不写进代码(仓库公开): 本地读 secrets.json 的 OI_API,
  Actions 里读环境变量 OI_API(GitHub Secret)。
- 每页 60 条(服务端上限), 默认抓 OI_PAGES=20 页 ≈ 1200 条;
  遇到已入库的条目连续 2 页即提前收尾(增量)。
- 产出:
    app/data/oi_gal_N.json    图片行 [id,title,body,cat,desc,cover,refs]
    app/data/oi_video_N.json  视频行 13 字段(同 video_*)
    .cache/oi_meta.json       给 build_oi.py 用的统计(不进仓库)
- 简介用中文: 标题取 zh-Hans 首句(截 42 字), desc 放 zh-Hans 全文。
- 媒体直连源图床(该主机国内可达、有 1 年强缓存), 不再走 Worker 代理。
"""
import json
import os
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "app", "data")
CACHE = os.path.join(ROOT, ".cache")
PAGE = 60
PAGES = int(os.environ.get("OI_PAGES", "20"))
CHUNK = 100          # 每个分片的条数(首屏只拉第 0 片, 拆小能明显加快首屏)
# 媒体直连源图床。该主机国内可达、带 1 年强缓存。
# 注意: 该图床有 Referer 防盗链(带 Referer 返回 403, 会被浏览器 ORB 拦),
# 因此站点的 HTML 必须声明 <meta name="referrer" content="no-referrer">。
# 主机名不写死在代码里, 运行时从 secrets.json 的 IMG_HOST_O / 环境变量取。
PROXY = ""           # 由 img_base() 在 main() 里填好

# 工具名 -> 分类(中文标签)。模型名保留原名, 用户按工具筛。
TOOLS = {}
ICON = "🎨"


def img_base():
    """源图床基础地址。优先环境变量 IMG_BASE_O, 其次 secrets.json 的 IMG_HOST_O。"""
    v = os.environ.get("IMG_BASE_O", "")
    if not v:
        sp = os.path.join(ROOT, "secrets.json")
        if os.path.exists(sp):
            s = json.load(open(sp, encoding="utf-8"))
            h = s.get("IMG_HOST_O") or ""
            if h:
                v = "https://" + h
    if not v:
        sys.exit("!! 缺少 IMG_HOST_O (环境变量 IMG_BASE_O 或 secrets.json)")
    return v.rstrip("/") + "/"


def proxy_rel(local):
    """镜像完整 URL -> 直连地址(换成本地配置的图床主机前缀)。"""
    if not local:
        return ""
    m = re.match(r"^https://[^/]+/(.+)$", local)
    return (PROXY + m.group(1)) if m else ""


def api_base():
    v = os.environ.get("OI_API", "")
    if v:
        return v.rstrip("/")
    sp = os.path.join(ROOT, "secrets.json")
    if os.path.exists(sp):
        s = json.load(open(sp, encoding="utf-8"))
        if s.get("OI_API"):
            return s["OI_API"].rstrip("/")
    sys.exit("!! 缺少 OI_API (环境变量或 secrets.json)")


def cat_key(tool):
    slug = re.sub(r"[^a-z0-9]+", "-", (tool or "other").lower()).strip("-") or "other"
    return "oi-" + slug


def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if i == tries - 1:
                print("  ! 页拉取失败:", url, e)
                return None
            time.sleep(2)
    return None


def proxy_rel(local):
    """镜像完整 URL -> 直连地址。只保留源图床路径, 换成本地配置的主机前缀。"""
    if not local:
        return ""
    m = re.match(r"^https://[^/]+/(.+)$", local)
    return (PROXY + m.group(1)) if m else ""


def zhtitle(zh):
    zh = (zh or "").strip()
    if not zh:
        return ""
    # 取第一句(。!?；), 再按长度截断
    m = re.split(r"(?<=[。！？!?；;])", zh)[0].strip()
    if len(m) > 42:
        m = m[:40].rstrip("，,、；;：:") + "…"
    return m or zh[:40]


def fetch_all():
    base = api_base()
    # 已有 id: 读现有 oi 分片做增量去重
    seen = set()
    for f in os.listdir(OUT):
        if f.startswith("oi_"):
            try:
                for row in json.load(open(os.path.join(OUT, f), encoding="utf-8")):
                    seen.add(row[0])
            except Exception:
                pass

    items, dup_run = [], 0
    for p in range(PAGES):
        d = get("%s/api/prompts?limit=%d&offset=%d" % (base, PAGE, p * PAGE))
        if not d or not d.get("items"):
            break
        fresh = 0
        for it in d["items"]:
            tid = str(it.get("tweet_id") or "")
            if not tid:
                continue
            medias = (("v", v) for v in (it.get("videos") or []))
            medias = list(medias) + [("i", im) for im in (it.get("images") or [])]
            for kind, md in medias:
                idx = md.get("index") or 1
                rid = "oi-%s-%s%s" % (tid, "v" if kind == "v" else "", idx)
                if rid in seen:
                    continue
                seen.add(rid)
                fresh += 1
                items.append({"item": it, "kind": kind, "md": md, "rid": rid, "tid": tid})
        print("  page %2d: +%d 媒体" % (p + 1, fresh))
        if fresh == 0:
            dup_run += 1
            if dup_run >= 2:
                print("  连续 2 页无新条目, 提前收尾(共 %d)" % len(items))
                break
        else:
            dup_run = 0
        time.sleep(0.4)
    return items


def main():
    global PROXY
    os.makedirs(CACHE, exist_ok=True)
    PROXY = img_base()
    print("[0/3] 媒体基础地址: %s" % PROXY)
    print("[1/3] 分页抓取…")
    items = fetch_all()
    if not items:
        print("无新数据")
        return

    print("[2/3] 映射行…")
    gal, vid, hero = [], [], []
    cats = {}
    for it in items:
        obj, kind, md = it["item"], it["kind"], it["md"]
        tr = obj.get("translations") or {}
        zh = tr.get("zh-Hans") or ""
        title = zhtitle(zh) or (obj.get("tool") or "精选") + " 作品"
        body = obj.get("prompt_text") or ""
        tool = obj.get("tool") or "综合"
        ck = cat_key(tool)
        label = tool if tool != "None" else "综合创作"
        cats.setdefault(ck, [label, ICON])
        author = obj.get("author") or ""

        if kind == "i":
            cover = proxy_rel(md.get("local") or "")
            if not cover:
                continue
            gal.append([it["rid"], title, body, ck, zh, cover, []])
            if len(hero) < 18 and title:
                hero.append({"id": it["rid"], "kind": "image", "cover": cover,
                             "title": title, "desc": zh, "cat": label})
        else:
            vurl = proxy_rel(md.get("local") or "")
            if not vurl or not vurl.endswith(".mp4"):
                continue
            poster = proxy_rel(md.get("poster") or "")
            vid.append([it["rid"], title, body, ck, zh, poster, vurl,
                        tool, author, "en", "oi", "en", []])
            if len(hero) < 18 and poster:
                hero.append({"id": it["rid"], "kind": "video", "cover": poster,
                             "video": vurl, "title": title, "desc": zh, "cat": label})

    print("[3/3] 写分片: 图 %d 条 / 视频 %d 条" % (len(gal), len(vid)))
    # 清掉旧 oi 分片, 重写
    for f in os.listdir(OUT):
        if f.startswith(("oi_gal_", "oi_video_")):
            os.remove(os.path.join(OUT, f))
    for prefix, rows in (("oi_gal", gal), ("oi_video", vid)):
        for i in range(0, max(len(rows), 1), CHUNK):
            part = rows[i:i + CHUNK]
            if not part:
                break
            json.dump(part, open(os.path.join(OUT, "%s_%d.json" % (prefix, i // CHUNK)), "w",
                                 encoding="utf-8"), ensure_ascii=False)

    meta = {"gal": len(gal), "video": len(vid), "cats": cats, "hero": hero,
            "fetched": time.strftime("%Y-%m-%d %H:%M:%S")}
    json.dump(meta, open(os.path.join(CACHE, "oi_meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("完成: %s" % meta["fetched"])


if __name__ == "__main__":
    main()
