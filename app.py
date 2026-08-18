"""
UFC 선수 비교 분석기
Play Lab Academy 2기 개인프로젝트 - 과제 1: 타 스포츠 데이터분석 웹사이트 제작

[왜 만들었는가]
UFC 팬들 사이에서 "저 선수 진짜 세냐", "이번에 붙으면 누가 이길까" 같은 논쟁은 항상
하이라이트 영상 몇 개, 기억에 남는 장면 하나로 결론이 나버린다. 그런데 UFC는 사실
경기마다 유효타 수, 테이크다운 성공률, 컨트롤 타임 같은 상세 기록이 전부 남는 스포츠다.
이 사이트는 그 기록을 근거로, "감"이 아니라 "데이터"로 두 선수를 비교하고
체급 전체의 흐름까지 읽을 수 있게 만든 것이 목적이다.

[사람들이 이걸로 할 수 있는 것]
1. 두 선수를 골라 전적 · 승리 방식 · 타격/그래플링 스탯을 나란히 비교해서
   "맞대결 논쟁"에 실제 근거 자료로 쓸 수 있다.
2. 좋아하는 선수의 커리어 전체 패턴(어떻게 이기고 지는 선수인가)을 데이터로 훑어볼 수 있다.
3. 관심 체급이 최근 몇 년 사이 어떻게 바뀌었는지(피니시 비율, 판정 비율 변화 등)
   트렌드로 확인할 수 있다.

데이터 출처: ufcstats.com 공식 기록 (Greco1899/scrape_ufc_stats 저장소가 매일 자동 수집)
데이터 기간: 1994년 ~ 2026년 8월 (가장 최근 이벤트까지 반영된 최신 데이터)
"""

import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="UFC 선수 비교 분석기", page_icon="🥊", layout="wide")


# ------------------------------------------------------------
# 데이터 로드
# ------------------------------------------------------------
@st.cache_data
def load_data():
    fights = pd.read_csv("data/ufc_fights.csv")
    fights["DATE"] = pd.to_datetime(fights["DATE"], errors="coerce")

    bio = pd.read_csv("data/ufc_fighter_bio.csv")
    career = pd.read_csv("data/ufc_fighter_career_stats.csv")

    return fights, bio, career


fights, bio, career = load_data()
all_fighters = sorted(set(fights["fighter_1"]).union(set(fights["fighter_2"])))

# ------------------------------------------------------------
# 사이드바 내비게이션
# ------------------------------------------------------------
page = st.sidebar.radio("화면 선택", ["🏠 소개", "🥊 선수 비교", "📊 체급별 트렌드"])

st.sidebar.markdown("---")
st.sidebar.caption(
    "데이터 출처: ufcstats.com (Greco1899/scrape_ufc_stats 매일 자동 수집)\n\n"
    f"데이터 기간: {fights['DATE'].min().date()} ~ {fights['DATE'].max().date()}"
)

