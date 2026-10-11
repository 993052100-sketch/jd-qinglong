#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析抓包日志 capture_log.jsonl，提取京东 / 淘宝等活动接口清单
===========================================================
用法:
    python3 analyze_capture.py                  # 全量汇总（按域名聚合，去重）
    python3 analyze_capture.py --host jd.com    # 只看京东域名
    python3 analyze_capture.py --host taobao    # 只看淘宝域名
    python3 analyze_capture.py --keyword 签到    # 关键词过滤（匹配 URL / 请求体 / 响应体）
    python3 analyze_capture.py --show-body      # 同时打印响应体片段
    python3 analyze_capture.py --export jd_apis.txt  # 导出京东接口清单

自动识别:
    - 京东: URL / 请求体里的 functionId=xxx
    - 淘宝: mtop 路径 /h5/{apiName}/1.0/ 里的 apiName
"""
import argparse
import json
import os
import re
from collections import defaultdict

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "capture_log.jsonl")


def load():
    rows = []
    if not os.path.exists(LOG):
        return rows
    with open(LOG, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def extract_jd_functionid(url, body):
    m = re.search(r"functionId=([^&]+)", url)
    if m:
        return m.group(1)
    m = re.search(r'"functionId"\s*:\s*"([^"]+)"', body)
    if m:
        return m.group(1)
    return None


def extract_taobao_apiname(url, body):
    m = re.search(r"/h5/([^/]+)/\d+\.\d+/", url)
    if m:
        return m.group(1)
    return None


def main():
    ap = argparse.ArgumentParser(description="分析抓包日志，提取活动接口")
    ap.add_argument("--host", help="按域名过滤（子串匹配）")
    ap.add_argument("--keyword", help="关键词过滤（URL/请求体/响应体）")
    ap.add_argument("--show-body", action="store_true", help="打印响应体片段")
    ap.add_argument("--export", help="导出京东/淘宝接口清单到文件")
    ap.add_argument("--limit", type=int, default=0, help="每个域名最多显示条数(0=不限制)")
    args = ap.parse_args()

    rows = load()
    if not rows:
        print(f"暂无抓包数据。请先启动代理并在手机上操作目标 App。\n日志路径: {LOG}")
        return

    print(f"共记录 {len(rows)} 条请求\n")

    by_host = defaultdict(list)
    for r in rows:
        by_host[r["host"]].append(r)

    export_lines = []
    for host in sorted(by_host):
        if args.host and args.host not in host:
            continue
        items = by_host[host]
        print(f"### {host}   ({len(items)} 条)")
        seen = set()
        shown = 0
        for r in items:
            hay = r["url"] + r["req_body"] + r["resp_body"]
            if args.keyword and args.keyword not in hay:
                continue
            key = r["method"] + "|" + r["url"]
            if key in seen:
                continue
            seen.add(key)
            fid = extract_jd_functionid(r["url"], r["req_body"])
            api = extract_taobao_apiname(r["url"], r["req_body"])
            tag = ""
            if fid:
                tag = f"  [京东 functionId={fid}]"
                export_lines.append(f"京东\t{fid}\t{r['url']}")
            if api:
                tag = f"  [淘宝 apiName={api}]"
                export_lines.append(f"淘宝\t{api}\t{r['url']}")
            print(f"  {r['method']:4} {r['url'][:130]}{tag}")
            if args.show_body and r["resp_body"]:
                snippet = r["resp_body"][:200].replace("\n", " ")
                print(f"        resp: {snippet}")
            shown += 1
            if args.limit and shown >= args.limit:
                break
        print()

    if args.export:
        with open(args.export, "w", encoding="utf-8") as f:
            f.write("\n".join(export_lines))
        print(f"已导出 {len(export_lines)} 条接口到 {args.export}")


if __name__ == "__main__":
    main()
