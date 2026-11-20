# -*- coding: utf-8 -*-
"""
人像资产分类引擎 v2
====================
对"人像人物 / 人像写真"两个分类的条目, 依据提示词文本重新判定为:
  - 非人物 (仅当完全无人物主体, 且强非人物主体明确) -> 归回真实类别
  - 动漫/插画/3D 风格人物 -> 人像动漫 (新建)
  - 写实真人 -> 人像写真
  - 人物但风格不明 -> 人像人物

核心修正 (v1 -> v2):
  1) 人物主体优先: 只要识别到人物主体, 绝不因场景/道具词踢出人像类
  2) negative 剥离: "--no" / "negative" 之后的词不参与风格统计
  3) 复合词保护: 热狗/自行车/校车/出租车 等不触发 动物/车辆
  4) 强写实优先: photorealistic/realistic/照片/摄影 压过偶发的风格词

用法:
  python tools/classify_portrait.py report   # 只统计+抽样
  python tools/classify_portrait.py apply    # 写回分片+重建cp包+更新manifest
"""
import json, glob, os, sys, re, random
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
PORTRAIT_CATS = {'人像人物', '人像写真', '人像动漫'}

# ---------- 特征词库 ----------
PERSON_STRONG = ['女人','男人','女孩','男孩','女性','男性','女士','先生','少女','少年','模特','人脸','肖像','人像',
    '美女','帅哥','新娘','新郎','青年','老人','小孩','儿童','婴儿','舞者','歌手','演员','女士','小伙','汉子','姑娘',
    'woman','man','girl','boy','female','male','portrait','face','model','lady','gentleman','child','baby','brunette',
    'blonde','she ','he ','her ','his ','young woman','young man','teenager','elderly','human','人物','少女','她','他']
PERSON_WEAK = ['人','脸','selfie','自拍','face','portrait']

# 纯非人物主体 (标题/主体明确)
ANIMAL_STRONG = ['一只狗','一只猫','一条狗','一只松鼠','一只鸟','一只狐狸','杜宾犬','柯基','柴犬','比熊','一只柯基',
    '猫肖像','狗肖像','一只鲸','一头鲸','海豚','巨嘴鸟','猫头鹰','雪人','一只蝴蝶','一只蜘蛛','一条蛇','考拉','熊猫',
    '小狗','小猫','一只鸭子','a cute','a dog','a cat','a squirrel','a fox','a whale','dolphin','owl portrait',
    'cat portrait','dog portrait','penguin','白天鹅','短毛狗','一只快乐的短毛狗','一只柯基犬','一只猫',
    '一只狗','一条狗','猫咪','狗狗']
ANIMAL_HEAD = re.compile(r'^(一只|一条|一头|一只可爱|这只|那只|一只快乐的)[^。，]{0,10}(狗|猫|犬|松鼠|鸟|狐狸|兔|鲸|熊猫|狮子|老虎|马|羊|猴|蛇|鼠|刺猬)')
VEHICLE_STRONG = ['一辆车','一辆汽车','保时捷','甲壳虫','铃木','吉姆尼','跑车','越野车','赛车','911 GT3','jimny',
    '一辆校车','一辆巴士','a car','porsche','ferrari','volkswagen','beetle','sports car']
# 保护词: 出现这些, 即便有动物/车词也不判非人物
PROTECT = ['热狗','汉堡','hot dog','骑自行车','自行车','骑行','校车改造','开车的人','车里的女人','车内的男人',
    '和狗','与狗','遛狗','抱着猫','抱着狗','猫和','狗和','与猫','女孩和狗','男孩和猫','与动物','吃','美食','蛋糕']

