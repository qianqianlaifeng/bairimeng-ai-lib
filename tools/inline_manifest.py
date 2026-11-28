#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 manifest.json 内联进 index.html。

为什么（2026-11-28，用户反馈"每次打开加载半天"）：
  首屏必须等 manifest.json 回来才知道有哪些分类/分片，而国内直连 GitHub Pages
  这一次往返实测 1~7 秒（偶发 40 秒）。manifest 只有 23KB，HTML 本来就要下载，
  内联进去等于把这次往返直接省掉 —— 首屏不用再等，脚本一执行就有分类和轮播。

做法：
  在 index.html 里找到 `window.__MANIFEST_INLINE = {...};` 这一段并替换为最新内容。
  前端 boot() 先用手上这份立即渲染，同时后台再拉一次 manifest 校正（数据若刚更新，
  下一次访问就自然换新）。HTML 的缓存是 10 分钟，比数据刷新的粒度粗，所以
  "内联的是上次构建时的版本"完全够用。

用法: python tools/inline_manifest.py [数据目录]
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data")
INDEX = os.path.join(ROOT, "index.html")

BEGIN = "/*__MANIFEST_INLINE_BEGIN__*/"
END = "/*__MANIFEST_INLINE_END__*/"


def main():
    m = json.load(open(os.path.join(DATA, "manifest.json"), encoding="utf-8"))
    payload = json.dumps(m, ensure_ascii=False, separators=(",", ":"))
    # 防止 JSON 里出现 </script> 提前闭合脚本块
    payload = payload.replace("</", "<\\/")

    html = open(INDEX, encoding="utf-8").read()
    block = ('<script>%s\nwindow.__MANIFEST_INLINE=%s;\n%s</script>'
             % (BEGIN, payload, END))

    if BEGIN in html:
        html = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END),
                      lambda _m: block[len('<script>'):-len('</script>')], html, flags=re.S)
    else:
        anchor = '<link rel="stylesheet" href="assets/css/style.css'
        i = html.find(anchor)
        if i < 0:
            sys.exit("!! index.html 里没找到插入点")
        j = html.find(">", i) + 1
        html = html[:j] + "\n" + block + html[j:]

    open(INDEX, "w", encoding="utf-8").write(html)
    print("已内联 manifest: %.1f KB (index.html 现 %.1f KB)"
          % (len(payload.encode()) / 1024, os.path.getsize(INDEX) / 1024))


if __name__ == "__main__":
    main()
