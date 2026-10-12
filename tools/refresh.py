#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
一键刷新「灵感画廊」数据并同步到站点。

流程: 登录拿新 token -> 全量抓取(游标分页) -> 转站点分片 -> 同步 manifest

用法:
  python refresh.py            # 完整刷新
  python refresh.py --pages 5  # 只抓 5 页(调试)

来源域名 / 密钥 / 账号统一由 sitecfg 提供(环境变量或 secrets.json), 本文件不含来源信息。
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sitecfg import SRC_BASE, SRC_AES_KEY, LEAK_RE, require  # noqa: E402

require(["SRC_BASE", "SRC_AES_KEY", "SRC_PHONE", "SRC_PASS", "IMG_HOST_I", "IMG_HOST_Q"])

CRED = os.environ.get("YC_CRED") or os.path.join(HERE, "secrets.json")
TOKEN_FILE = os.environ.get("YC_TOKEN_FILE") or os.path.join(HERE, ".token")
RAW = os.environ.get("GAL_RAW_DIR") or os.path.join(HERE, ".cache")
# 站点数据目录: 本仓库根目录下的 data/(仓库版), 或 app/data/(本地版)
DATA_DIR = os.environ.get("GAL_OUTDIR") or os.path.join(HERE, "app", "data")
MANIFEST = os.path.join(DATA_DIR, "manifest.json")

BASE = SRC_BASE
AES_KEY_HEX = SRC_AES_KEY.encode().hex()


def aes_encrypt(raw_password):
    """AES-256-ECB + PKCS7 -> Base64, 与前端 CryptoJS 行为一致。"""
    r = subprocess.run(
        ["openssl", "enc", "-aes-256-ecb", "-K", AES_KEY_HEX, "-nosalt", "-base64", "-A"],
        input=raw_password.encode("utf-8"), capture_output=True)
    if r.returncode != 0:
        raise RuntimeError("openssl 加密失败: " + r.stderr.decode("utf-8", "ignore"))
    return r.stdout.decode("utf-8").strip()


def curl(args, timeout=90):
    r = subprocess.run(["curl", "-s", "--max-time", str(timeout)] + args,
                       capture_output=True, text=True, encoding="utf-8", errors="ignore")
    try:
        return json.loads(r.stdout)
    except Exception:
        return {"code": -1, "_raw": (r.stdout or "")[:300]}


def login():
    c = json.load(open(CRED, encoding="utf-8")) if os.path.exists(CRED) else {}
    phone = c.get("SRC_PHONE") or c.get("phone") or os.environ.get("SRC_PHONE")
    password = c.get("SRC_PASS") or c.get("password") or os.environ.get("SRC_PASS")
    if not (phone and password):
        print("!! 缺少登录账号(配置 SRC_PHONE / SRC_PASS)"); sys.exit(1)
    body = json.dumps({
        "countryCode": "86", "loginAccountType": 0, "loginType": 1,
        "phone": phone, "password": aes_encrypt(password),
    }, ensure_ascii=False)
    d = curl([BASE + "/v1/login", "-H", "Content-Type: application/json",
              "-H", "Accept: application/json", "-d", body])
    tok = (d.get("data") or {}).get("token")
    if not tok:
        print("!! 登录失败:", json.dumps(d, ensure_ascii=False)[:300]); sys.exit(1)
    try:
        open(TOKEN_FILE, "w", encoding="utf-8").write(tok)
    except OSError:
        pass
    print("[1/4] 登录成功, token 长度", len(tok))
    return tok


def fetch_token():
    """优先复用未过期 token, 失效则重新登录。"""
    if os.path.exists(TOKEN_FILE):
        t = open(TOKEN_FILE, encoding="utf-8").read().strip()
        if t:
            d = curl([BASE + "/v1/jobs/discovery?limit=1", "-H", "Authorization: Bearer " + t])
            if d.get("code") == 200:
                print("[1/4] 复用已有 token")
                return t
    return login()


def crawl(token, max_pages=80):
    os.makedirs(RAW, exist_ok=True)
    seen, items, last = set(), [], None
    for p in range(max_pages):
        params = "" if last is None else "?" + urllib.parse.urlencode({"lastScore": last})
        d = curl([BASE + "/v1/jobs/discovery" + params,
                  "-H", "Authorization: Bearer " + token], timeout=120)
        if d.get("code") != 200:
            print("  第%d页 失败: %s" % (p + 1, str(d)[:120])); break
        data = d.get("data") or {}
        lst = data.get("list", [])
        if not lst:
            print("  第%d页 空列表, 结束" % (p + 1)); break
        new = 0
        for x in lst:
            if x.get("id") not in seen:
                seen.add(x["id"]); items.append(x); new += 1
        last = lst[-1].get("score")
        print("  第%d页: +%d (累计 %d)" % (p + 1, new, len(items)), flush=True)
        json.dump(items, open(os.path.join(RAW, "discovery.json"), "w", encoding="utf-8"),
                  ensure_ascii=False)
        if not data.get("hasMore"):
            break
        time.sleep(0.35)
    print("[2/4] 抓取完成: %d 条" % len(items))
    return len(items)


def build_and_sync():
    sys.path.insert(0, HERE)
    os.environ["GAL_RAW"] = os.path.join(RAW, "discovery.json")
    os.environ["GAL_OUTDIR"] = DATA_DIR
    os.environ["GAL_RAW_DIR"] = RAW
    import build_gal
    build_gal.main()
    print("[3/4] 分片生成完成")

    meta = json.load(open(os.path.join(RAW, "gal_meta.json"), encoding="utf-8"))
    man = json.load(open(MANIFEST, encoding="utf-8"))
    man.setdefault("catCounts", {})["gal"] = meta["counts"]
    man["galCats"] = meta["cats"]
    man["galCount"] = meta["total"]
    man.setdefault("chunks", {})["gal"] = meta["chunks"]
    man["totalCats"] = (len(man.get("cats", {})) + len(man.get("imageCats", {}))
                        + len(man.get("videoCats", {})) + len(man.get("galCats", {})))
    json.dump(man, open(MANIFEST, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("[4/4] manifest 已同步: galCount=%d chunks=%d galCats=%d"
          % (man["galCount"], man["chunks"]["gal"], len(man["galCats"])))


def verify():
    """确认分片结构正确、且提示词里无来源痕迹残留。"""
    import glob
    rows = leak_rows = badcover = 0
    for f in glob.glob(os.path.join(DATA_DIR, "gal_*.json")):
        for r in json.load(open(f, encoding="utf-8")):
            rows += 1
            # 封面允许出现路径, 但绝不能出现主机名
            if any(LEAK_RE.search(v) for i, v in enumerate(r) if isinstance(v, str) and i != 5):
                leak_rows += 1
            if r[5] and not re.match(r"^/m/[a-z0-9]+/.+$", r[5], re.I):
                badcover += 1
    print("自检 -> 条数 %d | 来源残留 %d | 封面格式异常 %d" % (rows, leak_rows, badcover))
    return rows, leak_rows, badcover


if __name__ == "__main__":
    pages = 80
    if "--pages" in sys.argv:
        pages = int(sys.argv[sys.argv.index("--pages") + 1])
    tok = fetch_token()
    crawl(tok, pages)
    build_and_sync()
    verify()
