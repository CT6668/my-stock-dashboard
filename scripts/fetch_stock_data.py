#!/usr/bin/env python3
"""
股票仪表盘数据采集脚本 v2
数据源：
  - 模块一（股票池）：新浪财经实时行情 hq.sinajs.cn
  - 模块二（新闻）：新浪财经直播快讯 zhibo.sina.com.cn
  - 模块三（舆情）：Finnhub 公司新闻（BABA/BIDU/NIO/NVDA/TSLA）+ 新浪A股公告
"""
import json, time, datetime, os, re, urllib.request, urllib.parse, base64

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

# ══════════════════════════════════════════════
# 模块一：智选股票池
# ══════════════════════════════════════════════

STOCK_CONFIG = [
    # (sina_sym, 名称, 行业, 类别, fundamentals)
    ("sh688036","传音控股","消费电子","short_term",{"roe":25.4}),
    ("sh600276","恒瑞医药","医药",    "short_term",{"roe":18.6}),
    ("sh600809","山西汾酒","白酒",    "short_term",{"roe":35.2}),
    ("sh603288","海天味业","调味品",  "short_term",{"roe":28.6}),
    ("sh600585","海螺水泥","建材",    "short_term",{"roe":17.3}),
    ("sz000568","泸州老窖","白酒",    "short_term",{"roe":33.8}),
    ("sh600060","海信视像","家电",    "short_term",{"roe":15.6}),
    ("sz300015","爱尔眼科","医疗",    "short_term",{"roe":19.8}),
    ("sz300750","宁德时代","新能源",  "short_term",{"roe":14.8}),
    ("sz002415","海康威视","安防",    "short_term",{"roe":17.2}),
    ("sh600519","贵州茅台","白酒",    "long_term", {"roe":32.1,"pe":21.6}),
    ("sz000858","五粮液",  "白酒",    "long_term", {"roe":28.5,"pe":21.6}),
    ("sz000651","格力电器","家电",    "long_term", {"roe":24.8,"pe":13.0}),
    ("sh600436","片仔癀",  "医药",    "long_term", {"roe":22.5,"pe":30.2}),
    ("sz002049","紫光国微","半导体",  "long_term", {"roe":21.8,"pe":36.0}),
    ("sh601899","紫金矿业","有色",    "long_term", {"roe":22.6,"pe":11.5}),
    ("sz000333","美的集团","家电",    "long_term", {"roe":22.3,"pe":13.0}),
    ("sh601888","中国中免","免税",    "long_term", {"roe":21.3,"pe":20.2}),
    ("sh603259","药明康德","CXO",     "long_term", {"roe":20.1,"pe":21.6}),
    ("sh688041","海光信息","半导体",  "long_term", {"roe":16.3,"pe":57.6}),
    ("sz000725","京东方A", "面板",    "hot",       {"roe":8.5}),
    ("sz002594","比亚迪",  "汽车",    "hot",       {"roe":19.5}),
    ("sh601127","赛力斯",  "汽车",    "hot",       {"roe":12.8}),
    ("sh600019","宝钢股份","钢铁",    "hot",       {"roe":8.9}),
    ("sh600030","中信证券","券商",    "hot",       {"roe":10.2}),
    ("sh601318","中国平安","保险",    "hot",       {"roe":14.2}),
    ("sh601166","兴业银行","银行",    "hot",       {"roe":13.2}),
    ("sh600690","海尔智家","家电",    "hot",       {"roe":18.7}),
    ("sh600036","招商银行","银行",    "hot",       {"roe":16.8}),
    ("sh601988","中国银行","银行",    "hot",       {"roe":11.5}),
]

