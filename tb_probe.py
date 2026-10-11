#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
淘宝 mtop 接口名探活工具（青龙面板辅助）
====================================
用途：
  淘宝签到/活动类的 mtop apiName 会随每期活动变化。本工具用一批候选接口名
  挨个打到淘宝网关（h5api.m.taobao.com），根据返回判定该接口「当前是否真实存在」。

判定逻辑（带任意 Cookie 都可探活，因为网关先解析 apiName 再校验登录）：
  - 返回 FAIL_SYS_API_NOT_FOUNDED / 请求API不存在  → 接口名不存在（死）
  - 返回其它（如会话失效/请登录/参数错误/SUCCESS） → 接口名存在（活），只差真实 Cookie

用法：
  # 1) 默认用内置候选列表探活（无需 Cookie）：
  python3 tb_probe.py
  # 2) 带上你的真实 TAO_COOKIE 探活（活接口会进一步显示是否签到成功）：
  TAO_COOKIE='_m_h5_tk=...; cookie2=...; ...' python3 tb_probe.py
  # 3) 指定自定义候选（逗号分隔）：
  API_LIST="mtop.x.a,mtop.y.b" python3 tb_probe.py

注意：仅用于确认接口是否存活，不泄露任何信息到第三方；Cookie 只发给淘宝官方域名。
"""

import os
import re
import sys
import json
import time
import hashlib
import random

try:
    import requests
except ImportError:
    print("缺少依赖 requests，请在青龙「依赖管理」安装 python 版 requests")
    sys.exit(1)

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 "
      "Mobile/15E148 Safari/604.1")
DEFAULT_APP_KEY = "12574478"
API_VERSION = "1.0"

# 候选接口名：覆盖淘宝常见的签到/活动类 mtop 接口（按命名规律整理，供探活）
DEFAULT_CANDIDATES = [
    # 现有占位（已知死，作为对照）
    "mtop.taobao.bgc.signin.index",
    "mtop.taobao.bgc.signin.doSignin",
    "mtop.taobao.lightoff.show",
    # 通用签到类
    "mtop.taobao.bgc.sign.index",
    "mtop.taobao.bgc.sign.doSign",
    "mtop.taobao.bgc.dailySign.index",
    "mtop.taobao.bgc.dailySign.doSign",
    "mtop.taobao.bgc.signInActivity.index",
    "mtop.taobao.bgc.signInActivity.doSign",
    "mtop.taobao.bgc.signIn.index",
    "mtop.taobao.bgc.signIn.sign",
    # 任务/签到中心
    "mtop.taobao.bgc.task.sign",
    "mtop.taobao.bgc.task.doSign",
    "mtop.taobao.bgc.signTask.index",
    "mtop.taobao.bgc.signTask.doSign",
    # 淘金币
    "mtop.taobao.bgc.goldcoin.sign",
    "mtop.taobao.bgc.goldcoin.index",
    "mtop.taobao.bgc.goldcoin.taskSign",
    # 闪购/特卖活动
    "mtop.taobao.flashsale.signin.index",
    "mtop.taobao.flashsale.signin.doSignin",
    "mtop.taobao.bgc.flashsale.sign.index",
    "mtop.taobao.marketing.signin.index",
    "mtop.taobao.marketing.signin.doSign",
    # 现金红包签到
    "mtop.taobao.cashredpacket.sign.index",
    "mtop.taobao.cashredpacket.sign.doSign",
    # 通用活动
    "mtop.taobao.wireless.activity.sign.index",
    "mtop.taobao.bgc.activity.sign",
]


def _extract_token(cookie):
    m = re.search(r"_m_h5_tk=([^;]+)", cookie)
    if not m:
        return ""
    return m.group(1).split("_")[0]


def _mtop_sign(token, t, app_key, data_str):
    return hashlib.md5(f"{token}&{t}&{app_key}&{data_str}".encode("utf-8")).hexdigest()


def probe(session, cookie, api_name, app_key=DEFAULT_APP_KEY, v=API_VERSION, data=None):
    data = data or {}
    url = f"https://h5api.m.taobao.com/h5/{api_name}/{v}/"
    t = str(int(time.time() * 1000))
    token = _extract_token(cookie) or "dummy"
    data_str = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    sign = _mtop_sign(token, t, app_key, data_str)
    params = {
        "jsv": "2.4.11", "appKey": app_key, "t": t, "sign": sign,
        "api": api_name, "v": v, "type": "originaljson", "dataType": "json",
    }
    headers = {
        "User-Agent": UA,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Cookie": cookie,
        "Origin": "https://h5.m.taobao.com",
        "Referer": "https://h5.m.taobao.com/",
        "x-appkey": app_key, "x-t": t, "x-sign": sign,
        "x-ttid": "100000@taobao_android_9.20.0",
    }
    try:
        r = session.post(url, params=params, data={"data": data_str},
                         headers=headers, timeout=15)
        res = r.json()
    except Exception as e:
        return "NET_ERR", str(e)
    ret = res.get("ret") or []
    code = ret[0] if ret else "NO_RET"
    return code, json.dumps(res, ensure_ascii=False)[:200]


def main():
    cookie = os.environ.get("TAO_COOKIE", "").strip()
    api_list = os.environ.get("API_LIST", "")
    candidates = [a.strip() for a in api_list.split(",") if a.strip()] or DEFAULT_CANDIDATES
    print(f"== 淘宝 mtop 接口探活：共 {len(candidates)} 个候选，"
          f"Cookie={'有(真实)' if cookie else '无(假token)'} ==")
    session = requests.Session()
    alive, dead = [], []
    for api in candidates:
        code, detail = probe(session, cookie or "_m_h5_tk=dummy_1700000000000", api)
        is_dead = ("API_NOT_FOUNDED" in code) or ("请求API不存在" in code) or ("NO_RET" in code)
        tag = "❌死" if is_dead else "✅活"
        print(f"  {tag}  {api}  ->  {code}")
        (dead if is_dead else alive).append((api, code))
        time.sleep(random.uniform(0.3, 1.0))
    print("\n--- 活着的接口（当前真实存在，只差真实 Cookie 即可用）---")
    for api, code in alive:
        print(f"  ✅ {api}   [{code}]")
    if not alive:
        print("  （本轮候选全部不存在，请用手机抓包获取当期真实 apiName）")
    print(f"\n统计：活 {len(alive)} / 死 {len(dead)} / 共 {len(candidates)}")


if __name__ == "__main__":
    main()
