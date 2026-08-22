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
import plotly.graph_objects as go
from urllib.parse import quote

st.set_page_config(page_title="UFC 선수 비교 분석기", page_icon="🥊", layout="wide")

# ------------------------------------------------------------
# 색상 팔레트 (dataviz 스킬의 검증된 카테고리 팔레트 — 고정 슬롯 매핑)
# 방식(승리 방식)은 항상 같은 색을 갖도록 고정: 필터가 바뀌어도 색이 안 변함
# ------------------------------------------------------------
METHOD_COLORS = {
    "Decision": "#2a78d6",    # slot 1 blue
    "KO/TKO": "#eb6834",      # slot 2 orange
    "Submission": "#1baf7a",  # slot 3 aqua
    "DQ": "#eda100",          # slot 4 yellow
    "기타": "#e34948",        # slot 8 red (fallback)
}
FIGHTER_COLORS = ["#2a78d6", "#eb6834"]        # 선수 A/B 비교용 slot 1, 2
TRIO_COLORS = ["#2a78d6", "#eb6834", "#1baf7a"]  # 3인 비교(한국 파이터)용 slot 1,2,3 — all-pairs 검증된 조합

CHART_TEMPLATE = dict(
    plot_bgcolor="#fcfcfb",
    paper_bgcolor="#fcfcfb",
    font=dict(color="#0b0b0b", family="system-ui, -apple-system, 'Segoe UI', sans-serif"),
    xaxis=dict(gridcolor="#e1e0d9", linecolor="#c3c2b7"),
    yaxis=dict(gridcolor="#e1e0d9", linecolor="#c3c2b7"),
    legend=dict(bgcolor="rgba(0,0,0,0)"),
    margin=dict(t=30, b=10, l=10, r=10),
)


def style_chart(fig):
    fig.update_layout(**CHART_TEMPLATE)
    return fig


def hex_to_rgba(hex_color, alpha=0.28):
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def avatar_html(name, color, size=56):
    parts = [p for p in name.replace("-", " ").split() if p]
    initials = "".join(p[0] for p in parts[:2]).upper() if parts else "?"
    return (
        f'<div style="width:{size}px;height:{size}px;border-radius:50%;'
        f"background:{color};color:#ffffff;display:flex;align-items:center;"
        f"justify-content:center;font-weight:700;font-size:{size * 0.38:.0f}px;"
        f"font-family:system-ui,-apple-system,'Segoe UI',sans-serif;"
        f'margin-bottom:6px;">{initials}</div>'
    )


# ------------------------------------------------------------
# 레이더(방사형) 차트용 지표 — 선수 개인 스탯을 전체 선수 대비 백분위로 환산
# (단위가 다른 지표들을 한 화면에서 비교하려면 백분위 정규화가 필요)
# ------------------------------------------------------------
RADAR_LABELS = {
    "sig_str_per_fight": "유효타/경기",
    "sig_str_accuracy": "유효타 정확도",
    "td_accuracy": "테이크다운 정확도",
    "ctrl_min_per_fight": "컨트롤타임(분/경기)",
    "sub_att_per_fight": "서브미션 시도/경기",
    "win_rate": "승률",
}
RADAR_KEYS = list(RADAR_LABELS.keys())


@st.cache_data
def build_fighter_metrics(fights, career):
    decided = fights[fights["result_type"] == "승패"]
    wins = decided.groupby("winner").size()
    losses = decided.groupby("loser").size()
    record = pd.DataFrame({"wins": wins, "losses": losses}).fillna(0)
    record["total"] = record["wins"] + record["losses"]
    record["win_rate"] = np.where(record["total"] > 0, record["wins"] / record["total"] * 100, np.nan)
    record.index.name = "FIGHTER"
    record = record.reset_index()

    metrics = career.merge(record[["FIGHTER", "win_rate"]], on="FIGHTER", how="left")
    metrics["sub_att_per_fight"] = metrics["total_sub_att"] / metrics["fights_recorded"]

    # 극단치 방지를 위해 3경기 이상 기록이 있는 선수만 비교 모집단으로 사용
    pool = metrics[metrics["fights_recorded"] >= 3]
    for col in RADAR_KEYS:
        sorted_pool = np.sort(pool[col].dropna().values)
        if len(sorted_pool) == 0:
            metrics[f"pct_{col}"] = np.nan
            continue
        metrics[f"pct_{col}"] = metrics[col].apply(
            lambda v: (np.searchsorted(sorted_pool, v, side="right") / len(sorted_pool) * 100)
            if pd.notna(v) else np.nan
        )

    return metrics.set_index("FIGHTER")


