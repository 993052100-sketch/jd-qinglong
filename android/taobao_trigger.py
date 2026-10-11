#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
青龙侧触发/检查脚本：淘宝签到的统一入口
========================================================
在青龙面板建一个定时任务(例如每天 10:00)，命令：
    python3 /ql/data/scripts/jd-qinglong/android/taobao_trigger.py

它做两件事：
  1) 检查手机端今天是否已上报签到结果(读 last_result.json)，把状态打到青龙日志；
  2) 若配置了 PHONE_SERVER_URL，主动 POST 触发手机端 AutoX.js 执行
     (需手机端脚本启用 server 模式，见 taobao_flashsign.js 顶部说明)。

推荐用法(解耦、最稳)：
  手机 AutoX.js 自带定时(每天 9:35)执行签到 → 自动上报到 receiver →
  本脚本每天 10:00 只做"查结果 + 汇总日志"，无需反向触发手机。

进阶用法(青龙统一调度)：
  手机 AutoX.js 启用 server 模式，本脚本配 PHONE_SERVER_URL，
  由青龙 cron 直接控制何时触发手机执行。
"""

import json
import os
import sys
import datetime
import urllib.request
import urllib.parse

BASE = os.path.dirname(os.path.abspath(__file__))
RESULT_FILE = os.path.join(BASE, "last_result.json")

# 接收端地址(用于读最近结果)；默认同机 localhost
RECEIVER_URL = os.environ.get("RECEIVER_URL", "http://127.0.0.1:5678")
# 手机端 AutoX.js server 地址(可选，启用 server 模式才填)
PHONE_SERVER_URL = os.environ.get("PHONE_SERVER_URL", "")


def get_today_result():
    """读 last_result.json，返回今天的结果(若有)。"""
    if not os.path.exists(RESULT_FILE):
        return None
    try:
        with open(RESULT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    t = data.get("time") or data.get("received_at") or ""
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    if today in t:
        return data
    return None


def trigger_phone():
    """主动触发手机端执行(需手机 server 模式)。"""
    if not PHONE_SERVER_URL:
        print("[trigger] 未配置 PHONE_SERVER_URL，跳过主动触发(手机将按自身定时执行)")
        return
    try:
        url = PHONE_SERVER_URL.rstrip("/") + "/run"
        req = urllib.request.Request(url, data=b"{}", method="POST")
        r = urllib.request.urlopen(req, timeout=10)
        print(f"[trigger] 已触发手机执行: {r.status}")
    except Exception as e:
        print(f"[trigger] 触发手机失败: {e}")


def main():
    print("==== 淘宝签到 青龙侧检查 ====")
    res = get_today_result()
    if res is None:
        print("[status] 今天手机端尚未上报结果")
        print("          可能原因：手机 AutoX.js 定时未到 / 未运行 / 接收端未启动")
    else:
        ok = res.get("ok")
        reason = res.get("reason", "")
        device = res.get("device", "")
        print(f"[status] 今天结果 -> {'成功' if ok else '失败'} | 设备:{device} | {reason}")

    # 主动触发(可选)
    trigger_phone()
    print("==== 检查完成 ====")


if __name__ == "__main__":
    main()
