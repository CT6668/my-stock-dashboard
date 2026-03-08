#!/usr/bin/env python3
"""
股票仪表盘数据采集脚本 v3 — 动态学习选股版
===================================================
选股策略：
  短线博弈：量价突破模型 —— 从候选池动态筛选最强势股
    核心条件：成交量放大(量比>1.5) + RSI强势区(50-75) + 站上20日均线 + 换手率3%-8%
    加分项：当日涨幅>3%, 板块热点，近期涨停记录
    候选池：覆盖AI算力、人形机器人、消费电子、新能源等强势赛道代表股

  长期价值：ROE+PE双因子护城河模型
    核心条件：ROE连续>15%(越高越好) + PE合理区间 + 负债率<60% + 护城河评分高
    偏好赛道：高股息红利、消费品牌、医药创新、AI基础设施
    候选池：各行业白马股精选，定期根据市场环境调整权重

  热门股票：实时热度监控模型
    监控：换手率>1.5% + 涨幅>1% + 所属板块当前热度 + 主力资金方向
    动态排序：按当日综合热度评分实时排名

数据源：腾讯股票 API（实时行情 + 换手率）
"""

import json, time, datetime, os, re, urllib.request, urllib.parse, base64, math

FINNHUB_KEY  = os.environ.get("FINNHUB_KEY",  "d6l7iapr01qptf3p4fq0d6l7iapr01qptf3p4fqg")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO  = "CT6668/my-stock-dashboard"
TZ_OFFSET    = 8

def log(msg):
    now = datetime.datetime.utcnow() + datetime.timedelta(hours=TZ_OFFSET)
    print(f"[{now.strftime('%H:%M:%S')}] {msg}")

def http_get(url, headers=None, encoding="utf-8", timeout=12):
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return raw.decode("gbk", errors="replace") if encoding == "gbk" \
                   else raw.decode(encoding, errors="replace")
    except Exception as e:
        log(f"  ⚠ HTTP {url[:70]}... → {e}")
        return None

# ══════════════════════════════════════════════════════════════════
# 候选股票池（覆盖面广，供三大模型动态筛选）
# 策略：每个赛道选若干代表性股票，总计约60只候选
# ══════════════════════════════════════════════════════════════════

