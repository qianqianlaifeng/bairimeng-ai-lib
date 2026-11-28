#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
抓取即梦(jimeng.jianying.com)探索页三个图片分类: 平面设计 / 电商 / 其他。

2026-11-28 修复(关键):
  旧版用 page.mouse.wheel() 滚动 —— 但即梦探索页的内容区是**内层滚动容器**
  (.scroll-container), 页面本身不滚动(body scrollHeight 恒等于视口高度)。
  于是 wheel 事件滚不动列表, 每个分类只截到首屏 6 屏的数据:
  「其他」只拿到 56 条, 而实际有 2000+ 条。

  修法: 直接把内层容器的 scrollTop 推到底, 并等 get_explore 返回新一页;
  连续 N 轮无新增就停。实测「其他」可拿 2158 条、「平面设计」2438 条、
  「电商」1617 条。

分类归属仍按 cid 白名单(两遍式):
  第1遍 逐个点击 页签/子分类, 记录"点击后新出现的 category_id" -> cid 归属;
  第2遍 逐个点击并滚动, 只收该分类自己 cid 的响应, 其余一律丢弃。
只收 effect_type == 9(真图片作品, 带 text2image_params.prompt)。

用法:
  python tools/fetch_jimeng.py                 # 默认每个分类滚到不再增长
  python tools/fetch_jimeng.py --max-rounds 60 # 限流调试
  python tools/fetch_jimeng.py --pages 30      # 只抓前 30 页/分类(快速刷新)
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

# 三个图片分类及其子分类(实测)
TARGETS = [
    ("平面设计", ["海报", "品牌设计"]),
    ("电商", ["电商头图", "商品展示"]),
    ("其他", []),
]
IMG_EFFECT_TYPES = (9,)

# 实测 cid 兜底(自动发现失败时用)
FALLBACK = {
    "19442373123084": "平面设计", "19442373124108": "平面设计",
    "19442373125132": "电商", "19442373126156": "电商",
    "11222": "其他",
}

# 滚到底: 找内容最深的内层滚动容器, 推到底
SCROLL_JS = """()=>{
  let best=null;
  document.querySelectorAll('div').forEach(e=>{
    if (e.scrollHeight > e.clientHeight + 200 && e.clientHeight > 200) {
      if (!best || (e.scrollHeight-e.clientHeight) > (best.scrollHeight-best.clientHeight)) best=e;
    }
  });
  if (best) { best.scrollTop = best.scrollHeight; return best.scrollHeight; }
  window.scrollTo(0, document.body.scrollHeight);
  return document.body.scrollHeight;
}"""


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-rounds", type=int, default=200,
                    help="每个分类最多滚动多少轮(每轮等 1 页)")
    ap.add_argument("--idle-stop", type=int, default=10,
                    help="连续多少轮没有新增就认为到底")
    ap.add_argument("--pages", type=int, default=0,
                    help="只抓每个分类的前 N 页(0=滚到底)")
    ap.add_argument("--only", default="",
                    help="只抓指定分类(逗号分隔, 如 电商,其他); 结果合并进已有缓存")
    return ap.parse_args()


def extract(item, cat):
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
        "cat": "jimeng-" + cat,
    }


def click_text(page, name, ymin, ymax, xmin=0):
    return page.evaluate(
        """(a)=>{const [n,lo,hi,xm]=a;
          const els=[...document.querySelectorAll('span,button,a,div')].filter(e=>(e.innerText||'').trim()===n);
          for(const e of els){const r=e.getBoundingClientRect();
            if(r.y>lo&&r.y<hi&&r.x>=xm&&r.width>5){e.click();return true;}}
          return false;}""",
        [name, ymin, ymax, xmin])


