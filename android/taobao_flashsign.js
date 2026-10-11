/*
 * 淘宝闪购签到 - AutoX.js (安卓端 UI 自动化)
 * ============================================================
 * 为什么用这个方案：
 *   淘宝 mtop 网关(h5api.m.taobao.com)现在拦截纯 md5 轻签名(x-sign)的请求，
 *   所有接口(包括购物车主页等核心接口)都统一返回 FAIL_SYS_API_NOT_FOUNDED。
 *   只有"在手机淘宝 App 内部运行"的请求，才会由淘宝自带的安全 SDK 自动签名而通过。
 *   所以改用 AutoX.js 在手机上模拟点击手淘完成签到，从根上绕开签名问题。
 *
 * 部署步骤见同目录 README.md。核心：
 *   1) 手机安装 AutoX.js (开源版，Android 7+)
 *   2) 授予 无障碍服务 + 悬浮窗 + 后台弹出/自启动 权限
 *   3) 导入本脚本，在 AutoX.js 里建定时任务(比如每天 9:35)
 *   4) 首次运行按本机淘宝 UI 校准下方 ENTRY 配置(入口控件/坐标)
 *
 * 重要：淘宝 UI 文案/布局随版本变化，脚本只保证"框架+容错"正确，
 *       具体入口和"签到"按钮的识别需要你在本机校准(见 ENTRY 注释)。
 * ============================================================
 */

// ===================== 配置区 =====================
const CONFIG = {
  // 淘宝 App 在系统中的显示名(一般是"手机淘宝"或"淘宝")
  taobaoAppName: "手机淘宝",

  // 是否把结果上报到青龙接收端(跑在 NAS/青龙同机的 taobao_receiver.py)
  enableUpload: true,
  // 青龙接收端地址：改成你 NAS/青龙机器的局域网 IP + 端口
  resultUploadUrl: "http://192.168.1.100:5678/result",

  // 随机延迟上限(毫秒)，防风控：触发后随机等 0~randomDelayMax 再执行
  randomDelayMax: 30 * 60 * 1000,

  // 单次执行超时(毫秒)，防止卡死
  runTimeout: 5 * 60 * 1000,

  // 调试日志输出到控制台(toast 会弹窗，关掉更安静)
  toastLog: true,

  // === 可选：被青龙远程触发(进阶) ===
  // 设为 true 后，脚本会起一个 HTTP server 监听 serverPort，
  // 青龙侧 taobao_trigger.py 配好 PHONE_SERVER_URL 即可主动触发手机执行。
  // 注意：需要 AutoX.js 支持 webserver 模块，且手机需常驻运行、IP 可达。
  // 不稳定/嫌麻烦就用默认的"AutoX.js 自带定时"模式，此项保持 false。
  enableServer: false,
  serverPort: 7788,
};

/*
 * 入口校准(★最关键的适配点★)
 * 不同淘宝版本"闪购签到"入口不同，下面提供两套策略，二选一或都留着自动兜底。
 * 你可以用 AutoX.js 的"布局分析"功能(悬浮窗→布局分析)查看控件的 text/desc/id，
 * 把对应文案填到下面的数组里。找不到就保持空数组，脚本会跳过该策略。
 */
const ENTRY = {
  // 策略A：我的淘宝页 → 顶部的"签到"/"打卡"入口
  // 用布局分析看"我的淘宝"页面里签到入口的文案，常见：签到、打卡、天天签到
  myTaobaoSignTexts: ["签到", "打卡", "天天签到", "领淘金币"],

  // 策略B：首页 → 点"闪购"频道 → 找"签到"
  // 很多版本首页底部没有闪购 tab，需要搜索，见 enterBySearch
  flashTabTexts: ["闪购", "限时秒杀"],

  // 策略B备选：首页搜索框输入关键词进入闪购会场
  searchKeyword: "闪购",

  // 在签到页里识别"签到"按钮的文案(点击它)
  signButtonTexts: ["签到", "立即签到", "去签到", "签到领"],

  // 识别"已经签到过"的结果文案(用来判断成功)
  signedDoneTexts: ["已签到", "明日再来", "签到成功", "今天已签", "已连续签到", "签到完成"],

  // 识别"未登录/弹窗"等异常
  failTexts: ["请先登录", "网络开小差", "稍后再试"],
};

// ===================== 工具函数 =====================
function log(msg) {
  const line = "[淘宝签到] " + msg;
  console.log(line);
  if (CONFIG.toastLog) toast(msg);
}