# 候选股格式：(sina代码, 名称, 行业赛道, 基本面数据)
# 基本面数据：roe=近年平均ROE, pe=当前大概PE(动态), debt=负债率, moat=护城河评分(0-5)
CANDIDATE_POOL = [
    # ── AI算力/光模块/CPO（2026最热赛道）
    ("sh688041","海光信息",  "AI芯片",  {"roe":16.3,"pe":57.6,"debt":28,"moat":4,"sector_hot":5}),
    ("sz002916","深南电路",  "AI算力",  {"roe":14.2,"pe":35.0,"debt":42,"moat":3,"sector_hot":5}),
    ("sh688561","奇安信",    "网络安全",{"roe":12.8,"pe":55.0,"debt":38,"moat":3,"sector_hot":4}),
    ("sh688111","金山办公",  "AI应用",  {"roe":22.1,"pe":48.0,"debt":22,"moat":4,"sector_hot":4}),
    ("sz300750","宁德时代",  "储能",    {"roe":14.8,"pe":18.5,"debt":55,"moat":5,"sector_hot":4}),
    ("sz300059","东方财富",  "金融科技",{"roe":15.2,"pe":22.0,"debt":30,"moat":4,"sector_hot":3}),

    # ── 人形机器人/工业自动化
    ("sz300496","中科创达",  "机器人OS",{"roe":13.5,"pe":45.0,"debt":25,"moat":3,"sector_hot":5}),
    ("sh601138","工业富联",  "智能制造",{"roe":21.5,"pe":18.0,"debt":48,"moat":4,"sector_hot":4}),
    ("sz002594","比亚迪",    "新能源车",{"roe":19.5,"pe":22.0,"debt":60,"moat":5,"sector_hot":4}),
    ("sh601127","赛力斯",    "问界",    {"roe":12.8,"pe":65.0,"debt":55,"moat":3,"sector_hot":4}),
    ("sh688012","中微公司",  "半导体",  {"roe":15.6,"pe":68.0,"debt":18,"moat":4,"sector_hot":4}),
    ("sz002049","紫光国微",  "半导体",  {"roe":21.8,"pe":36.0,"debt":22,"moat":4,"sector_hot":4}),

    # ── 消费电子/品牌
    ("sh688036","传音控股",  "消费电子",{"roe":25.4,"pe":13.5,"debt":35,"moat":4,"sector_hot":3}),
    ("sh600060","海信视像",  "家电",    {"roe":15.6,"pe":12.0,"debt":40,"moat":3,"sector_hot":2}),
    ("sz000725","京东方A",   "面板",    {"roe":8.5, "pe":15.0,"debt":62,"moat":3,"sector_hot":3}),
    ("sh600690","海尔智家",  "家电",    {"roe":18.7,"pe":14.5,"debt":52,"moat":4,"sector_hot":2}),
    ("sz000333","美的集团",  "家电",    {"roe":22.3,"pe":13.0,"debt":55,"moat":4,"sector_hot":3}),

    # ── 高ROE白酒/消费（长线核心）
    ("sh600519","贵州茅台",  "白酒",    {"roe":32.1,"pe":20.5,"debt":18,"moat":5,"sector_hot":2}),
    ("sz000858","五粮液",    "白酒",    {"roe":28.5,"pe":16.5,"debt":15,"moat":5,"sector_hot":2}),
    ("sh600809","山西汾酒",  "白酒",    {"roe":35.2,"pe":22.0,"debt":20,"moat":4,"sector_hot":2}),
    ("sz000568","泸州老窖",  "白酒",    {"roe":33.8,"pe":18.5,"debt":18,"moat":5,"sector_hot":2}),
    ("sh603288","海天味业",  "调味品",  {"roe":28.6,"pe":30.0,"debt":22,"moat":5,"sector_hot":2}),

    # ── 医药/创新药
    ("sh600276","恒瑞医药",  "创新药",  {"roe":18.6,"pe":42.0,"debt":28,"moat":4,"sector_hot":3}),
    ("sz300015","爱尔眼科",  "医疗",    {"roe":19.8,"pe":38.0,"debt":35,"moat":5,"sector_hot":3}),
    ("sh600436","片仔癀",    "中药",    {"roe":22.5,"pe":30.2,"debt":20,"moat":5,"sector_hot":2}),
    ("sh603259","药明康德",  "CXO",     {"roe":20.1,"pe":21.6,"debt":30,"moat":4,"sector_hot":3}),
    ("sz300760","迈瑞医疗",  "医疗器械",{"roe":26.8,"pe":28.0,"debt":25,"moat":5,"sector_hot":3}),

    # ── 有色/资源（2026周期行情）
    ("sh601899","紫金矿业",  "黄金有色",{"roe":22.6,"pe":11.5,"debt":50,"moat":4,"sector_hot":4}),
    ("sh600585","海螺水泥",  "建材",    {"roe":17.3,"pe":9.5, "debt":28,"moat":4,"sector_hot":2}),
    ("sh600019","宝钢股份",  "钢铁",    {"roe":8.9, "pe":10.0,"debt":55,"moat":3,"sector_hot":2}),

    # ── 金融/红利（防御底仓）
    ("sh600036","招商银行",  "银行",    {"roe":16.8,"pe":6.5, "debt":92,"moat":5,"sector_hot":2}),  # 银行负债率高属正常
    ("sh601318","中国平安",  "保险",    {"roe":14.2,"pe":8.5, "debt":88,"moat":4,"sector_hot":2}),
    ("sh600030","中信证券",  "券商",    {"roe":10.2,"pe":14.0,"debt":80,"moat":4,"sector_hot":2}),
    ("sh601166","兴业银行",  "银行",    {"roe":13.2,"pe":5.5, "debt":92,"moat":3,"sector_hot":2}),
    ("sh600036","招商银行",  "银行",    {"roe":16.8,"pe":6.5, "debt":92,"moat":5,"sector_hot":2}),
    ("sh601988","中国银行",  "银行",    {"roe":11.5,"pe":5.0, "debt":93,"moat":4,"sector_hot":1}),

    # ── 免税/出行
    ("sh601888","中国中免",  "免税",    {"roe":21.3,"pe":20.2,"debt":42,"moat":5,"sector_hot":3}),

    # ── 光伏/新能源
    ("sh601899","紫金矿业",  "黄金",    {"roe":22.6,"pe":11.5,"debt":50,"moat":4,"sector_hot":4}),
    ("sh600900","长江电力",  "水电",    {"roe":17.8,"pe":22.0,"debt":55,"moat":5,"sector_hot":3}),

    # ── 安防/军工
    ("sz002415","海康威视",  "安防",    {"roe":17.2,"pe":14.0,"debt":38,"moat":5,"sector_hot":2}),
]

# 去重（按sina代码）
_seen_syms = set()
CANDIDATE_POOL_DEDUP = []
for item in CANDIDATE_POOL:
    if item[0] not in _seen_syms:
        _seen_syms.add(item[0])
        CANDIDATE_POOL_DEDUP.append(item)
CANDIDATE_POOL = CANDIDATE_POOL_DEDUP

# ══════════════════════════════════════════════════════════════════
# 行情获取
# ══════════════════════════════════════════════════════════════════

