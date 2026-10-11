#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mitmproxy 抓包记录插件
===================
用法:
    mitmdump -s capture.py -p 8080 --set flow_detail=0

把经过本代理的所有「接口类 / 文本类」请求与响应写入 capture_log.jsonl。
为避免日志体积爆炸，仅记录 URL 含接口特征 或 响应为文本/JSON 类型，
且 body 体积 < 200KB 的请求。
"""
import json
import os
import time

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "capture_log.jsonl")
MAX_BODY = 200 * 1024  # 200KB

# 京东 / 淘宝常见接口域名白名单（命中即记录，不论 content-type）
API_HINTS = (
    "api.m.jd.com", "api.jd.com", "wq.jd.com", "h5api.m.taobao.com",
    "mtop", "functionId", "gw.", "ajax", "/json", "acs.m.taobao.com",
    "api.taobao.com", "guide-acs", "api.m.taobao.com",
)
TEXT_TYPES = ("json", "text/", "javascript", "xml", "x-www-form-urlencoded")


def _interesting(flow) -> bool:
    url = flow.request.url
    if any(h in url for h in API_HINTS):
        return True
    if flow.response:
        ct = flow.response.headers.get("content-type", "")
        if any(t in ct for t in TEXT_TYPES):
            return True
    return False


def response(flow):
    if not flow.response or not _interesting(flow):
        return
    try:
        req_body = flow.request.text or ""
        resp_body = flow.response.text or ""
    except Exception:
        return
    if len(req_body) > MAX_BODY or len(resp_body) > MAX_BODY:
        return
    entry = {
        "t": round(time.time(), 3),
        "method": flow.request.method,
        "url": flow.request.url,
        "host": flow.request.host,
        "req_headers": dict(flow.request.headers),
        "req_body": req_body,
        "status": flow.response.status_code,
        "resp_headers": dict(flow.response.headers),
        "resp_body": resp_body,
    }
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def done():
    print(f"[capture] 抓包日志写入: {LOG_PATH}")
