#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""同步「最新收录」三类作品：新作品自动进来，提示词自动拉全。

源站把这三类作品的提示词设成"受保护"，列表接口只给约 24 字预览，
全文要走登录态接口。所以本脚本需要一份登录 Cookie，优先级：

  1) 环境变量 KOOK_COOKIE（GitHub Actions 里来自 Secret，不落仓库）
  2) 本机临时文件 %TEMP%/bm-login-cookie.txt（「一键登录.bat」导出的）

做的事：
  - 拉源站图片列表（分页 200/页），跟 data/kook_image_*.json 里已有的比对；
  - 新作品的封面图下到 media/kook/<id>.webp（图床本身就是 webp 缩略图，不用转码）；
  - 新作品、以及"只有预览没有全文"的旧行，走 /site-user/api/images/<id>/full-prompt 拉全文；
  - 全部行按发布时间倒序重排，重新切成 100 条/片（与前端分片顺序一致）；
  - 顺手重写这三类的首屏包 cp_<hash>.json（取每类最新的 120 条）。
  - 其余 manifest 计数交给 tools/build_kook.py 与 tools/update_hero.py。

Cookie 失效（401/403）时只报警不改数据，退出码 0，免得把每日刷新链路跑红。

用法：
  python tools/kook_sync.py --dry-run     # 只看会新增/更新多少条，不写文件
  python tools/kook_sync.py               # 真同步
