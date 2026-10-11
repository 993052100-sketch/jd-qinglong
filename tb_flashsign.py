#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
淘宝闪购签到脚本（青龙面板专用）
================================
功能：
  1. 淘宝 / 闪购类签到活动（mtop 接口，使用 _m_h5_tk 进行 md5 签名）
  2. 多账号支持（TAO_COOKIE 环境变量，多个账号用 & 或换行分隔）
  3. 随机延迟 + 随机间隔，降低风控概率
  4. 复用青龙自带通知（notify.send），无则降级为打印

== 部署步骤（飞牛 NAS 上的青龙面板）==
1. 青龙面板 → 环境变量 → 新建：
      名称：TAO_COOKIE
      值  ：你的淘宝移动端 Cookie（需含 _m_h5_tk / cookie2 / _tb_token_ 等）
      多个账号用  &  或换行 分隔
2. 依赖管理 → 新建依赖 → 语言选 python → 输入 requests → 安装
3. 脚本管理 → 上传本文件到 /ql/data/scripts/tb_flashsign.py
4. 定时任务 → 新建：
      命令：python3 /ql/data/scripts/tb_flashsign.py
      cron：30 9 * * *   （每天上午 9:30，启动后会再随机延迟防风控）

== 关于淘宝接口的说明（请务必读完）==
- 淘宝 mtop 接口需要 x-sign 签名，本脚本内置了基于 _m_h5_tk 的 md5 签名实现，
  对大多数"h5 轻签名"接口可用。
- 但闪购/签到这类活动的「具体 apiName 和参数」会随每一期活动变化，
  脚本里已把当前（2026-10）常用的几个接口名做成常量放在顶部，
  若某任务返回 FAIL_SYS_ILLEGAL_REQUEST / FAIL_* 或一直不成功，
  多半是当期接口名/活动参数变了，需用手机淘宝 App 抓包核对后替换。抓包方法见 README。