# ==============================================================
# 화면 1. 소개
# ==============================================================
if page == "🏠 소개":
    st.title("🥊 UFC 선수 비교 분석기")

    st.markdown(
        """
        ### 왜 만들었나
        UFC 팬들 사이에서 "저 선수 진짜 세냐", "이번에 붙으면 누가 이길까" 논쟁은
        늘 하이라이트 영상 몇 개로 끝나버립니다. 하지만 UFC는 경기마다 유효타 수,
        테이크다운 성공률, 컨트롤 타임까지 상세히 기록되는 스포츠입니다.
        이 사이트는 그 기록을 근거로 **감이 아니라 데이터로** 선수를 비교하고,
        체급 전체의 흐름까지 읽을 수 있게 만들었습니다.

        ### 이 사이트로 할 수 있는 것
        - 두 선수의 전적 · 승리 방식 · 타격/그래플링 스탯을 나란히 비교
        - 좋아하는 선수의 커리어 전체 패턴(어떻게 이기고 지는가) 확인
        - 관심 체급이 최근 몇 년간 어떻게 바뀌었는지(피니시율 변화 등) 트렌드 파악
        """
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("전체 경기 수", f"{len(fights):,}경기")
    col2.metric("등장 선수 수", f"{len(all_fighters):,}명")
    col3.metric("데이터 기간", f"{int(fights['year'].min())}~{int(fights['year'].max())}")

    st.subheader("전체 승리 방식 분포")
    method_counts = fights[fights["result_type"] == "승패"]["method_simple"].value_counts().reset_index()
    method_counts.columns = ["방식", "횟수"]
    fig = px.bar(method_counts, x="방식", y="횟수", color="방식")
    st.plotly_chart(fig, use_container_width=True)

    st.info("왼쪽 사이드바에서 '선수 비교' 또는 '체급별 트렌드' 화면으로 이동해보세요 →")

# ==============================================================
# 화면 2. 선수 비교 (핵심 기능)
# ==============================================================
elif page == "🥊 선수 비교":
    st.title("🥊 선수 비교")
    st.caption("두 선수를 골라서 전적, 승리 방식, 타격·그래플링 스탯을 비교합니다.")

    c1, c2 = st.columns(2)
    default_a = all_fighters.index("Islam Makhachev") if "Islam Makhachev" in all_fighters else 0
    default_b = all_fighters.index("Conor McGregor") if "Conor McGregor" in all_fighters else 1
    fighter_a = c1.selectbox("선수 A", all_fighters, index=default_a)
    fighter_b = c2.selectbox("선수 B", all_fighters, index=default_b)

    def fighter_record(name):
        wins = fights[fights["winner"] == name]
        losses = fights[fights["loser"] == name]
        total = len(wins) + len(losses)
        win_methods = wins["method_simple"].value_counts()
        return {
            "name": name, "wins": len(wins), "losses": len(losses), "total": total,
            "win_rate": (len(wins) / total * 100) if total else 0,
            "win_methods": win_methods,
        }

    a = fighter_record(fighter_a)
    b = fighter_record(fighter_b)

    st.markdown("### 전적 비교")
    col1, col2 = st.columns(2)
    for col, s in [(col1, a), (col2, b)]:
        with col:
            st.subheader(s["name"])
            st.metric("전적 (승-패)", f"{s['wins']}승 {s['losses']}패")
            st.metric("승률", f"{s['win_rate']:.1f}%")

            bio_row = bio[bio["FIGHTER"] == s["name"]]
            if not bio_row.empty:
                row = bio_row.iloc[0]
                st.caption(
                    f"신장 {row.get('HEIGHT', '정보없음')} · 리치 {row.get('REACH', '정보없음')} · "
                    f"스탠스 {row.get('STANCE') if pd.notna(row.get('STANCE')) else '정보없음'}"
                )

            career_row = career[career["FIGHTER"] == s["name"]]
            if not career_row.empty:
                cr = career_row.iloc[0]
                st.metric("경기당 유효타", f"{cr['sig_str_per_fight']:.1f}개" if pd.notna(cr["sig_str_per_fight"]) else "정보없음")
                m1, m2 = st.columns(2)
                m1.metric("유효타 정확도", f"{cr['sig_str_accuracy']:.0f}%" if pd.notna(cr["sig_str_accuracy"]) else "-")
                m2.metric("테이크다운 성공률", f"{cr['td_accuracy']:.0f}%" if pd.notna(cr["td_accuracy"]) else "-")
            else:
                st.caption("상세 경기 통계 데이터 없음")

    st.markdown("### 승리 방식 비교 (KO/TKO · Submission · Decision)")
    compare_df = pd.DataFrame({
        fighter_a: a["win_methods"],
        fighter_b: b["win_methods"],
    }).fillna(0)
    compare_df.index.name = "방식"
    compare_df = compare_df.reset_index()
    compare_long = compare_df.melt(id_vars="방식", var_name="선수", value_name="승수")
    fig2 = px.bar(compare_long, x="방식", y="승수", color="선수", barmode="group")
    st.plotly_chart(fig2, use_container_width=True)

    st.markdown("### 맞대결 기록")
    h2h = fights[
        ((fights["fighter_1"] == fighter_a) & (fights["fighter_2"] == fighter_b)) |
        ((fights["fighter_1"] == fighter_b) & (fights["fighter_2"] == fighter_a))
    ]
    if h2h.empty:
        st.write("두 선수는 UFC에서 맞붙은 기록이 없습니다.")
    else:
        st.dataframe(h2h[["DATE", "EVENT", "winner", "loser", "METHOD", "weightclass"]])

# ==============================================================
# 화면 3. 체급별 트렌드
# ==============================================================
elif page == "📊 체급별 트렌드":
    st.title("📊 체급별 트렌드")
    st.caption("체급을 고르면 승리 방식 분포와, 최근 몇 년 사이 피니시(KO·서브미션) 비율 변화를 보여줍니다.")

    divisions = [d for d in fights["weight_division"].dropna().unique() if d != "기타"]
    weight_class = st.selectbox("체급 선택", sorted(divisions))
    filtered = fights[(fights["weight_division"] == weight_class) & (fights["result_type"] == "승패")].dropna(subset=["year"])

    st.markdown(f"### {weight_class} 승리 방식 분포")
    method_counts = filtered["method_simple"].value_counts().reset_index()
    method_counts.columns = ["방식", "횟수"]
    fig3 = px.pie(method_counts, names="방식", values="횟수")
    st.plotly_chart(fig3, use_container_width=True)

    st.markdown(f"### {weight_class} 연도별 피니시 비율 변화")
    filtered = filtered.copy()
    filtered["is_finish"] = filtered["method_simple"].isin(["KO/TKO", "Submission"])
    yearly = filtered.groupby(filtered["year"].astype(int)).agg(
        경기수=("method_simple", "count"),
        피니시비율=("is_finish", "mean"),
    ).reset_index()
    yearly["피니시비율"] = (yearly["피니시비율"] * 100).round(1)

    fig4 = px.line(yearly, x="year", y="피니시비율", markers=True,
                    labels={"year": "연도", "피니시비율": "피니시(KO·서브미션) 비율(%)"})
    st.plotly_chart(fig4, use_container_width=True)
    st.caption("판정까지 가지 않고 KO나 서브미션으로 끝난 경기 비율이 시대별로 어떻게 변했는지 보여줍니다.")
