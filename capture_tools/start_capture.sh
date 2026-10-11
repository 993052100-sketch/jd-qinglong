#!/bin/bash
# 启动抓包代理（mitmproxy）
# 手机 WiFi 手动代理配置: 服务器=<Mac局域网IP>  端口=8080
# 手机装证书: 配好代理后浏览器打开 http://mitm.it 下载并信任
set -e
cd "$(dirname "$0")"
PORT="${1:-8080}"
echo ">>> 启动抓包代理，端口 $PORT"
echo ">>> 日志: $(pwd)/capture_log.jsonl"
echo ">>> 手机代理服务器填 Mac 局域网 IP，端口 $PORT"
echo ">>> 手机浏览器访问 http://mitm.it 安装 CA 证书"
echo ">>> Ctrl+C 停止"
mitmdump -s capture.py -p "$PORT" --set flow_detail=0
