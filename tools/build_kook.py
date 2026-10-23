#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
把 kook_image 分片的分类键并入 manifest(幂等)。kook 是一次性快照: 只合并, 不抓取。

为什么需要本脚本(nightly 链路位置: refresh.py -> ... -> build_wf -> build_catpack -> **build_kook** -> 同步 DATA_VER):
  - tools/refresh.py 会整体重置 galCats / catCounts.gal / galCount(只含原画廊 gal);
  - tools/build_catpack.py 会整体覆盖 galCatPack(只含它读到的 wf_image/oi_gal/gal 分类);
  - wf 的键由 build_wf.py 加回, 而 kook 没有抓取脚本 —— 本脚本补上合并者角色,
    把 kook 的三个模型分类键(标签/计数/首屏包索引)加回 manifest。
  - 顺带重算 totalCats(refresh.py 用纯 gal 的 galCats 算, 会少算 wf+kook 共 9 个)。

数据目录优先取 GAL_OUTDIR(Actions 每日刷新用), 否则退回仓库 data/。
"""
import glob
import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.environ.get("GAL_OUTDIR") or os.path.join(ROOT, "data")
MANI = os.path.join(DATA, "manifest.json")

SOURCE_LABEL = ["KOOK灵绘库", ""]        # 对外只显示中性名, 不暴露来源
CAT_LABELS = {                           # 三个模型分类的中文标签(一次性快照, 不会变)
    "kook-yaoguang": ["瑶光", "🎨"],
    "kook-rumengsihuan": ["如梦似幻", "🎨"],
    "kook-gpt-image": ["Gpt Image", "🎨"],
}


def load_rows():
    rows = []
    for f in sorted(glob.glob(os.path.join(DATA, "kook_image_*.json"))):
        try:
            rows.extend(json.load(open(f, encoding="utf-8")))
        except Exception:
            pass
    return rows


def main():
    rows = load_rows()
    if not rows:
        print("[kook] 无 kook_image 分片, 跳过")
        return

    m = json.load(open(MANI, encoding="utf-8"))

    # ---- 分类中文标签 + 分类计数(只加 kook 键, 不动其他源的键) ----
    gcnt = {}
    for r in rows:
        gcnt[r[3]] = gcnt.get(r[3], 0) + 1
    galCats = dict(m.get("galCats") or {})
    for k, n in gcnt.items():
        galCats[k] = CAT_LABELS.get(k, ["KOOK灵绘库", "🎨"])
        m.setdefault("catCounts", {}).setdefault("gal", {})[k] = n
    m["galCats"] = galCats

    # ---- 首屏包索引(build_catpack 之后跑, 只加 kook 键) ----
    pack = dict(m.get("galCatPack") or {})
    for k in gcnt:
        pack[k] = "cp_" + hashlib.md5(k.encode("utf-8")).hexdigest()[:10]
    m["galCatPack"] = pack

    # ---- 计数折入 ----
    # nightly 链路语义(同 build_oi.py/build_wf.py, 2026-10-23 修正):
    # refresh.py 已把 galCount 重置为纯 gal 量, 前面各合并者依次加回各源量,
    # 这里直接加本轮 kook 量(不扣上一轮, 扣了会把重置后的基数吞掉)。
    n_k = len(rows)
    m["galCount"] = (m.get("galCount") or 0) + n_k
    m["kookImage"] = n_k

    # ---- 分片数 ----
    m.setdefault("chunks", {})["kook_image"] = len(
        glob.glob(os.path.join(DATA, "kook_image_*.json")))

    # ---- 来源(中性名) ----
    m.setdefault("sources", {})["kook"] = SOURCE_LABEL

    # ---- totalCats 重算(refresh.py 用纯 gal 的 galCats 算, 少算 wf+kook; 本脚本在链路最后, 一并修正) ----
    m["totalCats"] = (len(m.get("cats") or {}) + len(m.get("imageCats") or {})
                      + len(m.get("videoCats") or {}) + len(m.get("galCats") or {}))

    json.dump(m, open(MANI, "w", encoding="utf-8"), ensure_ascii=False)
    print("[kook] manifest: 图 %d | galCount=%s | chunks kook_image=%d | 分类 %s | totalCats=%d"
          % (n_k, m["galCount"], m["chunks"]["kook_image"],
             "/".join("%s:%d" % (k, v) for k, v in sorted(gcnt.items())), m["totalCats"]))


if __name__ == "__main__":
    main()