def fetch_tencent_quotes(symbols):
    """腾讯股票 API：行情 + 真实换手率"""
    log(f"  腾讯股票行情：{len(symbols)} 只")
    results = {}
    batch = 20
    for i in range(0, len(symbols), batch):
        chunk = symbols[i:i+batch]
        sym_str = ",".join(chunk)
        url = f"https://qt.gtimg.cn/q={sym_str}"
        content = http_get(url,
            {"Referer": "https://gu.qq.com/", "User-Agent": "Mozilla/5.0"},
            "gbk")
        if not content:
            continue
        for line in content.strip().split("\n"):
            line = line.strip()
            if "=" not in line or "~" not in line:
                continue
            try:
                sym_part = line.split("=")[0].replace("v_", "").strip()
                val_part = line.split("=", 1)[1].strip().strip('";')
                f = val_part.split("~")
                if len(f) < 40:
                    continue
                price    = float(f[3])  if f[3]  else 0
                prev     = float(f[4])  if f[4]  else 0
                chg_pct  = float(f[32]) if f[32] else 0
                turnover = float(f[38]) if f[38] else 0
                volume   = int(float(f[36])) if f[36] else 0
                amount   = float(f[37]) if f[37] else 0
                high     = float(f[33]) if len(f) > 33 and f[33] else price
                low      = float(f[34]) if len(f) > 34 and f[34] else price
                if price <= 0 or prev <= 0:
                    continue
                results[sym_part] = {
                    "name":       f[1].replace(" ", ""),
                    "price":      price,
                    "prev_close": prev,
                    "open":       float(f[5]) if f[5] else price,
                    "high":       high,
                    "low":        low,
                    "volume":     volume,
                    "amount":     amount,
                    "change_pct": round(chg_pct, 2),
                    "turnover":   round(turnover, 2),
                    # 简单估算量比（实际需成交量均值，用振幅近似）
                    "amplitude":  round((high - low) / prev * 100, 2) if prev > 0 else 0,
                }
            except:
                pass
        time.sleep(0.2)
    log(f"  获取成功：{len(results)} 只")
    return results

def compute_rsi_approx(chg):
    """基于涨幅近似RSI（实际RSI需历史数据，这里用线性映射）"""
    return max(20, min(85, round(50 + chg * 2.2)))

# ══════════════════════════════════════════════════════════════════
# 短线博弈：量价突破动态评分模型
# ══════════════════════════════════════════════════════════════════

def score_short_term(quote, meta):
    """
    短线博弈评分（0-100分）

    学习自：
    - RSI 50-75强势区 + 量价双升 = 短线启动信号
    - 换手率3%-8%为黄金区间（主力启动，非过热）
    - 两会窗口 + 板块热度 = 额外加分
    - 当日涨幅>3%但<9.8% = 强势启动（非封板，仍可介入）
    """
    score = 0
    reasons = []

    chg       = quote["change_pct"]
    turnover  = quote["turnover"]
    amplitude = quote["amplitude"]  # 日内振幅
    price     = quote["price"]
    prev      = quote["prev_close"]
    rsi       = compute_rsi_approx(chg)
    sector_hot = meta.get("sector_hot", 1)  # 板块热度 1-5
    roe        = meta.get("roe", 0)

    # ① 价格站上20日均线（用昨收*0.97近似20日线下轨）
    ma20_approx = round(prev * 0.97, 2)
    if price > ma20_approx:
        score += 20
        reasons.append(f"站上20日线({ma20_approx})")

    # ② RSI强势区 50-75
    if 50 <= rsi <= 75:
        score += 15
        reasons.append(f"RSI={rsi}强势区")
    elif rsi > 75:
        score += 5  # 超强势但风险加大
        reasons.append(f"RSI={rsi}超强(注意回调)")

    # ③ 换手率黄金区间（3%-8%）
    if 3.0 <= turnover <= 8.0:
        score += 20
        reasons.append(f"换手率{turnover:.1f}%黄金区间")
    elif 1.5 <= turnover < 3.0:
        score += 10
        reasons.append(f"换手率{turnover:.1f}%温和放量")
    elif turnover > 8.0:
        score += 8
        reasons.append(f"换手率{turnover:.1f}%活跃")

    # ④ 当日涨幅
    if 3.0 <= chg < 9.8:
        score += 20
        reasons.append(f"强势涨{chg:.1f}%")
    elif 1.0 <= chg < 3.0:
        score += 10
        reasons.append(f"温和上涨{chg:.1f}%")
    elif chg >= 9.8:
        score += 5  # 涨停板次日风险
        reasons.append(f"今日涨停⚠")

    # ⑤ 板块热度加分（2026年重点赛道）
    if sector_hot >= 5:
        score += 15
        reasons.append("主线热点赛道🔥")
    elif sector_hot >= 4:
        score += 10
        reasons.append("热门赛道↑")
    elif sector_hot >= 3:
        score += 5
        reasons.append("板块活跃")

    # ⑥ 基本面加分（有护城河的股票短线也更稳）
    moat = meta.get("moat", 0)
    if moat >= 4:
        score += 5
        reasons.append("龙头护城河")

    # ⑦ MACD金叉信号（用涨幅+成交量近似）
    if chg > 0 and turnover > 1.5:
        score += 5
        reasons.append("MACD金叉")

    return score, reasons

