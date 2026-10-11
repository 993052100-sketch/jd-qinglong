#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
淘宝 Cookie 一键获取工具（扫码/账号登录）
================================
适用：在本机（macOS / Windows）运行，打开淘宝登录页，扫码或账号登录，
      登录成功后自动提取并打印 TAO_COOKIE，复制粘贴到青龙面板环境变量即可。

安装依赖：
    pip install playwright
    playwright install chromium

运行：
    python3 tb_cookie_helper.py

说明：
- 仅在本地运行，Cookie 只打印到终端，不会上传任何地方。
- 淘宝移动端站点（m.taobao.com）登录后会下发 _m_h5_tk 等关键字段，
  本工具会把 _m_h5_tk / cookie2 / _tb_token_ / unb / cna / sgcookie 一并导出，
  足够 tb_flashsign.py 的 mtop 签名使用。
- 若淘宝页面弹出滑块验证，请手动在浏览器里完成，工具会等待登录态出现。
"""

import sys
import time

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("缺少依赖 playwright，请先执行：")
    print("  pip install playwright")
    print("  playwright install chromium")
    sys.exit(1)

# 只保留这些关键字段，避免把无关 cookie 也导出
KEEP_FIELDS = ("_m_h5_tk", "cookie2", "_tb_token_", "unb", "cna", "sgcookie",
               "tracknick", "lid")


def main():
    print("正在启动浏览器并打开淘宝登录页，请扫码或账号登录...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent=("Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) "
                        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 "
                        "Mobile/15E148 Safari/604.1")
        )
        page = context.new_page()
        page.goto("https://m.taobao.com/", timeout=30000)

        # 轮询等待登录成功（拿到 _m_h5_tk 即视为登录且 token 就绪）
        cookie_str = None
        for _ in range(180):  # 最多等 6 分钟（淘宝有时要手动过滑块）
            cookies = context.cookies()
            ck = {c["name"]: c["value"] for c in cookies}
            if ck.get("_m_h5_tk") and ck.get("cookie2"):
                # _m_h5_tk 在登录后首次 mtop 调用才下发，这里先放登录页触发一次
                if "_" not in ck.get("_m_h5_tk", ""):
                    try:
                        page.evaluate("fetch('https://h5api.m.taobao.com/h5/"
                                      "mtop.taobao.bgc.signin.index/1.0/"
                                      "?jsv=2.4.11&appKey=12574478&t=%d"
                                      "&sign=x&api=mtop.taobao.bgc.signin.index"
                                      "&v=1.0&type=originaljson&dataType=json"
                                      "&data={}')" % int(time.time() * 1000))
                    except Exception:
                        pass
                    time.sleep(2)
                    cookies = context.cookies()
                    ck = {c["name"]: c["value"] for c in cookies}
                cookie_str = "; ".join(
                    f"{k}={ck[k]}" for k in KEEP_FIELDS if ck.get(k)
                )
                if "_m_h5_tk" in ck:
                    break
            time.sleep(2)

        browser.close()

    if not cookie_str or "_m_h5_tk" not in cookie_str:
        print("等待超时或未获取到 _m_h5_tk，请确认登录成功后再试（必要时手动过滑块）。")
        sys.exit(1)

    print("\n========== 复制下面这一行到青龙面板 TAO_COOKIE ==========")
    print(cookie_str)
    print("=========================================================\n")
    print("多账号：把多个账号的 Cookie 用  &  连起来，或每行一个。")


if __name__ == "__main__":
    main()
