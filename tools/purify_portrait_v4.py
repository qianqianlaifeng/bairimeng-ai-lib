# -*- coding: utf-8 -*-
"""
人像资产净化 v4 (人物主语优先版)
==================================
用户反馈"一上来就错"——首屏混入手表/t恤/动物/场景。

策略（宁可保守，绝不误伤人像）：
  1) 全量清理【极保守】：只踢"标题开头就是明确非人物主语、且无人物主语"的条目。
     判断顺序：设计/局部/配饰主语(绝对开头) -> 有人物主语则保留 -> 非人主语才踢。
  2) 首屏纯度重排【主力】：cp 首屏包按"人像纯度分"重排，只放最典型的人像。
     这是"一上来就错"的真正解药——即使全量有杂质，首屏也一定干净，且零误伤。

用法：
  python tools/purify_portrait_v4.py            # DRY-RUN
  python tools/purify_portrait_v4.py --apply    # 写盘
"""
import json, glob, os, sys, re, hashlib, shutil
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
PORTRAIT_CATS = {'人像人物', '人像写真', '人像动漫'}
APPLY = '--apply' in sys.argv

# ============================================================
# 人物主语（宽松）：标题前 32 字内出现即认为有人物主语
# ============================================================
PERSON_SUBJECT = re.compile(
    r'女人|男人|女孩|男孩|女性|男性|少女|少年|女士|先生|模特|新娘|新郎|老人|小孩|儿童|婴儿|'
    r'姑娘|小伙|夫人|王子|公主|女王|国王|战士|仙女|精灵|舞者|歌手|演员|人物|人像|肖像|自拍|'
    r'她|他们|他人|'
    r'woman|women|man|men|girl|boy|female|male|model|lady|gentleman|child|baby|teenager|'
    r'brunette|blonde|portrait|selfie|headshot|\bshe\b|\bhe\b',
    re.I
)
FACE_RELATED = re.compile(
    r'脸|脸部|面部|头部|肖像|人像|全脸|正脸|portrait|face|selfie|自拍|'
    r'全身|上半身|半身|headshot|full.?body|\bbust\b|胸像', re.I
)

def has_person_subject(head):
    return bool(PERSON_SUBJECT.search(head[:34]))

# ============================================================
# 明确非人像主语（只匹配标题"绝对开头"）
# ============================================================
# 设计/产品：主语就是设计物
DESIGN_SUBJ = re.compile(
    r'^\s*(?:一款|一张|一个|这件|这|为)?\s*'
    r'(?:t\s*恤|T恤|T-?shirt|文化衫|卫衣设计|服装设计|海报|专辑封面|杂志封面|封面设计|'
    r'传单|包装设计|网页设计|无缝图案|logo设计|标志设计|简历设计|名片设计|贺卡设计)',
    re.I
)
# 身体局部特写：主语就是局部（"女人手里拿着X"不会命中，因为要求"X的特写"）
BODY_SUBJ = re.compile(
    r'^\s*(?:一张|一个|这幅|特写)?\s*'
    r'(?:(?:女人|女孩|男人|男孩|模特|female|male)' + "'?" + r's?\s*的?)?'
    r'(手腕|手掌|手指|嘴唇|嘴部|腿部|脚部|脚踝|指甲|牙齿|手背|手部)'
    r'(?:的)?(特写|近景|照片)|'
    r'^\s*(?:close-?up\s+(?:of|on)\s+)?(?:a\s+|the\s+)?'
    r"(?:woman|man|girl|boy|model|female|male)'?s?\s+"
    r'(wrist|hand|lips|mouth|leg|foot|nail|teeth)\b',
    re.I
)
# 配饰商品：主语就是商品本身（要求商品词在很靠前的位置）
ACCESSORY_SUBJ = re.compile(
    r'^\s*(?:一款|一块|一只|一个|这对|这枚)?\s*'
    r'(?:豪华的|金色的|银色的|奢侈的|精致的|闪亮的)?\s*'
    r'(手表|腕表|戒指|项链|耳环|手镯|手提包|'
    r'watch|wristwatch|necklace|earring|bracelet|handbag)\b',
    re.I
)
# 动物/植物/物品/场景/非人实体主语（绝对开头，去掉了宽泛的"花/树/猫"单字误伤）
NONPERSON_SUBJ = re.compile(
    r'^\s*(?:一张|一个|一只|一幅|一座|一辆|这片|这个|那|巨大的|美丽的|可爱的|宁静的|极简的|抽象的|豪华的|现代)?\s*'
    r'(猎豹|cheetah|大象|elephant|老虎|狮子|松鼠|狐狸|熊猫|企鹅|鲸|蝴蝶|蜘蛛|兔子|'
    r'泰迪熊|孔雀|牧羊犬|鹦鹉|仓鼠|'
    r'佛像|机器人|雕塑|瓷瓶|假人模特|木乃伊|怪物|怪兽|恶魔|丧尸|僵尸|骷髅|'
    r'橄榄树|银杏|樱花树|松树|柳树|盆景|玫瑰花|荷花|蘑菇|一朵花|'
    r'建筑|厨房|客厅|卧室|房子|废弃|景观|风景|公园|车站|更衣室|'
    r'蛋糕|披萨|甜甜圈|橙子|咖啡杯|食物|美食|'
    r'纸张|霓虹灯|汽车|捷豹|自行车|摩托车|火车|高铁|'
    r'大脑|脑部|心脏|器官|解剖图|细胞|神经元)',
    re.I
)
# 复合词保护：这些词出现时 NONPERSON_SUBJ 不生效
NONPERSON_PROTECT = re.compile(
    r'热狗|汉堡|女孩和|男孩和|抱着猫|抱着狗|和狗|与狗|遛狗|'
    r'猫女孩|狗女孩|狐狸尾巴|猫耳|兔耳|龙之王|骑着龙|骑着马|骑马', re.I
)

