#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
把 app/data 下所有 /m/<代号>/<路径> 形式的媒体地址改写成各图床的直连地址。

背景: 原先图片都走 Worker 代理域(img.fakashop.ccwu.cc), 但该域名在国内被
      针对性 SNI 阻断(IP 通、TLS 握手即 RST), 导致全站图片加载失败。
      各图床主机本身国内可达, 所以改为直连。

规则(与 worker/worker.js 的 RESIZE 保持一致):
  i -> IMG_HOST_I + 路径 + ?x-oss-process=image/resize,w_600/format,webp/quality,q_80
  q -> IMG_HOST_Q + 路径 + ?imageMogr2/thumbnail/600x/format/webp/quality/80
  v -> IMG_HOST_V + 路径 + ?x-oss-process=image/resize,w_600/format,webp/quality,q_80
       (视频 .mp4/.webm 等不加缩图参数, 原样透传)
  w -> IMG_HOST_W + 路径(原样)
  o -> 已是完整直连地址, 不处理

幂等: 已经是 http(s):// 开头的值直接跳过。
"""
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "app", "data")

RESIZE = {
    "i": "?x-oss-process=image/resize,w_600/format,webp/quality,q_80",
    "v": "?x-oss-process=image/resize,w_600/format,webp/quality,q_80",
    "q": "?imageMogr2/thumbnail/600x/format/webp/quality/80",
    "w": "",
}
VIDEO_RE = re.compile(r"\.(mp4|webm|mov|m4v)$", re.I)
PATH_RE = re.compile(r"^/m/([a-z0-9]+)/(.+)$", re.I)


def load_hosts():
    s = json.load(open(os.path.join(ROOT, "secrets.json"), encoding="utf-8"))
    out = {
        "i": s.get("IMG_HOST_I") or "",
        "q": s.get("IMG_HOST_Q") or "",
        "v": s.get("IMG_HOST_V") or "",
        "w": s.get("IMG_HOST_W") or "",
    }
    miss = [k for k in ("i", "q", "v") if not out[k]]
    if miss:
        sys.exit("!! secrets.json 缺少 IMG_HOST_%s" % ", IMG_HOST_".join(miss).upper())
    return out


def rewrite(u, hosts):
    """单条地址改写。非 /m/ 形式或已是完整地址则原样返回。"""
    if not isinstance(u, str) or not u.startswith("/m/"):
        return u
    m = PATH_RE.match(u)
    if not m:
        return u
    code = m.group(1).lower()
    host = hosts.get(code) or ""
    if not host:
        return u
    rel = m.group(2)
    clean = rel.split("?")[0]
    is_video = bool(VIDEO_RE.search(clean))
    suffix = "" if is_video else RESIZE.get(code, "")
    return "https://" + host + "/" + clean + suffix


def walk(o, hosts, stat):
    if isinstance(o, str):
        n = rewrite(o, hosts)
        if n != o:
            stat[0] += 1
        return n
    if isinstance(o, list):
        return [walk(x, hosts, stat) for x in o]
    if isinstance(o, dict):
        return {k: walk(v, hosts, stat) for k, v in o.items()}
    return o


def main():
    hosts = load_hosts()
    print("图床: i=%s | q=%s | v=%s | w=%s" % (hosts["i"], hosts["q"], hosts["v"], hosts["w"] or "(空)"))
    files = sorted(glob.glob(os.path.join(DATA, "*.json")))
    files = [f for f in files if os.path.basename(f) != "manifest.json"]
    total = [0]
    changed_files = []
    for f in files:
        try:
            o = json.load(open(f, encoding="utf-8"))
        except Exception as e:
            print("  跳过 %s: %s" % (os.path.basename(f), e))
            continue
        before = total[0]
        o = walk(o, hosts, total)
        if total[0] != before:
            json.dump(o, open(f, "w", encoding="utf-8"), ensure_ascii=False)
            changed_files.append((os.path.basename(f), total[0] - before))
    print("改写完成: %d 条媒体, 涉及 %d 个文件" % (total[0], len(changed_files)))
    if changed_files:
        print("  文件明细(前 12):", changed_files[:12])


if __name__ == "__main__":
    main()