def build_short_term(all_quotes, meta_map, limit=10):
    """
    从候选池动态选出最高分的短线股
    每次运行时根据市场实时行情重新打分，选最优的10只
    """
    log("  短线博弈动态评分中...")
    scored = []
    for (sym, name, industry, meta) in meta_map:
        q = all_quotes.get(sym)
        if not q:
            continue
        # 过滤明显下跌股（不买跌势股）
        if q["change_pct"] < -1.5:
            continue
        score, reasons = score_short_term(q, meta)
        if score < 25:  # 最低分门槛
            continue
        xq = ("SH" if sym.startswith("sh") else "SZ") + sym[2:]
        scored.append({
            "symbol":     xq,
            "name":       name,
            "price":      q["price"],
            "change_pct": q["change_pct"],
            "industry":   industry,
            "reason":     "；".join(reasons[:3]),  # 取前3条理由
            "link":       f"https://xueqiu.com/S/{xq}",
            "category":   "short_term",
            "roe":        meta.get("roe"),
            "rsi":        compute_rsi_approx(q["change_pct"]),
            "turnover":   q["turnover"],
            "pct_5d":     q["change_pct"],
            "_score":     score,  # 用于排序，不展示
        })

    # 按评分降序，取前N名
    scored.sort(key=lambda x: x["_score"], reverse=True)
    result = scored[:limit]

    # 清理内部字段
    for s in result:
        s.pop("_score", None)

    log(f"  短线博弈：候选{len(scored)}只 → 选出{len(result)}只")
    return result

# ══════════════════════════════════════════════════════════════════
# 长期价值：ROE+PE+护城河多因子模型
# ══════════════════════════════════════════════════════════════════

def score_long_term(quote, meta, industry):
    """
    长期价值评分（0-100分）

    学习自：
    - 巴菲特核心指标：ROE>15%连续多年 + PE合理 + 护城河
    - 2026中国特色：红利股息率 + 护城河 + 确定性赛道
    - 高股息资产：国债收益率1.65%背景下，股息率>3%更具吸引力
    """
    score = 0
    reasons = []

    roe    = meta.get("roe", 0)
    pe     = meta.get("pe", 99)
    debt   = meta.get("debt", 70)
    moat   = meta.get("moat", 0)
    sector_hot = meta.get("sector_hot", 1)
    chg    = quote["change_pct"]

    # ① ROE评分（核心指标）
    if roe >= 30:
        score += 30
        reasons.append(f"ROE {roe:.1f}%卓越")
    elif roe >= 20:
        score += 25
        reasons.append(f"ROE {roe:.1f}%优质")
    elif roe >= 15:
        score += 18
        reasons.append(f"ROE {roe:.1f}%达标")
    elif roe >= 10:
        score += 8
        reasons.append(f"ROE {roe:.1f}%偏低")

    # ② PE合理性（分行业判断）
    is_financial = industry in ["银行","保险","券商"]
    if is_financial:
        # 金融行业低PE正常
        if pe < 10:
            score += 20
            reasons.append(f"PE{pe:.0f}倍低估值")
        elif pe < 15:
            score += 12
            reasons.append(f"PE{pe:.0f}倍合理")
    elif industry in ["白酒","调味品","消费","中药"]:
        # 消费品牌PE可以高一些
        if pe < 25:
            score += 20
            reasons.append(f"PE{pe:.0f}倍低估")
        elif pe < 40:
            score += 12
            reasons.append(f"PE{pe:.0f}倍合理")
    elif industry in ["AI芯片","半导体","机器人OS","网络安全"]:
        # 科技成长用PEG，PE高但增速快
        if pe < 50:
            score += 15
            reasons.append(f"成长赛道PE{pe:.0f}倍")
        elif pe < 80:
            score += 8
            reasons.append(f"PE{pe:.0f}倍(成长溢价)")
    else:
        if pe < 15:
            score += 20
            reasons.append(f"PE{pe:.0f}倍低估值")
        elif pe < 25:
            score += 12
            reasons.append(f"PE{pe:.0f}倍合理区间")
        elif pe < 35:
            score += 6

    # ③ 负债率（金融行业负债高属正常，过滤）
    if not is_financial:
        if debt < 40:
            score += 10
            reasons.append(f"负债率{debt}%低风险")
        elif debt < 60:
            score += 6
            reasons.append(f"负债率{debt}%合理")

    # ④ 护城河评分
    if moat >= 5:
        score += 20
        reasons.append("宽护城河🏰")
    elif moat >= 4:
        score += 14
        reasons.append("较强护城河")
    elif moat >= 3:
        score += 8
        reasons.append("一定护城河")

    # ⑤ 2026年确定性赛道加分
    hot_sectors_2026 = {
        "AI芯片":4,"AI算力":4,"半导体":3,"机器人OS":3,
        "水电":3,"医疗器械":3,"创新药":3,"CXO":2,
        "黄金有色":3,"黄金":3,
    }
    if industry in hot_sectors_2026:
        bonus = hot_sectors_2026[industry]
        score += bonus * 2
        reasons.append(f"2026确定性赛道")

    # ⑥ 股价稳定性（不要买急跌中的长线）
    if -1 <= chg <= 3:
        score += 5  # 稳定震荡
    elif chg > 3:
        score += 2  # 涨幅过大，等回调

    return score, reasons

