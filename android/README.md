# 淘宝签到 · App 内自动化方案（Android）

> 为什么有这个目录：原 `tb_flashsign.py` / `tb_leyuan.py` 走纯 HTTP + md5 轻签名(x-sign)
> 调淘宝 mtop 接口，但**淘宝网关现在拦截这类请求**——实测无论接口名对不对，连购物车、
> 商品详情等核心接口都统一返回 `FAIL_SYS_API_NOT_FOUNDED`。根因是缺淘宝安全 SDK 签名参数
> （`x-sgext`/`x-mini-wua` 等）。只有"在手机淘宝 App 内部运行"的请求才会被自动签名通过。
>
> 所以淘宝签到改走 **AutoX.js 在手机上模拟点击手淘** 的方案，由淘宝自带安全 SDK 完成签名。

## 架构

```
青龙面板(NAS) ──定时/查看──▶ taobao_trigger.py  ─┐
        │                                        │
        │        taobao_receiver.py (接收+通知) ◀──┘ 局域网/公网
        ▲                                        │
        │ ③结果回传(POST /result)                  │ ②HTTP 触发(可选 server 模式)
        │                                        ▼
   ┌────┴─────────────────────────────────────────────┐
   │ 手机 AutoX.js 脚本 → 模拟点击 → 手机淘宝 App        │
   │                (淘宝安全 SDK 自动签名)             │
   └───────────────────────────────────────────────────┘
```

- **手机端** `taobao_flashsign.js`：AutoX.js UI 自动化，打开手淘、进签到页、点签到、识别结果。
- **青龙端** `taobao_receiver.py`：常驻 HTTP 服务，接收手机上报结果、落盘、推送(Bark/Server酱)。
- **青龙端** `taobao_trigger.py`：青龙 cron 入口，检查今日结果 / 可选主动触发手机。

---

## 部署步骤

### 一、手机端（必须）

1. **安装 AutoX.js**（开源版，Android 7+）
   从 AutoX.js 官方仓库 / 发布页下载 APK 安装。
2. **授予权限**（缺一不可）：
   - 无障碍服务（AutoX.js 设置里开启）
   - 悬浮窗（用于"布局分析"和脚本操作）
   - 自启动 / 后台弹出 / 电池无限制（否则脚本被系统杀掉）
3. **导入脚本**：AutoX.js → 新建/导入 → 选择本目录 `taobao_flashsign.js`。
4. **校准入口（★最关键）**：见下方"如何校准 ENTRY"。
5. **建定时任务**：AutoX.js → 定时任务 → 新建，选本脚本，时间建议 `35 9 * * *`（每天 9:35）。

### 二、青龙端（接收 + 通知）

在跑青龙的机器/NAS 上（与手机同局域网或手机有公网）：

```bash
cd /ql/data/scripts/jd-qinglong/android
pip install -r requirements.txt   # 仅标准库，一般无需额外安装

# 启动接收端（建议用 nohup / 青龙的"后台任务"常驻）
nohup python3 taobao_receiver.py > receiver.log 2>&1 &

# 可选：配置 Bark 推送（手机装 Bark 后复制 Key）
PORT=5678 BARK_KEY=你的BarkKey python3 taobao_receiver.py
```

然后在青龙面板建定时任务：
- 命令：`python3 /ql/data/scripts/jd-qinglong/android/taobao_trigger.py`
- 定时：`0 10 * * *`（每天 10:00，检查手机是否已完成签到并打印到青龙日志）

### 三、进阶（青龙统一调度，可选）

想让青龙 cron 直接控制手机何时执行（而不是手机自带定时）：
1. 手机端脚本 `CONFIG.enableServer = true`（需 AutoX.js 支持 webserver 模块）。
2. 青龙侧 `taobao_trigger.py` 配 `PHONE_SERVER_URL=http://手机IP:7788`。
3. 青龙定时任务改为触发：`PHONE_SERVER_URL=http://手机IP:7788 python3 .../taobao_trigger.py`。

> 此模式要求手机 IP 固定可达、AutoX.js 常驻，稳定性不如"手机自带定时"，按需选择。

---

## 如何校准 ENTRY（必看）

淘宝 UI 文案/布局随版本变化，脚本只保证框架正确，**入口和"签到"按钮的识别需要你在本机校准**：

1. 打开 AutoX.js 的 **布局分析**（悬浮窗 → 布局分析）。
2. 打开手机淘宝，进入"我的淘宝"页，看顶部/签到入口的 **text**（如"签到""打卡""领淘金币"），
   填到 `ENTRY.myTaobaoSignTexts`。
3. 进入闪购签到页，看"签到"按钮的 **text**，填到 `ENTRY.signButtonTexts`。
4. 看签到成功后页面的提示文案（如"已签到""明日再来"），填到 `ENTRY.signedDoneTexts`。
5. 保存后手动点一次脚本运行，看日志是否 `签到成功`。

校准后基本长期可用，淘宝大版本更新布局时再微调即可。

---

## 文件说明

| 文件 | 作用 |
|------|------|
| `taobao_flashsign.js` | 手机端 AutoX.js 主脚本（UI 自动化签到，含可选 server 模式） |
| `taobao_receiver.py` | 青龙端接收服务：收结果、落盘、推送通知 |
| `taobao_trigger.py` | 青龙 cron 入口：检查今日结果 / 可选主动触发 |
| `last_result.json` | 最近一次结果（运行时生成） |
| `result_history.json` | 历史结果（最近 20 条，运行时生成） |

## 常见问题

- **脚本找不到签到按钮**：99% 是 ENTRY 没校准，用布局分析核对 text。
- **手机执行完青龙没收到结果**：检查 `resultUploadUrl` 是否填成你的 NAS/青龙 IP，且 receiver 在跑。
- **触发模式连不上手机**：手机 IP 会变、或被省电策略杀掉，优先用"手机自带定时"模式。
- **京东脚本受影响吗**：不受影响，`jd_daily.py` / `jd_guagua.js` 走京东自己的接口体系，照常可用。