- Cookie 含登录凭证，请只保存在青龙环境变量中，切勿外泄或提交到仓库。
- 淘宝风控比京东更严，建议 crontab 时间错开、不要高频调用。
"""

import os
import re
import sys
import json
import time
import random
import hashlib

try:
    import requests
except ImportError:
    print("缺少依赖 requests，请在青龙「依赖管理」中安装 python 版 requests")
    sys.exit(1)

# ---------- 基础配置 ----------
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 "
      "Mobile/15E148 Safari/604.1")

# mtop 默认 h5 appKey（淘宝 H5 网页/手淘 H5 通用），可用 TAO_APPKEY 覆盖
DEFAULT_APP_KEY = "12574478"
API_VERSION = "1.0"

# ---------- 当期签到活动接口（需按实际活动核对，见上方说明） ----------
# 每个活动 = (展示名, 查询接口名, 签到接口名, 签到参数)
# 若某接口失效，替换这里的 apiName 即可，无需改主逻辑。
SIGN_ACTIVITIES = [
    {
        "name": "闪购签到",
        "index_api": "mtop.taobao.bgc.signin.index",
        "sign_api": "mtop.taobao.bgc.signin.doSignin",
        "sign_data": {"bizCode": "flashsale_signin", "source": "flashsale"},
    },
    {
        "name": "淘宝通用签到",
        "index_api": "mtop.taobao.lightoff.show",
        "sign_api": "mtop.taobao.bgc.signin.doSignin",
        "sign_data": {"bizCode": "taobao_signin", "source": "h5"},
    },
]

# 尝试导入青龙自带通知模块；不存在则用打印兜底
try:
    from notify import send as ql_send
    HAVE_QL_NOTIFY = True
except Exception:
    HAVE_QL_NOTIFY = False


def notify(title, content):
    if HAVE_QL_NOTIFY:
        try:
            ql_send(title, content)
            return
        except Exception:
            pass
    print(f"\n===== {title} =====\n{content}\n")


# ---------- 工具函数 ----------
def _read_from_env_file(name):
    """兜底：老版本青龙会把环境变量写入 env.sh，若任务进程未注入则从此文件读取。"""
    candidates = ["/ql/config/env.sh", "/ql/data/config/env.sh", "/ql/.env"]
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                txt = f.read()
            for line in txt.splitlines():
                line = line.strip()
                if line.startswith(f"export {name}=") or line.startswith(f"{name}="):
                    val = line.split("=", 1)[1].strip().strip("'").strip('"')
                    if val and val.lower() not in ("''", '""'):
                        return val
        except Exception:
            continue
    return ""


def _read_env_from_db(name):
    """兜底：青龙 2.x 的环境变量保存在 sqlite（env.db 等），API 创建的变量可能未注入进程。"""
    try:
        import sqlite3
    except Exception:
        return ""
    candidates = [
        "/ql/data/db/env.db",
        "/ql/data/db/database.sqlite",
        "/ql/data/db/settings.db",
        "/ql/data/db/ql.db",
    ]
    tables = ("envs", "Envs", "ENV", "env")
    for db in candidates:
        try:
            conn = sqlite3.connect(db)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tabs = [r[0] for r in cur.fetchall()]
            for tbl in tables:
                if tbl in tabs:
                    try:
                        cur.execute(f"SELECT name, value, status FROM {tbl}")
                        for n, value, status in cur.fetchall():
                            if n == name and str(status) == "0" and value:
                                conn.close()
                                return value
                    except Exception:
                        continue
            conn.close()
        except Exception:
            continue
    return ""


def get_env_value(name, default=""):
    """通用环境变量读取：进程环境 -> env.sh -> 青龙 env.db 兜底"""
    v = os.environ.get(name, "").strip()
    if not v:
        v = _read_from_env_file(name).strip()
    if not v:
        v = _read_env_from_db(name).strip()
    return v or default


def get_cookies():
    """从环境变量读取多个账号的 Cookie（支持 & 与换行分隔）"""
    raw = get_env_value("TAO_COOKIE")
    if not raw:
        return []
    parts = re.split(r"[&\n]+", raw.strip())
    return [p.strip() for p in parts if p.strip()]


def get_pin(cookie):
    """从淘宝 Cookie 里取用户标识（unb 或 _tb_token_ 兜底）"""
    m = re.search(r"unb=([^;]+)", cookie)
    if m:
        from urllib.parse import unquote
        return unquote(m.group(1))[:20]
    m = re.search(r"cookie2=([^;]+)", cookie)
    if m:
        return "ck2_" + m.group(1)[:12]
    return "未知账号"


def get_app_key():
    return get_env_value("TAO_APPKEY", DEFAULT_APP_KEY).strip()


# ---------- mtop 签名与请求 ----------
def _mtop_sign(token, t, app_key, data_str):
    """
    淘宝 mtop h5 签名（x-sign）。
    sign = md5( {token}&{t}&{app_key}&{dataStr} )
    其中 token 取 Cookie 中 _m_h5_tk 的「下划线前」部分。
    这是社区通用的 h5 轻签名实现，对绝大多数 h5 接口可用。
    """
    sign_str = f"{token}&{t}&{app_key}&{data_str}"
    return hashlib.md5(sign_str.encode("utf-8")).hexdigest()


def _extract_token(cookie):
    """
    从 Cookie 提取 mtop 签名 token。
    _m_h5_tk 形如  TOKEN_1700000000000  ，取下划线前的 TOKEN。
    若 _m_h5_tk 不存在（Cookie 太旧/未登录），返回空串，调用方会提示重抓。
    """
    m = re.search(r"_m_h5_tk=([^;]+)", cookie)
    if not m:
        return ""
    raw = m.group(1)
    return raw.split("_")[0]


def mtop(session, cookie, api_name, data, app_key=DEFAULT_APP_KEY, v=API_VERSION):
    """
    封装一次淘宝 mtop 调用。
    返回接口 JSON；网络异常返回 {"error": "..."}。
    """
    url = f"https://h5api.m.taobao.com/h5/{api_name}/{v}/"
    t = str(int(time.time() * 1000))
    token = _extract_token(cookie)
    data_str = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    sign = _mtop_sign(token, t, app_key, data_str)

    params = {
        "jsv": "2.4.11",
        "appKey": app_key,
        "t": t,
        "sign": sign,
        "api": api_name,
        "v": v,
        "type": "originaljson",
        "dataType": "json",
    }
    body = {"data": data_str}
    headers = {
        "User-Agent": UA,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Accept": "*/*",
        "Cookie": cookie,
        "Origin": "https://h5.m.taobao.com",
        "Referer": "https://h5.m.taobao.com/",
        "x-appkey": app_key,
        "x-t": t,
        "x-sign": sign,
        "x-ttid": "100000@taobao_android_9.20.0",
    }
    try:
        r = session.post(url, params=params, data=body, headers=headers, timeout=15)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def _mtop_ok(res):
    """mtop 返回成功判定：ret 数组首元素含 SUCCESS"""
    ret = res.get("ret") or []
    if ret and any("SUCCESS" in str(x) for x in ret):
        return True, ret[0]
    return False, (ret[0] if ret else "无返回")


# ---------- 具体任务 ----------
def task_sign_activity(session, cookie, act):
    """执行单个签到活动：先查状态，再签到"""
    pin = get_pin(cookie)
    name = act["name"]
    try:
        # 查询当前签到状态（很多活动不查也能签，但查一下能避免重复签到报错）
        idx = mtop(session, cookie, act["index_api"], act.get("index_data", {}),
                   app_key=get_app_key())
        time.sleep(random.uniform(1, 3))

        res = mtop(session, cookie, act["sign_api"], act["sign_data"],
                   app_key=get_app_key())
        ok, info = _mtop_ok(res)
        if res.get("error"):
            return f"【{pin}】{name}：请求异常 {res['error']}"
        if ok:
            data = res.get("data") or {}
            tip = data.get("tip") or data.get("message") or "签到成功"
            return f"【{pin}】{name}：{tip}"
        # 业务失败：把 ret 信息透出，方便定位是接口名失效还是参数问题
        return f"【{pin}】{name}：未成功 ({info})"
    except Exception as e:
        return f"【{pin}】{name}：异常 {e}"


# ---------- 主流程 ----------
def main():
    cookies = get_cookies()
    pins = [get_pin(c) for c in cookies]
    print(f"== 淘宝脚本启动：检测到 {len(cookies)} 个账号 -> {', '.join(pins)} ==")
    if not cookies:
        notify("淘宝脚本", "未检测到 TAO_COOKIE 环境变量（进程/配置文件/数据库均未找到），请在青龙面板中配置。")
        return

    # 检查每个账号是否含签名所需 token
    for c in cookies:
        if not _extract_token(c):
            print("⚠️ 警告：某账号 Cookie 缺少 _m_h5_tk，无法生成签名，"
                  "请重新抓取淘宝移动端 Cookie（见 README）。")

    # 防风控：随机延迟后再开始（TAO_DELAY_MAX 为最大分钟数，默认 30，设 0 关闭）
    try:
        delay_max = max(0, int(get_env_value("TAO_DELAY_MAX", "30")))
    except ValueError:
        delay_max = 30
    if delay_max > 0:
        delay = random.randint(0, delay_max * 60)
        print(f"== 防风控：随机延迟 {delay // 60} 分 {delay % 60} 秒后开始执行"
              f"（环境变量 TAO_DELAY_MAX 可调，单位分钟，0 为关闭）==")
        time.sleep(delay)

    all_msgs = []
    for cookie in cookies:
        s = requests.Session()
        s.headers.update({"Connection": "keep-alive"})
        for act in SIGN_ACTIVITIES:
            all_msgs.append(task_sign_activity(s, cookie, act))
            time.sleep(random.uniform(3, 8))   # 活动间随机间隔
        time.sleep(random.uniform(5, 12))      # 账号间随机间隔

    content = "\n".join(all_msgs)
    content += ("\n\n[说明] 若某活动长期返回 FAIL_SYS_ILLEGAL_REQUEST 或一直不成功，"
                "\n多半是当期接口名/参数已变更，请用手机淘宝抓包核对后替换脚本顶部"
                "\nSIGN_ACTIVITIES 里的 apiName / sign_data（详见 README 抓包方法）。")
    notify("淘宝闪购签到", content)
    print(content)


if __name__ == "__main__":
    main()