# 动漫/插画/3D/艺术风格 (主体是人物时)
ANIME_STYLE = ['动漫','动画','二次元','插画','漫画','卡通','手绘','油画','水彩','素描','彩铅','像素','pixar','disney',
    '吉卜力','宫崎骏','新海诚','CLAMP','日漫','anime','manga','cartoon','illustration','drawing','painting',
    'sketch','watercolor','oil painting','pixel art','3D渲染','3d render','手办风格','玩具人偶','PVC','可收藏',
    'art style','艺术风格','拼贴','波普','pop art','涂鸦','graffiti','童话','绘本','Q版','chibi','手办','雕像',
    '虚拟偶像','CG角色','游戏角色','3D模型','三维','3D卡通','低多边形','low poly','矢量','vector','emoji','meme',
    '恐怖娃娃','公仔','玩偶','人偶','毛毡','黏土','粘土','blender','octane','C4D','虚幻引擎','虚幻','厚涂','板绘',
    '数字插画','数字艺术','digital art','概念图','游戏CG','动漫风格','漫画风格','插画风格','卡通风格']
# 强写实
REAL_STRONG = ['photorealistic','ultra photorealistic','hyperrealistic','photograph','realistic','照片','写真','真人照片',
    '真人实拍','实拍','纪实','单反','相机拍摄','镜头','85mm','50mm','f/1.4','光圈','景深','皮肤毛孔','真实皮肤',
    'shot on','canon','sony a7','nikon','vogue','时尚大片','街拍','新闻摄影','战地摄影',' documentary','人像摄影',
    '肖像摄影','皮肤质感','真实毛发','发丝分明','cinematic photograph','电影剧照']
REAL_WEAK = ['写实','超写实','逼真的','超逼真','现实主义的','电影感','电影级','胶片','时尚大片','街拍',
    '轮廓光','伦勃朗光','蝴蝶光','眼神光','雀斑','自然瑕疵','皮肤质感','发丝分明']

def strip_negative(prompt):
    """把 --no / negative prompt / 负面 之后的内容去掉, 避免负面词污染统计。"""
    if not prompt: return ''
    t = prompt
    for pat in [r'--no\b', r'\bnegative\s*prompt\b', r'负面提示词', r'负面词']:
        m = re.search(pat, t, re.I)
        if m: t = t[:m.start()]
    return t

def has(text, words):
    tl = text.lower()
    return [w for w in words if w.lower() in tl]

# 英文人物词用词边界, 避免 "Facebook"->face, "trace"->race 之类误命中
EN_PERSON_RE = re.compile(r'\b(woman|women|man|men|girl|boy|female|male|model|portrait|face|lady|gentleman|child|baby|teenager|brunette|blonde|she|he|her|his)\b', re.I)
CN_PERSON_RE = re.compile(r'女孩|男孩|女人|男人|女性|男性|少女|少年|模特|人脸|肖像照|自拍|新娘|新郎|帅哥|美女|她|他|人们|人物')

def is_person(text):
    # "动物肖像/宠物" 里的 "肖像" 不算人
    t = text
    if re.search(r'动物肖像|宠物|一只狗|一只猫|一条狗|松鼠|兔子|熊|微距', t):
        t2 = t.replace('动物肖像', '').replace('肖像', '', 1) if '动物肖像' in t else t
    else:
        t2 = t
    return bool(EN_PERSON_RE.search(t2) or CN_PERSON_RE.search(t2))