def radar_values(name, metrics):
    if name not in metrics.index:
        return None, 0
    row = metrics.loc[name]
    vals = [row.get(f"pct_{c}", np.nan) for c in RADAR_KEYS]
    return vals, row.get("fights_recorded", 0)


def make_radar_chart(entries):
    """entries: [(라벨, 백분위값 리스트, 색상 hex), ...]"""
    labels = [RADAR_LABELS[k] for k in RADAR_KEYS]
    fig = go.Figure()
    for label, values, color in entries:
        vals = [v if pd.notna(v) else 0 for v in values]
        fig.add_trace(go.Scatterpolar(
            r=vals + vals[:1],
            theta=labels + labels[:1],
            fill="toself",
            name=label,
            line=dict(color=color, width=2),
            fillcolor=hex_to_rgba(color, 0.28),
        ))
    fig.update_layout(
        polar=dict(
            bgcolor="#fcfcfb",
            radialaxis=dict(visible=True, range=[0, 100], gridcolor="#e1e0d9", linecolor="#c3c2b7"),
            angularaxis=dict(gridcolor="#e1e0d9", linecolor="#c3c2b7"),
        ),
        paper_bgcolor="#fcfcfb",
        font=dict(color="#0b0b0b", family="system-ui, -apple-system, 'Segoe UI', sans-serif"),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        margin=dict(t=30, b=10, l=10, r=10),
    )
    return fig


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
metrics = build_fighter_metrics(fights, career)

KOREAN_FIGHTERS = [
    {"name": "Dong Hyun Kim", "kor": "김동현", "style": "그래플러 — 테이크다운·컨트롤타임 강세"},
    {"name": "Chan Sung Jung", "kor": "정찬성 (코리안 좀비)", "style": "올라운더 — 타격·그래플링 균형형"},
    {"name": "Dooho Choi", "kor": "최두호", "style": "타격가 — 유효타 정확도 강세"},
]

