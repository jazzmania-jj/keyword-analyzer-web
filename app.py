#!/usr/bin/env python3
"""
키워드 분석기 웹앱 (Streamlit Cloud 배포용)
판다랭크 스타일의 웹 인터페이스
"""

import streamlit as st
import hashlib
import hmac
import base64
import time
import json
import os
from datetime import datetime, timedelta
import requests
import pandas as pd

# ============================================================
# 페이지 설정
# ============================================================
st.set_page_config(
    page_title="키워드 분석기",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ============================================================
# 커스텀 CSS
# ============================================================
st.markdown("""
<style>
    .stApp { background-color: #f8fafc; }
    .metric-card {
        background: white; border-radius: 16px; padding: 20px 24px;
        border: 1px solid #e2e8f0; text-align: center;
    }
    .metric-card .label { font-size: 13px; color: #94a3b8; margin-bottom: 6px; }
    .metric-card .value { font-size: 28px; font-weight: 700; color: #1e293b; }
    .metric-card .unit { font-size: 14px; font-weight: 400; color: #94a3b8; }
    .metric-card .sub { font-size: 12px; color: #94a3b8; margin-top: 4px; }
    .grade-badge {
        display: inline-flex; flex-direction: column; align-items: center;
        justify-content: center; width: 80px; height: 80px; border-radius: 16px;
        color: white; font-weight: 700;
    }
    .grade-badge .grade { font-size: 28px; line-height: 1; }
    .grade-badge .grade-label { font-size: 11px; opacity: 0.9; margin-top: 2px; }
    .sat-badge {
        display: inline-block; padding: 2px 12px; border-radius: 10px;
        color: white; font-size: 12px; font-weight: 600;
    }

    .section-header { font-size: 18px; font-weight: 700; color: #1e293b; margin-bottom: 16px; }
    .footer { text-align: center; font-size: 12px; color: #94a3b8; padding: 24px 0 8px; }
</style>
""", unsafe_allow_html=True)


# ============================================================
# API 키 로드 (Streamlit Secrets 또는 사이드바 입력)
# ============================================================
def get_config():
    """Streamlit Secrets 또는 사이드바 입력에서 API 키 로드"""
    # 1순위: Streamlit Secrets (배포 환경)
    try:
        config = {
            "naver_searchad": {
                "customer_id": st.secrets["naver_searchad"]["customer_id"],
                "api_key": st.secrets["naver_searchad"]["api_key"],
                "secret_key": st.secrets["naver_searchad"]["secret_key"]
            },
            "naver_openapi": {
                "client_id": st.secrets["naver_openapi"]["client_id"],
                "client_secret": st.secrets["naver_openapi"]["client_secret"]
            }
        }
        return config
    except Exception:
        pass

    # 2순위: 세션에 저장된 설정
    if "config" in st.session_state:
        return st.session_state["config"]

    return None


# ============================================================
# API 클래스들
# ============================================================
class NaverSearchAdAPI:
    BASE_URL = "https://api.searchad.naver.com"

    def __init__(self, customer_id, api_key, secret_key):
        self.customer_id = customer_id
        self.api_key = api_key
        self.secret_key = secret_key

    def _generate_signature(self, timestamp, method, path):
        message = f"{timestamp}.{method}.{path}"
        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256
        ).digest()
        return base64.b64encode(signature).decode("utf-8")

    def _get_headers(self, method, path):
        timestamp = str(int(time.time() * 1000))
        signature = self._generate_signature(timestamp, method, path)
        return {
            "X-Timestamp": timestamp,
            "X-API-KEY": self.api_key,
            "X-Customer": self.customer_id,
            "X-Signature": signature,
            "Content-Type": "application/json"
        }

    def get_keyword_stats(self, keyword):
        path = "/keywordstool"
        method = "GET"
        # 띄어쓰기 있는 키워드가 실패하면 붙여서 재시도
        keyword_variants = [keyword]
        if " " in keyword:
            keyword_variants.append(keyword.replace(" ", ""))

        data = None
        for kw in keyword_variants:
            headers = self._get_headers(method, path)
            params = {"hintKeywords": kw, "showDetail": "1"}
            try:
                resp = requests.get(f"{self.BASE_URL}{path}", headers=headers, params=params, timeout=15)
                if resp.status_code == 400 and kw != keyword_variants[-1]:
                    continue
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception:
                if kw == keyword_variants[-1]:
                    st.warning(f"검색광고 API 오류: 키워드 '{keyword}'를 찾을 수 없습니다.")
                    return None
                continue

        if data is None:
            return None

        try:
            results = {"main_keyword": None, "related_keywords": []}

            for item in data.get("keywordList", []):
                kw_data = {
                    "keyword": item.get("relKeyword", ""),
                    "monthly_pc": item.get("monthlyPcQcCnt", 0),
                    "monthly_mobile": item.get("monthlyMobileQcCnt", 0),
                    "monthly_total": 0, "pc_ratio": 0, "mobile_ratio": 0,
                    "competition": item.get("compIdx", ""),
                    "avg_cpc": item.get("monthlyAvePcClkCnt", 0),
                    "avg_mobile_cpc": item.get("monthlyAveMobileClkCnt", 0),
                }
                pc = kw_data["monthly_pc"]
                mobile = kw_data["monthly_mobile"]
                if isinstance(pc, str):
                    pc = 5 if "< 10" in pc else int(pc.replace(",", ""))
                if isinstance(mobile, str):
                    mobile = 5 if "< 10" in mobile else int(mobile.replace(",", ""))
                kw_data["monthly_pc"] = pc
                kw_data["monthly_mobile"] = mobile
                kw_data["monthly_total"] = pc + mobile
                if kw_data["monthly_total"] > 0:
                    kw_data["pc_ratio"] = round(pc / kw_data["monthly_total"] * 100, 1)
                    kw_data["mobile_ratio"] = round(mobile / kw_data["monthly_total"] * 100, 1)
                if item.get("relKeyword", "").strip() == keyword.strip():
                    results["main_keyword"] = kw_data
                else:
                    results["related_keywords"].append(kw_data)

            results["related_keywords"].sort(key=lambda x: x["monthly_total"], reverse=True)
            return results
        except Exception as e:
            st.warning(f"검색광고 API 오류: {e}")
            return None


    def get_estimated_cpc(self, keyword):
        """키워드의 예상 클릭당 비용(CPC) 조회"""
        path = "/estimate/performance/keyword"
        method = "POST"
        headers = self._get_headers(method, path)
        bids = [500, 1000, 2000, 3000, 5000, 7000, 10000]
        
        total_cpc = 0
        cpc_count = 0
        
        for device in ["PC"]:  # PC 기준 CPC만 사용 (판다랭크 동일 기준)
            try:
                body = {"device": device, "keywordplus": False, "key": keyword, "bids": bids}
                resp = requests.post(f"{self.BASE_URL}{path}", headers=headers, json=body, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    for est in data.get("estimate", []):
                        clicks = est.get("clicks", 0)
                        cost = est.get("cost", 0)
                        if clicks > 0 and cost > 0:
                            cpc = cost / clicks
                            total_cpc += cpc
                            cpc_count += 1
                            break  # 클릭이 발생하는 최소 입찰가의 CPC만 사용
                # 서명 갱신 (타임스탬프 변경)
                import time as _t
                _t.sleep(0.2)
                headers = self._get_headers(method, path)
            except Exception:
                continue
        
        if cpc_count > 0:
            return round(total_cpc / cpc_count)
        return 0


class NaverBlogSearchAPI:
    BASE_URL = "https://openapi.naver.com/v1/search/blog.json"

    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret

    def get_monthly_publish_count(self, keyword):
        headers = {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret
        }
        try:
            # 1단계: start=1에서 100건 (최신)
            resp1 = requests.get(self.BASE_URL, headers=headers,
                params={"query": keyword, "display": 100, "start": 1, "sort": "date"}, timeout=15)
            resp1.raise_for_status()
            data1 = resp1.json()
            total = data1.get("total", 0)
            items1 = data1.get("items", [])
            if not items1:
                return 0, total

            now = datetime.now()
            thirty_days_ago = now - timedelta(days=30)

            # 최신 100건 중 30일 이내 비율 확인
            def count_recent(items):
                count = 0
                for item in items:
                    postdate = item.get("postdate", "")
                    if postdate:
                        try:
                            dt = datetime.strptime(postdate, "%Y%m%d")
                            if dt >= thirty_days_ago:
                                count += 1
                        except ValueError:
                            continue
                return count

            recent1 = count_recent(items1)

            # 100건 모두 30일 이내가 아니면, 이 100건 내에서 비율로 추정
            if recent1 < len(items1):
                if recent1 > 0:
                    return recent1, total
                else:
                    return 0, total

            # 100건 모두 최근 30일이면 → start=1000에서 추가 확인
            import time as _time
            _time.sleep(0.2)
            resp2 = requests.get(self.BASE_URL, headers=headers,
                params={"query": keyword, "display": 100, "start": 1000, "sort": "date"}, timeout=15)
            resp2.raise_for_status()
            data2 = resp2.json()
            items2 = data2.get("items", [])

            if not items2:
                return min(total, 1000), total

            # start=1000의 가장 오래된 글 날짜와 start=1의 가장 최근 글 날짜 비교
            def get_oldest_date(items):
                for item in reversed(items):
                    postdate = item.get("postdate", "")
                    if postdate:
                        try:
                            return datetime.strptime(postdate, "%Y%m%d")
                        except ValueError:
                            continue
                return None

            def get_newest_date(items):
                for item in items:
                    postdate = item.get("postdate", "")
                    if postdate:
                        try:
                            return datetime.strptime(postdate, "%Y%m%d")
                        except ValueError:
                            continue
                return None

            newest = get_newest_date(items1)
            oldest = get_oldest_date(items2)

            if newest and oldest:
                days_span = max((newest - oldest).days, 1)
                if days_span <= 30:
                    # 1100개가 N일에 걸쳐 있으면 일평균 = 1100/N, 월간 = 일평균*30
                    daily_rate = 1100 / days_span
                    estimated_monthly = int(daily_rate * 30)
                else:
                    # 1100개가 30일 이상이면, 30일 이내 비율로 추정
                    recent2 = count_recent(items2)
                    if recent2 < len(items2):
                        # 30일 경계가 start=1000 부근 → 비율로 보간
                        boundary_pos = 1000 + int(len(items2) * (recent2 / max(len(items2), 1)))
                        estimated_monthly = boundary_pos
                    else:
                        estimated_monthly = int(1100 / days_span * 30)
                return estimated_monthly, total
            else:
                return min(total, 1000), total

        except Exception as e:
            st.warning(f"블로그 검색 API 오류: {e}")
            return 0, 0


class NaverDataLabAPI:
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret

    def _request(self, endpoint, body):
        headers = {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret,
            "Content-Type": "application/json"
        }
        try:
            resp = requests.post(
                f"https://openapi.naver.com/v1/datalab/{endpoint}",
                headers=headers, json=body, timeout=15
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None

    def get_trend(self, keyword, period_months=36):
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=period_months * 30)).strftime("%Y-%m-%d")
        body = {
            "startDate": start_date, "endDate": end_date, "timeUnit": "week",
            "keywordGroups": [{"groupName": keyword, "keywords": [keyword]}]
        }
        data = self._request("search", body)
        if data and "results" in data:
            return [{"period": d["period"], "ratio": d["ratio"]} for d in data["results"][0].get("data", [])]
        return []

    def get_yoy_change(self, keyword):
        now = datetime.now()
        body_this = {
            "startDate": (now - timedelta(days=90)).strftime("%Y-%m-%d"),
            "endDate": now.strftime("%Y-%m-%d"),
            "timeUnit": "month",
            "keywordGroups": [{"groupName": keyword, "keywords": [keyword]}]
        }
        body_last = {
            "startDate": (now - timedelta(days=365 + 90)).strftime("%Y-%m-%d"),
            "endDate": (now - timedelta(days=365)).strftime("%Y-%m-%d"),
            "timeUnit": "month",
            "keywordGroups": [{"groupName": keyword, "keywords": [keyword]}]
        }
        data_this = self._request("search", body_this)
        data_last = self._request("search", body_last)
        avg_this = avg_last = 0
        if data_this and "results" in data_this:
            ratios = [d["ratio"] for d in data_this["results"][0].get("data", []) if d["ratio"] > 0]
            avg_this = sum(ratios) / len(ratios) if ratios else 0
        if data_last and "results" in data_last:
            ratios = [d["ratio"] for d in data_last["results"][0].get("data", []) if d["ratio"] > 0]
            avg_last = sum(ratios) / len(ratios) if ratios else 0
        if avg_last > 0:
            return round((avg_this - avg_last) / avg_last * 100, 2)
        return 0