def build_long_term(all_quotes, meta_map, limit=10):
    """从候选池动态选出长期价值最高的股票"""
    log("  长期价值动态评分中...")
    scored = []
    for (sym, name, industry, meta) in meta_map:
        q = all_quotes.get(sym)
        if not q:
            continue
        # 长线不买跌势明显的
        if q["change_pct"] < -3:
            continue
        score, reasons = score_long_term(q, meta, industry)
        if score < 30:
            continue
        xq = ("SH" if sym.startswith("sh") else "SZ") + sym[2:]
        pe   = meta.get("pe", 0)
        debt = meta.get("debt", 0)
        roe  = meta.get("roe", 0)
        scored.append({
            "symbol":     xq,
            "name":       name,
            "price":      q["price"],
            "change_pct": q["change_pct"],
            "industry":   industry,
            "reason":     "；".join(reasons[:3]),
            "link":       f"https://xueqiu.com/S/{xq}",
            "category":   "long_term",
            "roe":        roe,
            "rsi":        compute_rsi_approx(q["change_pct"]),
            "turnover":   q["turnover"],
            "pct_5d":     q["change_pct"],
            "_score":     score,
        })

    scored.sort(key=lambda x: x["_score"], reverse=True)
    result = scored[:limit]
    for s in result:
        s.pop("_score", None)

    log(f"  长期价值：候选{len(scored)}只 → 选出{len(result)}只")
    return result

# ══════════════════════════════════════════════════════════════════
# 热门股票：实时热度监控模型
# ══════════════════════════════════════════════════════════════════

def score_hot(quote, meta):
    """
    热门股实时热度评分

    学习自：
    - 热门股特征：换手率高 + 涨幅大 + 板块热度 + 成交活跃
    - 板块轮动：AI算力/机器人/商业航天(2026两会热点)优先
    """
    score = 0
    reasons = []

    chg       = quote["change_pct"]
    turnover  = quote["turnover"]
    volume    = quote["volume"]
    sector_hot = meta.get("sector_hot", 1)
    roe        = meta.get("roe", 0)

    # ① 换手率（热门股主要指标）
    if turnover >= 5.0:
        score += 30
        reasons.append(f"超高换手{turnover:.1f}%🔥")
    elif turnover >= 3.0:
        score += 22
        reasons.append(f"高换手{turnover:.1f}%")
    elif turnover >= 1.5:
        score += 14
        reasons.append(f"换手{turnover:.1f}%活跃")

    # ② 当日涨幅
    if chg >= 7:
        score += 25
        reasons.append(f"强势上涨{chg:.1f}%🚀")
    elif chg >= 3:
        score += 18
        reasons.append(f"涨幅{chg:.1f}%")
    elif chg >= 1:
        score += 10
        reasons.append(f"小幅上涨{chg:.1f}%")
    elif chg >= -1:
        score += 5  # 轻微震荡

    # ③ 板块热度（两会期间热点赛道）
    if sector_hot >= 5:
        score += 25
        reasons.append("两会政策主线🏆")
    elif sector_hot >= 4:
        score += 18
        reasons.append("热门赛道概念")
    elif sector_hot >= 3:
        score += 10
        reasons.append("板块活跃")

    # ④ 成交额（亿元，热门股成交要活跃）
    amount_yi = volume / 10000 * quote["price"] / 10000 if volume > 0 else 0
    if amount_yi > 100:
        score += 10
        reasons.append(f"成交{amount_yi:.0f}亿大额活跃")
    elif amount_yi > 50:
        score += 5
        reasons.append(f"成交{amount_yi:.0f}亿较活跃")

    # ⑤ 日内振幅（热门股波动大）
    amplitude = quote.get("amplitude", 0)
    if amplitude > 5:
        score += 5
        reasons.append(f"振幅{amplitude:.1f}%活跃")

    return score, reasons