function randInt(a, b) { return Math.floor(random(a, b + 1)); }

// 申请无障碍并等待用户授予
function ensureAccessibility() {
  try {
    auto.waitFor();
  } catch (e) {
    log("请在弹出的设置里开启 AutoX.js 的无障碍服务，开启后脚本会自动继续");
    app.startActivity({ action: "android.settings.ACCESSIBILITY_SETTINGS" });
    // 等待最多 60s 让用户开启
    let waited = 0;
    while (!auto.serviceRunning() && waited < 60000) {
      sleep(1000);
      waited += 1000;
    }
    if (!auto.serviceRunning()) throw new Error("无障碍服务未开启，退出");
  }
  log("无障碍服务就绪");
}

// 关闭开屏/中途弹窗(跳过、领券、关闭等)
function dismissPopups() {
  const popups = ["跳过", "立即开启", "关闭", "取消", "以后", "领券", "知道了", "X"];
  for (let i = 0; i < 3; i++) {
    let w = textMatches(popups.join("|")).visibleToUser(true).findOne(1500);
    if (w) {
      try { w.click(); } catch (e) {}
      sleep(800);
    } else {
      // 也尝试可点击的关闭图标(常见 desc 为"关闭")
      let close = descMatches(/关闭|close/i).findOne(1000);
      if (close) { try { close.click(); } catch (e) {} sleep(800); }
    }
  }
}

// 回到淘宝首页
function goHome() {
  // 连续按返回直到出现首页(最多 5 次)
  for (let i = 0; i < 5; i++) {
    let homeTab = desc("首页").findOne(800) || text("首页").findOne(800);
    if (homeTab) { sleep(500); return; }
    back();
    sleep(1000);
  }
}

// 通过"我的淘宝"页找签到入口(策略A)
function enterByMyTaobao() {
  log("尝试策略A：我的淘宝 → 签到");
  // 点底部"我的淘宝"
  let mine = desc("我的淘宝").findOne(3000) || text("我的淘宝").findOne(3000);
  if (!mine) { log("未找到'我的淘宝'入口"); return false; }
  mine.click();
  sleep(2500);
  dismissPopups();

  for (const t of ENTRY.myTaobaoSignTexts) {
    let w = text(t).visibleToUser(true).findOne(2500);
    if (w) {
      log("在'我的淘宝'找到入口: " + t);
      // 点它(可能是按钮也可能是整块区域)
      clickWidget(w);
      sleep(3000);
      return true;
    }
  }
  log("'我的淘宝'页未找到签到入口，策略A失败");
  return false;
}

// 通过搜索进入闪购会场(策略B)
function enterBySearch() {
  log("尝试策略B：搜索进入闪购");
  // 点首页搜索框
  let search = descMatches(/搜索/).findOne(2000) || textMatches(/搜索/).findOne(2000);
  if (!search) {
    // 也可能直接有搜索框控件
    search = className("android.widget.EditText").findOne(2000);
  }
  if (!search) { log("未找到搜索框"); return false; }
  search.click();
  sleep(1200);
  // 输入关键词
  setText(ENTRY.searchKeyword);
  sleep(800);
  // 点搜索按钮(键盘上的搜索或页面里的"搜索")
  let go = desc("搜索").findOne(1500) || text("搜索").findOne(1500);
  if (go) go.click();
  sleep(3000);
  dismissPopups();

  // 在结果里找"签到"或"闪购会场"入口
  for (const t of ENTRY.signButtonTexts.concat(ENTRY.flashTabTexts)) {
    let w = text(t).visibleToUser(true).findOne(2500);
    if (w) { log("搜索结果找到入口: " + t); clickWidget(w); sleep(3000); return true; }
  }
  log("策略B未找到签到入口");
  return false;
}

// 通用点击控件(优先 click()，失败用坐标)
function clickWidget(w) {
  if (!w) return false;
  let b = w.bounds();
  if (w.clickable() || w.longClickable()) {
    return w.click();
  }
  // 不可点击则点其中心坐标
  return click(b.centerX(), b.centerY());
}