# v4.1: 动物/物主语 + 人物伪装词（肖像/自拍/人像）——词面像人像，主语却是物
CREATURE = re.compile(
    r'(虎斑猫|北极熊|浣熊|牧羊犬|雪纳瑞|西伯利亚猫|花猫|蜂鸟|白鹅|乌鸦|老鼠|'
    r'蝾螈|考拉|树懒|猫头鹰|狗|猿|豹子|狐狸|鹅|熊|地精|怪物|怪兽|恶魔|'
    r'机器人|雕像|雕塑|宝马|汽车|香水瓶|笔记本|花瓶)', re.I
)
MASK_WORD = re.compile(r'肖像|自拍|人像|portrait|selfie|写真|人形|人物', re.I)
# 真人有动物陪同（不算错分）
CREATURE_COMPANY = re.compile(
    r'(女孩|男孩|女人|男人|模特|少女|她|他|woman|man|girl|boy)'
    r'.{0,6}(和|与|抱|带|旁边|牵|骑).{0,4}(猫|狗|熊|狐|龙|马)', re.I
)

def creature_disguised(title):
    """主语是动物/物却用人物词伪装 -> True（用于降权/清理）。语序无关。"""
    t = _s(title)[:58]
    # 人形角色保护：猫娘/狐妖/狗女/兔耳 等拟人角色，主语仍是"人"，不误伤
    if re.search(r'(猫|狗|狐|熊|兔|狼|鼠)(娘|女|妖|人|耳|尾)', t):
        return False
    # 拟人化的动物/物（花猫律师、拟人机器人）-> 不是人像，直接判错分
    if re.search(r'拟人化|拟人|anthropomorph', t, re.I) and CREATURE.search(t):
        return True
    c = CREATURE.search(t)
    m = MASK_WORD.search(t)
    if not c or not m:
        return False
    # 真人主语出现在物/动物词之前 -> 主语是人，物只是场景道具，不误伤
    # （如"一位巴西女性坐在汽车后座自拍"、"女士把香水瓶举到脸前，模特…"）
    if re.search(
        r'女人|男人|女性|男性|女孩|男孩|少女|少年|模特|女士|先生|教师|老师|'
        r'战士|王子|公主|国王|女王|精灵|女神|她|'
        r'woman|man|girl|boy|female|male|model|lady|gentleman|teacher',
        t[:c.start()], re.I
    ):
        return False
    # 真人与动物同框（女孩抱着猫的肖像）-> 保留
    if CREATURE_COMPANY.search(t):
        return False
    # 动物/物主语 + 人物伪装词（语序无关）-> 判错分
    return True


def strip_negative(prompt):
    if not prompt:
        return ''
    t = prompt
    for pat in [r'--no\b', r'\bnegative\s*prompt\b', r'负面提示词', r'负面词']:
        m = re.search(pat, t, re.I)
        if m:
            t = t[:m.start()]
    return t


def nonperson_target(kw):
    """根据命中的非人主语关键词，返回归位分类"""
    if re.search(r'猎豹|大象|老虎|狮子|松鼠|狐狸|熊猫|企鹅|鲸|蝴蝶|蜘蛛|兔子|泰迪熊|孔雀|牧羊犬|鹦鹉|仓鼠', kw):
        return '动物自然', '动物主语:' + kw
    if re.search(r'橄榄树|银杏|樱花树|松树|柳树|盆景|玫瑰花|荷花|蘑菇|一朵花', kw):
        return '风景自然', '植物主语:' + kw
    if re.search(r'蛋糕|披萨|甜甜圈|橙子|咖啡杯|食物|美食', kw):
        return '日常生活', '美食主语:' + kw
    if re.search(r'大脑|脑部|心脏|器官|解剖图|细胞|神经元', kw):
        return '综合精选', '医学科普:' + kw
    if re.search(r'佛像|机器人|雕塑|瓷瓶|假人模特|木乃伊|怪物|怪兽|恶魔|丧尸|僵尸|骷髅', kw):
        return '插画动漫', '非人实体:' + kw
    return '综合精选', '场景物品主语:' + kw