# ------------------------------------------------------------
# 사이드바 내비게이션
# ------------------------------------------------------------
page = st.sidebar.radio(
    "화면 선택",
    ["🏠 소개", "🥊 선수 비교", "📊 체급별 트렌드", "🇰🇷 한국 파이터"],
)

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
        - 두 선수의 전적 · 승리 방식 · 타격/그래플링 스탯을 나란히 비교하고,
          **레이더 차트**로 스타일 차이(타격형 vs 그래플러형)를 한눈에 확인
        - 좋아하는 선수의 커리어 전체 패턴(어떻게 이기고 지는가) 확인
        - 관심 체급이 최근 몇 년간 어떻게 바뀌었는지(피니시율 변화, 타격 vs 그래플링
          승리 비중 변화 등) 트렌드로 파악
        - 김동현 · 정찬성 · 최두호 등 **한국 파이터**들의 스타일을 데이터로 비교
        """
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("전체 경기 수", f"{len(fights):,}경기")
    col2.metric("등장 선수 수", f"{len(all_fighters):,}명")
    col3.metric("데이터 기간", f"{int(fights['year'].min())}~{int(fights['year'].max())}")

    st.subheader("전체 승리 방식 분포")
    method_counts = fights[fights["result_type"] == "승패"]["method_simple"].value_counts().reset_index()
    method_counts.columns = ["방식", "횟수"]
    fig = px.bar(method_counts, x="방식", y="횟수", color="방식", color_discrete_map=METHOD_COLORS)
    fig = style_chart(fig)
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
    for col, s, avatar_color in [(col1, a, FIGHTER_COLORS[0]), (col2, b, FIGHTER_COLORS[1])]:
        with col:
            st.markdown(avatar_html(s["name"], avatar_color), unsafe_allow_html=True)
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
    fig2 = px.bar(compare_long, x="방식", y="승수", color="선수", barmode="group",
                   color_discrete_sequence=FIGHTER_COLORS)
    fig2 = style_chart(fig2)
    st.plotly_chart(fig2, use_container_width=True)

    st.markdown("### 스타일 비교 (레이더 차트)")
    st.caption(
        "경기당 유효타 · 정확도 · 테이크다운 · 컨트롤타임 · 서브미션 시도 · 승률을 "
        "**전체 선수 대비 백분위**로 환산해 겹쳐 그렸습니다. 바깥쪽으로 뻗을수록 "
        "그 항목에서 상위권이라는 뜻이라, 예를 들어 그래플러형(테이크다운·컨트롤타임 우세)과 "
        "타격가형(유효타 정확도 우세)의 모양 차이가 한눈에 드러납니다."
    )
    vals_a, n_a = radar_values(fighter_a, metrics)
    vals_b, n_b = radar_values(fighter_b, metrics)
    if vals_a is None or vals_b is None:
        st.write("두 선수 중 상세 경기 통계가 없는 선수가 있어 레이더 차트를 그릴 수 없습니다.")
    else:
        radar_fig = make_radar_chart([
            (fighter_a, vals_a, FIGHTER_COLORS[0]),
            (fighter_b, vals_b, FIGHTER_COLORS[1]),
        ])
        st.plotly_chart(radar_fig, use_container_width=True)
        low_sample = [n for n in [(fighter_a, n_a), (fighter_b, n_b)] if n[1] < 3]
        if low_sample:
            names = ", ".join(n[0] for n in low_sample)
            st.caption(f"⚠️ {names} 선수는 기록된 경기 수가 적어(3경기 미만) 참고용으로만 봐주세요.")

    st.markdown("### 🎥 이 매치업 하이라이트 찾아보기")
    yt_query = quote(f"{fighter_a} vs {fighter_b} highlights")
    st.markdown(
        f"UFC 기록 데이터만으로는 '보는 재미'가 부족하니, 실제 경기 영상도 바로 찾아볼 수 있게 "
        f"연결했습니다 → [YouTube에서 '{fighter_a} vs {fighter_b}' 하이라이트 검색하기]"
        f"(https://www.youtube.com/results?search_query={yt_query})"
    )

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
    st.caption(
        "체급을 고르면 승리 방식 분포, 최근 몇 년 사이 피니시(KO·서브미션) 비율 변화, "
        "타격/그래플링 스타일 비중 변화, 최다승 선수까지 보여줍니다."
    )

    divisions = [d for d in fights["weight_division"].dropna().unique() if d != "기타"]
    weight_class = st.selectbox("체급 선택", sorted(divisions))
    filtered = fights[(fights["weight_division"] == weight_class) & (fights["result_type"] == "승패")].dropna(subset=["year"])

    st.markdown(f"### {weight_class} 승리 방식 분포")
    method_counts = filtered["method_simple"].value_counts().reset_index()
    method_counts.columns = ["방식", "횟수"]
    fig3 = px.pie(method_counts, names="방식", values="횟수", color="방식", color_discrete_map=METHOD_COLORS)
    fig3 = style_chart(fig3)
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
                    labels={"year": "연도", "피니시비율": "피니시(KO·서브미션) 비율(%)"},
                    color_discrete_sequence=["#2a78d6"])
    fig4 = style_chart(fig4)
    st.plotly_chart(fig4, use_container_width=True)
    st.caption("판정까지 가지 않고 KO나 서브미션으로 끝난 경기 비율이 시대별로 어떻게 변했는지 보여줍니다.")

    st.markdown(f"### {weight_class} 연도별 승리 방식 비중 변화 (타격 vs 그래플링)")
    style_ct = pd.crosstab(filtered["year"].astype(int), filtered["method_simple"], normalize="index") * 100
    style_long = style_ct.reset_index().melt(id_vars="year", var_name="방식", value_name="비율")
    fig6 = px.line(
        style_long, x="year", y="비율", color="방식", markers=True,
        color_discrete_map=METHOD_COLORS,
        labels={"year": "연도", "비율": "비율(%)"},
    )
    fig6 = style_chart(fig6)
    st.plotly_chart(fig6, use_container_width=True)
    st.caption(
        "판정(Decision) · KO/TKO(타격) · Submission(그래플링) 각각이 연도별 전체 승리 중 "
        "몇 %를 차지했는지 보여줍니다. 예를 들어 서브미션 비중이 꾸준히 낮고 판정·KO 비중이 "
        "높다면, 그 체급은 최근 그래플링보다 타격/체력전 중심으로 흘러갔다고 읽을 수 있습니다."
    )

    st.markdown(f"### {weight_class} 체급 내 최다승 TOP 5")
    top_winners = filtered["winner"].value_counts().head(5).reset_index()
    top_winners.columns = ["선수", "승수"]
    if top_winners.empty:
        st.write("표시할 데이터가 없습니다.")
    else:
        fig5 = px.bar(
            top_winners.sort_values("승수"), x="승수", y="선수", orientation="h",
            color_discrete_sequence=["#2a78d6"],
        )
        fig5 = style_chart(fig5)
        st.plotly_chart(fig5, use_container_width=True)
        st.caption(f"{weight_class} 체급 경기에서 UFC 데이터 기준 가장 많은 승수를 기록한 선수 5명입니다.")

# ==============================================================
# 화면 4. 한국 파이터
# ==============================================================
elif page == "🇰🇷 한국 파이터":
    st.title("🇰🇷 한국 파이터 스포트라이트")
    st.caption(
        "한국 팬들에게 익숙한 세 선수 — 김동현 · 정찬성 · 최두호 — 를 같은 레이더 차트 위에 "
        "겹쳐서, 스타일이 실제로 얼마나 다른지 데이터로 확인합니다."
    )

    cols = st.columns(3)
    radar_entries = []
    for col, fighter, color in zip(cols, KOREAN_FIGHTERS, TRIO_COLORS):
        name = fighter["name"]
        with col:
            st.markdown(avatar_html(name, color, size=72), unsafe_allow_html=True)
            st.subheader(f"{fighter['kor']}")
            st.caption(f"{name} · {fighter['style']}")

            wins = (fights["winner"] == name).sum()
            losses = (fights["loser"] == name).sum()
            st.metric("전적 (승-패)", f"{wins}승 {losses}패")

            career_row = career[career["FIGHTER"] == name]
            if not career_row.empty:
                cr = career_row.iloc[0]
                m1, m2 = st.columns(2)
                m1.metric("유효타 정확도", f"{cr['sig_str_accuracy']:.0f}%" if pd.notna(cr["sig_str_accuracy"]) else "-")
                m2.metric("테이크다운 정확도", f"{cr['td_accuracy']:.0f}%" if pd.notna(cr["td_accuracy"]) else "-")

        vals, n = radar_values(name, metrics)
        if vals is not None:
            radar_entries.append((fighter["kor"], vals, color))

    st.markdown("### 세 선수 스타일 레이더 비교")
    if len(radar_entries) >= 2:
        st.plotly_chart(make_radar_chart(radar_entries), use_container_width=True)
        st.caption(
            "테이크다운·컨트롤타임 쪽으로 뻗어 있으면 그래플러형, 유효타 정확도 쪽으로 "
            "뻗어 있으면 타격가형입니다. 세 선수의 모양이 다르게 나온다면, 실제로 서로 "
            "다른 스타일로 UFC에서 활동했다는 뜻입니다."
        )
    else:
        st.write("레이더 차트를 그릴 만큼 상세 통계가 있는 선수가 부족합니다.")

    st.info(
        "이 페이지는 '한국 팬들이 바로 알아볼 수 있는 선수부터 보여주자'는 피드백을 반영해 "
        "추가했습니다. 더 많은 한국 파이터를 추가하려면 위 코드의 KOREAN_FIGHTERS 리스트에 "
        "선수 이름만 추가하면 됩니다."
    )
