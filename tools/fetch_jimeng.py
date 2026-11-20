#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
抓取即梦(jimeng.jianying.com)探索页三个图片分类: 平面设计 / 电商 / 其他。

修复的根因(2026-11-20 第二次重写):
  页面会并发请求多个 category_id, 旧版把"没认出来的 cid"按"当前点着的页签"
  兜底打标, 于是别的分类的图被贴上了当前页签的标签 -> 图片和分类对不上。

  本版做法(两遍式, 严格按 cid 归属):
    第1遍 发现: 逐个点击 页签/子分类, 记录"点击后新出现的 category_id",
                即得到 权威的 cid -> 分类 映射。
    第2遍 收集: 再次逐个点击, 只收该分类自己 cid 的响应, 其余一律丢弃。
    最后再按 cid 白名单过滤一次, 保证没有串类。

只收 effect_type == 9(真图片作品, 带 text2image_params.prompt)。
209 是音色样本、210 是视频, 都不收。

用法:
  python tools/fetch_jimeng.py
  python tools/fetch_jimeng.py --max-scroll 6
"""
import os
import sys
import json
import time
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE = os.path.join(ROOT, ".cache")
OUT = os.path.join(CACHE, "jimeng_raw.json")

EXPLORE_URL = "https://jimeng.jianying.com/ai-tool/explore"

# 三个图片分类及其子分类(实测 2026-11-20)
TARGETS = [
    ("平面设计", ["海报", "品牌设计"]),
    ("电商", ["电商头图", "商品展示"]),
    ("其他", []),
]
IMG_EFFECT_TYPES = (9,)


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-scroll", type=int, default=6)
    return ap.parse_args()


def extract(item):
    ca = item.get("common_attr") or {}
    if ca.get("effect_type") not in IMG_EFFECT_TYPES:
        return None
    ap = item.get("aigc_image_params") or {}
    t2i = ap.get("text2image_params") or {}
    prompt = (t2i.get("prompt") or ap.get("prompt") or "").strip()
    cmap = ca.get("cover_url_map") or {}
    cover = cmap.get("1080") or cmap.get("720") or cmap.get("480") or ca.get("cover_url") or ""
    if not cover:
        return None
    title = (ca.get("title") or "").strip() or prompt[:36].replace("\n", " ")
    if not title:
        return None
    return {
        "id": "jm-" + str(ca.get("id") or ca.get("effect_id") or ""),
        "title": title,
        "prompt": prompt or title,
        "author": (item.get("author") or {}).get("name") or "",
        "cover": cover,
        "ctime": ca.get("create_time") or 0,
        "width": ca.get("cover_width") or 0,
        "height": ca.get("cover_height") or 0,
    }


def click_text(page, name, ymin, ymax, xmin=0):
    return page.evaluate(
        """(a)=>{const [n,lo,hi,xm]=a;
          const els=[...document.querySelectorAll('span,button,a')].filter(e=>(e.innerText||'').trim()===n);
          for(const e of els){const r=e.getBoundingClientRect();
            if(r.y>lo&&r.y<hi&&r.x>=xm&&r.width>5){e.click();return true;}}
          return false;}""",
        [name, ymin, ymax, xmin])


def main():
    args = parse_args()
    os.makedirs(CACHE, exist_ok=True)
    from playwright.sync_api import sync_playwright

    req_cids = []          # 观察到的 cid 顺序(用于"新出现"检测)
    resp_by_cid = {}       # cid -> [items]

    def on_request(req):
        if "get_explore" not in req.url:
            return
        try:
            b = json.loads(req.request.post_data) if req.post_data else {}
        except Exception:
            return
        cid = b.get("category_id")
        if cid:
            req_cids.append(str(cid))

    def on_response(resp):
        if "get_explore" not in resp.url:
            return
        try:
            b = json.loads(resp.request.post_data) if resp.request.post_data else {}
        except Exception:
            return
        cid = b.get("category_id")
        if not cid:
            return
        try:
            d = resp.json()
        except Exception:
            return
        items = (d.get("data", {}) or {}).get("item_list", [])
        if items:
            resp_by_cid.setdefault(str(cid), []).extend(items)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True, timeout=30000)
        ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = ctx.new_page()
        page.on("request", on_request)
        page.on("response", on_response)
        try:
            page.goto(EXPLORE_URL, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            print("打开页面超时(可能已加载):", str(e)[:80])
        try:
            page.get_by_text("平面设计", exact=True).first.wait_for(state="visible", timeout=30000)
        except Exception:
            print("!! 分类栏 30s 未出现, 可能被风控")
        time.sleep(3)

        # ---------- 第1遍: 发现 cid -> 分类 ----------
        cid2cat = {}
        for tab, subs in TARGETS:
            for sub in ([None] + list(subs)):
                before = set(req_cids)
                if sub is None:
                    ok = click_text(page, tab, 40, 130)
                else:
                    ok = click_text(page, sub, 95, 200)
                time.sleep(4.5)
                new = set(req_cids) - before
                for c in new:
                    cid2cat.setdefault(c, tab)
                label = tab if sub is None else "%s/%s" % (tab, sub)
                print("发现 %-14s 新 cid: %s (click=%s)" % (label, sorted(new), ok))

        # 兜底: 已知实测 cid
        FALLBACK = {
            "19442373123084": "平面设计", "19442373124108": "平面设计",
            "19442373125132": "电商", "19442373126156": "电商",
            "11222": "其他",
        }
        for c, cat in FALLBACK.items():
            cid2cat.setdefault(c, cat)
        print("\ncid -> 分类:", json.dumps(cid2cat, ensure_ascii=False))

        # ---------- 第2遍: 按分类滚动收集 ----------
        rows = {}
        for tab, subs in TARGETS:
            for sub in ([None] + list(subs)):
                if sub is None:
                    click_text(page, tab, 40, 130)
                else:
                    click_text(page, sub, 95, 200)
                time.sleep(3.5)
                for _ in range(args.max_scroll):
                    page.mouse.wheel(0, 2600)
                    time.sleep(1.7)
            # 只留属于该 tab 的 cid
            good = [c for c in resp_by_cid if cid2cat.get(c) == tab]
            n = 0
            for c in good:
                for it in resp_by_cid[c]:
                    r = extract(it)
                    if r:
                        r["cat"] = "jimeng-" + tab
                        r["cid"] = c
                        rows.setdefault(r["id"], r)
                        n += 1
            print("分类[%s] 采集 %d 条 (cid %s)" % (tab, n, good))
        browser.close()

    out = sorted(rows.values(), key=lambda r: (r.get("ctime") or 0), reverse=True)
    if not out and os.path.exists(OUT):
        print("!! 本轮 0 条, 保留旧缓存")
        return

    # 白名单复核: 任何 cid 不在映射里的, 一律剔除
    bad = [r for r in out if r.get("cid") not in cid2cat]
    if bad:
        print("!! 剔除无归属 %d 条" % len(bad))
        out = [r for r in out if r.get("cid") in cid2cat]

    from collections import Counter
    cc = Counter(r["cat"] for r in out)
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print("\n总计 %d 条 -> %s" % (len(out), OUT))
    print("分类分布:", dict(cc))
    print("有独立提示词: %d 条" % sum(1 for r in out if r["prompt"] and r["prompt"] != r["title"]))
    with open(os.path.join(CACHE, "jimeng_cidmap.json"), "w", encoding="utf-8") as f:
        json.dump(cid2cat, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
