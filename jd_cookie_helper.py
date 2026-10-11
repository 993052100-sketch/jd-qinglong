#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
京东 Cookie 一键获取工具（扫码登录）
================================
适用：在本机（macOS / Windows）运行，打开京东登录页，手机京东 App 扫码，
      登录成功后自动提取并打印 JD_COOKIE，复制粘贴到青龙面板环境变量即可。

安装依赖：
    pip install playwright
    playwright install chromium

运行：
    python3 jd_cookie_helper.py

说明：
- 仅在本地运行，Cookie 只打印到终端，不会上传任何地方。
- 默认只提取登录必需的字段（pt_key / pt_pin 等），足够青龙脚本使用。
- 如果京东页面默认不是二维码登录，手动点一下「扫码登录」再扫。
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
KEEP_FIELDS = ("pt_key", "pt_pin", "pt_token", "pwdt_id", "sessionid")


def main():
    print("正在启动浏览器并打开京东登录页，请用手机京东 App 扫码...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://passport.jd.com/new/login.aspx", timeout=30000)

        # 轮询等待登录成功（拿到 pt_key 即视为登录）
        cookie_str = None
        for _ in range(150):  # 最多等 5 分钟
            cookies = context.cookies()
            ck = {c["name"]: c["value"] for c in cookies}
            if ck.get("pt_key") and ck.get("pt_pin"):
                cookie_str = "; ".join(
                    f"{k}={ck[k]}" for k in KEEP_FIELDS if ck.get(k)
                )
                break
            time.sleep(2)

        browser.close()

    if not cookie_str:
        print("等待超时，未检测到登录成功，请重试。")
        sys.exit(1)

    print("\n========== 复制下面这一行到青龙面板 JD_COOKIE ==========")
    print(cookie_str)
    print("=======================================================\n")
    print("多账号：把多个账号的 Cookie 用  &  连起来，或每行一个。")


if __name__ == "__main__":
    main()
