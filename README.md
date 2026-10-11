# 京东青龙脚本仓库

在飞牛 NAS 的青龙面板上运行的京东自动化脚本合集。

## 包含文件
| 文件 | 作用 |
|------|------|
| `jd_daily.py` | 每日任务：京东 App 签到领京豆、做任务赚京豆（含逛首页） |
| `jd_guagua.js` | 天天刮京豆（社区脚本，内置 h5st 签名；做任务攒刮卡次数 + 刮卡 + 签到卡） |
| `jd_guagua_run.py` | 刮刮卡启动器：兜底读取 JD_COOKIE 后启动上面的 JS（绕开 API 建变量不注入问题） |
| `jd_cookie_helper.py` | 在你自己电脑上运行，扫码登录后一键提取京东 Cookie |
| `tb_flashsign.py` | 淘宝 / 闪购签到（mtop 接口 + _m_h5_tk 签名，多账号） |
| `tb_cookie_helper.py` | 在你自己电脑上运行，登录后一键提取淘宝移动端 Cookie |
| `requirements.txt` | 青龙面板需要的依赖（requests） |
| `requirements-local.txt` | 仅本机 Cookie 工具需要（playwright），青龙上不用装 |

## 当前支持的活动（2026-10 实测校准）
| 任务 | 状态 |
|------|------|
| 京东 App 签到领京豆（signBeanAct） | ✅ 实测可用 |
| 做任务赚京豆（beanTaskList/beanDoTask） | ✅ 实测格式正确（高频调用会被风控限流，脚本已限速） |
| 京喜签到 | ❌ 活动疑似下线（专用域名不可达、functionId 失效） |
| 京东超市签到 | ❌ 旧接口失效，新接口需 h5st 签名 |
| 东东农场 / 东东牧场 | ❌ 旧接口全部失效，新接口需 h5st 签名 |

> h5st 是京东新一代接口签名体系（带混淆 JS、设备指纹），纯 HTTP 脚本无法简单绕过。
> 需要农场/牧场等完整支持的话，请订阅社区维护的 JS 仓库（内置 h5st 签名）。

---

## 方法一：最简单（不用 Git，直接上传）
适合不想折腾 Git 的情况，两步搞定：

1. 青龙面板 → **脚本管理** → 上传，把本仓库里的 `jd_daily.py` 传上去
   （`jd_cookie_helper.py` 只在你电脑上用，不用传到青龙）
2. 青龙面板 → **环境变量** → 新建：
   - 名称：`JD_COOKIE`
   - 值：你的京东 Cookie（见下方"获取 Cookie"）
   - 多个账号用 `&` 或换行连起来
3. 青龙面板 → **定时任务** → 新建：
   - 命令：`python3 /ql/data/scripts/jd_daily.py`
   - 定时规则：`0 9 * * *`（每天上午 9 点）

> 依赖：青龙「依赖管理」里确认有 python 版 `requests`（一般自带，缺失就装一下）。

---

## 方法二：Git 订阅（支持自动更新）
把本仓库推到 GitHub / Gitee 后，青龙能一键拉取并自动同步更新。

1. 在 GitHub 或 Gitee 新建一个**私有**仓库（空仓库，别勾 README）
2. 把本仓库推上去（命令见仓库根目录，或让帮你搭脚本的人执行）
3. 青龙面板 → **订阅管理** → 新建订阅：
   - 仓库地址：填你刚建的仓库 URL
   - 定时：留空或设个更新频率（如 `0 1 * * *` 每天拉一次）
4. 保存后手动"运行一次"拉取，再按方法一配置 `JD_COOKIE` 和定时任务即可

---

## 获取京东 Cookie
Cookie 相当于登录凭证，**只保存在青龙环境变量里，不要外泄**。

在本机（Mac / Windows）执行：
```bash
pip install playwright
playwright install chromium
python3 jd_cookie_helper.py
```
脚本会打开京东登录页，用手机京东 App 扫码，登录成功后终端会打印一行
`pt_key=...; pt_pin=...`，整行复制填到青龙的 `JD_COOKIE` 即可。

---

---

## 淘宝闪购签到（tb_flashsign.py）

