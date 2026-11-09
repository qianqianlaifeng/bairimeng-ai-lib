#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""登录态统一管理：token 快过期就自动重新登录，登录后顺手把新 Cookie 写回仓库 Secret。

以前 Cookie（site_user_token，JWT，7 天有效）一过期，就得手动跑「一键登录.bat」
再把新 Cookie 粘进 Secrets，很烦。现在只要在仓库里配一次账号密码
（KOOK_USER / KOOK_PASS），之后：

  * kook_sync 启动时先看 token 的 exp，剩余不足 SAFE_HOURS 就直接登录换新的；
  * 请求中途撞到 401/403，也会立刻登录重试一次；
  * 登录拿到的新 Cookie 会写回 Secret KOOK_COOKIE（需要 GH_PAT），
    这样下次运行直接复用，不用反复登录（登录频率降到 7 天一次）；
  * 本地跑的时候不写 Secret，只缓存到 %TEMP%/bm-login-cookie.txt。

环境变量 / 本地 tools/cred.json（已 gitignore，不进仓库）：
  KOOK_USER    站点登录账号
  KOOK_PASS    站点登录密码
  KOOK_COOKIE  已有 Cookie（可选，用于复用）
  GH_PAT       有 secrets:write 权限的 GitHub token（可选，用于写回 Secret）
  GITHUB_REPOSITORY   Actions 里自动有，形如 owner/repo