"""
import argparse
import glob
import hashlib
import json
import os
import re
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.environ.get("GAL_OUTDIR") or os.path.join(ROOT, "data")
MEDIA = os.path.join(ROOT, "media", "kook")
BASE = "https://kookaigc.top"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
CAT_MAP = {
    "gpt-image": "kook-gpt-image",
    "yaoguang": "kook-yaoguang",
    "rumengsihuan": "kook-rumengsihuan",
}
NEUTRAL = "灵感画廊"
SHARD_SIZE = 100
PACK_LIMIT = 120
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
_lock = threading.Lock()


def read_cookie():
    c = (os.environ.get("KOOK_COOKIE") or "").strip()
    if c:
        return c
    p = os.path.join(os.environ.get("TEMP") or "/tmp", "bm-login-cookie.txt")
    if os.path.exists(p):
        return open(p, encoding="utf-8").read().strip()
    return ""


COOKIE = read_cookie()


def http(url, headers=None, tries=3, timeout=25):
    h = {"User-Agent": UA, "Referer": BASE + "/", "Cookie": COOKIE}
    h.update(headers or {})
    last = None
    for n in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h),
                                        timeout=timeout, context=ctx) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (401, 403):
                return e.code, e.read(), dict(e.headers)
        except Exception as e:
            last = e
        time.sleep(0.5 * (n + 1))
    return 0, str(last).encode(), {}


def get_json(url, headers=None):
    st, body, _ = http(url, headers)
    if st != 200:
        return None
    try:
        return json.loads(body.decode("utf-8", "ignore"))
    except Exception:
        return None


def short(t, n=26):
    s = re.sub(r"\s+", " ", str(t or "")).strip()
    return s if len(s) <= n else s[:n] + "…"


def fetch_list():
    home = get_json(BASE + "/api/home") or {}
    tok = home.get("public_api_token") or ""
    out, page = [], 1
    while page <= 60:
        j = get_json(BASE + "/api/images?page=%d&page_size=200" % page,
                     {"X-Public-Access-Token": tok, "Accept": "application/json"})
        if not j:
            break
        imgs = j.get("images") or []
        out.extend(imgs)
        if not j.get("has_more") or not imgs:
            break
        page += 1
    return out


def fetch_full(iid):
    """登录态接口取完整提示词；拿不到返回 None。"""
    if not COOKIE:
        return None
    st, body, _ = http(BASE + "/site-user/api/images/%s/full-prompt" % iid,
                       {"Accept": "application/json"})
    if st != 200:
        return None
    try:
        p = (json.loads(body.decode("utf-8", "ignore")) or {}).get("prompt") or ""
    except Exception:
        return None
    return p.strip() or None


def fetch_cover(iid, url, dry=False):
    dst = os.path.join(MEDIA, iid + ".webp")
    if os.path.exists(dst) and os.path.getsize(dst) > 1024:
        return True
    if dry or not url:
        return False
    st, body, _ = http(url, tries=2, timeout=40)
    if st == 200 and len(body) > 1024:
        os.makedirs(MEDIA, exist_ok=True)
        with open(dst, "wb") as f:
            f.write(body)
        return True
    return False


def load_rows():
    rows = []
    for p in sorted(glob.glob(os.path.join(DATA, "kook_image_*.json"))):
        try:
            rows.extend(json.load(open(p, encoding="utf-8")))
        except Exception:
            pass
    return rows


def needs_full(src):
    """这条要不要去拉全文：受保护 + 只有预览（预览自带省略号）。"""
    prev = str(src.get("prompt_preview") or "")
    if not src.get("prompt_protected"):
        return False
    return prev.endswith("...") or prev.endswith("…")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    imgs = fetch_list()
    if not imgs:
        print("[kook] 列表拉取失败，跳过")
        return 0
    old = {str(r[0])[5:]: r for r in load_rows() if isinstance(r, list) and len(r) >= 8}
    src = {str(x.get("id")): x for x in imgs if CAT_MAP.get(x.get("primary_category_key"))}
    new_ids = [i for i in src if i not in old]
    # 旧行里"正文还是预览长度"的，说明当初没拿到全文（Cookie 失效/还没登录），这次补上
    refill = [i for i in src if i in old and needs_full(src[i])
              and len(str(old[i][2] or "")) <= 32]
    print("[kook] 源站 %d 条 | 已收录 %d 条 | 新增 %d 条 | 待补全文 %d 条%s"
          % (len(src), len(old), len(new_ids), len(refill), "（干跑）" if args.dry_run else ""))

    if not new_ids and not refill:
        if not args.dry_run:
            rewrite(load_rows(), src)
        return 0

    # 新作品：补封面 + 补全文
    got_full, no_full = 0, 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {}
        for i in new_ids:
            s = src[i]
            futs[ex.submit(fetch_cover, i, s.get("url"), args.dry_run)] = ("cover", i)
            futs[ex.submit(fetch_full, i)] = ("full", i)
        results = {}
        for f, (kind, i) in futs.items():
            ok = f.result()
            results[(kind, i)] = ok
    for i in refill:
        if fetch_full(i):
            results[("full", i)] = True

    rows_new = []
    for i in new_ids:
        s = src[i]
        full = results.get(("full", i))
        prev = str(s.get("prompt_preview") or "").rstrip(".…").strip()
        body = full or prev
        got_full += 1 if full else 0
        no_full += 0 if full else 1
        rows_new.append([
            "kook-" + i,
            short(s.get("title") or body),
            body,
            CAT_MAP[s["primary_category_key"]],
            NEUTRAL,
            "media/kook/%s.webp" % i,
            [],
            str(s.get("upload_time") or "")[:10],
        ])
    for i in refill:
        full = results.get(("full", i))
        if full and i in old:
            old[i][2] = full
            old[i][1] = short(old[i][1] or full)
            got_full += 1

    allrows = list(old.values()) + rows_new
    print("[kook] 写入 %d 行（新增 %d，全文到手 %d，仍只有预览 %d）"
          % (len(allrows), len(rows_new), got_full, no_full))
    if args.dry_run:
        print("[kook] 干跑结束，未改动文件")
        return 0
    rewrite(allrows, src)
    return 0


def rewrite(rows, src):
    """按发布时间倒序重排 + 重切分片 + 重写三类首屏包。"""
    def tkey(r):
        i = str(r[0])[5:]
        return str(src.get(i, {}).get("upload_time") or (r[7] if len(r) > 7 else ""))
    rows.sort(key=tkey, reverse=True)

    for p in glob.glob(os.path.join(DATA, "kook_image_*.json")):
        os.remove(p)
    n = max(1, (len(rows) + SHARD_SIZE - 1) // SHARD_SIZE)
    for k in range(n):
        chunk = rows[k * SHARD_SIZE:(k + 1) * SHARD_SIZE]
        with open(os.path.join(DATA, "kook_image_%d.json" % k), "w", encoding="utf-8") as f:
            json.dump(chunk, f, ensure_ascii=False, separators=(",", ":"))

    by_cat = {}
    for r in rows:
        by_cat.setdefault(r[3], []).append(r)
    for cat, items in by_cat.items():
        name = "cp_" + hashlib.md5(cat.encode("utf-8")).hexdigest()[:10]
        with open(os.path.join(DATA, name + ".json"), "w", encoding="utf-8") as f:
            json.dump(items[:PACK_LIMIT], f, ensure_ascii=False, separators=(",", ":"))

    # manifest 里的分类计数改成绝对值(不是累加), 这样定时重复跑也不会越加越多
    mp = os.path.join(DATA, "manifest.json")
    try:
        man = json.load(open(mp, encoding="utf-8"))
        cc = man.setdefault("catCounts", {}).setdefault("gal", {})
        for cat, items in by_cat.items():
            cc[cat] = len(items)
        man["kookImage"] = len(rows)
        man.setdefault("chunks", {})["kook_image"] = n
        with open(mp, "w", encoding="utf-8") as f:
            json.dump(man, f, ensure_ascii=False, separators=(",", ":"))
    except Exception as e:
        print("[kook] manifest 更新失败: %s" % e)

    # 轮播跟着换成最新一批（复用中性化 + 选片逻辑）
    try:
        import subprocess
        subprocess.run([sys.executable, os.path.join(HERE, "update_hero.py")], check=False)
    except Exception as e:
        print("[kook] 轮播刷新失败: %s" % e)

    print("[kook] 分片 %d 个 | 首屏包 %d 类 | 最新一条 %s"
          % (n, len(by_cat), rows[0][7] if rows else "-"))


if __name__ == "__main__":
    sys.exit(main())
