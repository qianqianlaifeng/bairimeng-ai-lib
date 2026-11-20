#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
抓取即梦(jimeng.jianying.com)探索页的图片作品: 提示词 + 原图URL + 时间。

无需登录/Cookie: 探索页公开可见, 用 Playwright 打开页面、点图片分类,
拦截 get_explore 接口响应即可拿到完整数据(a_bogus 签名由页面 JS 自己生成)。

用法:
  python tools/fetch_jimeng.py                 # 抓到 .cache/jimeng_raw.json
  python tools/fetch_jimeng.py --max-scroll 8  # 每个分类多滚几屏
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
# 有图片(item_type 9)的分类。点 category_name 即可拿到该分类的图片流。
IMG_CATS = ["平面设计", "电商", "动画动漫", "影视作品"]


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-scroll", type=int, default=6,
                    help="每个分类最多滚动次数(每次约20条), 默认6")
    ap.add_argument("--cats", default="", help="覆盖分类列表, 逗号分隔")
    return ap.parse_args()


def extract(item):
    """从一条探索页 item 提取可用字段, 非图片返回 None。
    2026-11-20 实测: 图片分类的流已从 get_explore(effect_type=9) 迁到
    /mweb/v1/feed(effect_type=209), 两个接口都要认; 字段结构相同。"""
    ca = item.get("common_attr") or {}
    if ca.get("effect_type") not in (9, 209):   # 9/209 = 图片, 210 = 短剧/视频
        return None
    ap = item.get("aigc_image_params") or {}
    t2i = ap.get("text2image_params") or {}
    prompt = (t2i.get("prompt") or ap.get("prompt") or "").strip()
    cmap = ca.get("cover_url_map") or {}
    # 优先 1080, 退而求其次取最大的可用图
    cover = cmap.get("1080") or cmap.get("720") or cmap.get("480") or ca.get("cover_url") or ""
    if not cover:
        return None
    title = (ca.get("title") or "").strip()
    if not title:
        title = prompt[:36].replace("\n", " ")
    author = (item.get("author") or {}).get("name") or ""
    stat = item.get("statistic") or {}
    return {
        "id": "jm-" + str(ca.get("id") or ca.get("effect_id") or ""),
        "title": title,
        "prompt": prompt or title,
        "cat": "",                 # 由调用方按分类填
        "author": author,
        "cover": cover,
        "ctime": ca.get("create_time") or 0,
        "digg": stat.get("digg_count") or 0,
    }


def main():
    args = parse_args()
    cats = [c.strip() for c in args.cats.split(",") if c.strip()] or IMG_CATS
    os.makedirs(CACHE, exist_ok=True)

    from playwright.sync_api import sync_playwright

    captured = {}

    def on_response(resp):
        # 旧接口 get_explore 与新接口 /mweb/v1/feed 都拦(图片流已迁到 feed)
        if "get_explore?" in resp.url or "/mweb/v1/feed" in resp.url:
            try:
                items = resp.json().get("data", {}).get("item_list", [])
                if items:
                    captured.setdefault("items", [])
                    captured["items"] = captured["items"] + items
            except Exception:
                pass

    all_rows = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True, timeout=30000)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("response", on_response)
        try:
            page.goto(EXPLORE_URL, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            print("打开页面超时(可能已加载):", str(e)[:80])
        # 等分类栏真正渲染出来(写死 sleep 6s 在网络慢时会扑空, 实测过)
        try:
            page.get_by_text(cats[0], exact=True).first.wait_for(state="visible", timeout=30000)
        except Exception:
            print("!! 分类栏 30s 未出现, 页面可能被风控或改版")
        time.sleep(3)

        for cat in cats:
            loc = page.get_by_text(cat, exact=True)
            try:
                loc.first.wait_for(state="visible", timeout=15000)
            except Exception:
                print("!! 找不到分类按钮:", cat)
                continue
            captured.clear()
            try:
                loc.first.click(timeout=6000)
                time.sleep(4)
            except Exception as e:
                print("!! 点击失败", cat, str(e)[:60])
                continue
            # 首屏那批先收进来(原来只收滚动后的批次, 每个分类丢最前 ~20 条)
            for it in (captured.get("items") or []):
                row = extract(it)
                if row:
                    row["cat"] = "jimeng-" + cat
                    all_rows.setdefault(row["id"], row)
            got = len(all_rows)
            # 滚动加载更多
            idle = 0
            for s in range(args.max_scroll):
                captured.clear()
                page.mouse.wheel(0, 2600)
                time.sleep(2.2)
                batch = captured.get("items") or []
                before = got
                for it in batch:
                    row = extract(it)
                    if row:
                        row["cat"] = "jimeng-" + cat
                        all_rows.setdefault(row["id"], row)
                        got += 1
                if got == before:
                    idle += 1
                    if idle >= 2:
                        break
                else:
                    idle = 0
            # 最后把首屏那批也收进来
            for it in (captured.get("items") or []):
                row = extract(it)
                if row:
                    row["cat"] = "jimeng-" + cat
                    all_rows.setdefault(row["id"], row)
            print("分类[%s] 累计 %d 条" % (cat, len(all_rows)))
        browser.close()

    rows = sorted(all_rows.values(), key=lambda r: r.get("ctime") or 0, reverse=True)
    if not rows and os.path.exists(OUT):
        # 一条没抓到(风控/改版/断网): 别拿空列表覆盖上一轮的好数据
        print("!! 本轮 0 条, 保留旧缓存不覆盖:", OUT)
        return
    json.dump(rows, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    with_prompt = sum(1 for r in rows if r["prompt"] and r["prompt"] != r["title"])
    print("\n总计 %d 条 -> %s" % (len(rows), OUT))
    print("有独立提示词: %d 条" % with_prompt)
    if rows:
        print("样例:", rows[0]["title"][:30], "|", rows[0]["cover"][:60])


if __name__ == "__main__":
    main()
