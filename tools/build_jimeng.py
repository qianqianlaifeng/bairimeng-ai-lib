#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
把 .cache/jimeng_raw.json 转成前端 gal 分片格式(jimeng_gal_*.json)并并入 manifest。

行格式与 expandGal 一致: [id, title, body, cat, desc, cover, refs, time, portrait, gender]
  - body     = 完整提示词
  - cat      = jimeng-<分类名>(如 jimeng-平面设计)
  - desc     = 作者名
  - time     = 发布时间 YYYY-MM-DD(用于「日期最新」排序)
  - cover    = 即梦签名原图直链
  - portrait = 1 画面主体是人 / 0 不是(供「即梦·人像」用)
  - gender   = 'F' 女 / 'M' 男 / '' 认不出(多人、背影、剪影一律留空)

分类作为独立分组显示在分类栏(带 🆕 标记), 不混入原有中文分类。
另外产出「即梦·人像」首屏包 jimeng_portrait.json: 跨平面设计/电商/其他三个
分类收全部人像, 单独给 ♀/♂ 筛选用。人像/性别逐条判定见 jimeng_gender.py,
每天随抓取重算 —— 新增作品当天就会进人像分类, 不需要人工补。
可重复运行(幂等): 每轮重建 jimeng 分片并同步 manifest 计数。
"""
import os
import re
import sys
import json
import glob
import hashlib
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jimeng_gender  # noqa: E402  人像/性别判定(人工标签优先, 其次文案兜底)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.environ.get("GAL_OUTDIR") or os.path.join(ROOT, "data")
MANI = os.path.join(DATA, "manifest.json")
RAW = os.path.join(ROOT, ".cache", "jimeng_raw.json")
LABELS = os.path.join(HERE, "jimeng_visual_labels_by_id.json")
CHUNK = 600

CAT_ICON = {
    "jimeng-人像": ["即梦·人像", "👤"],
    "jimeng-平面设计": ["即梦·平面设计", "🆕"],
    "jimeng-电商": ["即梦·电商", "🛍️"],
    "jimeng-动画动漫": ["即梦·动漫", "🎬"],
    "jimeng-影视作品": ["即梦·影视", "🎞️"],
}


def ts_to_date(ts):
    try:
        ts = int(ts)
        if ts <= 0:
            return ""
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return ""


def cat_icon(cat):
    if cat in CAT_ICON:
        return CAT_ICON[cat]
    # 兜底: jimeng-XXX -> 即梦·XXX
    name = cat.split("-", 1)[-1] if "-" in cat else cat
    return ["即梦·" + name, "🆕"]


def main():
    if not os.path.exists(RAW):
        print("无 jimeng_raw.json, 请先运行 fetch_jimeng.py")
        return
    rows = json.load(open(RAW, encoding="utf-8"))
    if not rows:
        print("即梦数据为空, 跳过")
        return

    # ---- 视觉判定持久映射: 按作品ID强制回填已判定分类 ----
    # 每日刷新会重跑 fetch_jimeng.py, 它按官方页签打标, 会覆盖人工逐张判定的结果。
    # 这里以 jimeng_visual_labels_by_id.json 为最高优先级: 已判定的ID一律回填,
    # 只有本表没有的新增ID才用官方页签(fallback), 保证"图片与分类一致"不被刷新冲掉。
    label_map = {}
    if os.path.exists(LABELS):
        try:
            _d = json.load(open(LABELS, encoding="utf-8"))
            label_map = _d.get("labels") or {}
            print("已加载视觉判定映射: %d 条 (优先于官方页签)" % len(label_map))
        except Exception as e:
            print("!! 视觉判定映射读取失败, 退回官方页签:", str(e)[:80])
    overridden = 0

    # 转为 gal 行格式
    gal = []
    p_n = g_f = g_m = 0
    for r in rows:
        rid = r.get("id") or ("jm-" + hashlib.md5(((r.get("title") or "") + (r.get("cover") or "")).encode()).hexdigest()[:12])
        cat = r.get("cat") or "jimeng-其他"
        if rid in label_map:
            fixed = "jimeng-" + label_map[rid]
            if fixed != cat:
                overridden += 1
            cat = fixed
        prompt = r.get("prompt") or r.get("title") or ""
        title = r.get("title") or prompt[:36]
        desc = r.get("author") or ""
        cover = r.get("cover") or ""
        if not cover:
            continue
        # 人像 / 性别：人工逐张看图的标签优先，新作品用文案兜底（每天重算）
        portrait, gender = jimeng_gender.label_for(rid, title, prompt)
        if portrait:
            p_n += 1
            if gender == "F":
                g_f += 1
            elif gender == "M":
                g_m += 1
        else:
            gender = ""
        gal.append([
            rid,
            title, prompt, cat, desc, cover, [], ts_to_date(r.get("ctime")),
            portrait, gender
        ])
    if overridden:
        print("按视觉判定回填分类: %d 条" % overridden)
    if not gal:
        print("无有效行, 跳过")
        return

    # 按时间倒序(新在前)
    gal.sort(key=lambda x: x[7] or "", reverse=True)

    # 清理上一轮 jimeng 分片
    for f in glob.glob(os.path.join(DATA, "jimeng_gal_*.json")):
        os.remove(f)
    chunks = [gal[i:i + CHUNK] for i in range(0, len(gal), CHUNK)]
    for i, ch in enumerate(chunks):
        with open(os.path.join(DATA, "jimeng_gal_%d.json" % i), "w", encoding="utf-8") as f:
            json.dump(ch, f, ensure_ascii=False, separators=(",", ":"))

    # ---- 「即梦·人像」首屏包 ----
    # 人像是跨三个分类抽出来的虚拟分类：平面设计/电商/其他里都有人物图。
    # 单独出一个包，点「即梦·人像」不用等全部分片就能出图（和分类首屏包同机制）。
    portrait_rows = [r for r in gal if len(r) > 8 and r[8]]
    with open(os.path.join(DATA, "jimeng_portrait.json"), "w", encoding="utf-8") as f:
        json.dump(portrait_rows, f, ensure_ascii=False, separators=(",", ":"))

    # ---- 更新 manifest ----
    m = json.load(open(MANI, encoding="utf-8"))

    # 先扣掉上一轮 jimeng 计数(用 jimeng 分类键识别), 再加本轮
    gc = m.setdefault("catCounts", {}).setdefault("gal", {})
    old_keys = [k for k in gc if str(k).startswith("jimeng-")]
    old_total = sum(gc[k] for k in old_keys)
    for k in old_keys:
        del gc[k]
    m["galCount"] = max(0, (m.get("galCount") or 0) - old_total)

    gcat = m.setdefault("galCats", {})
    for k in list(gcat):
        if str(k).startswith("jimeng-"):
            del gcat[k]

    from collections import Counter
    cc = Counter(r[3] for r in gal)
    for cat, n in cc.items():
        gcat[cat] = cat_icon(cat)
        gc[cat] = n

    m["galCount"] = (m.get("galCount") or 0) + len(gal)
    ch_map = m.setdefault("chunks", {})
    ch_map["jimeng_gal"] = len(chunks)
    m.setdefault("sources", {})["jimeng"] = ["即梦AI 创作社区", "https://jimeng.jianying.com/ai-tool/explore"]
    m["jimengGalCount"] = len(gal)

    # ---- 人像 / 性别 计数 ----
    # 「即梦·人像」是跨分类的虚拟分类（条目本身仍属于平面设计/电商/其他），
    # 所以只记人像口径的计数，不并进 galCats / catCounts，避免总数被重复累加。
    m["jimengPortraitCount"] = p_n
    m["jimengPortraitF"] = g_f
    m["jimengPortraitM"] = g_m
    m["jimengPortraitPack"] = "jimeng_portrait"

    json.dump(m, open(MANI, "w", encoding="utf-8"), ensure_ascii=False)
    print("jimeng 分片 %d 个 / %d 条, 分类: %s" % (len(chunks), len(gal), dict(cc)))
    print("人像 %d 条 (♀%d / ♂%d / 未判 %d)" % (p_n, g_f, g_m, p_n - g_f - g_m))
    print("galCount=%d (扣旧%d 加新%d)" % (m["galCount"], old_total, len(gal)))


if __name__ == "__main__":
    main()
