# -*- coding: utf-8 -*-
"""即梦封面「人像 / 性别」视觉打标 —— 生成拼版 + 结果回填。

流程（人工/AI 协作，每轮 12 格）：
  1) python tools/vision_label_jimeng.py sheets --start 0 --count 12
       -> 打印 .cache/jmrv/rXXX.jpg 的路径清单（给视觉模型看）
  2) 视觉读完把结果写成 json: {"r087": {"000": [1,"F"], "001": [0,""], ...}}
  3) python tools/vision_label_jimeng.py apply --file res.json
       -> 合并进 tools/jimeng_vision_labels.json（按作品 ID 固化）

拼版里的编号是"审查序号"，与作品 ID 的对应关系落在
.cache/jmrv/index.json，apply 时据此还原，避免张冠李戴。
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE = os.path.join(ROOT, ".cache")
FULL = os.path.join(CACHE, "jimeng_full.json")
IDX = os.path.join(CACHE, os.environ.get("JMSHEET_DIR", "jmrv"), "index.json")
OUT = os.path.join(HERE, "jimeng_vision_labels.json")

GENDER = {"男": "M", "女": "F", "多人": "", "不明": "", "—": "", "-": "", "": ""}


def cmd_sheets(start, count):
    idx = json.load(open(IDX, encoding="utf-8"))
    end = min(len(idx), start + count)
    for k in range(start, end):
        print(os.path.join(CACHE, "jmrv", "r%03d.jpg" % k))
    print("# 本批 %d 版 / %d 条" % (end - start, sum(len(v) for v in idx[start:end])))


def cmd_apply(path):
    idx = json.load(open(IDX, encoding="utf-8"))
    payload = json.load(open(path, encoding="utf-8"))
    labels = {}
    if os.path.exists(OUT):
        labels = json.load(open(OUT, encoding="utf-8"))
    added = fixed = 0
    for sheet, cells in payload.items():
        try:
            n = int(str(sheet).lstrip("rf"))
        except ValueError:
            print("!! 跳过无法解析的版号:", sheet)
            continue
        rows = idx[n]
        for ck, val in cells.items():
            try:
                pos = int(ck)
            except ValueError:
                continue
            if pos >= len(rows):
                print("!! %s 越界 #%s" % (sheet, ck))
                continue
            rid = rows[pos]["id"]
            if isinstance(val, (list, tuple)):
                por, g = int(val[0]), str(val[1] if len(val) > 1 else "")
            else:
                por, g = int(val), ""
            g = GENDER.get(g, g)
            g = "F" if g in ("F", "女") else ("M" if g in ("M", "男") else "")
            if not por:
                g = ""
            rec = {"portrait": 1 if por else 0, "gender": g}
            if rid in labels and labels[rid] != rec:
                fixed += 1
            elif rid not in labels:
                added += 1
            labels[rid] = rec
    json.dump(labels, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    pn = sum(1 for v in labels.values() if v["portrait"])
    print("已回填: 新增 %d / 修正 %d | 视觉标签共 %d 条 (人像 %d)"
          % (added, fixed, len(labels), pn))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "sheets":
        start = int(sys.argv[sys.argv.index("--start") + 1]) if "--start" in sys.argv else 0
        count = int(sys.argv[sys.argv.index("--count") + 1]) if "--count" in sys.argv else 12
        cmd_sheets(start, count)
    elif cmd == "apply":
        cmd_apply(sys.argv[sys.argv.index("--file") + 1])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