def main():
    args = parse_args()
    os.makedirs(CACHE, exist_ok=True)
    from playwright.sync_api import sync_playwright

    req_cids = []
    resp_by_cid = {}
    page_meta = {}      # cid -> 已合并页数

    def on_request(req):
        if "get_explore" not in req.url:
            return
        try:
            b = json.loads(req.request.post_data) if req.request.post_data else {}
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
        data = d.get("data", {}) or {}
        items = data.get("item_list", []) or []
        if items:
            resp_by_cid.setdefault(str(cid), []).extend(items)
            page_meta[str(cid)] = page_meta.get(str(cid), 0) + 1

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True, timeout=40000)

        def new_page():
            ctx = browser.new_context(viewport={"width": 1440, "height": 1000},
                                      user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                                  "Chrome/120.0.0.0 Safari/537.36"))
            pg = ctx.new_page()
            pg.on("request", on_request)
            pg.on("response", on_response)
            # 连开几个上下文时站点会限速, goto 偶尔 60s 超时 -> 退避重试
            last_err = None
            for attempt in range(4):
                try:
                    pg.goto(EXPLORE_URL, wait_until="domcontentloaded", timeout=90000)
                    last_err = None
                    break
                except Exception as e:
                    last_err = e
                    print("  打开超时(第%d次), 退避 %ds" % (attempt + 1, 15 * (attempt + 1)))
                    time.sleep(15 * (attempt + 1))
            if last_err:
                raise last_err
            try:
                pg.get_by_text("平面设计", exact=True).first.wait_for(state="visible", timeout=60000)
            except Exception:
                print("!! 分类栏 60s 未出现, 可能被风控")
            time.sleep(5)
            return ctx, pg

        # ---------- 第1遍: 发现 cid -> 分类 ----------
        cid2cat = {}
        ctx, page = new_page()
        for tab, subs in TARGETS:
            for sub in ([None] + list(subs)):
                before = set(req_cids)
                ok = click_text(page, tab, 40, 140) if sub is None else click_text(page, sub, 95, 200)
                time.sleep(3)
                for c in set(req_cids) - before:
                    cid2cat.setdefault(c, tab)
        ctx.close()
        for c, cat in FALLBACK.items():
            cid2cat.setdefault(c, cat)
        print("cid -> 分类:", json.dumps(cid2cat, ensure_ascii=False))

        # ---------- 第2遍: 每个分类各开一个新页面滚到底 ----------
        # 切换页签复用一个页面时, 列表经常没真正重置(实测「电商」切换后 0 页),
        # 所以每个分类用独立浏览器上下文, 保证从该分类第一页重新加载。
        rows = {}
        only = [x.strip() for x in args.only.split(",") if x.strip()]
        for tab, subs in TARGETS:
            if only and tab not in only:
                continue
            want = {c for c, cat in cid2cat.items() if cat == tab}
            before_pages = {c: page_meta.get(c, 0) for c in want}
            ctx, page = new_page()
            # 只点主分类: 点过子分类后, 滚动加载的是"子分类的游标", 主分类会少拿
            # 一大截(实测平面设计 1434 vs 2438)。子分类本身是主分类的子集, 不需要单独抓。
            ok = click_text(page, tab, 40, 140)
            time.sleep(4.0)
            idle = 0
            rounds = 0
            last_got = 0
            for i in range(args.max_rounds):
                rounds = i + 1
                page.evaluate(SCROLL_JS)
                time.sleep(1.0)
                now = sum(page_meta.get(c, 0) - before_pages.get(c, 0) for c in want)
                if now == last_got:
                    idle += 1
                    if idle >= args.idle_stop:
                        break
                else:
                    idle = 0
                    last_got = now
                if args.pages and now >= args.pages:
                    break
            got_pages = sum(page_meta.get(c, 0) - before_pages.get(c, 0) for c in want)
            uniq = set()
            for c in want:
                for it in resp_by_cid.get(c, []):
                    r = extract(it, tab)
                    if r:
                        r["cid"] = c
                        rows[r["id"]] = r
                        uniq.add(r["id"])
            print("分类[%-4s] click=%s 滚动%d轮 拉页%d 唯一图%d (cid %s)"
                  % (tab, ok, rounds, got_pages, len(uniq), sorted(want)))
            ctx.close()
        browser.close()

    out = sorted(rows.values(), key=lambda r: (r.get("ctime") or 0), reverse=True)

    # 分分类落盘: 分批抓(规避站点限速)时, 各分类互不覆盖, 最后再合并。
    if only:
        from collections import Counter as _C
        for tab in only:
            part = [r for r in out if r["cat"] == "jimeng-" + tab]
            fp = os.path.join(CACHE, "jimeng_part_%s.json" % tab)
            json.dump(part, open(fp, "w", encoding="utf-8"), ensure_ascii=False)
            print("已落盘 %s: %d 条 -> %s" % (tab, len(part), fp))
        out = [r for r in out if r["cat"].replace("jimeng-", "") in only]

    if not out and os.path.exists(OUT):
        print("!! 本轮 0 条, 保留旧缓存")
        return

    bad = [r for r in out if r.get("cid") not in cid2cat]
    if bad:
        print("!! 剔除无归属 %d 条" % len(bad))
        out = [r for r in out if r.get("cid") in cid2cat]

    from collections import Counter
    cc = Counter(r["cat"] for r in out)
    # 增量合并: 探索页只保留近期作品, 已下线但仍在库里的历史条目保留下来,
    # 否则每次刷新都会让库缩水(用户看到的"怎么越来越少")。
    old = {}
    if os.path.exists(OUT):
        try:
            for r in json.load(open(OUT, encoding="utf-8")):
                old[r["id"]] = r
        except Exception:
            old = {}
    fresh = {r["id"]: r for r in out}
    merged = dict(old)
    merged.update(fresh)          # 新抓的覆盖旧记录(签名/标题可能更新)
    out = sorted(merged.values(), key=lambda r: (r.get("ctime") or 0), reverse=True)

    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    print("\n本轮抓到 %d 条 (其中历史保留 %d 条) -> %s"
          % (len(fresh), len(out) - len(fresh), OUT))
    print("分类分布:", dict(Counter(r["cat"] for r in out)))
    print("有独立提示词: %d 条" % sum(1 for r in out if r["prompt"] and r["prompt"] != r["title"]))
    with open(os.path.join(CACHE, "jimeng_cidmap.json"), "w", encoding="utf-8") as f:
        json.dump(cid2cat, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
