#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""就地修复分片里"畸形参考图路径"。

背景: 原始提示词里偶见 `https://host/https://host/path` 这种畸形地址,
旧解析把整段当路径, 于是分片里出现了
`/m/v/https://youchuan-imagine.../webp/xxx` —— 域名被带出去了。

本脚本对 app/data 下的 gal_*/video_* 分片逐条扫描:
  - 嵌套 refs 里的路径含 `://` 或来源痕迹  -> 用 url_path 重新解析并替换
  - 解析不出来的 -> 直接删掉该参考图
幂等: 修好的再跑不会变。

用法: python fix_refs.py [数据目录]
"""
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_gal import url_path, LEAK_RE  # noqa: E402

OUTDIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "app", "data")
REF_OK = re.compile(r"^/m/[a-z0-9]+/.+$", re.I)


def fix_one(u):
    """返回修好的路径; 修不出来返回 ""。"""
    if not u:
        return ""
    if REF_OK.match(u) and "://" not in u and not LEAK_RE.search(u):
        return u
    # 尝试重新解析: 补回协议头再交给 url_path
    cand = u
    if not re.match(r"^https?://", cand):
        m = re.search(r"https?://(\S+)$", cand)
        if m:
            cand = m.group(0)
        else:
            # 形如 /m/v/https://host/path —— 取 /m/<代号>/ 之后的部分
            m2 = re.match(r"^/m/([a-z0-9]+)/(.+)$", cand, re.I)
            if m2:
                rest = m2.group(2)
                cand = rest if re.match(r"^https?://", rest) else "https://" + rest
            else:
                return ""
    tok, path = url_path(cand)
    if tok and path and "://" not in path and not LEAK_RE.search(path):
        return "/m/%s/%s" % (tok, path)
    return ""


def main():
    files = (sorted(glob.glob(os.path.join(OUTDIR, "gal_*.json")))
             + sorted(glob.glob(os.path.join(OUTDIR, "video_*.json"))))
    nfix = ndrop = nfile = 0
    for p in files:
        d = json.load(open(p, encoding="utf-8"))
        changed = False
        for r in d:
            if len(r) > 6 and isinstance(r[6], list):
                new = []
                for it in r[6]:
                    u = it[1] if isinstance(it, (list, tuple)) and len(it) > 1 else ""
                    good = fix_one(u)
                    if good:
                        if good != u:
                            nfix += 1
                            changed = True
                        new.append([it[0], good])
                    else:
                        ndrop += 1
                        changed = True
                if changed:
                    r[6] = new
        if changed:
            json.dump(d, open(p, "w", encoding="utf-8"),
                      ensure_ascii=False, separators=(",", ":"))
            nfile += 1
            print("修复 %s" % os.path.relpath(p, HERE))
    print("就地修复完成 | 改写路径 %d | 丢弃无法解析 %d | 涉及分片 %d"
          % (nfix, ndrop, nfile))


if __name__ == "__main__":
    main()