def strict_classify(title, prompt):
    """返回 (目标分类, 原因)；拿不准返回 (None,'') 保留人像类。"""
    t = _s(title).strip()
    if not t:
        return None, ''
    head = t[:44]

    # 1) 绝对开头的设计/局部/配饰主语 -> 直接踢（即使后面有人物，主语也是物）
    m = DESIGN_SUBJ.search(head)
    if m:
        return '产品电商', '平面设计:' + m.group(0)[:12]
    m = BODY_SUBJ.search(head)
    if m and not FACE_RELATED.search(head[:20]):
        return '综合精选', '身体局部:' + m.group(0)[:14]
    m = ACCESSORY_SUBJ.search(head)
    if m:
        return '产品电商', '配饰商品:' + m.group(0)[:12]

    # 2) 有人物主语 -> 一律保留（防止"女孩抱着猫/穿t恤/戴耳环"被误伤）
    if has_person_subject(head):
        return None, ''

    # 3) 无人称主语 + 明确非人主语 -> 踢
    if not NONPERSON_PROTECT.search(head):
        m = NONPERSON_SUBJ.search(head)
        if m:
            return nonperson_target(m.group(1) if m.lastindex else m.group(0))

    # 4) v4.1: 动物/物主语 + 人物伪装词（肖像/自拍）-> 踢
    #    creature_disguised 内部已排除"女孩和猫"陪同 & "猫娘/狐妖"人形角色
    if creature_disguised(t):
        return '动物自然', '动物/物主语伪装肖像:' + (_s(t)[:18])

    return None, ''


# ============================================================
# 人像纯度评分（首屏重排）—— 与清理规则保持一致，避免误扣分
# ============================================================
def _s(v):
    """容错：某些历史脏数据字段可能是 bool/None，统一转字符串"""
    return v if isinstance(v, str) else ('' if v is None else str(v))

def portrait_score(r):
    t = _s(r[1]).strip()
    p = _s(r[2])[:160]
    cat = _s(r[3])
    s = 0
    if has_person_subject(t[:34]):
        s += 8
    if FACE_RELATED.search(t[:50]):
        s += 3
    if cat == '人像写真' and re.search(r'照片|摄影|写真|photograph|photo|realistic|相机|镜头|写实', t + p, re.I):
        s += 2
    if cat == '人像动漫' and re.search(
        r'动漫|插画|卡通|二次元|anime|manga|illustration|cartoon|3D|油画|水彩|漫画|手绘|剪纸|毛毡|CG',
        t + p, re.I
    ):
        s += 2
    # 负分（与 strict_classify 同源）
    if DESIGN_SUBJ.search(t[:44]):
        s -= 25
    if BODY_SUBJ.search(t[:44]) and not FACE_RELATED.search(t[:20]):
        s -= 20
    if ACCESSORY_SUBJ.search(t[:44]):
        s -= 15
    if not has_person_subject(t[:34]) and NONPERSON_SUBJ.search(t[:44]) and not NONPERSON_PROTECT.search(t[:44]):
        s -= 20
    # 拟人/雕塑/非人实体主语降权：词面有"肖像/自拍"但主语是物/动物
    if re.search(r'^(一只|一尊|一匹|一座|不锈钢|金属质感|银色铬|佛像|雕塑|雕像|'
                 r'公鸡|母鸡|泰迪熊|玩偶|公仔|吉祥物|黏液|机器人)', t):
        s -= 16
    # v4.1: 动物/物主语 + 人物伪装词 -> 大幅降权，退出首屏
    if creature_disguised(t):
        s -= 24
    return s


# ============================================================
# 主流程
# ============================================================
def slug(cat):
    return 'cp_' + hashlib.md5(cat.encode('utf-8')).hexdigest()[:10]


def load_shards():
    out = []
    for prefix in ('wf_image', 'oi_gal', 'gal', 'kook_image'):
        i = 0
        while True:
            fp = os.path.join(DATA, '%s_%d.json' % (prefix, i))
            if not os.path.exists(fp):
                break
            out.extend(json.load(open(fp, encoding='utf-8')))
            i += 1
    return out