# ============================================================
# 난이도 등급
# ============================================================
def calculate_difficulty(monthly_search, cpc, competition):
    score = 0
    if monthly_search >= 50000: score += 30
    elif monthly_search >= 20000: score += 25
    elif monthly_search >= 10000: score += 20
    elif monthly_search >= 5000: score += 15
    elif monthly_search >= 1000: score += 10
    else: score += 5

    if cpc >= 2000: score += 20
    elif cpc >= 1000: score += 15
    elif cpc >= 500: score += 12
    elif cpc >= 200: score += 8
    else: score += 5

    comp_map = {"낮음": 20, "보통": 12, "높음": 5}
    score += comp_map.get(competition, 10) if isinstance(competition, str) else 10

    grades = [(85,"A+","매우 쉬움"),(75,"A","쉬움"),(65,"A-","약간 쉬움"),(55,"B+","보통"),
              (45,"B","약간 어려움"),(35,"B-","어려움"),(25,"C","매우 어려움"),(0,"D","극도로 어려움")]
    for threshold, grade, label in grades:
        if score >= threshold:
            return grade, label, score
    return "D", "극도로 어려움", score


# ============================================================
# 분석 실행
# ============================================================
def run_analysis(keyword, config):
    result = {
        "keyword": keyword,
        "analyzed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "search_volume": {}, "blog_stats": {},
        "trend": {}, "difficulty": {},
        "related_keywords": [], "cpc": {}
    }

    progress = st.progress(0, text="🔍 네이버 검색광고 API 조회 중...")

    # 1. 검색광고 API
    ad_api = NaverSearchAdAPI(
        config["naver_searchad"]["customer_id"],
        config["naver_searchad"]["api_key"],
        config["naver_searchad"]["secret_key"]
    )
    kw_stats = ad_api.get_keyword_stats(keyword)
    if kw_stats and kw_stats["main_keyword"]:
        main = kw_stats["main_keyword"]
        result["search_volume"] = {
            "monthly_total": main["monthly_total"],
            "monthly_pc": main["monthly_pc"],
            "monthly_mobile": main["monthly_mobile"],
            "pc_ratio": main["pc_ratio"],
            "mobile_ratio": main["mobile_ratio"]
        }
        # 실제 CPC(원) 조회
        estimated_cpc = ad_api.get_estimated_cpc(keyword)
        result["cpc"] = {
            "avg_pc_cpc": estimated_cpc,
            "avg_mobile_cpc": main.get("avg_mobile_cpc", 0),
            "competition": main.get("competition", "")
        }
        for rk in kw_stats["related_keywords"][:15]:
            result["related_keywords"].append({
                "keyword": rk["keyword"], "monthly_total": rk["monthly_total"]
            })

    progress.progress(25, text="📝 블로그 발행량 조회 중...")

    # 2. 블로그 발행량
    blog_api = NaverBlogSearchAPI(
        config["naver_openapi"]["client_id"],
        config["naver_openapi"]["client_secret"]
    )
    monthly_publish, total_posts = blog_api.get_monthly_publish_count(keyword)
    result["blog_stats"] = {"monthly_publish": monthly_publish, "total_posts": total_posts}

    # 3. DataLab
    progress.progress(40, text="📈 검색 트렌드 조회 중...")
    datalab = NaverDataLabAPI(
        config["naver_openapi"]["client_id"],
        config["naver_openapi"]["client_secret"]
    )
    trend = datalab.get_trend(keyword)
    yoy_change = datalab.get_yoy_change(keyword)
    result["trend"] = {"data": trend, "yoy_change": yoy_change}

    # 4. 난이도
    cpc_val = result["cpc"].get("avg_pc_cpc", 0)
    if isinstance(cpc_val, str): cpc_val = 0
    monthly_search = result["search_volume"].get("monthly_total", 1)
    grade, grade_label, grade_score = calculate_difficulty(
        monthly_search, cpc_val,
        result["cpc"].get("competition", "보통")
    )
    result["difficulty"] = {"grade": grade, "label": grade_label, "score": grade_score}

    progress.progress(100, text="✅ 분석 완료!")
    time.sleep(0.5)
    progress.empty()
    return result


