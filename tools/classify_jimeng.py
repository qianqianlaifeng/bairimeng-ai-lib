#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
校正即梦作品的三分类(平面设计 / 电商 / 其他), 让图片与分类一致。

设计原则:
  以即梦官方页签为基准(平台本身按内容分好), 只做"高置信度"纠错,
  不用泛词("海报""广告""艺术"这类太泛, 会误伤), 只用专有名词。
  宁少改, 不乱改。

改判规则(按优先级):
  A. 菜谱/食谱/步骤教程/菜单排版        -> 平面设计
  B. 产品摄影/静物摄影/电商主图/详情页/棚拍/产品广告 -> 电商
  C. 海报设计/版式/字体/logo/品牌视觉/主视觉/三视图/
     画册/折页/易拉宝/信息图/包装设计/壁纸   -> 平面设计
  D. 真人写实摄影(且无设计/商品/插画元素)     -> 其他

用法:
  python tools/classify_jimeng.py             # 干跑: 统计 + 抽样
  python tools/classify_jimeng.py --apply     # 写回 .cache/jimeng_raw.json
"""
import os
import re
import json
import random
import argparse
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RAW = os.path.join(ROOT, ".cache", "jimeng_raw.json")

# A. 菜谱/教程排版稿
RECIPE = re.compile(
    r"菜谱|食谱|做法[:：]|食材[:：]|步骤\s*[1１一二]|步骤图|制作步骤|教程图|"
    r"步骤说明|菜单设计|烹饪步骤|手账风格|制作流程", re.I)

# B. 电商专有特征
ECOM_HARD = re.compile(
    r"产品摄影|产品广告|产品图|商品图|静物摄影|静物拍摄|电商主图|商品主图|"
    r"详情页|白底图|棚拍|产品展示|商品展示|产品特写|商业摄影|广告摄影|"
    r"电商头图|卖点图|促销图|产品静物|商品静物|产品海报|产品广告海报", re.I)

# C. 平面设计专有特征
DESIGN_HARD = re.compile(
    r"海报设计|宣传海报|活动海报|促销海报|插画海报|商业海报|新品海报|"
    r"杂志封面|书籍装帧|版式设计|排版设计|字体设计|书法字|毛笔字|"
    r"logo设计|标志设计|品牌设计|品牌视觉|视觉识别|主视觉|"
    r"三视图|角色设定图|设定图|画册|宣传册|折页|易拉宝|展架|"
    r"信息图|长图设计|界面设计|ui设计|包装设计|名片设计|菜单设计|"
    r"海报排版|版式|kv设计|字体海报|字体|海报", re.I)

# D. 真人写实
PORTRAIT_HARD = re.compile(
    r"人像摄影|写真|真人写实|写实摄影|美妆模特|模特特写|肖像照|证件照|"
    r"自拍|面部特写|大头近景|真人电影质感", re.I)

# 排除: 有这些就不是"单纯人像"
NOT_PURE = re.compile(
    r"海报|设计|排版|字体|logo|包装|产品|商品|静物|广告|插画|动漫|3d|建模|"
    r"水彩|油画|厚涂|手绘|线稿|素描|剪纸|国潮|IP形象|吉祥物|三视图|"
    r"脚本|分镜|去掉|改写|文案", re.I)


def classify(title, prompt, src_cat):
    src = str(src_cat or "").replace("jimeng-", "") or "其他"
    t = (title or "") + " " + (prompt or "")

    if RECIPE.search(t):
        return "平面设计", "recipe"
    if ECOM_HARD.search(t):
        return "电商", "ecom"
    if DESIGN_HARD.search(t):
        return "平面设计", "design"
    if PORTRAIT_HARD.search(t) and not NOT_PURE.search(t):
        return "其他", "portrait"
    return src, "keep"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--samples", type=int, default=4)
    args = ap.parse_args()

    rows = json.load(open(RAW, encoding="utf-8"))
    out, changed, reasons = [], 0, Counter()
    for r in rows:
        src = str(r.get("cat") or "jimeng-其他").replace("jimeng-", "")
        cat, why = classify(r.get("title"), r.get("prompt"), src)
        r2 = dict(r)
        r2["cat"] = "jimeng-" + cat
        r2["src_cat"] = "jimeng-" + src
        r2["why"] = why
        reasons[why] += 1
        if src != cat:
            changed += 1
        out.append(r2)

    cc = Counter(r["cat"] for r in out)
    print("总数 %d, 改判 %d 条 (%.1f%%)" % (len(out), changed, 100.0 * changed / max(1, len(out))))
    print("新分类分布:", dict(cc))
    print("改判依据:", dict(reasons))

    print("\n原页签 -> 新分类:")
    m = {}
    for r in out:
        m.setdefault(r["src_cat"], Counter())[r["cat"]] += 1
    for k in sorted(m):
        print("  %-16s %s" % (k, dict(m[k])))

    random.seed(11)
    print("\n抽样:")
    for cat in ("jimeng-平面设计", "jimeng-电商", "jimeng-其他"):
        pool = [r for r in out if r["cat"] == cat]
        print(" -- %s (%d 条)" % (cat.replace("jimeng-", ""), len(pool)))
        for r in random.sample(pool, min(args.samples, len(pool))):
            print("    %s | %s" % (r["title"][:24], (r["prompt"] or "")[:56].replace("\n", " ")))

    if args.apply:
        json.dump(out, open(RAW, "w", encoding="utf-8"), ensure_ascii=False)
        print("\n已写回:", RAW)
    else:
        print("\n(干跑, 未写回; 加 --apply 生效)")


if __name__ == "__main__":
    main()
