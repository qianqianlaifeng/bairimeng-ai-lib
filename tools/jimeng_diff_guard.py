# -*- coding: utf-8 -*-
"""即梦高频同步的"防抖"闸门：只有内容真的变了才提交。

为什么需要：
  即梦封面是带签名的直链，同一个作品每次抓取拿到的签名/主机名几乎都会变
  （实测一轮 198 条里有 104 条签名不同）。每 2 小时提交一次 = 每轮把
  280KB 的分片整文件重写，仓库几个月就膨胀上百 MB，而这些改动对用户
  毫无意义（同一张图，只是签名串不一样）。

判定"内容变了"的口径（任一满足才提交）：
  1) 作品集合变了（有新增 / 下线）
  2) 任一条的人像标记或性别变了（用户要的「实时更新」就在这）
  3) 标题或提示词变了
  4) 现有封面签名快过期了（< REFRESH_DAYS 天）—— 签名到期图会 403，
     这时必须把新签名写回去

没变时把 data/ 恢复成仓库里的版本，让后面的提交步骤空跑。

用法: python tools/jimeng_diff_guard.py [--force]
退出码 0 = 继续提交；3 = 无需提交（已在内部恢复文件）
"""
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
REF = "HEAD"
REFRESH_DAYS = 7          # 签名剩余有效期少于这么多天，就强制刷新


def git_show(rev, path):
    try:
        out = subprocess.run(["git", "show", "%s:%s" % (rev, path)],
                             cwd=ROOT, capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
        if out.returncode != 0:
            return None
        return json.loads(out.stdout)
    except Exception:
        return None


def min_expiry(rows):
    """行里封面签名的最早过期时间（epoch 秒）；没有则 0。"""
    exp = []
    for r in rows:
        m = re.search(r"x-expires=(\d+)", str(r[5] if len(r) > 5 else ""))
        if m:
            exp.append(int(m.group(1)))
    return min(exp) if exp else 0


def signature(rows):
    """只比对和用户有关的内容：id / 标题 / 提示词 / 人像 / 性别。"""
    d = {}
    for r in rows:
        d[r[0]] = (
            (r[1] or "")[:80],
            (r[2] or "")[:200],
            r[8] if len(r) > 8 else None,
            (r[9] or "") if len(r) > 9 else "",
        )
    return d


def main():
    force = "--force" in sys.argv
    path = os.path.join(DATA, "jimeng_gal_0.json")
    if not os.path.exists(path):
        print("!! 没有即梦分片, 交给后面步骤处理")
        return 0
    new = json.load(open(path, encoding="utf-8"))
    old = git_show(REF, "data/jimeng_gal_0.json")
    if old is None:
        print("仓库里没有旧的即梦分片（首次接入），直接提交")
        return 0

    sn, so = signature(new), signature(old)
    added = set(sn) - set(so)
    removed = set(so) - set(sn)
    changed = [k for k in set(sn) & set(so) if sn[k] != so[k]]

    exp_old = min_expiry(old)
    days_left = (exp_old - time.time()) / 86400 if exp_old else 999
    print("作品: 新增 %d / 下线 %d / 内容变化 %d | 旧签名剩余 %.1f 天"
          % (len(added), len(removed), len(changed), days_left))
    for k in list(added)[:5]:
        print("   + %s %s" % (k, sn[k][0][:26]))
    for k in list(removed)[:5]:
        print("   - %s %s" % (k, so[k][0][:26]))
    for k in changed[:5]:
        print("   ~ %s %s -> %s" % (k, so[k][2:], sn[k][2:]))

    if force or added or removed or changed:
        print("=> 有实质变化, 继续提交")
        return 0
    if days_left < REFRESH_DAYS:
        print("=> 签名仅剩 %.1f 天, 强制刷新签名" % days_left)
        return 0

    print("=> 仅签名变动, 内容无变化: 恢复仓库版本, 跳过提交")
    subprocess.run(["git", "checkout", "--", "data"], cwd=ROOT, check=False)
    return 3


if __name__ == "__main__":
    sys.exit(main())