# ---------- v3: 标题主语级"强非人物"判定 ----------
# 标题开头的主语是这些东西时, 即便正文有"肖像/脸/女人"也判非人物
SUBJECT_NONPERSON = [
    # 植物/树
    (r'^(一棵|一株|这棵|一棵棵)?[^，。]{0,8}(树|橄榄树|橡树|樱花树|松树|柳树|盆景|花|玫瑰|荷花|花朵|蘑菇)', '植物'),
    # 动物 (标题主语, 含"肖像/油画")
    (r'^(一只|一头|这条|这幅|抽象画|色彩)?[^，。]{0,8}(老虎|狮子|猫|狗|犬|松鼠|马|鸟|鹰|天鹅|狐狸|熊猫|企鹅|鲸|章鱼|蝴蝶|龙虾|鸭子|猴|蛇|鼠|刺猬|考拉|袋鼠|骆驼|长颈鹿)', '动物'),
    # 食物/餐饮
    (r'^(一道|一份|一碗|一盘|场景[:：]|家常菜|美食|食物|自制|食谱)?[^，。]{0,10}(菜|食物|餐|美食|料理|甜点|蛋糕|披萨|汉堡|寿司|面条|早餐|午餐|晚餐|食材|烹饪|烘焙)', '美食'),
    # 化妆品/产品静物
    (r'^(一个|一款|豪华的|一套)?[^，。]{0,10}(化妆品|口红|腮红|香水|护肤|美容|包装|粉底|唇膏|精华|面霜|产品展示|平面展示)', '产品'),
    # 大脑/器官/解剖 (允许出现在标题前段任意位置, 因为是强主体特征)
    (r'^.{0,26}(大脑|脑部|心脏|器官|解剖图|骨骼|细胞|神经元)', '医学科普'),
    # 木乃伊/怪物/玩偶 (非人实体)
    (r'^(20世纪|一个|一只)?[^，。]{0,10}(木乃伊|怪物|怪兽|恶魔|丧尸|僵尸|骷髅头|稻草人|机器人|雕像|假人模特|人体模型)', '非人实体'),
]
def subject_nonperson(title, prompt=''):
    t = (title or '').strip()
    if not t: return None
    head = t[:26]
    for pat, cat in SUBJECT_NONPERSON:
        if re.search(pat, head):
            return cat
    # 标题主语看起来是场景(以"场景/一名..."开头)但正文前 120 字是强美食/产品描述:
    lead = (prompt or '')[:120]
    food = re.search(r'(家常菜|这道菜|丰盛的食材|开胃|烧烤痕迹|鲜嫩的肉|烹饪|食谱|美食摄影)', lead)
    if food and not re.search(r'女孩|男孩|女人|男人|模特|woman|man|girl|boy', head, re.I):
        return '美食'
    return None

def classify(title, prompt):
    main = strip_negative(prompt)
    text = (title or '') + ' ' + main
    # v3 前置: 标题主语就是非人物 -> 直接归位, 不看正文的人物词
    subj = subject_nonperson(title, main)
    if subj:
        return {
            '植物': '风景自然', '动物': '动物自然', '美食': '日常生活',
            '产品': '产品电商', '医学科普': '综合精选', '非人实体': '插画动漫'
        }[subj], '标题主语非人物:' + subj

    has_person = is_person(text)

    protect = has(text, PROTECT)
    # ---- 非人物判定: 无人物主体 + 强非人物词 + 无保护词 ----
    # 句首"一只XX狗/猫" 即便句中有"女孩"也是动物主体 (如"一只快乐的短毛狗...另有一个女孩")
    head_animal = bool(ANIMAL_HEAD.search((title or '') + ' ' + main))
    ah = has(text, ANIMAL_STRONG)
    vh = has(text, VEHICLE_STRONG)
    # 无人物主体: 动物/车辆主体优先 (protect 只防有人物时的误伤, 这里无人物就不保护)
    if not has_person:
        if ah or head_animal: return '动物自然', '动物主体:' + (','.join(ah[:2]) or '句首动物')
        if vh: return '产品电商', '车辆主体:' + ','.join(vh[:2])
        sc = has(text, ['风景','雪景','小镇','梅花','海浪','风景照','landscape','cityscape','静物','花瓶','蛋糕','雕塑','一片','一座'])
        if sc and len(main) < 120:
            return '综合精选', '场景静物:' + ','.join(sc[:2])
        return None, '无人物主体-保留'

    # ---- 有人物: 分人像子类 ----
    # 强艺术风格优先 (工笔/国画/水墨/油画/3D游戏 即便带"镜头/cinematic"也不是写真)
    art_first = has(main, ['工笔画','国画','水墨','油画','水彩','素描','彩铅','版画','壁画','年画','浮世绘',
                           'thin line','铁丝笔','矿物颜料','工笔重彩','3D game','game cinematic','3d game',
                           'cg渲染','游戏CG','3D渲染','3d render','虚幻引擎','unreal engine','blender','octane'])
    if art_first and has_person:
        return '人像动漫', '艺术/3D画风:' + ','.join(art_first[:2])

    # 强写实优先
    real_s = has(main, REAL_STRONG)
    if real_s:
        return '人像写真', '强写实:' + ','.join(real_s[:2])

    anime = has(main, ANIME_STYLE)
    real_w = has(main, REAL_WEAK)
    # 动漫风格明显, 且写实弱词不多于动漫词
    if anime and len(anime) > len(real_w):
        return '人像动漫', '动漫/艺术:' + ','.join(anime[:3])
    # 3D/玩偶童话风
    if has(main, ['3D立体','3D卡通','毛毡','黏土','粘土','玩偶','人偶','公仔','盲盒','Q版','chibi','童话','梦幻','可爱卡通']):
        return '人像动漫', '3D/玩偶童话风'
    if real_w:
        return '人像写真', '写实弱词:' + ','.join(real_w[:2])
    return '人像人物', '人物主体/风格不明'