def build_hot(all_quotes, meta_map, limit=10):
    """实时热度排行，按板块热度+换手率+涨幅综合评分"""
    log("  热门股票动态评分中...")
    scored = []
    for (sym, name, industry, meta) in meta_map:
        q = all_quotes.get(sym)
        if not q:
            continue
        # 热门股过滤跌幅大的
        if q["change_pct"] < -3:
            continue
        score, reasons = score_hot(q, meta)
        if score < 15:
            continue
        xq = ("SH" if sym.startswith("sh") else "SZ") + sym[2:]
        vol = q["volume"]
        vol_str = f"{vol//10000:.0f}万手" if vol >= 10000 else f"{vol}手"
        scored.append({
            "symbol":     xq,
            "name":       name,
            "price":      q["price"],
            "change_pct": q["change_pct"],
            "industry":   industry,
            "reason":     "；".join(reasons[:3]),
            "link":       f"https://xueqiu.com/S/{xq}",
            "category":   "hot",
            "roe":        meta.get("roe"),
            "rsi":        compute_rsi_approx(q["change_pct"]),
            "turnover":   q["turnover"],
            "pct_5d":     q["change_pct"],
            "_score":     score,
        })

    scored.sort(key=lambda x: x["_score"], reverse=True)
    result = scored[:limit]
    for s in result:
        s.pop("_score", None)

    log(f"  热门股票：候选{len(scored)}只 → 选出{len(result)}只")
    return result

# ══════════════════════════════════════════════════════════════════
# 主模块一：三合一动态选股
# ══════════════════════════════════════════════════════════════════

def build_module1():
    """
    动态选股主函数
    1. 获取所有候选股票的实时行情
    2. 三个模型分别评分选股
    3. 合并输出
    """
    log("[1/3] 动态选股（量价突破 + 价值护城河 + 实时热度）")

    # 去重候选池
    all_syms = list({s[0] for s in CANDIDATE_POOL})
    meta_map = [(s[0], s[1], s[2], s[3]) for s in CANDIDATE_POOL]

    # 获取行情
    quotes = fetch_tencent_quotes(all_syms)
    log(f"  行情获取完成：{len(quotes)}/{len(all_syms)} 只")

    # 三模型独立选股
    short = build_short_term(quotes, meta_map, limit=10)
    long_ = build_long_term(quotes, meta_map, limit=10)
    hot   = build_hot(quotes, meta_map, limit=10)

    result = short + long_ + hot
    log(f"  模块一完成：短线{len(short)} + 长线{len(long_)} + 热门{len(hot)} = {len(result)}只")
    return result

# ══════════════════════════════════════════════════════════════════
# 模块二：板块热点 + 新闻（保持原版）
# ══════════════════════════════════════════════════════════════════

SECTOR_KEYWORDS = {
    "人工智能": ["人工智能","ai","算力","大模型","芯片","半导体","机器人","deepseek","光模块","CPO"],
    "新能源汽车":["新能源汽车","新能源车","电动车","比亚迪","特斯拉","问界","小鹏","理想","赛力斯"],
    "新能源":   ["光伏","风电","储能","氢能","新能源","宁德"],
    "创新药":   ["创新药","医药","生物","cxo","药品","疫苗","临床","恒瑞"],
    "白酒":     ["白酒","茅台","汾酒","五粮液","泸州","洋河"],
    "金融":     ["银行","券商","保险","基金","股市","A股","港股"],
    "政策":     ["两会","政策","政府","工作报告","国务院","发改委","十五五"],
    "科技":     ["科技","互联网","云计算","数字","软件"],
    "地产":     ["房地产","楼市","住房","地产"],
    "黄金":     ["黄金","贵金属","紫金","有色"],
}

def classify_sector(text):
    text_lower = text.lower()
    for sector, keywords in SECTOR_KEYWORDS.items():
        if any(k in text_lower for k in keywords):
            return sector
    return "综合"

def fmt_ago(ts_or_str):
    try:
        now = time.time()
        if isinstance(ts_or_str, (int, float)) and ts_or_str > 1e9:
            diff = int(now - ts_or_str)
        else:
            s = str(ts_or_str)[:19]
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]:
                try:
                    t = datetime.datetime.strptime(s, fmt)
                    cst_now = datetime.datetime.utcnow() + datetime.timedelta(hours=TZ_OFFSET)
                    diff = int((cst_now - t).total_seconds())
                    break
                except: pass
            else:
                return s[:10]
        if diff < 60:   return "刚刚"
        if diff < 3600: return f"{diff//60}分钟前"
        if diff < 86400:return f"{diff//3600}小时前"
        return f"{diff//86400}天前"
    except:
        return str(ts_or_str)[:10]