// 在签到页执行签到并判断结果
function doSign() {
  log("进入签到页，开始识别签到按钮");
  // 先关一次弹窗
  dismissPopups();
  sleep(1000);

  // 先判断是不是已经签过了(页面直接显示已签到)
  for (const t of ENTRY.signedDoneTexts) {
    if (textMatches(t).visibleToUser(true).findOne(1500)) {
      return { ok: true, reason: "页面显示已签到(" + t + ")" };
    }
  }

  // 找签到按钮并点
  let clicked = false;
  for (const t of ENTRY.signButtonTexts) {
    let w = text(t).visibleToUser(true).findOne(3000);
    if (w) {
      log("找到签到按钮: " + t);
      clickWidget(w);
      clicked = true;
      sleep(3500);
      break;
    }
  }
  if (!clicked) {
    // 兜底：找 desc 含"签到"的可点击元素
    let w = descMatches(/签到/).clickable(true).findOne(3000);
    if (w) { log("用 desc 找到签到按钮"); clickWidget(w); clicked = true; sleep(3500); }
  }
  if (!clicked) return { ok: false, reason: "未找到可点击的签到按钮" };

  // 读取结果
  for (const t of ENTRY.signedDoneTexts) {
    if (textMatches(t).visibleToUser(true).findOne(3000)) {
      return { ok: true, reason: "签到成功(" + t + ")" };
    }
  }
  for (const t of ENTRY.failTexts) {
    if (textMatches(t).visibleToUser(true).findOne(2000)) {
      return { ok: false, reason: "页面提示异常(" + t + ")" };
    }
  }
  // 没明确结果，默认认为点了(可能成功)
  return { ok: true, reason: "已点击签到按钮，未捕获明确结果文案" };
}

// 上报结果到青龙接收端
function uploadResult(result) {
  if (!CONFIG.enableUpload) return;
  try {
    let payload = {
      task: "tb_flashsign",
      device: device.brand + " " + device.model,
      time: new Date().toISOString(),
      ok: result.ok,
      reason: result.reason || "",
    };
    let r = http.postJson(CONFIG.resultUploadUrl, payload);
    log("结果已上报: " + r.statusCode());
  } catch (e) {
    log("上报失败(青龙接收端未启动或地址不对): " + e);
  }
}

// ===================== 主流程 =====================
function main() {
  const startTs = Date.now();
  log("==== 淘宝签到开始 ====");

  // 随机延迟防风控
  if (CONFIG.randomDelayMax > 0) {
    let d = randInt(0, CONFIG.randomDelayMax);
    log("随机延迟 " + Math.round(d / 1000) + "s 防风控");
    sleep(d);
  }

  let result = { ok: false, reason: "未知" };
  try {
    ensureAccessibility();

    // 启动淘宝
    app.launchApp(CONFIG.taobaoAppName);
    log("已启动淘宝，等待加载");
    sleep(6000);
    dismissPopups();

    // 尝试进入签到页(策略A失败再试B)
    let entered = enterByMyTaobao();
    if (!entered) {
      goHome();
      sleep(1500);
      entered = enterBySearch();
    }
    if (!entered) {
      result = { ok: false, reason: "无法进入签到页(请校准 ENTRY 配置)" };
    } else {
      result = doSign();
    }
  } catch (e) {
    result = { ok: false, reason: "脚本异常: " + (e && e.message ? e.message : e) };
    log(result.reason);
  } finally {
    uploadResult(result);
    let cost = Math.round((Date.now() - startTs) / 1000);
    log("==== 结束 (" + cost + "s) 结果: " + (result.ok ? "成功" : "失败") + " " + result.reason + " ====");
    // 回到桌面，避免停在淘宝耗电
    goHome();
    sleep(500);
    home();
  }
}

// ===================== 入口分发 =====================
if (CONFIG.enableServer) {
  // 进阶模式：起 HTTP server，等待青龙(taobao_trigger.py)远程触发
  try {
    var webserver = require("webserver");
    var server = webserver.create();
    server.listen(CONFIG.serverPort, {
      onRequest: function (req, res) {
        if (req.url.indexOf("/run") >= 0) {
          res.send("triggered");
          log("收到青龙触发，开始执行签到");
          // 异步执行，避免阻塞 server
          threads.start(function () { main(); });
        } else {
          res.send("tb_flashsign server alive");
        }
      },
    });
    log("server 模式已启动，监听端口 " + CONFIG.serverPort + "，等待青龙触发");
    // 阻塞保活(server 模式常驻)
    setInterval(function () {}, 60000);
  } catch (e) {
    log("server 模式启动失败(本版本可能不支持 webserver 模块)，改用定时模式: " + e);
    main();
  }
} else {
  // 默认模式：AutoX.js 自带定时 / 手动点击运行
  main();
}