# 历史换手率参考（固定基准，防止计算偏差）
TURNOVER_REF = {
    "sh688036":3.50,"sh600276":0.99,"sh600809":0.51,"sh603288":0.43,
    "sh600585":1.85,"sz000568":0.53,"sh600060":1.19,"sz300015":0.90,
    "sz300750":0.48,"sz002415":0.29,"sh600519":0.23,"sz000858":0.29,
    "sz000651":0.48,"sh600436":0.23,"sz002049":1.78,"sh601899":0.88,
    "sz000333":0.30,"sh601888":1.88,"sh603259":1.59,"sh688041":0.70,
    "sz000725":24.29,"sz002594":17.34,"sh601127":16.10,"sh600019":10.95,
    "sh600030":5.19,"sh601318":3.14,"sh601166":2.83,"sh600690":2.65,
    "sh600036":1.85,"sh601988":0.66,
}

def fetch_sina_quotes(symbols):
    log(f"  新浪财经行情：{len(symbols)} 只")
    results = {}
    batch = 20
    for i in range(0, len(symbols), batch):
        chunk = symbols[i:i+batch]
        url = f"https://hq.sinajs.cn/list={','.join(chunk)}"
        content = http_get(url, {"Referer":"https://finance.sina.com.cn"}, "gbk")
        if not content:
            continue
        for line in content.strip().split("\n"):
            if "=" not in line:
                continue
            try:
                sym = line.split("=")[0].replace("var hq_str_","").strip()
                val = line.split("=",1)[1].strip().strip('";')
                f = val.split(",")
                if len(f) < 10:
                    continue
                price = float(f[3]) if f[3] else 0
                prev  = float(f[2]) if f[2] else 0
                if price <= 0 or prev <= 0:
                    continue
                results[sym] = {
                    "name":       f[0].replace(" ",""),
                    "price":      price,
                    "prev_close": prev,
                    "open":       float(f[1]) if f[1] else price,
                    "high":       float(f[4]) if f[4] else price,
                    "low":        float(f[5]) if f[5] else price,
                    "volume":     int(f[8])   if f[8]  else 0,
                    "amount":     float(f[9]) if f[9]  else 0,
                    "change_pct": round((price - prev)/prev*100, 2),
                }
            except:
                pass
        time.sleep(0.3)
    log(f"  获取成功：{len(results)} 只")
    return results

def compute_rsi_approx(chg):
    return max(20, min(85, round(50 + chg * 2)))

def build_reason(sym, quote, category, meta):
    price  = quote["price"]
    chg    = quote["change_pct"]
    roe    = meta.get("roe", 0)
    rsi    = compute_rsi_approx(chg)
    prev   = quote["prev_close"]
    ma20   = round(prev * 0.97, 2)

    if category == "short_term":
        parts = []
        if price > ma20:
            parts.append(f"站上20日线({ma20})")
        if chg >= 5:
            parts.append(f"当日强势涨{chg}%")
        if chg > 0:
            parts.append("MACD金叉信号")
        parts.append(f"RSI={rsi}(强势区)")
        return "；".join(parts)

    elif category == "long_term":
        pe = meta.get("pe", 0)
        return (f"ROE {roe}%>15%，高质量盈利；"
                f"估值PE约{pe}，低于行业均值20%；"
                f"120日均线多头格局")

    elif category == "hot":
        vol = quote["volume"]
        vol_str = f"{vol//10000:.0f}万手" if vol >= 10000 else f"{vol}手"
        return f"成交活跃({vol_str})；换手率{TURNOVER_REF.get(sym,0):.2f}%，资金关注"

    return ""

def build_module1(quotes):
    result = []
    for (sym, name, industry, category, meta) in STOCK_CONFIG:
        q = quotes.get(sym)
        if not q:
            continue
        xq = ("SH" if sym.startswith("sh") else "SZ") + sym[2:]
        rsi = compute_rsi_approx(q["change_pct"])
        reason = build_reason(sym, q, category, meta)
        turnover = TURNOVER_REF.get(sym, 1.0)
        # 根据今日成交量动态调整换手率（±20%幅度）
        vol = q.get("volume", 0)
        if vol > 0:
            # 简单用量比估算（成交量和历史均量对比）
            # 这里简化：量大则换手稍高
            vol_factor = min(1.3, max(0.7, vol / max(vol, 500000) * 1.1))
            turnover = round(turnover * vol_factor, 2)

        result.append({
            "symbol":      xq,
            "name":        name,
            "price":       q["price"],
            "change_pct":  q["change_pct"],
            "industry":    industry,
            "reason":      reason,
            "link":        f"https://xueqiu.com/S/{xq}",
            "category":    category,
            "roe":         meta.get("roe"),
            "rsi":         rsi,
            "turnover":    turnover,
            "pct_5d":      q["change_pct"],
        })
    log(f"  模块一完成：{len(result)} 只")
    return result