"""
import base64
import json
import os
import ssl
import urllib.error
import urllib.request

BASE = "https://kookaigc.top"
LOGIN_URL = BASE + "/site-user/api/login"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
HERE = os.path.dirname(os.path.abspath(__file__))
CRED_FILE = os.path.join(HERE, "cred.json")
COOKIE_FILE = os.path.join(os.environ.get("TEMP") or "/tmp", "bm-login-cookie.txt")
SAFE_SECONDS = 24 * 3600          # 剩余有效期不足 1 天就主动换新

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


# ---------------------------------------------------------------- 配置读取
def load_cred():
    c = {}
    if os.path.exists(CRED_FILE):
        try:
            c.update(json.load(open(CRED_FILE, encoding="utf-8")))
        except Exception:
            pass
    for k in ("KOOK_USER", "KOOK_PASS", "KOOK_COOKIE", "GH_PAT"):
        v = (os.environ.get(k) or "").strip()
        if v:
            c[k] = v
    return c


def save_cred(**kv):
    """本地缓存（只给本机用，仓库里靠 .gitignore 挡住）。"""
    try:
        c = {}
        if os.path.exists(CRED_FILE):
            c = json.load(open(CRED_FILE, encoding="utf-8"))
        c.update({k: v for k, v in kv.items() if v})
        with open(CRED_FILE, "w", encoding="utf-8") as f:
            json.dump(c, f, ensure_ascii=False, indent=1)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- cookie 工具
def cookie_value(cookie, name="site_user_token"):
    for part in (cookie or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k.strip() == name:
            return v.strip()
    return ""


def jwt_exp(token):
    """不验签，只读 payload 里的 exp；解析失败返回 0。"""
    try:
        p = token.split(".")[1]
        p += "=" * (-len(p) % 4)
        d = json.loads(base64.urlsafe_b64decode(p.encode()))
        return int(d.get("exp") or 0)
    except Exception:
        return 0


def cookie_state(cookie):
    """返回 (是否可用, 剩余秒数, 说明)。"""
    tok = cookie_value(cookie)
    if not tok:
        return False, 0, "无 token"
    exp = jwt_exp(tok)
    if not exp:
        return True, 0, "无法解析 exp，按可用处理"
    left = exp - int(__import__("time").time())
    if left <= 0:
        return False, left, "已过期"
    return True, left, "剩余 %.1f 天" % (left / 86400.0)


# ---------------------------------------------------------------- 登录
def login(user=None, password=None, quiet=False):
    """账号密码登录，成功返回新的 Cookie 串，失败返回空串。"""
    c = load_cred()
    user = (user or c.get("KOOK_USER") or "").strip()
    password = password or c.get("KOOK_PASS") or ""
    if not (user and password):
        if not quiet:
            print("[auth] 未配置账号密码(KOOK_USER/KOOK_PASS)，跳过自动登录")
        return ""

    body = json.dumps({"username": user, "password": password}).encode("utf-8")
    req = urllib.request.Request(LOGIN_URL, data=body, headers={
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": UA,
        "Origin": BASE,
        "Referer": BASE + "/",
    })
    raw, setcookies, code = "", [], 0
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            code = r.status
            raw = r.read().decode("utf-8", "ignore")
            setcookies = r.headers.get_all("Set-Cookie") or []
    except urllib.error.HTTPError as e:
        code = e.code
        try:
            raw = e.read().decode("utf-8", "ignore")
        except Exception:
            raw = ""
        setcookies = e.headers.get_all("Set-Cookie") or []
    except Exception as e:
        if not quiet:
            print("[auth] 登录请求失败:", e)
        return ""

    # 1) 优先从 Set-Cookie 里捡
    jars = {}
    for sc in setcookies:
        head = sc.split(";")[0]
        k, _, v = head.partition("=")
        if k.strip() and v.strip():
            jars[k.strip()] = v.strip()

    # 2) 再从响应体里找 token（不同版本字段名不一致，多兜几个）
    body_tok = ""
    try:
        j = json.loads(raw)
    except Exception:
        j = {}
    if isinstance(j, dict):
        data = j.get("data") if isinstance(j.get("data"), dict) else {}
        for src in (data, j):
            for key in ("site_user_token", "token", "access_token", "accessToken"):
                v = src.get(key)
                if isinstance(v, str) and v.count(".") >= 2:
                    body_tok = v
                    break
            if body_tok:
                break

    tok = jars.get("site_user_token") or body_tok
    if not tok:
        if not quiet:
            ok = isinstance(j, dict) and j.get("success")
            msg = (j.get("message") if isinstance(j, dict) else "") or raw[:120]
            print("[auth] 登录未拿到 token（HTTP %s，success=%s）：%s" % (code, ok, msg))
        return ""

    jars["site_user_token"] = tok
    cookie = "; ".join("%s=%s" % (k, v) for k, v in jars.items())
    if not quiet:
        ok, left, why = cookie_state(cookie)
        print("[auth] 登录成功，token %s（%s）" % (why, "已续期" if left > 0 else "异常"))
    return cookie


# ---------------------------------------------------------------- 写回 Secret
def push_secret(name, value, pat=None, repo=None):
    """把值写回 GitHub Actions Secret。需要 pynacl + pat 有 secrets:write。"""
    pat = pat or (load_cred().get("GH_PAT") or os.environ.get("GH_PAT") or "")
    repo = repo or os.environ.get("GITHUB_REPOSITORY") or ""
    if not (pat and repo):
        return False, "缺少 GH_PAT / GITHUB_REPOSITORY"
    try:
        from nacl import encoding, public
    except Exception:
        return False, "未安装 pynacl"

    def api(url, method="GET", payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        r = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": "Bearer " + pat,
            "Accept": "application/vnd.github+json",
            "User-Agent": "kook-auth",
            "Content-Type": "application/json",
        })
        with urllib.request.urlopen(r, timeout=30) as resp:
            txt = resp.read().decode("utf-8", "ignore")
            return resp.status, (json.loads(txt) if txt.strip() else {})

    try:
        base = "https://api.github.com/repos/%s/actions/secrets" % repo
        _, k = api(base + "/public-key")
        pk = public.PublicKey(k["key"].encode(), encoding.Base64Encoder())
        sealed = public.SealedBox(pk).encrypt(value.encode("utf-8"))
        enc = base64.b64encode(sealed).decode()
        st, _ = api("%s/%s" % (base, name), "PUT", {"encrypted_value": enc, "key_id": k["key_id"]})
        return st in (201, 204), "HTTP %s" % st
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "ignore")[:160]
        except Exception:
            pass
        return False, "HTTP %s %s" % (e.code, detail)
    except Exception as e:
        return False, str(e)[:160]


# ---------------------------------------------------------------- 对外主入口
def ensure_cookie(force_login=False, allow_login=True, quiet=False):
    """拿到一个尽量新鲜、可用的 Cookie。拿不到就返回空串。"""
    c = load_cred()
    cur = (c.get("KOOK_COOKIE") or "").strip()
    if not cur and os.path.exists(COOKIE_FILE):
        try:
            cur = open(COOKIE_FILE, encoding="utf-8").read().strip()
        except Exception:
            cur = ""

    if cur and not force_login:
        ok, left, why = cookie_state(cur)
        if not quiet:
            print("[auth] 现有 Cookie：%s" % why)
        if ok and left > SAFE_SECONDS:
            return cur
        if ok and left <= SAFE_SECONDS and not allow_login:
            return cur

    if not allow_login:
        return cur

    if not quiet:
        print("[auth] 需要换新 token，开始自动登录…")
    new = login(quiet=quiet)
    if not new:
        return cur

    # 本地缓存，方便下次跑
    try:
        open(COOKIE_FILE, "w", encoding="utf-8").write(new)
    except Exception:
        pass
    save_cred(KOOK_COOKIE=new)

    # Actions 里写回 Secret，让下一轮直接复用（7 天才登录一次）
    if os.environ.get("GITHUB_ACTIONS") == "true":
        ok, why = push_secret("KOOK_COOKIE", new)
        print("[auth] 新 Cookie 写回 Secret：%s（%s）" % ("成功" if ok else "失败", why))
    return new


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test-login":
        u = sys.argv[2] if len(sys.argv) > 2 else None
        p = sys.argv[3] if len(sys.argv) > 3 else None
        ck = login(u, p)
        print("RESULT:", "OK" if ck else "FAIL")
        sys.exit(0 if ck else 1)
    ck = ensure_cookie(quiet=False)
    print("COOKIE_OK" if ck else "COOKIE_MISSING")
