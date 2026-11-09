#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""黑金轮播改用「最新收录」图片 + 对外文案中性化。

在每日刷新链路里必须排在 build_oi / build_wf / build_catpack / build_kook 之后
（那几个脚本会重写 manifest.oiHero 和分类包），并且排在 DATA_VER 计算之前。

- 轮播数据从 kook_image_*.json 取：按发布时间倒序，三个分类轮流挑，
  保证 Gpt Image / 瑶光 / 如梦似幻 的最新作品都出现在轮播里。
- 数据里残留的来源字样统一换成中性名，站内任何位置都不暴露出处。
"""
import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.environ.get("GAL_OUTDIR") or os.path.join(ROOT, "data")
MANI = os.path.join(DATA, "manifest.json")
NEUTRAL = "灵感画廊"
HERO_N = 12


def read(p):
    with open(p, encoding="utf-8") as f:
        text = f.read()
    return json.loads(text), text


def write(p, obj, old_text):
    # 原文件是紧凑还是带空格，照原样写回，避免制造大段无意义 diff
    sep = (", ", ": ") if (', "' in old_text[:500] or '": ' in old_text[:500]) else (",", ":")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=sep)


def looks_like_source(s):
    if not isinstance(s, str):
        return False
    t = s.strip()
    # 只认真正的来源标签；作者名里恰好带 kook 字样的不能误伤
    return t.upper().startswith("KOOK") or "灵绘库" in t or t == NEUTRAL


def neutralize_data():
    """把分片/首屏包里第 5 列（画面描述）的来源字样换成中性名。"""
    n = 0
    for p in sorted(glob.glob(os.path.join(DATA, "*.json"))):
        if p == MANI:
            continue
        try:
            obj, old = read(p)
        except Exception:
            continue
        if not isinstance(obj, list):
            continue
        changed = False
        for r in obj:
            if (isinstance(r, list) and len(r) >= 5
                    and str(r[0]).startswith("kook-") and looks_like_source(r[4])):
                r[4] = NEUTRAL
                changed = True
                n += 1
        if changed:
            write(p, obj, old)
    return n


def build_hero():
    rows = []
    for p in sorted(glob.glob(os.path.join(DATA, "kook_image_*.json"))):
        try:
            rows.extend(read(p)[0])
        except Exception:
            pass
    # 有发布时间的按时间倒序；同一批内保持原顺序
    rows.sort(key=lambda r: (r[7] if len(r) > 7 and r[7] else ""), reverse=True)
    # 三个分类轮流挑，轮播里每类都有最新作品
    buckets, out, seen = {}, [], set()
    for r in rows:
        buckets.setdefault(r[3], []).append(r)
    keys = list(buckets)
    while len(out) < HERO_N and any(buckets[k] for k in keys):
        for k in keys:
            if not buckets[k]:
                continue
            r = buckets[k].pop(0)
            if r[0] in seen:
                continue
            seen.add(r[0])
            out.append({
                "id": r[0], "kind": "image", "cover": r[5],
                "title": r[1], "desc": r[4], "cat": r[3],
                "body": r[2], "time": r[7] if len(r) > 7 else "",
            })
            if len(out) >= HERO_N:
                break
    return out


def main():
    n = neutralize_data()
    m, old = read(MANI)
    # manifest 里的来源表 / 分类默认标签也一并中性化
    for k, v in (m.get("sources") or {}).items():
        if isinstance(v, list) and v and looks_like_source(v[0]):
            v[0] = NEUTRAL
    for k, v in (m.get("galCats") or {}).items():
        if isinstance(v, list) and v and looks_like_source(v[0]):
            v[0] = NEUTRAL
    m["oiHero"] = build_hero()
    m["uiVersion"] = "2026-11-09b"
    write(MANI, m, old)
    print("[hero] 中性化 %d 行 | 轮播最新图片 %d 张" % (n, len(m["oiHero"])))


if __name__ == "__main__":
    main()