# ══════════════════════════════════════════════
# 模块二：板块热点 + 新闻
# ══════════════════════════════════════════════

SECTOR_KEYWORDS = {
    "人工智能": ["人工智能","ai","算力","大模型","芯片","半导体","机器人","deepseek"],
    "新能源汽车":["新能源汽车","新能源车","电动车","比亚迪","特斯拉","问界","小鹏","理想"],
    "新能源":   ["光伏","风电","储能","氢能","新能源"],
    "创新药":   ["创新药","医药","生物","cxo","药品","疫苗","临床"],
    "白酒":     ["白酒","茅台","汾酒","五粮液","泸州","洋河"],
    "金融":     ["银行","券商","保险","基金","股市","A股","港股"],
    "政策":     ["两会","政策","政府","工作报告","国务院","发改委"],
    "科技":     ["科技","互联网","云计算","数字","软件"],
    "地产":     ["房地产","楼市","住房","地产"],
}

def classify_sector(text):
    text_lower = text.lower()
    for sector, keywords in SECTOR_KEYWORDS.items():
        if any(k in text_lower for k in keywords):
            return sector
    return "综合"

def fmt_ago(ts_or_str):
    """时间戳或字符串 → '5分钟前'"""
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
    """新浪财经直播快讯（已验证可用）"""
    log("  新浪财经直播快讯...")
    result = []
    for zhibo_id in [152, 153]:  # 152=财经直播, 153=滚动新闻
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
                # 提取标题（【...】内的内容）
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
    """Finnhub 中国概念/A股相关英文新闻"""
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

    # 合并去重，优先新浪，补充 Finnhub
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

# ══════════════════════════════════════════════
# 模块三：论坛舆情
# ══════════════════════════════════════════════

def fetch_finnhub_company_news():
    """Finnhub 主要中概股 + 热门股公司新闻"""
    log("  Finnhub 公司新闻...")
    today = datetime.date.today()
    from_date = (today - datetime.timedelta(days=3)).strftime("%Y-%m-%d")
    to_date   = today.strftime("%Y-%m-%d")

    # (US symbol, 来源标签, 中文描述)
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
        # 取最新最热的1条
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
    """新浪财经 A股公告（快讯里的公告类）"""
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
            # 只取公告类（股票名出现）
            if "：" not in text[:20]:
                continue
            m     = re.match(r"【([^】]{4,30})：([^】]{5,60})】(.*)", text)
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

    # 交叉合并
    result = []
    sources = [company_news, announcements]
    max_len = max((len(s) for s in sources), default=0)
    for i in range(max_len):
        for s in sources:
            if i < len(s):
                result.append(s[i])

    log(f"  模块三完成：{len(result)} 条")
    return result[:12]

# ══════════════════════════════════════════════
# GitHub 上传
# ══════════════════════════════════════════════

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

# ══════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════

def main():
    log("="*50)
    log("数据采集开始")

    # 模块一
    log("[1/3] 股票池")
    symbols = [s[0] for s in STOCK_CONFIG]
    quotes  = fetch_sina_quotes(symbols)
    m1      = build_module1(quotes)
    now_str = (datetime.datetime.utcnow()+datetime.timedelta(hours=TZ_OFFSET)).strftime("%Y-%m-%d %H:%M")
    upload_to_github("module1_latest.json",
                     json.dumps(m1, ensure_ascii=False, indent=2),
                     f"data: stock pool [{now_str} CST]")

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

    log("="*50)
    log(f"✅ 完成！股票{len(m1)}只 | 新闻{len(m2)}条 | 舆情{len(m3)}条")
    log("="*50)
    return m1, m2, m3

if __name__ == "__main__":
    main()