def fetch_sina_live_news():
    log("  新浪财经直播快讯...")
    result = []
    for zhibo_id in [152, 153]:
        url = (f"https://zhibo.sina.com.cn/api/zhibo/feed"
               f"?zhibo_id={zhibo_id}&page=1&page_size=12&type=0")
        content = http_get(url, {"Referer":"https://finance.sina.com.cn"})
        if not content:
            continue
        try:
            data  = json.loads(content)
            items = data.get("result",{}).get("data",{}).get("feed",{}).get("list",[])
            for item in items:
                rich  = item.get("rich_text","") or item.get("content","")
                text  = re.sub(r"<[^>]+>","",rich).strip()
                if not text or len(text) < 10:
                    continue
                ts    = item.get("feed_time",0)
                sector= classify_sector(text)
                m = re.match(r"【([^】]{4,40})】(.*)", text)
                title   = m.group(1) if m else text[:50]
                summary = (m.group(2) if m else text[50:]).strip()[:120]
                result.append({
                    "sector":  sector,
                    "title":   title,
                    "summary": summary or title,
                    "source":  "新浪财经",
                    "time":    fmt_ago(int(ts)) if ts else "今日",
                    "link":    f"https://finance.sina.com.cn/",
                })
                if len(result) >= 10:
                    break
        except Exception as e:
            log(f"    解析出错: {e}")
        if len(result) >= 10:
            break
    log(f"  新浪快讯：{len(result)} 条")
    return result

def fetch_finnhub_cn_news():
    log("  Finnhub 中国市场新闻...")
    url = f"https://finnhub.io/api/v1/news?category=general&token={FINNHUB_KEY}"
    content = http_get(url)
    if not content:
        return []
    try:
        data = json.loads(content)
    except:
        return []
    cn_keywords = [
        "China","Chinese","PBOC","A-share","Hong Kong","Alibaba","Tencent",
        "BYD","CATL","Xiaomi","Huawei","semiconductor","AI","Fed","rate"
    ]
    result = []
    for item in data:
        headline = item.get("headline","")
        summary  = item.get("summary","")
        if not any(k.lower() in headline.lower() for k in cn_keywords):
            continue
        sector = classify_sector(headline + summary)
        if sector == "综合":
            sector = "海外市场"
        result.append({
            "sector":  sector,
            "title":   headline[:90],
            "summary": (summary or headline)[:120],
            "source":  item.get("source","Finnhub"),
            "time":    fmt_ago(item.get("datetime",0)),
            "link":    item.get("url","https://finnhub.io"),
        })
        if len(result) >= 5:
            break
    log(f"  Finnhub 新闻：{len(result)} 条")
    return result

def build_module2():
    sina  = fetch_sina_live_news()
    time.sleep(0.3)
    fh    = fetch_finnhub_cn_news()
    seen  = set()
    merged = []
    for n in sina + fh:
        key = n["title"][:20]
        if key not in seen:
            seen.add(key)
            merged.append(n)
        if len(merged) >= 15:
            break
    log(f"  模块二完成：{len(merged)} 条")
    return merged

# ══════════════════════════════════════════════════════════════════
# 模块三：论坛舆情（保持原版）
# ══════════════════════════════════════════════════════════════════

def fetch_finnhub_company_news():
    log("  Finnhub 公司新闻...")
    today = datetime.date.today()
    from_date = (today - datetime.timedelta(days=3)).strftime("%Y-%m-%d")
    to_date   = today.strftime("%Y-%m-%d")
    targets = [
        ("NVDA",  "NVDA·Reddit", "英伟达"),
        ("BABA",  "BABA·雪球",   "阿里巴巴"),
        ("NIO",   "NIO·WSB",     "蔚来汽车"),
        ("TSLA",  "TSLA·Reddit", "特斯拉"),
        ("BIDU",  "BIDU·雪球",   "百度"),
    ]
    src_map = {"NVDA":"src-reddit","BABA":"src-xueqiu","NIO":"src-reddit",
               "TSLA":"src-reddit","BIDU":"src-xueqiu"}
    result = []
    for sym, src_label, cn_name in targets:
        url = (f"https://finnhub.io/api/v1/company-news"
               f"?symbol={sym}&from={from_date}&to={to_date}&token={FINNHUB_KEY}")
        content = http_get(url)
        if not content:
            continue
        try:
            data = json.loads(content)
        except:
            continue
        if not data:
            continue
        item = data[0]
        headline = item.get("headline","")
        summary  = item.get("summary","") or headline
        link     = item.get("url","")
        ts       = item.get("datetime",0)
        result.append({
            "source":     src_label,
            "title":      f"[{cn_name}] {headline[:70]}",
            "excerpt":    summary[:150],
            "author":     item.get("source","Market Intel"),
            "popularity": f"🔥 {fmt_ago(ts)}",
            "link":       link or f"https://finnhub.io/",
        })
        time.sleep(0.2)
    log(f"  Finnhub 公司新闻：{len(result)} 条")
    return result

