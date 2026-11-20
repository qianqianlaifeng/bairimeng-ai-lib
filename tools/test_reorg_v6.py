# -*- coding: utf-8 -*-
"""本地回归：分类重整 v6 的 UI 实测（Playwright + 系统 Chrome）

用法:
    python -m http.server 8137      # 在仓库根目录开服务
    python tools/test_reorg_v6.py   # 另开一个窗口跑
检查点: 「人像（全部）」跨分类计数 / 性别筛选条数 / 人像写真首屏无非写实 / GPT 只剩一个分类
"""
import json, sys, time
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:8137/index.html'
OUT = r'D:\AI\2026-11-20-08-58-15\bairimeng-ai-lib\tools\_shots'
import os
os.makedirs(OUT, exist_ok=True)

errs = []
with sync_playwright() as pw:
    b = pw.chromium.launch(channel='chrome', headless=True)
    pg = b.new_page(viewport={'width': 1440, 'height': 950})
    pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
    pg.on('pageerror', lambda e: errs.append('PAGEERROR ' + str(e)))
    pg.goto(BASE, wait_until='domcontentloaded')
    pg.wait_for_selector('#categoriesScroll .chip', timeout=20000)
    pg.wait_for_timeout(2500)

    chips = pg.eval_on_selector_all('#categoriesScroll .chip', 'els=>els.map(e=>e.textContent.trim())')
    print('分类 chips 共', len(chips))
    print('前 12:', chips[:12])
    print('含 GPT 的:', [c for c in chips if 'GPT' in c.upper()])
    print('人像全部 chip:', [c for c in chips if '人像（全部）' in c])

    def click_chip(label_part):
        pg.eval_on_selector_all('#categoriesScroll .chip',
            "els=>{const e=els.find(x=>x.textContent.includes(%r)); if(e) e.click();}" % label_part)

    def snapshot(tag, wait=4000):
        pg.wait_for_timeout(wait)
        cnt = pg.text_content('#resultCount')
        title = pg.text_content('#listTitle')
        hint = pg.text_content('#hint')
        cards = pg.eval_on_selector_all('#grid .prompt-card .card-title', 'els=>els.slice(0,6).map(e=>e.textContent)')
        cats = pg.eval_on_selector_all('#grid .prompt-card .cat-tag', 'els=>els.map(e=>e.textContent)')
        from collections import Counter
        print('\n[%s] 标题=%s | 条数=%s' % (tag, title.strip(), cnt.strip()))
        print('    提示:', (hint or '').strip()[:70])
        print('    卡片分类分布:', dict(Counter(cats)))
        for c in cards[:4]:
            print('    -', c[:46])
        pg.screenshot(path=os.path.join(OUT, tag + '.png'), full_page=False)
        return cnt, cats

    click_chip('人像（全部）'); c_all, cats_all = snapshot('01_portrait_all', 5000)
    gender_visible = pg.eval_on_selector('#genderBar', 'e=>!e.hidden')
    print('    性别栏可见:', gender_visible)

    pg.eval_on_selector_all('#genderGroup button', "els=>els.find(e=>e.dataset.gender==='F').click()")
    c_f, cats_f = snapshot('02_portrait_female', 6000)
    pg.eval_on_selector_all('#genderGroup button', "els=>els.find(e=>e.dataset.gender==='M').click()")
    c_m, cats_m = snapshot('03_portrait_male', 6000)

    click_chip('人像写真'); c_x, _ = snapshot('04_portrait_xiezhen', 5000)
    titles = pg.eval_on_selector_all('#grid .prompt-card .card-title', 'els=>els.map(e=>e.textContent)')
    bad = [t for t in titles if any(w in t for w in ('超现实', '动漫', '卡通', '插画', '3D', '粘土'))]
    print('    首屏疑似非写实:', len(bad), bad[:5])

    click_chip('GPT Image'); c_g, cats_g = snapshot('05_gpt_image', 5000)
    print('    GPT 卡内的分类标签:', set(cats_g))

    click_chip('人像动漫'); snapshot('06_portrait_anime', 4000)
    pg.eval_on_selector_all('#categoriesScroll .chip', "els=>els[0].click()")
    snapshot('07_all', 3000)

    b.close()

print('\n控制台错误:', len(errs))
for e in errs[:8]:
    print('  !', e[:160])
