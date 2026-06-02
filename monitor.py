import os
import ssl
import pandas as pd
import requests
import base64
import time
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# 避免 Mac 下的 OpenSSL 报错
ssl._create_default_https_context = ssl._create_unverified_context
os.environ['no_proxy'] = '*'

# 解决 matplotlib 中文显示问题 (Mac 使用 Arial Unicode MS)
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

# ==================== 配置区域 ====================
# ==================== 配置区域 ====================
# 改为使用 os.environ.get 从 GitHub 的安全环境变量中读取
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN")  
TARGET_ETFS = ["159549", "159545"]

# GitHub 图床配置
GITHUB_TOKEN = os.environ.get("MY_GITHUB_TOKEN") 
GITHUB_USER = "yekang"                                     
GITHUB_REPO = "etf-monitor-images"                         
# =================================================
                      
# =================================================

def fetch_tencent_etf_data(symbol):
    """直接调用腾讯财经底层 API 获取 ETF 历史复权数据"""
    # 159 开头的 ETF 均属于深圳交易所，添加 sz 前缀
    market_symbol = f"sz{symbol}"
    # 抓取过去 300 个交易日的日线前复权数据
    url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={market_symbol},day,,,300,qfq"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        return None
        
    data = res.json()
    
    # 腾讯的数据结构：优先取 qfqday (前复权)，如果没有则取 day
    kline_data = data.get('data', {}).get(market_symbol, {}).get('qfqday')
    if not kline_data:
        kline_data = data.get('data', {}).get(market_symbol, {}).get('day')
        
    if not kline_data:
        return None
        
    # 腾讯数据格式为: [日期, 开盘, 收盘, 最高, 最低, 成交量]
    df = pd.DataFrame(kline_data, columns=['日期', '开盘', '收盘', '最高', '最低', '成交量'])
    df['收盘'] = df['收盘'].astype(float)
    df['日期'] = pd.to_datetime(df['日期'])
    
    # 按日期升序排列
    df = df.sort_values(by="日期").reset_index(drop=True)
    return df

def calculate_rsi(df, periods=14):
    """计算标准 RSI"""
    delta = df['收盘'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=periods-1, adjust=False).mean()
    ema_down = down.ewm(com=periods-1, adjust=False).mean()
    rs = ema_up / ema_down
    df['RSI_14'] = 100 - (100 / (1 + rs))
    return df

def draw_trend_chart(df, symbol, name):
    """绘制趋势图并保存在本地"""
    df_plot = df.tail(250).copy()
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), sharex=True)
    fig.suptitle(f'{name} ({symbol}) - 价格与 RSI 趋势图', fontsize=16, fontweight='bold')

    ax1.plot(df_plot['日期'], df_plot['收盘'], label='收盘价', color='#1f77b4', linewidth=1.5)
    ax1.plot(df_plot['日期'], df_plot['MA250'], label='MA250 (年线)', color='#ff7f0e', linestyle='--', linewidth=1.5)
    ax1.set_ylabel('价格')
    ax1.set_title('价格 vs 250日年线', fontsize=12)
    ax1.grid(True, linestyle='--', alpha=0.6)
    ax1.legend(loc='upper left')

    ax2.plot(df_plot['日期'], df_plot['RSI_14'], label='RSI(14)', color='#9467bd', linewidth=1.5)
    ax2.axhline(70, color='red', linestyle='--', linewidth=1, label='超买线 (70)')
    ax2.axhline(30, color='green', linestyle='--', linewidth=1, label='超卖线 (30)')
    ax2.fill_between(df_plot['日期'], 70, df_plot['RSI_14'], where=(df_plot['RSI_14'] >= 70), color='red', alpha=0.2)
    ax2.fill_between(df_plot['日期'], 30, df_plot['RSI_14'], where=(df_plot['RSI_14'] <= 30), color='green', alpha=0.2)
    ax2.set_ylabel('RSI 数值')
    ax2.set_title('14日相对强弱指标 (RSI)', fontsize=12)
    ax2.set_ylim(0, 100)
    ax2.grid(True, linestyle='--', alpha=0.6)
    ax2.legend(loc='upper left')
    
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    fig.autofmt_xdate()
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    
    filename = f"{symbol}_chart.png"
    plt.savefig(filename, dpi=150)
    print(f"📸 成功生成趋势图并保存为: {filename}")
    plt.close()
    return filename