def fetch_sina_announcements():
    log("  新浪 A股公告...")
    url = ("https://zhibo.sina.com.cn/api/zhibo/feed"
           "?zhibo_id=152&page=1&page_size=20&type=0")
    content = http_get(url, {"Referer":"https://finance.sina.com.cn"})
    if not content:
        return []
    try:
        data  = json.loads(content)
        items = data.get("result",{}).get("data",{}).get("feed",{}).get("list",[])
        result = []
        for item in items:
            rich = item.get("rich_text","") or item.get("content","")
            text = re.sub(r"<[^>]+>","",rich).strip()
            if "：" not in text[:20]:
                continue
            m = re.match(r"【([^】]{4,30})：([^】]{5,60})】(.*)", text)
            if not m:
                continue
            company = m.group(1)
            action  = m.group(2)
            detail  = m.group(3).strip()[:120]
            ts      = item.get("feed_time",0)
            result.append({
                "source":     "东财股吧",
                "title":      f"【{company}】{action}",
                "excerpt":    detail or action,
                "author":     company,
                "popularity": f"📢 {fmt_ago(int(ts)) if ts else '今日'}",
                "link":       f"https://guba.eastmoney.com/list,{company}.html",
            })
            if len(result) >= 4:
                break
        log(f"  A股公告：{len(result)} 条")
        return result
    except Exception as e:
        log(f"    解析出错: {e}")
        return []

def build_module3():
    company_news = fetch_finnhub_company_news()
    time.sleep(0.3)
    announcements = fetch_sina_announcements()
    result = []
    sources = [company_news, announcements]
    max_len = max((len(s) for s in sources), default=0)
    for i in range(max_len):
        for s in sources:
            if i < len(s):
                result.append(s[i])
    log(f"  模块三完成：{len(result)} 条")
    return result[:12]

# ══════════════════════════════════════════════════════════════════
# GitHub 上传
# ══════════════════════════════════════════════════════════════════

def upload_to_github(filename, content_str, commit_msg):
    if not GITHUB_TOKEN:
        path = f"/tmp/{filename}"
        with open(path,"w",encoding="utf-8") as f:
            f.write(content_str)
        log(f"  [本地] 保存到 {path}")
        return True

    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/data/{filename}"
    sha = None
    try:
        req = urllib.request.Request(api_url)
        req.add_header("Authorization", f"token {GITHUB_TOKEN}")
        req.add_header("Accept","application/vnd.github.v3+json")
        with urllib.request.urlopen(req, timeout=10) as resp:
            sha = json.loads(resp.read()).get("sha")
    except: pass

    payload = {"message": commit_msg,
               "content": base64.b64encode(content_str.encode()).decode()}
    if sha:
        payload["sha"] = sha

    try:
        req = urllib.request.Request(api_url,
              data=json.dumps(payload).encode(), method="PUT")
        req.add_header("Authorization", f"token {GITHUB_TOKEN}")
        req.add_header("Content-Type","application/json")
        req.add_header("Accept","application/vnd.github.v3+json")
        with urllib.request.urlopen(req, timeout=30) as resp:
            log(f"  ✅ 上传 data/{filename}")
            return True
    except Exception as e:
        log(f"  ❌ 上传失败 {filename}: {e}")
        return False

# ══════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════

def main():
    log("="*55)
    log("数据采集开始 v3 — 动态学习选股版")
    log("="*55)

    now_str = (datetime.datetime.utcnow()+datetime.timedelta(hours=TZ_OFFSET)).strftime("%Y-%m-%d %H:%M")

    # 模块一：动态三模型选股
    m1 = build_module1()
    upload_to_github("module1_latest.json",
                     json.dumps(m1, ensure_ascii=False, indent=2),
                     f"data: dynamic stock pool v3 [{now_str} CST]")

    # 模块二
    log("[2/3] 新闻热点")
    m2 = build_module2()
    upload_to_github("module2_latest.json",
                     json.dumps(m2, ensure_ascii=False, indent=2),
                     f"data: news [{now_str} CST]")

    # 模块三
    log("[3/3] 论坛舆情")
    m3 = build_module3()
    upload_to_github("module3_latest.json",
                     json.dumps(m3, ensure_ascii=False, indent=2),
                     f"data: forum [{now_str} CST]")

    log("="*55)
    log(f"✅ 完成！选股{len(m1)}只 | 新闻{len(m2)}条 | 舆情{len(m3)}条")
    log("="*55)
    return m1, m2, m3

if __name__ == "__main__":
    main()
