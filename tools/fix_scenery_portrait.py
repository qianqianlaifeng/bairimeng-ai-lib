"""把「风景自然」里主体是人物的图转移到人像三类。默认干跑，--apply 才写入。
规则：标题前部有明确人物主语 + 脸部/肖像/全身/摄影等人物信号；
      若同时有强风景主体词且人物只是点缀，则不动。"""
import os, sys, json, glob, re
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
APPLY = '--apply' in sys.argv

import purify_portrait_v4 as V4
from purify_portrait_v4 import has_person_subject, FACE_RELATED, _s
import reorg_cats_v6 as R

SRC = '风景自然'
PORTRAIT_CATS = ('人像写真', '人像人物', '人像动漫')

# 人物作为主体的强信号（标题前 60 字）
PERSON_STRONG = re.compile(
    r'肖像|人像|自拍|头像|脸部|面部|特写|半身|全身|正面|侧脸|写真|照片|摄影|'
    r'portrait|selfie|headshot|close.?up|full.?body|face\b', re.I)
# 明确风景主体（标题开头就是景物，人物只是陪衬）
SCENE_HEAD = re.compile(
    r'^\s*(?:一张|一幅|这片|这个|那|一座|一片|远处|俯瞰|航拍)?\s*'
    r'(?:风景|山水|山川|大海|海洋|天空|日出|日落|森林|树林|湖泊|河流|草原|沙漠|'
    r'雪山|花海|薰衣草|樱花|建筑|城市|街道|公园|花园|山谷|田野|云海|星空|极光|'
    r'瀑布|溪流|海滩|沙滩|山脉|山峰|湖水|竹林|荷花池|油菜花)', re.I)
# 人物身份词（标题前部）
PERSON_ID = re.compile(
    r'女人|男人|女孩|男孩|女性|男性|少女|少男|女士|先生|模特|新娘|新郎|老人|'
    r'小孩|儿童|婴儿|宝宝|姑娘|小伙|夫人|王子|公主|女王|国王|战士|仙女|精灵|'
    r'舞者|歌手|演员|人物|人像|肖像|她|他们|'
    r'woman|women|man|men|girl|boy|female|male|model|lady|baby|child|'
    r'brunette|blonde|portrait|selfie', re.I)


# 拟人/局部/非真人物主体：这些词做主语时不是人物图，不该转人像
NONHUMAN = re.compile(
    r'形状像|像一个|像一位|形似|树叶|叶子|橄榄树|花瓣|一朵|一棵|一座|'
    r'骨架|骷髅| skeleton|手部|手掌|手指|的女性之手|男人之手|一只手|双手|'
    r'雕像|雕塑|玩偶|娃娃|吉祥物|机器人', re.I)
# 明确"XX的肖像"里 XX 是物：XX的肖像/人脸 一律不算人像
THING_PORTRAIT = re.compile(r'(树|叶子|花|山|建筑|车|动物|狗|猫|鸟)[^，。]{0,6}的(肖像|人脸|脸)', re.I)


def decide(r):
    """返回 (目标分类, 原因) 或 (None, '')。"""
    t = _s(r[1])
    head = t[:60]
    # 开头就是纯景物 -> 风景正确，人物是陪衬，不动
    if SCENE_HEAD.search(t[:24]):
        return None, ''
    # 拟人/局部/物的肖像 -> 不是真人图，不动
    if NONHUMAN.search(head[:40]) or THING_PORTRAIT.search(head[:50]):
        return None, ''
    # 必须有明确的人物身份主语
    pm = PERSON_ID.search(head[:40])
    if not pm:
        return None, ''
    # 人物词后面紧跟物品/场景名词 -> 主语是物（"女性香水瓶""景观"），不算人像
    tail = head[pm.end():pm.end() + 8]
    if re.search(r'香水瓶|瓶|礼盒|包装|海报|封面|标志|图案|景观|书店|装饰|摆件|模型|玩偶| statue|瓶身', tail, re.I):
        return None, ''
    # 需要人物强信号（肖像/照片/特写等）或 has_person_subject
    strong = bool(PERSON_STRONG.search(head)) or has_person_subject(head[:34])
    if not strong:
        return None, ''
    # 交给 v7 的画风/写实规则决定进写真/人物/动漫
    nc, why = R.style_fix(r[1], r[2], '人像人物')
    if nc in PORTRAIT_CATS:
        return nc, '画风:' + why.split(':')[0]
    # 默认兜底进人像人物（风格不明）
    return '人像人物', '人物主体'


def main():
    files = sorted(glob.glob(os.path.join(DATA, 'gal_*.json')))
    moved = Counter()
    samples = []
    total = 0
    for fp in files:
        d = json.load(open(fp, encoding='utf-8'))
        dirty = False
        for r in d:
            if len(r) < 6 or _s(r[3]) != SRC:
                continue
            total += 1
            nc, why = decide(r)
            if nc and nc != SRC:
                moved[nc] += 1
                if len(samples) < 40:
                    samples.append((nc, why, _s(r[1])[:58]))
                r[3] = nc
                dirty = True
        if dirty and APPLY:
            with open(fp, 'w', encoding='utf-8') as fh:
                json.dump(d, fh, ensure_ascii=False, separators=(',', ':'))

    print('%s 总数: %d' % (SRC, total))
    print('拟转移到人像: %d 条' % sum(moved.values()))
    for k, v in moved.most_common():
        print('  -> %s : %d' % (k, v))
    print('\n--- 抽样（前 25）---')
    for nc, why, t in samples[:25]:
        print('  [%s|%s] %s' % (nc, why, t))
    if not APPLY:
        print('\n[干跑] 未写入。加 --apply 才真正转移。')


if __name__ == '__main__':
    main()
