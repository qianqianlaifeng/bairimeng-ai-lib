# -*- coding: utf-8 -*-
"""把 index.html 里静态资源的 ?v= 换成文件内容哈希（缓存击穿用）。

改了 app.js / style.css / config.js 之后跑一次，浏览器就一定会拉新版，
不用手动去猜版本号。每日刷新工作流里也调用它。
"""
import hashlib, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, 'index.html')
ASSETS = ['assets/js/config.js', 'assets/js/theme.js', 'assets/js/app.js',
          'assets/js/settings.js', 'assets/css/style.css']


def h(rel):
    with open(os.path.join(ROOT, rel), 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()[:8]


def main():
    t = open(INDEX, encoding='utf-8').read()
    for rel in ASSETS:
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            continue
        v = h(rel)
        pat = re.escape(rel) + r'(\?v=[0-9a-f]+)?'
        t = re.sub(pat, rel + '?v=' + v, t)
        print('  %-28s ?v=%s' % (rel, v))
    open(INDEX, 'w', encoding='utf-8').write(t)
    print('index.html 已同步')


if __name__ == '__main__':
    main()