def main():
    if APPLY:
        bak = os.path.join(ROOT, '_backup_pre_portrait_v4')
        os.makedirs(bak, exist_ok=True)
        for f in glob.glob(os.path.join(DATA, 'gal_*.json')) + \
                 glob.glob(os.path.join(DATA, 'cp_*.json')) + \
                 [os.path.join(DATA, 'manifest.json')]:
            shutil.copy2(f, os.path.join(bak, os.path.basename(f)))
        print('已备份 ->', bak)

    # 1) 全量保守清理
    changed = {}
    total = 0
    for f in sorted(glob.glob(os.path.join(DATA, 'gal_*.json'))):
        d = json.load(open(f, encoding='utf-8'))
        dirty = False
        for r in d:
            if len(r) >= 6 and r[3] in PORTRAIT_CATS:
                total += 1
                nc, why = strict_classify(r[1], r[2])
                if nc and nc != r[3]:
                    changed[r[0]] = (r[3], nc, why)
                    r[3] = nc
                    dirty = True
        if dirty and APPLY:
            with open(f, 'w', encoding='utf-8') as fh:
                json.dump(d, fh, ensure_ascii=False, separators=(',', ':'))

    print('人像类条目总数:', total)
    print('清理踢出:', len(changed), '条 (%.1f%%)' % (len(changed) * 100.0 / max(total, 1)))
    reasons = Counter(v[2].split(':')[0] for v in changed.values())
    for k, n in reasons.most_common():
        print('  %5d  %s' % (n, k))

    # 2) 同步 cp 包中同 id 条目
    if APPLY:
        for f in glob.glob(os.path.join(DATA, 'cp_*.json')):
            if os.path.basename(f) == 'cp_all.json':
                continue
            d = json.load(open(f, encoding='utf-8'))
            dirty = False
            for r in d:
                if len(r) >= 6 and r[0] in changed:
                    r[3] = changed[r[0]][1]
                    dirty = True
            if dirty:
                with open(f, 'w', encoding='utf-8') as fh:
                    json.dump(d, fh, ensure_ascii=False, separators=(',', ':'))

    # 3) 首屏纯度重排预览
    rows = load_shards()
    by_cat = {}
    for r in rows:
        if len(r) > 3:
            by_cat.setdefault(r[3], []).append(r)

    for cat in ['人像写真', '人像人物', '人像动漫']:
        items = by_cat.get(cat, [])
        top = sorted(items, key=portrait_score, reverse=True)[:120]
        low = sum(1 for r in top if portrait_score(r) < 6)
        print('\n=== %s（共%d，取%d，末位分=%d，低分<6的=%d）===' % (
            cat, len(items), len(top),
            portrait_score(top[-1]) if top else 0, low))
        for r in top[:16]:
            print('  [%2d] %s' % (portrait_score(r), r[1][:62]))

    if not APPLY:
        print('\n[DRY-RUN] 未写盘。')
        return

    # 4) 写回 cp 首屏包
    for cat, items in by_cat.items():
        name = slug(cat)
        ranked = sorted(items, key=portrait_score, reverse=True)[:120]
        with open(os.path.join(DATA, name + '.json'), 'w', encoding='utf-8') as fh:
            json.dump(ranked, fh, ensure_ascii=False, separators=(',', ':'))
    print('\n重建 cp 包:', len(by_cat), '类')

    # 5) 更新 manifest 计数
    mp = os.path.join(DATA, 'manifest.json')
    man = json.load(open(mp, encoding='utf-8'))
    cnt = Counter(r[3] for r in rows if len(r) > 3 and not str(r[3]).startswith(('oi-', 'wf-', 'kook-')))
    for k, v in cnt.items():
        man['catCounts']['gal'][k] = v
    man['uiVersion'] = '2026-11-20-portrait-purify-v4'
    with open(mp, 'w', encoding='utf-8') as fh:
        json.dump(man, fh, ensure_ascii=False, separators=(',', ':'))
    print('人像计数: 写真=%d 人物=%d 动漫=%d' % (
        cnt.get('人像写真', 0), cnt.get('人像人物', 0), cnt.get('人像动漫', 0)))

    # 6) DATA_VER + config 版本
    ver = hashlib.md5(open(mp, 'rb').read()).hexdigest()[:8]
    cp = os.path.join(ROOT, 'assets', 'js', 'config.js')
    s = open(cp, encoding='utf-8').read()
    s2 = re.sub(r"DATA_VER: '[^']*'", "DATA_VER: '%s'" % ver, s)
    open(cp, 'w', encoding='utf-8').write(s2)
    h = hashlib.md5(open(cp, 'rb').read()).hexdigest()[:8]
    ip = os.path.join(ROOT, 'index.html')
    t = open(ip, encoding='utf-8').read()
    t2 = re.sub(r'assets/js/config\.js(\?v=[0-9a-f]+)?', 'assets/js/config.js?v=' + h, t)
    open(ip, 'w', encoding='utf-8').write(t2)
    print('DATA_VER =', ver, '| config.js?v=', h)


if __name__ == '__main__':
    main()