> ⚠️ 淘宝接口与京东不同：走 `mtop` 体系，必须用 `_m_h5_tk` 做 md5 签名（x-sign），
> 且**签到活动的接口名（apiName）会随每一期活动变化**。脚本内置的接口名是当前（2026-10）
> 常见的，若某活动长期失败，需要你按当期活动抓包核对后替换脚本顶部 `SIGN_ACTIVITIES`。

### 部署（与京东类似）
1. 青龙面板 → **环境变量** → 新建 `TAO_COOKIE`，值为你的淘宝移动端 Cookie（见下方"获取淘宝 Cookie"）
2. 定时任务 → 新建：
   - 命令：`python3 /ql/data/scripts/tb_flashsign.py`
   - 定时：`30 9 * * *`（每天 9:30，脚本会再随机延迟 0~30 分钟防风控）
3. 可选环境变量：
   - `TAO_DELAY_MAX`：最大随机延迟分钟数（默认 30，设 `0` 立即执行，手动测试用）
   - `TAO_APPKEY`：mtop 的 appKey（默认 `12574478`，一般不用改）

### 获取淘宝 Cookie
在本机（Mac / Windows）执行：
```bash
pip install playwright
playwright install chromium
python3 tb_cookie_helper.py
```
脚本打开淘宝登录页，扫码/账号登录（必要时手动过滑块），成功后终端打印一行
含 `_m_h5_tk` 的 Cookie，整行复制填到青龙的 `TAO_COOKIE` 即可。

### 如何核对 / 更新签到接口（抓包法）
当某活动返回 `FAIL_SYS_ILLEGAL_REQUEST` 或一直不成功时：
1. 手机装好 **HttpCanary / 抓包精灵**（Android）或在电脑用 Charles/Fiddler 配合手机代理
2. 打开手机淘宝 → 进入「闪购」→「签到」页面，触发一次签到
3. 在抓包记录里找域名 `h5api.m.taobao.com` 的请求，
   其 URL 路径 `/h5/{apiName}/1.0/` 里的 `apiName` 就是签到接口名，
   请求体里的 `data` JSON 就是签到参数
4. 把这两个值替换进 `tb_flashsign.py` 顶部 `SIGN_ACTIVITIES` 对应项即可

> 提示：淘宝风控较严，建议 crontab 时间与京东错开、不要短时间高频调用；
> Cookie 一般几天到几十天失效，签到突然不跑就重新抓一次。

---

## 天天刮京豆（jd_guagua.js）

京东 App「京豆」页里的「天天刮京豆」活动：做浏览类任务攒刮卡次数 → 刮卡得京豆，
另有每日签到卡。该活动接口必须 h5st 签名，因此使用社区维护的混淆 JS 脚本（feverrun/my_scripts）。

1. **Node 依赖**（青龙 → 依赖管理 → NodeJs）：`axios`、`got`、`tough-cookie`、`crypto-js`、`https-proxy-agent`、`global-agent`
2. **定时任务**：
   - 命令：`python3 /ql/data/scripts/993052100-sketch_jd-qinglong_main/jd_guagua_run.py`
   - 定时：`20 9 * * *`（与主任务错开 20 分钟）
3. Cookie 复用 `JD_COOKIE` 环境变量，无需另建（启动器会自动兜底读取并传给 JS）

> ⚠️ 说明：该 JS 为社区混淆脚本（京东此类脚本惯例，防接口分析），运行时会将你的
> Cookie 用于调用京东官方接口。介意者可自行审计或放弃此任务。

---

## 重要提醒
- **防风控随机化（已内置）**：脚本每天触发后会先**随机延迟 0~30 分钟**再签到（实际执行时间每天不同），
  任务之间、任务内部的间隔也是随机的。可通过环境变量 `JD_DELAY_MAX` 调整最大延迟分钟数（默认 30，
  设 `0` 为关闭——手动测试想立即出结果时用它）。
- **京东活动接口经常变动**：某个任务长期报错，多半是当期接口改了，需要按当期活动
  微调脚本里的 `functionId` / 请求参数。赚京豆任务高频调用会触发风控软限流
  （日志显示"活动太火爆/参与人数较多"即为此类，等第二天正常运行即可恢复）。
- **Cookie 会过期**：一般几天到几十天失效，签到突然不跑就重新抓一次 Cookie。
- 想要农场/牧场等 h5st 签名活动的完整支持，建议在青龙「订阅管理」里额外订阅
  社区维护的 JD 脚本仓库（搜"青龙 jd 订阅"找当前活跃的几个）。
