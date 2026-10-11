#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
天天刮京豆 启动器（青龙面板专用）
================================
为什么要这个启动器：
  本面板（青龙 2.22）通过 API 创建的 JD_COOKIE 环境变量不会注入到任务进程，
  而 jd_guagua.js（社区刮刮卡脚本，内置 h5st 签名）需要从进程环境读 Cookie。
  本启动器用"进程 env → env.sh → env.db(sqlite)"三级兜底拿到 JD_COOKIE，
  再以 JD_COOKIE / CookieJD 两个常见变量名传给 node 子进程，兼容各脚本读取习惯。

用法（青龙定时任务）：
  python3 /ql/data/scripts/993052100-sketch_jd-qinglong_main/jd_guagua_run.py

依赖：
  - python3（青龙自带）
  - node（青龙自带）
  - node 依赖：axios、got、tough-cookie、crypto-js、https-proxy-agent、global-agent
    （在青龙 依赖管理 → NodeJs 中安装；缺失时脚本会打印缺失模块名）
"""

import os
import re
import sqlite3
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 可选：设置后跳过 guagua 脚本自身的随机等待，便于手动测试（默认不设）
DELAY_ENV = "JD_GUAGUA_NOWAIT"


def _read_from_env_file():
    """兜底1：青龙 env.sh（若存在）"""
    for path in ("/ql/config/env.sh", "/ql/data/config/env.sh", "/ql/.env"):
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


def _read_from_db():
    """兜底2：青龙 sqlite 数据库（env.db / database.sqlite 的 envs 表）"""
    candidates = (
        "/ql/data/db/env.db",
        "/ql/data/db/database.sqlite",
        "/ql/data/db/settings.db",
    )
    tables = ("envs", "Envs", "ENV", "env")
    for db in candidates:
        try:
            conn = sqlite3.connect(db)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tabs = [r[0] for r in cur.fetchall()]
            for tbl in tables:
                if tbl not in tabs:
                    continue
                try:
                    cur.execute(f"SELECT name, value, status FROM {tbl}")
                    for name, value, status in cur.fetchall():
                        if name == "JD_COOKIE" and str(status) == "0" and value:
                            conn.close()
                            return value
                except Exception:
                    continue
            conn.close()
        except Exception:
            continue
    return ""


def get_cookie():
    raw = os.environ.get("JD_COOKIE", "")
    if not raw:
        raw = _read_from_env_file()
    if not raw:
        raw = _read_from_db()
    return raw.strip()


def main():
    ck = get_cookie()
    if not ck:
        print("【刮刮卡启动器】未找到 JD_COOKIE（进程 / env.sh / 数据库均无），退出。")
        sys.exit(1)

    accounts = [p.strip() for p in re.split(r"[&\n]+", ck) if p.strip()]
    print(f"【刮刮卡启动器】检测到 {len(accounts)} 个账号 -> "
          + ", ".join(re.findall(r"pt_pin=([^;&]+)", ck) or ["未知"]))

    env = dict(os.environ)
    # 两个常见变量名都设，兼容不同脚本的读取习惯
    env["JD_COOKIE"] = ck
    env["CookieJD"] = accounts[0]
    if DELAY_ENV:
        env[DELAY_ENV] = "1"

    target = os.path.join(SCRIPT_DIR, "jd_guagua.js")
    if not os.path.exists(target):
        print(f"【刮刮卡启动器】未找到 {target}，请确认订阅已拉取，退出。")
        sys.exit(1)

    print("【刮刮卡启动器】启动 node jd_guagua.js ...\n", flush=True)
    ret = subprocess.call(["node", target], env=env)
    print(f"\n【刮刮卡启动器】jd_guagua.js 退出码 {ret}")
    sys.exit(ret)


if __name__ == "__main__":
    main()
