"""
RSU 股价测算工具 - Streamlit 版本
功能：输入港股代码和目标日期，自动倒推20个港股交易日，计算平均收盘价
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import akshare as ak
import time
import os

# ============== 密码保护 ==============
def check_password():
    """简单的密码登录验证"""
    def password_entered():
        if st.session_state["password"] == st.secrets.get("APP_PASSWORD", "rsu2024"):
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("请输入访问密码", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("请输入访问密码", type="password", on_change=password_entered, key="password")
        st.error("密码错误，请重试")
        return False
    else:
        return True

# ============== 数据获取函数 ==============
@st.cache_data(ttl=3600)  # 缓存1小时，减少重复请求
def get_hk_stock_hist(symbol: str):
    """
    获取港股历史日线数据，带多数据源容错
    返回: DataFrame with columns [日期, 收盘]
    """
    # 数据源1: 东方财富 (akshare默认)
    try:
        df = ak.stock_hk_hist(symbol=symbol, period="daily", start_date="20200101", end_date="20500101", adjust="")
        if df is not None and not df.empty:
            # 标准化列名
            df = df.rename(columns={"日期": "date", "收盘": "close"})
            df["date"] = pd.to_datetime(df["date"])
            df = df[["date", "close"]].sort_values("date").reset_index(drop=True)
            return df, "东方财富"
    except Exception as e:
        st.warning(f"东方财富数据源请求失败，尝试备用源...")
        time.sleep(1)

    # 数据源2: 新浪财经 (akshare港股接口)
    try:
        df = ak.stock_hk_daily(symbol=f"hk{symbol}", adjust="")
        if df is not None and not df.empty:
            df = df.rename(columns={"date": "date", "close": "close"})
            df["date"] = pd.to_datetime(df["date"])
            df = df[["date", "close"]].sort_values("date").reset_index(drop=True)
            return df, "新浪财经"
    except Exception as e:
        st.error(f"新浪财经数据源也请求失败: {e}")

    return None, None

# ============== 核心计算逻辑 ==============
def calculate_20d_avg(df: pd.DataFrame, target_date: datetime):
    """
    从目标日期往前倒推20个交易日，计算平均收盘价
    """
    # 筛选目标日期之前（含当天）的交易日
    df_before = df[df["date"] <= target_date].copy()
    
    if len(df_before) < 20:
        return None, "历史数据不足20个交易日"
    
    # 取最近20个交易日
    last_20 = df_before.tail(20).copy()
    avg_price = last_20["close"].mean()
    
    return last_20, avg_price

# ============== 页面布局 ==============
st.set_page_config(page_title="RSU 股价测算工具", page_icon="📈", layout="wide")

if not check_password():
    st.stop()

st.title("📈 RSU 港股股价测算工具")
st.markdown("---")

# 输入区域
col1, col2 = st.columns(2)

with col1:
    stock_code = st.text_input(
        "港股代码", 
        value="00700", 
        help="输入5位港股代码，如腾讯00700、美团03690"
    )

with col2:
    target_date = st.date_input(
        "目标日期",
        value=datetime.today(),
        help="选择需要测算的目标日期"
    )

calculate_btn = st.button("🔍 开始测算", type="primary", use_container_width=True)

# 测算结果
if calculate_btn:
    with st.spinner("正在获取行情数据并计算..."):
        # 清洗股票代码（补前导0到5位）
        stock_code_clean = stock_code.strip().zfill(5)
        
        # 获取数据
        df, source = get_hk_stock_hist(stock_code_clean)
        
        if df is None:
            st.error("❌ 无法获取行情数据，请稍后重试或检查股票代码")
        else:
            st.success(f"✅ 数据来源：{source}")
            
            # 计算
            result_df, avg_price = calculate_20d_avg(df, datetime.combine(target_date, datetime.min.time()))
            
            if result_df is None:
                st.warning(f"⚠️ {avg_price}")
            else:
                st.markdown("---")
                
                # 核心结果卡片
                result_col1, result_col2, result_col3 = st.columns(3)
                with result_col1:
                    st.metric("测算股票代码", f"HK {stock_code_clean}")
                with result_col2:
                    st.metric("目标日期", target_date.strftime("%Y-%m-%d"))
                with result_col3:
                    st.metric("20日平均收盘价", f"HK$ {avg_price:.4f}")
                
                st.markdown("---")
                
                # 明细表
                st.subheader("📊 最近20个交易日明细")
                display_df = result_df.copy()
                display_df["date"] = display_df["date"].dt.strftime("%Y-%m-%d")
                display_df.columns = ["交易日期", "收盘价 (HK$)"]
                display_df.index = range(1, len(display_df) + 1)
                display_df.index.name = "序号"
                
                st.dataframe(display_df, use_container_width=True)
                
                # 导出CSV
                csv = display_df.to_csv(encoding="utf-8-sig").encode("utf-8-sig")
                st.download_button(
                    label="📥 导出 CSV 报表",
                    data=csv,
                    file_name=f"RSU_{stock_code_clean}_{target_date.strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )

# 底部说明
st.markdown("---")
st.caption("⚠️ 数据来源：东方财富/新浪财经公开行情接口，仅供内部参考，不构成投资建议")
st.caption("📌 计算规则：从目标日期往前倒推20个港股交易日，取收盘价算术平均值")
#（注：内容由AI生成）
