#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
京东每日自动化脚本（青龙面板专用）
================================
功能：
  1. 京东 App 签到领京豆
  2. 京喜签到
  3. 京东超市签到
  4. 看视频 / 做任务赚京豆（best-effort，接口随活动变动）
  5. 东东农场（种豆得豆）：签到 + 浇水 + 任务奖励领取 + 抽奖
  6. 东东牧场（养牛养羊）：签到 + 喂养 + 任务奖励领取 + 抽奖

== 部署步骤（飞牛 NAS 上的青龙面板）==
1. 青龙面板 → 环境变量 → 新建：
      名称：JD_COOKIE
      值  ：你的京东 Cookie（浏览器 F12 复制，需含 pt_key=...; pt_pin=...）
      多个账号用  &  或换行 分隔
2. 依赖管理 → 新建依赖 → 语言选 python → 输入 requests → 安装
3. 脚本管理 → 上传本文件到 /ql/data/scripts/jd_daily.py （或走订阅拉取）
4. 定时任务 → 新建：
      命令：python3 /ql/data/scripts/jd_daily.py
      cron：0 9 * * *   （每天上午 9 点）

== 说明 ==
- 本脚本调用京东公开接口，依赖京东服务端稳定性；部分活动接口会调整，
  如某任务长期失败，请参照青龙社区脚本更新对应 functionId / body。
