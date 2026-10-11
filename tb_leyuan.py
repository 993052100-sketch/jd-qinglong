#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
淘宝「乐园币」玩法复刻脚本（青龙面板专用）
======================================
玩法来源：两年前淘宝「乐园币」活动
  入口路径：淘宝闪购 → 搜索 → 天天免单 → 跳转参与
  典型玩法（游戏化签到）：
    1. 查询活动首页（拿活动状态、币余额、任务列表）
    2. 每日签到领币（连续签到 Day-N 通常领更多）
    3. 做任务攒币（浏览商品/店铺、分享、加购等，每个任务带 taskToken）
    4. 查询币余额（可用于兑换红包/实物）

== 部署步骤（飞牛 NAS 上的青龙面板）==
1. 青龙面板 → 环境变量 → 新建：
      名称：TAO_COOKIE
      值  ：你的淘宝移动端 Cookie（需含 _m_h5_tk / cookie2 / _tb_token_ 等）
      多个账号用  &  或换行 分隔
2. 依赖管理 → 新建依赖 → 语言选 python → 输入 requests → 安装
3. 脚本管理 → 上传本文件到 /ql/data/scripts/tb_leyuan.py
4. 定时任务 → 新建：
      命令：python3 /ql/data/scripts/tb_leyuan.py
      cron：40 9 * * *   （每天上午 9:40，启动后会再随机延迟防风控）

== 关于接口名的重要说明（务必读完）==
- 两年前的乐园币活动接口现在大概率已下线，脚本里 `LEYUAN` 配置里的 apiName
  是「按当年命名规律推算的占位值」，需要你用手机淘宝抓包核对后替换：
    · 打开手机淘宝 → 闪购 → 搜索「天天免单」→ 进活动 → 参与乐园币
    · 用 HttpCanary/Charles 抓 `h5api.m.taobao.com` 的请求
    · URL 路径 `/h5/{apiName}/1.0/` 里的 apiName 即为真实接口名
    · 请求体 data JSON 即为对应参数（通常含 activityId / bizCode 等）
- 签名框架（_m_h5_tk 的 md5 x-sign）是通用的、可复用的，与具体活动无关，
  只要接口名/参数填对即可工作（tb_flashsign.py 已实测签名可被淘宝服务器接受）。
- Cookie 含登录凭证，请只保存在青龙环境变量中，切勿外泄或提交到仓库。
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

DEFAULT_APP_KEY = "12574478"
API_VERSION = "1.0"

# ---------- 乐园币活动接口配置（★需按当期活动抓包核对 apiName / 参数） ----------
# 玩法逻辑固定（首页→签到→任务→查余额），但「接口名和参数」随活动变化。
# 当年乐园币相关 mtop 接口前缀一般是 mtop.taobao.leyuan.* ，
# 下面为按命名规律推算的占位值，运行返回 FAIL_SYS_API_NOT_FOUNDED / API 不存在
# 时即说明需要替换为真实接口名（抓包方法见上方说明与 README）。
LEYUAN = {
    "name": "乐园币",
    # 活动标识：部分活动需要在参数里带 activityId / bizCode，从抓包 data 里取
    "activity_id": "",          # ★ 抓包 data 里的 activityId（如需要）
    "biz_code": "leyuan_coin",  # ★ 抓包 data 里的 bizCode（如需要）

    "index_api": "mtop.taobao.leyuan.index",       # 查询首页/余额/任务
    "sign_api": "mtop.taobao.leyuan.sign",         # 每日签到领币
    "task_list_api": "mtop.taobao.leyuan.taskList",# 任务列表
    "task_do_api": "mtop.taobao.leyuan.doTask",    # 完成任务领币

    # 各接口的请求体（占位，按抓包 data 调整）
    "index_data": {},
    "sign_data": {},
    "task_list_data": {},
    "task_do_extra": {},      # doTask 时额外固定参数（如 activityId）
}

# 单次最多完成的子任务数（防风控，避免高频）
MAX_TASKS = 10

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
    v = os.environ.get(name, "").strip()
    if not v:
        v = _read_from_env_file(name).strip()
    if not v:
        v = _read_env_from_db(name).strip()
    return v or default


def get_cookies():
    raw = get_env_value("TAO_COOKIE")
    if not raw:
        return []
    parts = re.split(r"[&\n]+", raw.strip())
    return [p.strip() for p in parts if p.strip()]


def get_pin(cookie):
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
    """淘宝 mtop h5 签名：sign = md5( token&t&app_key&dataStr )"""
    sign_str = f"{token}&{t}&{app_key}&{data_str}"
    return hashlib.md5(sign_str.encode("utf-8")).hexdigest()


def _extract_token(cookie):
    """提取 mtop 签名 token：_m_h5_tk 下划线前部分"""
    m = re.search(r"_m_h5_tk=([^;]+)", cookie)
    if not m:
        return ""
    return m.group(1).split("_")[0]


def mtop(session, cookie, api_name, data, app_key=DEFAULT_APP_KEY, v=API_VERSION):
    """封装一次淘宝 mtop 调用，返回接口 JSON；异常返回 {"error": "..."}"""
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
    ret = res.get("ret") or []
    if ret and any("SUCCESS" in str(x) for x in ret):
        return True, ret[0]
    return False, (ret[0] if ret else "无返回")