def load_rows():
    rows = []
    for f in sorted(glob.glob(os.path.join(DATA, 'gal_*.json'))):
        d = json.load(open(f, encoding='utf-8'))
        for i, r in enumerate(d):
            if len(r) >= 6 and r[3] in PORTRAIT_CATS:
                rows.append((os.path.basename(f), i, r))
    return rows

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'report'
    rows = load_rows()
    result = Counter(); changed = []
    for f, i, r in rows:
        newcat, why = classify(r[1], r[2])
        if newcat is None:
            newcat = r[3]; why = '无人物主体-保留'
        result[newcat] += 1
        if newcat != r[3]:
            changed.append((f, i, r[3], newcat, why, r[1][:44]))
    print('=== 人像类条目总数:', len(rows))
    print('=== 重分类后分布 ===')
    for k, v in result.most_common(): print(f'{v:6d}  {k}')
    moved = len(changed)
    print(f'=== 需改分类: {moved} 条 ({moved*100.0/len(rows):.1f}%) ===')
    flow = Counter((c[2], c[3]) for c in changed)
    print('=== 流向 ===')
    for (a, b), n in flow.most_common(): print(f'{n:6d}  {a} -> {b}')
    random.seed(42)
    print('\n=== 抽样 (每流向3条) ===')
    seen = defaultdict(int)
    for f, i, old, new, why, title in changed:
        if seen[(old, new)] < 3:
            seen[(old, new)] += 1
            print(f'[{old}->{new}] {why} | {title}')

if __name__ == '__main__':
    main()

# ---------- apply 逻辑 (追加) ----------
def apply_changes():
    import hashlib
    # 1) 遍历 gal 分片, 改分类字段
    changed_map = {}   # id -> newcat
    total = 0
    for f in sorted(glob.glob(os.path.join(DATA, 'gal_*.json'))):
        d = json.load(open(f, encoding='utf-8'))
        dirty = False
        for r in d:
            if len(r) >= 6 and r[3] in PORTRAIT_CATS:
                total += 1
                newcat, why = classify(r[1], r[2])
                if newcat and newcat != r[3]:
                    changed_map[r[0]] = (r[3], newcat, why)
                    r[3] = newcat
                    dirty = True
        if dirty:
            with open(f, 'w', encoding='utf-8') as fh:
                json.dump(d, fh, ensure_ascii=False, separators=(',', ':'))
    # 2) cp 包里的同 id 条目也要同步改 (cp包是gal子集)
    for f in glob.glob(os.path.join(DATA, 'cp_*.json')):
        if os.path.basename(f) == 'cp_all.json': continue
        d = json.load(open(f, encoding='utf-8'))
        dirty = False
        for r in d:
            if len(r) >= 6 and r[0] in changed_map:
                r[3] = changed_map[r[0]][1]
                dirty = True
        if dirty:
            with open(f, 'w', encoding='utf-8') as fh:
                json.dump(d, fh, ensure_ascii=False, separators=(',', ':'))
    print('分片改动条目:', len(changed_map))
    return changed_map

def _orig_apply_patch():
    pass