- Cookie 含登录凭证，请只保存在青龙环境变量中，切勿外泄或提交到仓库。
"""

import os
import re
import sys
import json
import time
import random
import hashlib
import string

try:
    import requests
except ImportError:
    print("缺少依赖 requests，请在青龙「依赖管理」中安装 python 版 requests")
    sys.exit(1)

# ---------- 基础配置 ----------
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 "
      "Mobile/15E148 Safari/604.1")

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
def _read_from_env_file():
    """兜底：青龙通常会把环境变量写入 /ql/config/env.sh，
    若任务进程未注入 JD_COOKIE，则从此文件读取。"""
    candidates = ["/ql/config/env.sh", "/ql/data/config/env.sh", "/ql/.env"]
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                txt = f.read()
            for line in txt.splitlines():
                line = line.strip()
                if line.startswith("export JD_COOKIE=") or line.startswith("JD_COOKIE="):
                    val = line.split("=", 1)[1].strip().strip("'").strip('"')
                    if val and val.lower() not in ("''", '""'):
                        return val
        except Exception:
            continue
    return ""


def get_cookies():
    """从环境变量读取多个账号的 Cookie（支持 & 与换行分隔）"""
    raw = os.environ.get("JD_COOKIE", "")
    if not raw:
        raw = _read_from_env_file()
    if not raw:
        return []
    parts = re.split(r"[&\n]+", raw.strip())
    return [p.strip() for p in parts if p.strip()]


def get_pin(cookie):
    m = re.search(r"pt_pin=([^;]+)", cookie)
    if m:
        from urllib.parse import unquote
        return unquote(m.group(1))
    return "未知账号"


def gen_uuid():
    return "".join(random.choices(string.hexdigits.lower(), k=16))


def sign(body, stk, uuid="", version="2.0.0"):
    """
    京东简化签名算法（社区通用实现）。
    老接口通常无需签名；若某任务需要 h5st，可在此扩展后注入 api() 的 params。
    """
    ts = str(int(time.time() * 1000))
    st = [str(body.get(k, "")) for k in stk.split(",")]
    sha = hashlib.sha256()
    sha.update(("".join(st)).encode("utf-8"))
    stk_hash = sha.hexdigest()
    sha = hashlib.sha256()
    sha.update(("".join([uuid, stk_hash, ts, version])).encode("utf-8"))
    return {"st": stk_hash, "sign": sha.hexdigest(), "sv": version, "ts": ts}


def api(session, cookie, function_id, body, appid="ld"):
    """封装京东 client.action 请求"""
    url = "https://api.m.jd.com/client.action"
    ts = str(int(time.time() * 1000))
    uuid = gen_uuid()
    params = {
        "functionId": function_id,
        "appid": appid,
        "client": "android",
        "clientVersion": "11.0.0",
        "networkType": "wifi",
        "osVersion": "31",
        "uuid": uuid,
        "timestamp": ts,
    }
    data = {
        "body": json.dumps(body, separators=(",", ":")),
        "build": "167728",
    }
    headers = {
        "User-Agent": UA,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Accept": "*/*",
        "Cookie": cookie,
        "Referer": "https://h5.m.jd.com/",
        "Origin": "https://h5.m.jd.com",
    }
    try:
        r = session.post(url, params=params, data=data, headers=headers, timeout=15)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def _result(res, pin, name):
    """统一把接口返回转换成可读结果字符串"""
    if res.get("error"):
        return f"【{pin}】{name}失败：{res['error']}"
    if res.get("success") or res.get("code") in ("0", 0):
        return f"【{pin}】{name}成功"
    return f"【{pin}】{name}：{res.get('message') or res}"


# ---------- 具体任务 ----------
def task_jd_bean_sign(session, cookie):
    """京东 App 签到领京豆"""
    pin = get_pin(cookie)
    try:
        body = {"flag": "cp_sign", "version": 2, "channel": "签到领京豆"}
        api(session, cookie, "signBeanIndex", body)          # 查状态
        act = api(session, cookie, "signBeanAct", body)       # 执行签到
        if act.get("success") or act.get("code") in ("0", 0):
            d = act.get("data", {})
            num = d.get("beanNum") or d.get("message") or "已签到"
            return f"【{pin}】京东签到成功：{num}"
        return _result(act, pin, "京东签到")
    except Exception as e:
        return f"【{pin}】京东签到异常：{e}"


def task_jingxi_sign(session, cookie):
    """京喜签到"""
    pin = get_pin(cookie)
    try:
        body = {
            "businessId": "", "jumpType": 1, "pageClickKey": "BOTTOM_TAB",
            "pageId": "MSHOP_HOME", "reqSrc": "", "scene": "",
            "subTitleId": "", "titleId": "", "token": "",
        }
        res = api(session, cookie, "interact_sign_getSign", body, appid="CcApp")
        return _result(res, pin, "京喜签到")
    except Exception as e:
        return f"【{pin}】京喜签到异常：{e}"


def task_supermarket_sign(session, cookie):
    """京东超市签到"""
    pin = get_pin(cookie)
    try:
        api(session, cookie, "getSignInfo", {"channel": "99"}, appid="ld")
        res = api(session, cookie, "doSign", {"channel": "99"}, appid="ld")
        return _result(res, pin, "京东超市签到")
    except Exception as e:
        return f"【{pin}】京东超市签到异常：{e}"


def task_bean_video(session, cookie):
    """
    看视频 / 做任务赚京豆（best-effort）
    京东赚京豆任务体系接口变动频繁，这里给出通用流程骨架：
    查任务 → 领任务 → 做任务（看视频类通常等待后上报）。
    具体 functionId / body 可能需按当期活动微调。
    """
    pin = get_pin(cookie)
    try:
        res = api(session, cookie, "queryTaskList", {"taskType": "bean"}, appid="ld")
        if res.get("error"):
            return f"【{pin}】赚京豆查询失败：{res['error']}"
        tasks = res.get("data", {}).get("taskList", []) or []
        done = 0
        for t in tasks:
            t_id = t.get("taskId") or t.get("id")
            if not t_id:
                continue
            api(session, cookie, "getTaskDetail", {"taskId": t_id}, appid="ld")
            do = api(session, cookie, "doTask",
                     {"taskId": t_id, "taskType": "bean"}, appid="ld")
            if do.get("success") or do.get("code") in ("0", 0):
                done += 1
            time.sleep(1)
        return (f"【{pin}】赚京豆任务完成 {done} 个"
                f"（接口随活动变化，请关注运行日志）")
    except Exception as e:
        return f"【{pin}】赚京豆任务异常：{e}"


def task_jd_farm(session, cookie):
    """
    东东农场（种豆得豆）每日任务（best-effort）
    流程：进入农场 → 签到 → 浇水(用满当日水) → 领取任务奖励 → 抽奖。
    各动作相互独立、异常兜底，单个失败不影响其他。
    接口随版本变动是常态，请关注运行日志；若某 functionId 长期报错，按当期活动微调。
    """
    pin = get_pin(cookie)
    log = []
    try:
        home = api(session, cookie, "farmHome", {"version": 4, "channel": 1}, appid="ld")
        if home.get("error"):
            return f"【{pin}】东东农场进入失败：{home['error']}"
        data = home.get("data", {}) or {}
        round_id = data.get("roundId") or data.get("farmUserPro", {}).get("roundId")

        # 签到
        try:
            r = api(session, cookie, "farmSign", {"roundId": round_id}, appid="ld")
            ok = r.get("success") or r.get("code") in ("0", 0)
            log.append("签到:" + ("OK" if ok else str(r.get("message", "-"))))
        except Exception as e:
            log.append(f"签到异常:{e}")

        # 浇水（最多连续 10 次，用满当日水滴即停）
        try:
            for _ in range(10):
                w = api(session, cookie, "farmWater",
                        {"roundId": round_id, "type": 1}, appid="ld")
                if not (w.get("success") or w.get("code") in ("0", 0)):
                    break
                time.sleep(1)
            log.append("浇水:已执行")
        except Exception as e:
            log.append(f"浇水异常:{e}")

        # 任务列表：查询 + 领取已完成任务奖励
        try:
            tl = api(session, cookie, "farmTaskList",
                     {"version": 4, "channel": 1, "roundId": round_id}, appid="ld")
            tasks = (tl.get("data", {}) or {}).get("taskList", []) or []
            got = 0
            for t in tasks:
                t_id = t.get("taskId")
                if not t_id:
                    continue
                rr = api(session, cookie, "receiveFarmTask",
                         {"taskId": t_id, "taskType": t.get("taskType", 2),
                          "roundId": round_id}, appid="ld")
                if rr.get("success") or rr.get("code") in ("0", 0):
                    got += 1
                time.sleep(1)
            log.append(f"任务领奖:{got}个")
        except Exception as e:
            log.append(f"任务领取异常:{e}")

        # 抽奖（用剩余抽奖券，最多 5 次）
        try:
            for _ in range(5):
                lot = api(session, cookie, "farmLottery",
                          {"type": 1, "actionType": 1, "roundId": round_id}, appid="ld")
                if not (lot.get("success") or lot.get("code") in ("0", 0)):
                    break
                time.sleep(1)
            log.append("抽奖:已执行")
        except Exception as e:
            log.append(f"抽奖异常:{e}")

        return f"【{pin}】东东农场：{' | '.join(log)}"
    except Exception as e:
        return f"【{pin}】东东农场异常：{e}"


def task_jd_ranch(session, cookie):
    """
    东东牧场（养牛养羊）每日任务（best-effort）
    流程：初始化 → 签到 → 喂养(用满饲料) → 领取任务奖励 → 抽奖。
    各动作相互独立、异常兜底。接口变动频繁，请按需微调。
    """
    pin = get_pin(cookie)
    log = []
    try:
        init = api(session, cookie, "taskInit", {"version": 2}, appid="ld")
        if init.get("error"):
            return f"【{pin}】东东牧场进入失败：{init['error']}"

        # 签到
        try:
            r = api(session, cookie, "ranchSign", {"version": 2, "type": 1}, appid="ld")
            ok = r.get("success") or r.get("code") in ("0", 0)
            log.append("签到:" + ("OK" if ok else str(r.get("message", "-"))))
        except Exception as e:
            log.append(f"签到异常:{e}")

        # 喂养（最多连续 10 次，用满饲料即停）
        try:
            for _ in range(10):
                f = api(session, cookie, "feed", {"version": 2, "type": 1}, appid="ld")
                if not (f.get("success") or f.get("code") in ("0", 0)):
                    break
                time.sleep(1)
            log.append("喂养:已执行")
        except Exception as e:
            log.append(f"喂养异常:{e}")

        # 任务列表：查询 + 领取已完成任务奖励
        try:
            tl = api(session, cookie, "taskList", {"version": 2}, appid="ld")
            tasks = (tl.get("data", {}) or {}).get("taskList", []) or []
            got = 0
            for t in tasks:
                t_id = t.get("taskId")
                if not t_id:
                    continue
                rr = api(session, cookie, "receieveRanchTask",
                         {"taskId": t_id, "version": 2}, appid="ld")
                if rr.get("success") or rr.get("code") in ("0", 0):
                    got += 1
                time.sleep(1)
            log.append(f"任务领奖:{got}个")
        except Exception as e:
            log.append(f"任务领取异常:{e}")

        # 抽奖（最多 5 次）
        try:
            for _ in range(5):
                lot = api(session, cookie, "ranchLottery",
                          {"version": 2, "type": 1}, appid="ld")
                if not (lot.get("success") or lot.get("code") in ("0", 0)):
                    break
                time.sleep(1)
            log.append("抽奖:已执行")
        except Exception as e:
            log.append(f"抽奖异常:{e}")

        return f"【{pin}】东东牧场：{' | '.join(log)}"
    except Exception as e:
        return f"【{pin}】东东牧场异常：{e}"


# ---------- 主流程 ----------
def main():
    cookies = get_cookies()
    pins = [get_pin(c) for c in cookies]
    print(f"== 京东脚本启动：检测到 {len(cookies)} 个账号 -> {', '.join(pins)} ==")
    if not cookies:
        notify("京东脚本", "未检测到 JD_COOKIE 环境变量，请在青龙面板中配置。")
        return

    all_msgs = []
    for cookie in cookies:
        s = requests.Session()
        s.headers.update({"Connection": "keep-alive"})
        msgs = [
            task_jd_bean_sign(s, cookie),
            task_jingxi_sign(s, cookie),
            task_supermarket_sign(s, cookie),
            task_bean_video(s, cookie),
            task_jd_farm(s, cookie),
            task_jd_ranch(s, cookie),
        ]
        all_msgs.extend(msgs)
        time.sleep(2)  # 账号间稍作间隔，降低风控

    content = "\n".join(all_msgs)
    notify("京东每日任务", content)
    print(content)


if __name__ == "__main__":
    main()
