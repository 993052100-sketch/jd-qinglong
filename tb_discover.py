#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
淘宝闪购签到接口自动发现（真实登录态）
====================================
仅用于用真实 TAO_COOKIE 探测当期闪购/签到活动的真实 mtop apiName。
步骤：
  1) 会话校验：调用一个必定存在且需登录的接口（购物车汇总），确认 Cookie 有效。
  2) 用真实登录态重新探活签到类候选接口（部分接口只在已登录时才解析）。
  3) 拉取若干 H5 落地页（闪购/淘金币/签到），从 HTML/JS 中嗅探 mtop apiName。
Cookie 从 /tmp/tao_cookie.txt 读取（不写仓库/日志）。
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
    print("缺少 requests")
    sys.exit(1)

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 "
      "Mobile/15E148 Safari/604.1")
DEFAULT_APP_KEY = "12574478"
API_VERSION = "1.0"

CANDIDATES = [
    "mtop.taobao.bgc.signin.index", "mtop.taobao.bgc.signin.doSignin",
    "mtop.taobao.lightoff.show",
    "mtop.taobao.bgc.sign.index", "mtop.taobao.bgc.sign.doSign",
    "mtop.taobao.bgc.dailySign.index", "mtop.taobao.bgc.dailySign.doSign",
    "mtop.taobao.bgc.signInActivity.index", "mtop.taobao.bgc.signInActivity.doSign",
    "mtop.taobao.bgc.signIn.index", "mtop.taobao.bgc.signIn.sign",
    "mtop.taobao.bgc.task.sign", "mtop.taobao.bgc.task.doSign",
    "mtop.taobao.bgc.signTask.index", "mtop.taobao.bgc.signTask.doSign",
    "mtop.taobao.bgc.goldcoin.sign", "mtop.taobao.bgc.goldcoin.index",
    "mtop.taobao.bgc.goldcoin.taskSign",
    "mtop.taobao.flashsale.signin.index", "mtop.taobao.flashsale.signin.doSignin",
    "mtop.taobao.bgc.flashsale.sign.index",
    "mtop.taobao.marketing.signin.index", "mtop.taobao.marketing.signin.doSign",
    "mtop.taobao.cashredpacket.sign.index", "mtop.taobao.cashredpacket.sign.doSign",
    "mtop.taobao.wireless.activity.sign.index", "mtop.taobao.bgc.activity.sign",
    # 再加一批更可能命中的（签到中心/任务中心/营销活动）
    "mtop.taobao.bgc.signCenter.index", "mtop.taobao.bgc.signCenter.doSign",
    "mtop.taobao.bgc.taskCenter.index", "mtop.taobao.bgc.taskCenter.list",
    "mtop.taobao.wireless.personal.sign.index", "mtop.taobao.bgc.userSign.index",
    "mtop.taobao.bgc.userSign.doSign", "mtop.taobao.promotion.signed.index",
    "mtop.taobao.marketing.sign.index", "mtop.taobao.marketing.activity.sign.index",
]

H5_PAGES = [
    "https://h5.m.taobao.com/flashsale/index.html",
    "https://h5.m.taobao.com/goldcoin/index.html",
    "https://h5.m.taobao.com/taolife/sign/index.html",
    "https://market.m.taobao.com/",
    "https://uland.taobao.com/",
]


def _extract_token(cookie):
    m = re.search(r"_m_h5_tk=([^;]+)", cookie)
    return m.group(1).split("_")[0] if m else ""


def _sign(token, t, app_key, data_str):
    return hashlib.md5(f"{token}&{t}&{app_key}&{data_str}".encode("utf-8")).hexdigest()


def mtop(session, cookie, api_name, data=None, app_key=DEFAULT_APP_KEY, v=API_VERSION):
    data = data or {}
    url = f"https://h5api.m.taobao.com/h5/{api_name}/{v}/"
    t = str(int(time.time() * 1000))
    token = _extract_token(cookie) or "dummy"
    data_str = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    sign = _sign(token, t, app_key, data_str)
    params = {"jsv": "2.4.11", "appKey": app_key, "t": t, "sign": sign,
              "api": api_name, "v": v, "type": "originaljson", "dataType": "json"}
    headers = {"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
               "Cookie": cookie, "Origin": "https://h5.m.taobao.com",
               "Referer": "https://h5.m.taobao.com/", "x-appkey": app_key,
               "x-t": t, "x-sign": sign, "x-ttid": "100000@taobao_android_9.20.0"}
    try:
        r = session.post(url, params=params, data={"data": data_str}, headers=headers, timeout=15)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def session_ok(session, cookie):
    # 购物车汇总：必定存在且需登录
    res = mtop(session, cookie, "mtop.taobao.bgc.cart.summary", {"exParams": ""})
    ret = res.get("ret") or []
    code = ret[0] if ret else (res.get("error", "NO_RET"))
    print(f"[会话校验] cart.summary -> {code}")
    return code


def probe_signins(session, cookie):
    print("\n[步骤2] 真实登录态探活候选签到接口：")
    alive = []
    for api in CANDIDATES:
        res = mtop(session, cookie, api)
        ret = res.get("ret") or []
        code = ret[0] if ret else (res.get("error", "NO_RET"))
        dead = ("API_NOT_FOUNDED" in code) or ("请求API不存在" in code) or ("NO_RET" in code)
        tag = "❌" if dead else "✅"
        if not dead:
            alive.append((api, code))
            print(f"  {tag} {api} -> {code}  | {json.dumps(res, ensure_ascii=False)[:160]}")
        else:
            print(f"  {tag} {api} -> {code}")
        time.sleep(random.uniform(0.3, 0.8))
    print(f"  => 活着的：{alive if alive else '无'}")
    return alive


def sniff_pages(session, cookie):
    print("\n[步骤3] 拉取 H5 落地页嗅探 apiName：")
    pat = re.compile(r"mtop\.taobao\.[A-Za-z0-9_.]*(?:sign|Sign|flashsale|FlashSale|goldcoin|GoldCoin|activity|Activity)[A-Za-z0-9_.]*")
    found = set()
    for url in H5_PAGES:
        try:
            r = session.get(url, headers={"User-Agent": UA, "Cookie": cookie,
                                          "Referer": "https://h5.m.taobao.com/"}, timeout=15)
            txt = r.text
            hits = pat.findall(txt)
            print(f"  {url}  HTTP {r.status_code}  命中api: {sorted(set(hits))[:10]}")
            found.update(hits)
        except Exception as e:
            print(f"  {url}  ERR {e}")
        time.sleep(random.uniform(0.3, 0.8))
    print(f"\n  汇总嗅探到的 sign/活动类 apiName：{sorted(found)}")
    return found


def main():
    path = "/tmp/tao_cookie.txt"
    if not os.path.exists(path):
        print("未找到 /tmp/tao_cookie.txt")
        return
    cookie = open(path, "r", encoding="utf-8").read().strip()
    print(f"== 真实登录态发现：Cookie 长度 {len(cookie)}，含 _m_h5_tk={'是' if '_m_h5_tk=' in cookie else '否'} ==")
    s = requests.Session()
    session_ok(s, cookie)
    alive = probe_signins(s, cookie)
    sniff_pages(s, cookie)
    print("\n== 结论 ==")
    if alive:
        print("发现可能在线的接口，请用 tb_probe.py 带真实 Cookie 进一步验证并实跑签到。")
    else:
        print("候选接口均未命中；H5 嗅探结果见上。若 H5 也未暴露 apiName，说明该活动需 App 内渲染，只能手机抓包。")


if __name__ == "__main__":
    main()