# ============================================================
# 결과 표시
# ============================================================
def display_results(result):
    sv = result["search_volume"]
    bs = result["blog_stats"]
    diff = result["difficulty"]
    trend = result["trend"]
    cpc = result["cpc"]
    related = result["related_keywords"]

    grade_colors = {"A+":"#16a34a","A":"#22c55e","A-":"#84cc16","B+":"#eab308",
                    "B":"#f59e0b","B-":"#f97316","C":"#ef4444","D":"#dc2626"}
    gc = grade_colors.get(diff["grade"], "#94a3b8")

    st.markdown(f"""
    <div style="background:white;border-radius:16px;padding:24px;border:1px solid #e2e8f0;display:flex;align-items:center;gap:20px;margin-bottom:20px">
        <div class="grade-badge" style="background:{gc}">
            <span class="grade">{diff["grade"]}</span>
            <span class="grade-label">{diff["label"]}</span>
        </div>
        <div>
            <div style="font-size:24px;font-weight:700">{result["keyword"]}</div>
            <div style="font-size:14px;color:#94a3b8;margin-top:6px">
                난이도 <strong>{diff["label"]}</strong> · 점수 {diff["score"]}/100 · {result["analyzed_at"]}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    yoy = trend.get("yoy_change", 0)
    yoy_color = "#ef4444" if yoy < 0 else "#22c55e"
    yoy_icon = "📉" if yoy < 0 else "📈"

    cols = st.columns(5)
    metrics = [
        ("월 검색량", f"{sv.get('monthly_total',0):,}", "회", ""),
        ("월 발행량", f"{bs.get('monthly_publish',0):,}", "개", ""),
        ("평균 클릭 광고비", f"{cpc.get('avg_pc_cpc',0)}", "원", ""),
        ("경쟁도", f"{cpc.get('competition','')}", "", ""),
        ("전년대비", f"{yoy:+.1f}", "%", f"{yoy_icon} {'감소' if yoy < 0 else '증가'}"),
    ]
    for col, (label, value, unit, sub) in zip(cols, metrics):
        with col:
            val_color = yoy_color if label == "전년대비" else "#1e293b"
            st.markdown(f"""
            <div class="metric-card">
                <div class="label">{label}</div>
                <div class="value" style="color:{val_color}">{value}<span class="unit">{unit}</span></div>
                <div class="sub">{sub}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # 트렌드 차트
    trend_data = trend.get("data", [])
    if trend_data:
        st.markdown(f"""
        <div class="section-header">📈 검색 트렌드
            <span style="font-size:14px;font-weight:400;color:{yoy_color}">
                전년대비 {yoy:+.1f}% {'감소' if yoy < 0 else '증가'}
            </span>
        </div>
        """, unsafe_allow_html=True)
        df_trend = pd.DataFrame(trend_data)
        df_trend["period"] = pd.to_datetime(df_trend["period"])
        df_trend = df_trend.set_index("period")
        st.area_chart(df_trend["ratio"], color="#22c55e", use_container_width=True)

    # 연관 키워드
    st.markdown('<div class="section-header">🔗 연관 키워드</div>', unsafe_allow_html=True)
    if related:
        rows = []
        for rk in related:
            rows.append({"키워드": rk["keyword"], "월 검색량": f"{rk['monthly_total']:,}"})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=min(len(rows)*40+40, 600))

    # JSON 다운로드
    st.markdown("<br>", unsafe_allow_html=True)
    st.download_button(
        "📥 분석 결과 JSON 다운로드",
        json.dumps(result, ensure_ascii=False, indent=2),
        f"keyword_{result['keyword']}.json", "application/json"
    )


