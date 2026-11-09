#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一次性配置：把站点账号密码写进仓库 Secrets，之后登录态永久自动续期。

用法（一般不用手敲，双击「一键配置自动续期.bat」就行）：
    set KOOK_USER=xxx
    set KOOK_PASS=yyy
    python tools/setup_autologin.py

它会：
  1. 用账号密码真登录一次，确认能拿到 token（失败就直接告诉你原因，不写任何东西）；
  2. 把 KOOK_USER / KOOK_PASS / KOOK_COOKIE / GH_PAT 写进仓库 Secret；
  3. 之后 Actions 每 30 分钟跑一次，token 快过期就自己登录换新，你不用再管。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kook_auth  # noqa: E402

REPO = "qianqianlaifeng/bairimeng-ai-lib"


def find_pat():
    """从环境或 git 凭据里找一个能写 Secret 的 GitHub token。"""
    env = (os.environ.get("GH_PAT") or "").strip()
    if env:
        return env, "环境变量"
    for p in (os.path.expanduser("~/.git-credentials"),
              r"C:\Users\%s\.git-credentials" % os.environ.get("USERNAME", "")):
        if not os.path.exists(p):
            continue
        cands = []
        for line in open(p, encoding="utf-8", errors="ignore"):
            m = re.match(r"https://([^:]+):([^@]+)@github\.com", line.strip())
            if m:
                tok = m.group(2)
                # fine-grained(github_pat_) 优先，其次 ghp_
                score = 0 if tok.startswith("github_pat_") else 1
                cands.append((score, tok))
        for _, tok in sorted(cands):
            return tok, "本机 git 凭据"
    return "", ""


def main():
    user = (os.environ.get("KOOK_USER") or "").strip()
    pwd = os.environ.get("KOOK_PASS") or ""

    print("=" * 52)
    print(" 配置自动续期（只需要做这一次）")
    print("=" * 52)
    if not user or not pwd:
        print("!! 没有拿到账号密码，请用「一键配置自动续期.bat」运行")
        return 2

    print("[1/4] 用账号 %s 试登录…" % (user[:3] + "***" + user[-2:] if len(user) > 6 else user))
    cookie = kook_auth.login(user, pwd)
    if not cookie:
        print("!! 登录失败。请确认账号密码正确（注意不是手机短信验证码登录）。")
        return 1
    ok, left, why = kook_auth.cookie_state(cookie)
    print("      登录成功，token %s" % why)

    print("[2/4] 找 GitHub 写入凭据…")
    pat, src = find_pat()
    if not pat:
        print("!! 本机找不到 GitHub 凭据，无法自动写 Secret")
        return 1
    print("      已找到（%s）" % src)

    print("[3/4] 写入仓库 Secrets（4 个）…")
    fails = []
    for name, val in (("KOOK_USER", user), ("KOOK_PASS", pwd),
                      ("KOOK_COOKIE", cookie), ("GH_PAT", pat)):
        good, why = kook_auth.push_secret(name, val, pat=pat, repo=REPO)
        print("      %-12s %s%s" % (name, "OK" if good else "失败",
                                   "" if good else "  " + str(why)))
        if not good:
            fails.append(name)

    print("[4/4] 本地缓存同一份 Cookie（本机跑也能用）…")
    kook_auth.save_cred(KOOK_USER=user, KOOK_PASS=pwd, KOOK_COOKIE=cookie)
    try:
        open(kook_auth.COOKIE_FILE, "w", encoding="utf-8").write(cookie)
    except Exception:
        pass
    print("      完成")

    print("-" * 52)
    if fails:
        print("部分 Secret 没写成功：%s" % ", ".join(fails))
        print("多半是这个 GitHub token 没有 secrets 写权限。")
        return 1
    print("全部完成。以后 token 到期会自动续，不用再管。")
    print("（可选的下一步：到仓库 Actions 里手动跑一次「实时同步最新收录」验证）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