def upload_to_github(local_file_path):
    """上传至 GitHub 并返回 CDN 链接"""
    print(f"☁️ 正在将 {local_file_path} 上传至 GitHub...")
    symbol = local_file_path.split('_')[0]
    timestamp = int(time.time())
    file_name = f"{symbol}_chart_{timestamp}.png"
    
    url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/images/{file_name}"
    
    try:
        with open(local_file_path, "rb") as image_file:
            encoded_content = base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        print(f"❌ 读取图片失败: {e}")
        return None

    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    payload = {"message": f"Auto-upload ETF chart {file_name}", "content": encoded_content, "branch": "main"}
    
    try:
        response = requests.put(url, headers=headers, json=payload)
        if response.status_code == 201:
            print("✅ GitHub 上传成功！")
            return f"https://cdn.jsdelivr.net/gh/{GITHUB_USER}/{GITHUB_REPO}/images/{file_name}"
        else:
            print(f"❌ GitHub 上传失败: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ 上传异常: {e}")
        return None

def monitor_etf(etf_list):
    results = []
    for symbol in etf_list:
        name = "红利低波ETF天弘" if symbol == "159549" else "恒生红利低波ETF"
        print(f"\n⏳ 正在通过腾讯财经 API 获取 {name} ({symbol}) 数据...")
        
        # 使用自建腾讯接口获取数据
        df = fetch_tencent_etf_data(symbol)
        
        if df is None or df.empty:
            print(f"❌ 获取 {symbol} 数据为空，跳过处理。")
            continue
            
        try:
            df['MA250'] = df['收盘'].rolling(window=250).mean()
            df = calculate_rsi(df, periods=14)
            df_for_plot = df.dropna(subset=['MA250', 'RSI_14'])
            
            image_url = None
            if not df_for_plot.empty:
                local_img = draw_trend_chart(df_for_plot, symbol, name)
                image_url = upload_to_github(local_img)
            
            latest = df.iloc[-1]
            results.append({
                "基金代码": symbol,
                "基金名称": name,
                "交易日期": str(latest['日期'])[:10], 
                "最新收盘价": round(latest['收盘'], 3),
                "MA250": round(latest['MA250'], 3) if pd.notna(latest['MA250']) else "上市不足250日",
                "RSI_14": round(latest['RSI_14'], 2) if pd.notna(latest['RSI_14']) else "数据不足",
                "图表链接": image_url
            })
        except Exception as e:
            print(f"❌ 分析异常: {e}")
            
    return results

def send_to_wechat(title, content):
    url = "http://www.pushplus.plus/send"
    data = {"token": PUSHPLUS_TOKEN, "title": title, "content": content, "template": "markdown"}
    try:
        response = requests.post(url, json=data)
        if response.json().get("code") == 200:
            print("🚀 微信消息推送成功！")
        else:
            print(f"❌ 推送失败: {response.text}")
    except Exception as e:
        print(f"❌ 推送异常: {e}")

def format_markdown_report(results):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    md = f"### 📊 红利低波 ETF 每日监控\n> 生成时间: {now_str}\n\n---\n"
    for res in results:
        md += f"#### 🎯 {res['基金名称']} ({res['基金代码']})\n"
        md += f"*   **收盘价**: `{res['最新收盘价']}`\n"
        md += f"*   **250日线**: `{res['MA250']}`\n"
        md += f"*   **RSI(14)**: `{res['RSI_14']}`\n"
        
        if isinstance(res['RSI_14'], float):
            if res['RSI_14'] < 30: md += f"*   🚨 <font color='red'>**【超卖区间】** 极低估，可定投！</font>\n"
            elif res['RSI_14'] > 70: md += f"*   🚨 <font color='green'>**【超买区间】** 注意回调！</font>\n"
            else: md += f"*   💡 正常波动区间\n"
                
        if isinstance(res['MA250'], float):
            if res['最新收盘价'] > res['MA250']: md += f"*   📈 价格在年线之上 (强势)\n"
            else: md += f"*   📉 价格在年线之下 (弱势)\n"
                
        if res.get('图表链接'):
            md += f"\n![趋势图]({res['图表链接']})\n"
        md += "\n---\n"
    return md

if __name__ == "__main__":
    print("开始执行 ETF 指标监控...")
    monitor_results = monitor_etf(TARGET_ETFS)
    if monitor_results:
        markdown_content = format_markdown_report(monitor_results)
        send_to_wechat(title="🔴红利低波指标监控提醒", content=markdown_content)
    else:
        print("未获取到有效监控结果。")
