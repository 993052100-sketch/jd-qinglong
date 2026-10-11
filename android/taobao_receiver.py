#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
青龙侧接收端：接收手机 AutoX.js 上报的淘宝签到结果
========================================================
部署在跑青龙的机器/NAS 上(与青龙同机或同局域网)，作用是把手机端
AutoX.js 的执行结果收口到青龙工作流里：落盘 + 推送通知。

启动：
    python3 taobao_receiver.py
    # 改端口/通知：
    PORT=5678 BARK_KEY=xxxx python3 taobao_receiver.py

接口：
    POST /result        手机 AutoX.js 上报结果(JSON)
    GET  /result        查看最近一次结果
    GET  /health        健康检查

结果会写入同目录 last_result.json，方便青龙定时任务读取/归档。

通知：默认把结果打印到日志，并可选通过 Bark / Server 酱 推送到手机。
      青龙自身的通知(青龙面板→配置文件)也可在收到结果后调用青龙 API，
      见文件底部 NOTIFY 段注释。
"""

import json
import os
import sys
import datetime
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get("PORT", "5678"))

# ---- 通知配置(按需填写，留空则不推送) ----
# Bark：在手机装 Bark，复制设备 Key(形如 abc123)，下面填 Key 即可
BARK_KEY = os.environ.get("BARK_KEY", "")
# Server 酱：https://sct.ftqq.com/ 申请的 SendKey
SERVERCHAN_KEY = os.environ.get("SERVERCHAN_KEY", "")

RESULT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_result.json")


def save_result(payload: dict):
    """落盘最近一次结果，并保留历史(最近 20 条)。"""
    payload["received_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # 最近一次
    with open(RESULT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    # 历史
    hist_file = os.path.join(os.path.dirname(RESULT_FILE), "result_history.json")
    history = []
    if os.path.exists(hist_file):
        try:
            with open(hist_file, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []
    history.insert(0, payload)
    history = history[:20]
    with open(hist_file, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def notify(title: str, content: str):
    """通过 Bark / Server 酱 推送(配置为空则跳过)。"""
    import urllib.request
    if BARK_KEY:
        try:
            url = f"https://api.day.app/{BARK_KEY}/{urllib.parse.quote(title)}/{urllib.parse.quote(content)}"
            urllib.request.urlopen(url, timeout=10)
            print(f"[{datetime.datetime.now()}] Bark 推送成功")
        except Exception as e:
            print(f"[{datetime.datetime.now()}] Bark 推送失败: {e}")
    if SERVERCHAN_KEY:
        try:
            url = f"https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send"
            data = urllib.parse.urlencode({"title": title, "desp": content}).encode()
            req = urllib.request.Request(url, data=data, method="POST")
            urllib.request.urlopen(req, timeout=10)
            print(f"[{datetime.datetime.now()}] Server 酱 推送成功")
        except Exception as e:
            print(f"[{datetime.datetime.now()}] Server 酱 推送失败: {e}")


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body: str):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_GET(self):
        if self.path.startswith("/result"):
            if os.path.exists(RESULT_FILE):
                with open(RESULT_FILE, "r", encoding="utf-8") as f:
                    self._send(200, f.read())
            else:
                self._send(404, json.dumps({"msg": "尚无结果"}, ensure_ascii=False))
        elif self.path.startswith("/health"):
            self._send(200, json.dumps({"status": "ok"}, ensure_ascii=False))
        else:
            self._send(404, json.dumps({"msg": "not found"}, ensure_ascii=False))

    def do_POST(self):
        if not self.path.startswith("/result"):
            self._send(404, json.dumps({"msg": "not found"}, ensure_ascii=False))
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw.decode("utf-8"))
        except Exception as e:
            self._send(400, json.dumps({"msg": f"bad json: {e}"}, ensure_ascii=False))
            return

        save_result(payload)
        ok = payload.get("ok")
        reason = payload.get("reason", "")
        device = payload.get("device", "")
        title = "淘宝签到" + ("成功" if ok else "失败")
        content = f"设备:{device}\n结果:{reason}\n时间:{payload.get('time','')}"
        print(f"[{datetime.datetime.now()}] 收到结果 -> {title} | {content}")
        notify(title, content)
        self._send(200, json.dumps({"msg": "received"}, ensure_ascii=False))

    def log_message(self, fmt, *args):
        # 简化日志
        sys.stderr.write("[receiver] " + (fmt % args) + "\n")


def main():
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"淘宝签到接收端已启动: http://0.0.0.0:{PORT}")
    print(f"  结果文件: {RESULT_FILE}")
    print(f"  Bark: {'已配置' if BARK_KEY else '未配置'} | Server酱: {'已配置' if SERVERCHAN_KEY else '未配置'}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