# ---------- 乐园币玩法 ----------
def _merge(data, cfg, key):
    """把活动公共参数（activityId/bizCode）并入请求体"""
    base = dict(data or {})
    if cfg.get("activity_id"):
        base.setdefault("activityId", cfg["activity_id"])
    if cfg.get("biz_code"):
        base.setdefault("bizCode", cfg["biz_code"])
    return base


def task_leyuan(session, cookie, cfg):
    """复刻乐园币玩法：首页查询 → 签到领币 → 做任务 → 查余额"""
    pin = get_pin(cookie)
    name = cfg["name"]
    logs = []

    # 1) 首页查询（活动状态 + 币余额 + 任务列表入口）
    idx = mtop(session, cookie, cfg["index_api"],
               _merge(cfg.get("index_data"), cfg, "index_data"),
               app_key=get_app_key())
    if idx.get("error"):
        return f"【{pin}】{name}：首页请求异常 {idx['error']}"
    ok, info = _mtop_ok(idx)
    if not ok:
        return f"【{pin}】{name}：首页查询失败 ({info})"
    data = idx.get("data") or {}
    # 余额字段名不确定，常见 coin / balance / gold / remainCoin
    balance = (data.get("coin") or data.get("balance") or
               data.get("gold") or data.get("remainCoin") or "?")
    logs.append(f"余额:{balance}")

    # 2) 每日签到领币
    time.sleep(random.uniform(1, 3))
    sign = mtop(session, cookie, cfg["sign_api"],
                _merge(cfg.get("sign_data"), cfg, "sign_data"),
                app_key=get_app_key())
    s_ok, s_info = _mtop_ok(sign)
    if s_ok:
        sd = (sign.get("data") or {})
        tip = sd.get("tip") or sd.get("message") or "签到成功"
        logs.append(f"签到:{tip}")
    else:
        logs.append(f"签到:{s_info}")
    time.sleep(random.uniform(2, 4))

    # 3) 任务列表 + 逐个完成
    tl = mtop(session, cookie, cfg["task_list_api"],
              _merge(cfg.get("task_list_data"), cfg, "task_list_data"),
              app_key=get_app_key())
    t_ok, t_info = _mtop_ok(tl)
    if t_ok:
        tdata = tl.get("data") or {}
        tasks = (tdata.get("taskList") or tdata.get("tasks") or
                 tdata.get("taskInfos") or [])
        done = 0
        for t in tasks[:MAX_TASKS]:
            token = (t.get("taskToken") or t.get("bizToken") or
                     t.get("token") or "")
            if not token:
                continue
            t_title = t.get("title") or t.get("name") or t.get("taskName") or "任务"
            do_data = {"taskToken": token}
            do_data.update(cfg.get("task_do_extra") or {})
            do_data = _merge(do_data, cfg, "task_do_extra")
            r = mtop(session, cookie, cfg["task_do_api"], do_data,
                     app_key=get_app_key())
            r_ok, r_info = _mtop_ok(r)
            if r_ok:
                done += 1
                logs.append(f"{t_title}:OK")
            else:
                logs.append(f"{t_title}:{r_info}")
            time.sleep(random.uniform(3, 8))   # 任务间随机间隔防风控
        logs.append(f"任务完成:{done}个")
    else:
        logs.append(f"任务列表:{t_info}")

    return f"【{pin}】{name}：{' | '.join(logs)}"


# ---------- 主流程 ----------
def main():
    cookies = get_cookies()
    pins = [get_pin(c) for c in cookies]
    print(f"== 淘宝乐园币脚本启动：检测到 {len(cookies)} 个账号 -> {', '.join(pins)} ==")
    if not cookies:
        notify("淘宝乐园币", "未检测到 TAO_COOKIE 环境变量（进程/配置文件/数据库均未找到），请在青龙面板中配置。")
        return

    for c in cookies:
        if not _extract_token(c):
            print("⚠️ 警告：某账号 Cookie 缺少 _m_h5_tk，无法生成签名，"
                  "请重新抓取淘宝移动端 Cookie（见 README）。")

    # 防风控：随机延迟（TAO_DELAY_MAX 为最大分钟数，默认 30，设 0 关闭）
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
        all_msgs.append(task_leyuan(s, cookie, LEYUAN))
        time.sleep(random.uniform(5, 12))      # 账号间随机间隔

    content = "\n".join(all_msgs)
    content += ("\n\n[说明] 两年前乐园币活动接口可能已下线，若返回 "
                "FAIL_SYS_API_NOT_FOUNDED / API 不存在，"
                "\n说明脚本顶部 LEYUAN 里的 apiName 需要替换为真实接口名。"
                "\n请用手机淘宝走「闪购→搜索天天免单→参与乐园币」抓包 "
                "h5api.m.taobao.com 的 /h5/{apiName}/1.0/ 核对（详见 README）。")
    notify("淘宝乐园币", content)
    print(content)


if __name__ == "__main__":
    main()