# ============================================================
# 메인
# ============================================================
def main():
    config = get_config()

    # API 키가 없으면 사이드바에서 입력
    if config is None:
        with st.sidebar:
            st.markdown("### ⚙️ API 설정")
            config_file = st.file_uploader("config.json 업로드", type=["json"])
            if config_file:
                st.session_state["config"] = json.load(config_file)
                st.success("설정 완료!")
                st.rerun()

            st.markdown("---")
            st.markdown("**직접 입력:**")
            st.markdown("##### 네이버 검색광고 API")
            cid = st.text_input("Customer ID", type="password")
            akey = st.text_input("API Key", type="password")
            skey = st.text_input("Secret Key", type="password")
            st.markdown("##### 네이버 오픈 API")
            oid = st.text_input("Client ID", type="password")
            osec = st.text_input("Client Secret", type="password")
            if cid and akey and skey and oid and osec:
                st.session_state["config"] = {
                    "naver_searchad": {"customer_id": cid, "api_key": akey, "secret_key": skey},
                    "naver_openapi": {"client_id": oid, "client_secret": osec}
                }
                st.success("API 키 설정 완료!")
                st.rerun()

        config = get_config()

    # 메인 UI
    st.markdown("""
    <div style="text-align:center;margin-bottom:32px">
        <h1 style="font-size:32px;font-weight:800">🔍 키워드 분석기</h1>
        <p style="color:#94a3b8;font-size:15px">네이버 검색량 · 발행량 · 트렌드를 한눈에</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([4, 1])
    with col1:
        keyword = st.text_input("키워드", placeholder="분석할 키워드를 입력하세요", label_visibility="collapsed")
    with col2:
        analyze_btn = st.button("🔍 분석하기", use_container_width=True)

    if analyze_btn and keyword:
        if config is None:
            st.error("⚠️ 왼쪽 사이드바(>) 에서 API 설정을 먼저 완료해주세요.")
            return
        result = run_analysis(keyword, config)
        st.session_state["last_result"] = result

    if "last_result" in st.session_state:
        display_results(st.session_state["last_result"])

    st.markdown('<div class="footer">Powered by 네이버 API · Built with Streamlit</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()
