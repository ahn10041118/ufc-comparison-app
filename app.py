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

import base64
import os
import pandas as pd
import numpy as np
import requests
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from urllib.parse import quote

st.set_page_config(page_title="UFC 선수 비교 분석기", page_icon="🥊", layout="wide")

# 다크 테마 + 카드형 레이아웃: 스포츠 중계 화면처럼 큰 숫자·굵은 라벨이 잘 보이도록,
# 장식용 이모지 대신 색상 배지/타이포그래피로 정보 위계를 표현
st.markdown(
    """
    <style>
    div[data-testid="stVerticalBlockBorderWrapper"] > div {
        border-radius: 14px;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        box-shadow: 0 1px 6px rgba(0,0,0,0.35);
        border-radius: 14px;
        border: 1px solid rgba(255,255,255,0.08) !important;
        transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        transform: translateY(-3px);
        box-shadow: 0 10px 24px rgba(0,0,0,0.5);
        border-color: rgba(224,57,62,0.45) !important;
    }
    [data-testid="stMetricLabel"] {
        color: #c3c2b7;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        font-size: 0.72rem !important;
    }
    [data-testid="stMetricValue"] { font-weight: 800; }
    .stTabs [data-baseweb="tab-list"] { gap: 4px; }
    h2, h3 { margin-top: 0.9em; letter-spacing: 0.01em; }
    section[data-testid="stSidebar"] .stRadio label { font-size: 0.95rem; }
    .stButton > button {
        border-radius: 10px;
        border: 1px solid rgba(224,57,62,0.5);
        background: transparent;
        color: #ffffff;
        font-weight: 600;
        transition: background 0.15s ease, border-color 0.15s ease, transform 0.15s ease;
    }
    .stButton > button:hover {
        background: rgba(224,57,62,0.15);
        border-color: #e0393e;
        color: #ffffff;
        transform: translateY(-1px);
    }
    div[data-baseweb="select"] > div, div[data-baseweb="input"] > div {
        border-radius: 10px !important;
        border-color: rgba(255,255,255,0.15) !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------
# 색상 팔레트 (dataviz 스킬의 검증된 카테고리 팔레트 — 다크 서피스용 스텝, 고정 슬롯 매핑)
# 방식(승리 방식)은 항상 같은 색을 갖도록 고정: 필터가 바뀌어도 색이 안 변함
# ------------------------------------------------------------
CHART_SURFACE = "#1a1a19"   # 다크 모드 차트 배경
CHART_INK = "#ffffff"       # 다크 모드 주 텍스트
CHART_GRID = "#2c2c2a"      # 다크 모드 격자선
CHART_AXIS = "#383835"      # 다크 모드 축선
ACCENT_RED = "#e0393e"      # 앱 강조색 (스포츠 중계 느낌의 레드 포인트)

METHOD_COLORS = {
    "Decision": "#3987e5",    # slot 1 blue (dark)
    "KO/TKO": "#d95926",      # slot 2 orange (dark)
    "Submission": "#199e70",  # slot 3 aqua (dark)
    "DQ": "#c98500",          # slot 4 yellow (dark)
    "기타": "#e66767",        # slot 8 red (dark, fallback)
}
FIGHTER_COLORS = ["#3987e5", "#d95926"]        # 선수 A/B 비교용 slot 1, 2
TRIO_COLORS = ["#3987e5", "#d95926", "#199e70"]  # 3인 비교(한국 파이터)용 slot 1,2,3 — all-pairs 검증된 조합
STYLE_COLORS = {
    "그래플러형": TRIO_COLORS[2],
    "타격가형": TRIO_COLORS[1],
    "올라운더형": TRIO_COLORS[0],
}

CHART_TEMPLATE = dict(
    plot_bgcolor=CHART_SURFACE,
    paper_bgcolor=CHART_SURFACE,
    font=dict(color=CHART_INK, family="system-ui, -apple-system, 'Segoe UI', sans-serif"),
    xaxis=dict(gridcolor=CHART_GRID, linecolor=CHART_AXIS),
    yaxis=dict(gridcolor=CHART_GRID, linecolor=CHART_AXIS),
    legend=dict(bgcolor="rgba(0,0,0,0)"),
    margin=dict(t=30, b=10, l=10, r=10),
)


def section_header(text, color=None):
    """일반 마크다운 헤더 대신 쓰는, 왼쪽에 색 막대가 붙은 섹션 제목 — 카드의 색 막대와
    같은 디자인 언어를 페이지 전체에 반복해서 시각적으로 하나의 제품처럼 보이게 함."""
    bar_color = color or ACCENT_RED
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:10px;margin:1.3em 0 0.7em 0;">'
        f'<div style="width:4px;height:22px;border-radius:2px;background:{bar_color};flex-shrink:0;"></div>'
        f'<div style="font-size:1.3rem;font-weight:800;color:#ffffff;">{text}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def style_badge_html(label):
    color = STYLE_COLORS.get(label, "#666666")
    return (
        f'<span style="display:inline-block;background:{color};color:#ffffff;'
        f'padding:3px 12px;border-radius:999px;font-size:12px;font-weight:700;'
        f'letter-spacing:0.02em;">{label}</span>'
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

# 레이더 차트를 처음 보는 사람도 각 지표가 뭘 뜻하는지 바로 이해할 수 있도록 짧은 설명 추가
RADAR_METRIC_DESC = {
    "sig_str_per_fight": "한 경기당 상대에게 적중시킨 유효타(스트라이크) 평균 횟수",
    "sig_str_accuracy": "시도한 타격 중 실제로 맞춘 비율 — 높을수록 정교한 타격가",
    "td_accuracy": "시도한 테이크다운(넘어뜨리기) 중 성공한 비율 — 높을수록 그래플링이 강함",
    "ctrl_min_per_fight": "경기당 상대를 그라운드에서 제압하고 있었던 평균 시간(분)",
    "sub_att_per_fight": "경기당 관절기 · 조르기 등 서브미션을 시도한 평균 횟수",
    "win_rate": "전체 경기 중 실제로 이긴 경기의 비율",
}


def render_radar_metric_guide():
    with st.expander("레이더 차트 지표가 무슨 뜻인지 보기"):
        for key in RADAR_KEYS:
            st.markdown(f"**{RADAR_LABELS[key]}** — {RADAR_METRIC_DESC[key]}")


@st.cache_data(show_spinner="🥊 선수별 스탯 계산하는 중...")
def build_fighter_metrics(fights, career):
    decided = fights[fights["result_type"] == "승패"]
    wins = decided.groupby("winner").size()
    losses = decided.groupby("loser").size()
    record = pd.DataFrame({"wins": wins, "losses": losses}).fillna(0)
    record["total"] = record["wins"] + record["losses"]
    record["win_rate"] = np.where(record["total"] > 0, record["wins"] / record["total"] * 100, np.nan)
    record.index.name = "FIGHTER"
    record = record.reset_index()

    metrics = career.merge(record[["FIGHTER", "wins", "losses", "win_rate"]], on="FIGHTER", how="left")
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
            bgcolor=CHART_SURFACE,
            radialaxis=dict(visible=True, range=[0, 100], gridcolor=CHART_GRID, linecolor=CHART_AXIS),
            angularaxis=dict(gridcolor=CHART_GRID, linecolor=CHART_AXIS),
        ),
        paper_bgcolor=CHART_SURFACE,
        font=dict(color=CHART_INK, family="system-ui, -apple-system, 'Segoe UI', sans-serif"),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        margin=dict(t=30, b=10, l=10, r=10),
    )
    return fig


# ------------------------------------------------------------
# 가상 대결 승부 예측기 — 실제 예측 모델이 아니라, 레이더 차트에 쓰는 6개 백분위 지표의
# 평균 차이를 로지스틱 함수로 눌러 "확률처럼" 보여주는 참고용 지표. 스타일 상성 · 부상 ·
# 컨디션 등은 전혀 반영하지 않으므로 재미로만 보라는 캡션을 항상 함께 표시한다.
# ------------------------------------------------------------
def predict_matchup(fighter_a, fighter_b, metrics):
    vals_a, n_a = radar_values(fighter_a, metrics)
    vals_b, n_b = radar_values(fighter_b, metrics)
    if vals_a is None or vals_b is None:
        return None
    # 결측 지표는 중간값(50)으로 대체해 특정 지표 하나가 극단적으로 결과를 흔들지 않게 함
    vals_a = [v if pd.notna(v) else 50 for v in vals_a]
    vals_b = [v if pd.notna(v) else 50 for v in vals_b]
    avg_a = sum(vals_a) / len(vals_a)
    avg_b = sum(vals_b) / len(vals_b)
    diff = avg_a - avg_b
    prob_a = 1 / (1 + np.exp(-0.05 * diff))
    return {
        "avg_a": avg_a, "avg_b": avg_b, "diff": diff,
        "prob_a": prob_a * 100, "prob_b": (1 - prob_a) * 100,
        "n_a": n_a, "n_b": n_b,
    }


# ------------------------------------------------------------
# 선수 얼굴 사진 (실시간 조회, 없으면 이니셜 아바타로 대체)
# 2,740명 전원의 사진을 직접 수급/저장하는 건 이번 마감 안에는 무리라,
# 공개 API를 그때그때 조회해서 있으면 보여주는 방식으로 구현.
# 1순위: 영어 위키백과 → 2순위: 한국어 위키백과 → 3순위: Wikidata 이미지(P18)
# (영어 위키백과 문서 자체에 사진이 없는 선수를 위한 보강 — 예: 최두호)
# ------------------------------------------------------------
WIKI_TITLE_OVERRIDES = {
    "Dooho Choi": "Choi Doo-ho",  # 데이터셋 표기 -> 영어 위키백과 정식 표기
}
# 영어 위키백과에 사진이 없는 선수를 위한 보강 소스 (필요한 선수만 등록)
PHOTO_FALLBACK_OVERRIDES = {
    "Dooho Choi": {"ko_title": "최두호", "wikidata_qid": "Q16233713"},
}
WIKI_HEADERS = {"User-Agent": "PlayLabAcademy-UFC-App/1.0 (educational project)"}


def _wiki_summary_thumbnail(lang, title):
    try:
        resp = requests.get(
            f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(title)}",
            headers=WIKI_HEADERS, timeout=3,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("type") == "disambiguation":
                return None
            return (data.get("thumbnail") or {}).get("source")
    except Exception:
        pass
    return None


def _wikidata_image(qid):
    try:
        resp = requests.get(
            f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json",
            headers=WIKI_HEADERS, timeout=3,
        )
        if resp.status_code == 200:
            entity = resp.json()["entities"][qid]
            p18 = entity.get("claims", {}).get("P18")
            if p18:
                filename = p18[0]["mainsnak"]["datavalue"]["value"]
                return f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(filename.replace(' ', '_'))}"
    except Exception:
        pass
    return None


@st.cache_data(show_spinner=False, ttl=60 * 60 * 24)
def get_fighter_photo_url(name):
    title = WIKI_TITLE_OVERRIDES.get(name, name)
    candidates = [title, f"{title} (fighter)", f"{title} (mixed martial artist)", f"{title} (martial artist)"]
    for candidate in candidates:
        thumb = _wiki_summary_thumbnail("en", candidate)
        if thumb:
            return thumb

    fallback = PHOTO_FALLBACK_OVERRIDES.get(name)
    if fallback:
        ko_title = fallback.get("ko_title")
        if ko_title:
            thumb = _wiki_summary_thumbnail("ko", ko_title)
            if thumb:
                return thumb
        qid = fallback.get("wikidata_qid")
        if qid:
            thumb = _wikidata_image(qid)
            if thumb:
                return thumb

    return None


LOCAL_PHOTO_DIR = "data/photos"


def _local_photo_data_uri(name):
    """data/photos/ 폴더에 <이름>.jpg(또는 png/jpeg/webp)를 직접 넣어두면 그 사진을 최우선으로 사용.
    위키백과에 사진이 없는 선수(예: 최두호)를 위해, 저작권 확인이 된 사진을 직접 넣을 수 있는 통로."""
    if not os.path.isdir(LOCAL_PHOTO_DIR):
        return None
    slug = name.lower().replace(" ", "_").replace("'", "").replace(".", "")
    for ext in ("jpg", "jpeg", "png", "webp"):
        path = os.path.join(LOCAL_PHOTO_DIR, f"{slug}.{ext}")
        if os.path.isfile(path):
            mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}[ext]
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            return f"data:{mime};base64,{b64}"
    return None


# GitHub 웹 UI로 바이너리 이미지 파일을 올리다가 확장자가 깨지는 문제가 반복돼서,
# 최두호 사진은 app.py 안에 base64 텍스트로 직접 박아넣음 (텍스트 파일 편집은 안정적으로 됨)
EMBEDDED_PHOTOS = {
    "Dooho Choi": "data:image/jpeg;base64,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",
}


def render_avatar(name, color, size=64):
    """1순위: data/photos/ 로컬 파일, 2순위: 위키백과 실시간 조회, 없으면 이니셜 아바타."""
    photo_url = EMBEDDED_PHOTOS.get(name) or _local_photo_data_uri(name) or get_fighter_photo_url(name)
    if photo_url:
        return (
            f'<img src="{photo_url}" style="width:{size}px;height:{size}px;'
            f"border-radius:50%;object-fit:cover;object-position:50% 15%;border:3px solid {color};"
            f'display:block;margin-bottom:6px;" />'
        )
    return avatar_html(name, color, size)


# ------------------------------------------------------------
# 스타일 자동 분류 — "감"이 아니라 데이터로 타격가형/그래플러형/올라운더형 구분
# 그래플링 지표(테이크다운·컨트롤타임·서브미션 시도)와 타격 지표(유효타 정확도·빈도)를
# 각각 전체 선수 대비 백분위로 평균 내서, 그 차이로 스타일을 판정
# ------------------------------------------------------------
STRIKE_KEYS = ["sig_str_accuracy", "sig_str_per_fight"]
GRAPPLE_KEYS = ["td_accuracy", "ctrl_min_per_fight", "sub_att_per_fight"]


def classify_style(name, metrics):
    if name not in metrics.index:
        return None
    row = metrics.loc[name]
    grapple_vals = [row.get(f"pct_{k}") for k in GRAPPLE_KEYS if pd.notna(row.get(f"pct_{k}"))]
    strike_vals = [row.get(f"pct_{k}") for k in STRIKE_KEYS if pd.notna(row.get(f"pct_{k}"))]
    if not grapple_vals or not strike_vals:
        return None
    g = sum(grapple_vals) / len(grapple_vals)
    s = sum(strike_vals) / len(strike_vals)
    diff = g - s
    if diff >= 15:
        label = "그래플러형"
    elif diff <= -15:
        label = "타격가형"
    else:
        label = "올라운더형"
    return {"label": label, "grapple_score": round(g, 1), "strike_score": round(s, 1)}


# ------------------------------------------------------------
# 닮은꼴 선수 추천 — 레이더 차트에 쓰는 6개 백분위 지표를 벡터로 놓고,
# 유클리드 거리가 가장 가까운 다른 선수를 찾아 "스타일이 비슷한 선수"로 추천
# ------------------------------------------------------------
def find_similar_fighters(name, metrics, top_n=3, min_fights=3):
    if name not in metrics.index:
        return []
    pct_cols = [f"pct_{k}" for k in RADAR_KEYS]
    row = metrics.loc[name]
    vec = np.array([row.get(c, np.nan) for c in pct_cols], dtype=float)
    if np.isnan(vec).any():
        return []

    pool = metrics[(metrics["fights_recorded"] >= min_fights) & (metrics.index != name)]
    pool_vals = pool[pct_cols].to_numpy(dtype=float)
    valid = ~np.isnan(pool_vals).any(axis=1)
    pool = pool[valid]
    pool_vals = pool_vals[valid]
    if len(pool) == 0:
        return []

    dists = np.sqrt(((pool_vals - vec) ** 2).sum(axis=1))
    order = np.argsort(dists)[:top_n]
    return [{"name": pool.index[i], "distance": float(dists[i])} for i in order]


def render_similar_fighters(name, metrics, top_n=3):
    similar = find_similar_fighters(name, metrics, top_n=top_n)
    if not similar:
        return
    st.markdown(f"**{name}와(과) 스타일이 가장 비슷한 선수**")
    st.caption("레이더 차트에 쓰인 6개 지표의 백분위 값을 벡터로 놓고, 거리가 가장 가까운 선수를 찾은 결과입니다.")
    sim_cols = st.columns(len(similar))
    for col, s in zip(sim_cols, similar):
        with col:
            st.markdown(render_avatar(s["name"], ACCENT_RED, size=56), unsafe_allow_html=True)
            st.caption(s["name"])
            twin_style = classify_style(s["name"], metrics)
            if twin_style:
                st.markdown(style_badge_html(twin_style["label"]), unsafe_allow_html=True)


# ------------------------------------------------------------
# 최근 폼 — 최근 5경기를 승/패 점으로 시각화 (지금 상승세인지 하락세인지 감을 잡기 위함)
# ------------------------------------------------------------
def recent_form(name, fights_df, n=5):
    wins = fights_df[(fights_df["winner"] == name) & (fights_df["result_type"] == "승패")][["DATE", "METHOD"]].copy()
    wins["result"] = "W"
    losses = fights_df[(fights_df["loser"] == name) & (fights_df["result_type"] == "승패")][["DATE", "METHOD"]].copy()
    losses["result"] = "L"
    combined = pd.concat([wins, losses]).dropna(subset=["DATE"]).sort_values("DATE", ascending=False).head(n)
    combined = combined.sort_values("DATE")
    return combined.to_dict("records")


def render_recent_form(name, fights_df, n=5):
    form = recent_form(name, fights_df, n=n)
    if not form:
        return
    win_color = TRIO_COLORS[2]
    loss_color = ACCENT_RED
    dots = ""
    for f in form:
        is_win = f["result"] == "W"
        color = win_color if is_win else loss_color
        label = "승" if is_win else "패"
        method = str(f.get("METHOD", "")).strip()
        title = f'{f["DATE"].date()} · {label} · {method}'
        dots += (
            f'<span title="{title}" style="display:inline-block;width:14px;height:14px;'
            f'border-radius:50%;background:{color};margin-right:5px;"></span>'
        )
    st.markdown(f'<div style="margin:4px 0;">{dots}</div>', unsafe_allow_html=True)
    st.caption("최근 5경기 (왼쪽=과거 → 오른쪽=최신, 초록 승 · 빨강 패)")


# ------------------------------------------------------------
# 리치-신장 비율 — "리치가 긴 선수가 실제로 유리한가?" (참고: Lucy Liu의 UFC 데이터 분석 글)
# HEIGHT는 "5' 11\"", REACH는 "71\"" 형식의 문자열이라 인치 단위 숫자로 파싱
# ------------------------------------------------------------
def _parse_height_inches(h):
    if not isinstance(h, str) or h.strip() in ("--", ""):
        return np.nan
    try:
        feet_part, inches_part = h.replace('"', "").split("'")
        return int(feet_part.strip()) * 12 + int(inches_part.strip())
    except Exception:
        return np.nan


def _parse_reach_inches(r):
    if not isinstance(r, str) or r.strip() in ("--", ""):
        return np.nan
    try:
        return float(r.replace('"', "").strip())
    except Exception:
        return np.nan


# ------------------------------------------------------------
# 커리어 흐름 — 코너 맥그리거처럼 전성기와 하락기가 있는 선수를 시계열로 보면
# 스탯 평균만으로는 안 보이는 "지금 상승세인지 하락세인지"가 드러남
# ------------------------------------------------------------
def career_timeline(name, fights_df, window=5):
    wins = fights_df[(fights_df["winner"] == name) & (fights_df["result_type"] == "승패")][["DATE"]].copy()
    wins["result"] = 1
    losses = fights_df[(fights_df["loser"] == name) & (fights_df["result_type"] == "승패")][["DATE"]].copy()
    losses["result"] = 0
    combined = pd.concat([wins, losses]).dropna(subset=["DATE"]).sort_values("DATE").reset_index(drop=True)
    if combined.empty:
        return None
    combined["match_no"] = range(1, len(combined) + 1)
    combined["rolling_win_rate"] = combined["result"].rolling(window=window, min_periods=1).mean() * 100
    return combined


def render_career_timeline(fighter_a, fighter_b, fights_df, window=5):
    st.caption(
        f"각 선수의 UFC 커리어를 경기 순서대로 놓고, 매 시점 직전 {window}경기 승률을 선으로 "
        "그렸습니다. 선이 올라가면 상승세, 내려가면 하락세라는 뜻입니다. 두 선수의 커리어 길이가 "
        "다르므로 x축은 날짜가 아니라 '커리어 내 몇 번째 경기인지'로 맞췄습니다."
    )
    frames = []
    for name in [fighter_a, fighter_b]:
        tl = career_timeline(name, fights_df, window=window)
        if tl is not None:
            tl = tl.copy()
            tl["선수"] = name
            frames.append(tl)
    if not frames:
        st.write("표시할 경기 기록이 없습니다.")
        return
    combined = pd.concat(frames)
    fig8 = px.line(
        combined, x="match_no", y="rolling_win_rate", color="선수", markers=True,
        color_discrete_map={fighter_a: FIGHTER_COLORS[0], fighter_b: FIGHTER_COLORS[1]},
        labels={"match_no": "경기 순번(커리어 내)", "rolling_win_rate": f"직전 {window}경기 승률(%)"},
    )
    fig8 = style_chart(fig8)
    st.plotly_chart(fig8, use_container_width=True)


@st.cache_data(show_spinner=False)
def build_reach_height_table(bio):
    df = bio[["FIGHTER", "HEIGHT", "REACH"]].copy()
    df["height_in"] = df["HEIGHT"].apply(_parse_height_inches)
    df["reach_in"] = df["REACH"].apply(_parse_reach_inches)
    df["reach_height_ratio"] = df["reach_in"] / df["height_in"]
    return df.set_index("FIGHTER")[["height_in", "reach_in", "reach_height_ratio"]]


# ------------------------------------------------------------
# 전체 선수 검색·랭킹 테이블 — 체급/스타일/전적으로 필터링해 전체 선수를 탐색할 수 있도록
# 체급은 각 선수가 가장 많이 뛴 체급(최빈값)으로, 스타일은 classify_style과 같은 기준을
# 벡터 연산으로 한 번에 계산해 붙인다.
# ------------------------------------------------------------
@st.cache_data(show_spinner="🔍 전체 선수 랭킹 정리하는 중...")
def build_roster_table(fights, metrics):
    div_source = pd.concat([
        fights[["fighter_1", "weight_division"]].rename(columns={"fighter_1": "FIGHTER"}),
        fights[["fighter_2", "weight_division"]].rename(columns={"fighter_2": "FIGHTER"}),
    ])
    div_source = div_source[div_source["weight_division"].notna() & (div_source["weight_division"] != "기타")]
    main_division = div_source.groupby("FIGHTER")["weight_division"].agg(lambda s: s.value_counts().idxmax())

    roster = metrics.reset_index()
    roster["주 체급"] = roster["FIGHTER"].map(main_division).fillna("정보없음")

    grapple_avg = roster[[f"pct_{k}" for k in GRAPPLE_KEYS]].mean(axis=1, skipna=True)
    strike_avg = roster[[f"pct_{k}" for k in STRIKE_KEYS]].mean(axis=1, skipna=True)
    style_diff = grapple_avg - strike_avg
    roster["스타일"] = np.select(
        [style_diff >= 15, style_diff <= -15],
        ["그래플러형", "타격가형"],
        default="올라운더형",
    )
    roster.loc[grapple_avg.isna() | strike_avg.isna(), "스타일"] = "정보부족"

    roster["wins"] = roster["wins"].fillna(0).astype(int)
    roster["losses"] = roster["losses"].fillna(0).astype(int)
    roster["win_rate"] = roster["win_rate"].round(1)
    return roster


# ------------------------------------------------------------
# 데이터 로드
# ------------------------------------------------------------
@st.cache_data(show_spinner="🥊 UFC 전적 데이터 불러오는 중...")
def load_data():
    fights = pd.read_csv("data/ufc_fights.csv")
    fights["DATE"] = pd.to_datetime(fights["DATE"], errors="coerce")

    bio = pd.read_csv("data/ufc_fighter_bio.csv")
    career = pd.read_csv("data/ufc_fighter_career_stats.csv")

    return fights, bio, career


fights, bio, career = load_data()
all_fighters = sorted(set(fights["fighter_1"]).union(set(fights["fighter_2"])))
metrics = build_fighter_metrics(fights, career)
reach_height = build_reach_height_table(bio)

KOREAN_FIGHTERS = [
    {"name": "Dong Hyun Kim", "kor": "김동현", "nickname": "스턴건"},
    {"name": "Chan Sung Jung", "kor": "정찬성", "nickname": "코리안 좀비"},
    {"name": "Dooho Choi", "kor": "최두호", "nickname": "코리안 슈퍼보이"},
]

# ------------------------------------------------------------
# 사이드바 내비게이션
# (소개 페이지의 미리보기 카드에서 버튼으로 바로 이동할 수 있도록 session_state로 관리)
# ------------------------------------------------------------
NAV_OPTIONS = ["🏠 소개", "🥊 선수 비교", "📊 체급별 트렌드", "🔍 전체 선수", "🇰🇷 한국 파이터"]
if "nav_page" not in st.session_state:
    st.session_state.nav_page = NAV_OPTIONS[0]

st.sidebar.markdown(
    f"""
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:18px;">
        <div style="width:34px;height:34px;border-radius:9px;background:{ACCENT_RED};
                    display:flex;align-items:center;justify-content:center;font-size:1.1rem;">🥊</div>
        <div style="line-height:1.2;">
            <div style="font-weight:800;font-size:0.95rem;color:#ffffff;">UFC 분석기</div>
            <div style="font-size:0.7rem;color:#8a8a86;letter-spacing:0.04em;">DATA-DRIVEN</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

page = st.sidebar.radio("화면 선택", NAV_OPTIONS, key="nav_page")


def _set_nav_page(target_page):
    # 버튼의 on_click 콜백 안에서만 session_state를 바꿀 수 있음
    # (라디오 위젯이 이미 그려진 뒤 스크립트 본문에서 직접 바꾸면 StreamlitAPIException 발생)
    st.session_state.nav_page = target_page

st.sidebar.markdown("---")
st.sidebar.caption(
    "데이터 출처: ufcstats.com (Greco1899/scrape_ufc_stats 매일 자동 수집)\n\n"
    f"데이터 기간: {fights['DATE'].min().date()} ~ {fights['DATE'].max().date()}"
)

# ==============================================================
# 화면 1. 소개
# ==============================================================
if page == "🏠 소개":
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, #2a0a0b 0%, {CHART_SURFACE} 55%, #0d0d0d 100%);
            border: 1px solid rgba(224,57,62,0.35);
            border-radius: 18px;
            padding: 40px 36px;
            margin-bottom: 26px;
        ">
            <div style="color:{ACCENT_RED};font-weight:800;letter-spacing:0.14em;
                        text-transform:uppercase;font-size:0.78rem;margin-bottom:10px;">
                DATA-DRIVEN FIGHT ANALYSIS
            </div>
            <div style="font-size:2.3rem;font-weight:800;color:#ffffff;line-height:1.2;">
                🥊 UFC 선수 비교 분석기
            </div>
            <div style="color:#c3c2b7;font-size:1rem;margin-top:14px;max-width:700px;line-height:1.6;">
                "저 선수 진짜 세냐", "이번에 붙으면 누가 이길까" — 하이라이트 영상 몇 개가 아니라
                <strong style="color:#ffffff;">경기당 유효타 · 테이크다운 · 컨트롤 타임 기록</strong>으로
                답을 찾습니다.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("전체 경기 수", f"{len(fights):,}경기")
    col2.metric("등장 선수 수", f"{len(all_fighters):,}명")
    col3.metric("데이터 기간", f"{int(fights['year'].min())}~{int(fights['year'].max())}")

    section_header("이 사이트로 할 수 있는 것")
    preview_cards = [
        {
            "target": "🥊 선수 비교",
            "title": "선수 비교",
            "desc": "두 선수의 전적 · 스탯을 나란히 놓고, 레이더 차트로 스타일 차이를 한눈에 봅니다.",
            "color": FIGHTER_COLORS[0],
        },
        {
            "target": "📊 체급별 트렌드",
            "title": "체급별 트렌드",
            "desc": "관심 체급이 최근 몇 년 사이 타격 중심으로 변했는지, 그래플링 중심으로 변했는지 추적합니다.",
            "color": FIGHTER_COLORS[1],
        },
        {
            "target": "🇰🇷 한국 파이터",
            "title": "한국 파이터",
            "desc": "김동현 · 정찬성 · 최두호, 세 선수의 스타일을 같은 레이더 위에 겹쳐서 비교합니다.",
            "color": TRIO_COLORS[2],
        },
    ]
    preview_cols = st.columns(3)
    for col, card in zip(preview_cols, preview_cards):
        with col:
            with st.container(border=True):
                st.markdown(
                    f'<div style="width:36px;height:6px;border-radius:999px;'
                    f'background:{card["color"]};margin-bottom:10px;"></div>',
                    unsafe_allow_html=True,
                )
                st.markdown(f"**{card['title']}**")
                st.caption(card["desc"])
                st.button(
                    "바로가기",
                    key=f"goto_{card['target']}",
                    on_click=_set_nav_page,
                    args=(card["target"],),
                )

    if "Islam Makhachev" in metrics.index and "Conor McGregor" in metrics.index:
        preview_vals_a, _ = radar_values("Islam Makhachev", metrics)
        preview_vals_b, _ = radar_values("Conor McGregor", metrics)
        if preview_vals_a is not None and preview_vals_b is not None:
            section_header("미리보기 — 스타일이 정반대인 두 선수를 겹쳐보면")
            with st.container(border=True):
                st.plotly_chart(
                    make_radar_chart([
                        ("Islam Makhachev", preview_vals_a, FIGHTER_COLORS[0]),
                        ("Conor McGregor", preview_vals_b, FIGHTER_COLORS[1]),
                    ]),
                    use_container_width=True,
                )
                st.caption(
                    "그래플러형 마카체프와 타격가형 맥그리거를 겹쳐보면 레이더 모양 자체가 다릅니다 — "
                    "'선수 비교' 화면에서 원하는 두 선수로 직접 그려볼 수 있습니다."
                )

    section_header("전체 데이터 한눈에 보기")
    with st.container(border=True):
        method_counts = fights[fights["result_type"] == "승패"]["method_simple"].value_counts().reset_index()
        method_counts.columns = ["방식", "횟수"]
        fig = px.bar(method_counts, x="방식", y="횟수", color="방식", color_discrete_map=METHOD_COLORS)
        fig = style_chart(fig)
        st.plotly_chart(fig, use_container_width=True)

# ==============================================================
# 화면 2. 선수 비교 (핵심 기능)
# ==============================================================
elif page == "🥊 선수 비교":
    st.title("🥊 선수 비교")
    st.caption("두 선수를 골라서 전적, 스타일, 맞대결 기록을 비교합니다.")

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

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["전적 · 스탯", "스타일 레이더", "맞대결 · 하이라이트", "커리어 흐름", "가상 대결 예측"]
    )

    with tab1:
        col1, col2 = st.columns(2)
        for col, s, avatar_color in [(col1, a, FIGHTER_COLORS[0]), (col2, b, FIGHTER_COLORS[1])]:
            with col:
                with st.container(border=True):
                    st.markdown(render_avatar(s["name"], avatar_color, size=72), unsafe_allow_html=True)
                    st.subheader(s["name"])

                    style = classify_style(s["name"], metrics)
                    if style:
                        st.markdown(style_badge_html(style["label"]), unsafe_allow_html=True)
                        st.caption(f"그래플링 지수 {style['grapple_score']} · 타격 지수 {style['strike_score']} (전체 선수 백분위 평균)")

                    st.metric("전적 (승-패)", f"{s['wins']}승 {s['losses']}패")
                    st.metric("승률", f"{s['win_rate']:.1f}%")
                    render_recent_form(s["name"], fights)

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

        st.markdown("##### 승리 방식 비교 (KO/TKO · Submission · Decision)")
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

        career_a = career[career["FIGHTER"] == fighter_a]
        career_b = career[career["FIGHTER"] == fighter_b]

        def _stat(df, col):
            if df.empty or pd.isna(df.iloc[0].get(col)):
                return None
            return df.iloc[0][col]

        compare_stats = pd.DataFrame({
            "지표": ["승", "패", "승률(%)", "경기당 유효타", "유효타 정확도(%)", "테이크다운 정확도(%)", "컨트롤타임(분/경기)"],
            fighter_a: [
                a["wins"], a["losses"], round(a["win_rate"], 1),
                _stat(career_a, "sig_str_per_fight"), _stat(career_a, "sig_str_accuracy"),
                _stat(career_a, "td_accuracy"), _stat(career_a, "ctrl_min_per_fight"),
            ],
            fighter_b: [
                b["wins"], b["losses"], round(b["win_rate"], 1),
                _stat(career_b, "sig_str_per_fight"), _stat(career_b, "sig_str_accuracy"),
                _stat(career_b, "td_accuracy"), _stat(career_b, "ctrl_min_per_fight"),
            ],
        })
        csv_bytes = compare_stats.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            f"'{fighter_a} vs {fighter_b}' 비교 데이터 CSV 다운로드",
            data=csv_bytes,
            file_name=f"{fighter_a}_vs_{fighter_b}_compare.csv",
            mime="text/csv",
        )

    with tab2:
        st.caption(
            "경기당 유효타 · 정확도 · 테이크다운 · 컨트롤타임 · 서브미션 시도 · 승률을 "
            "**전체 선수 대비 백분위**로 환산해 겹쳐 그렸습니다. 바깥쪽으로 뻗을수록 "
            "그 항목에서 상위권이라는 뜻이라, 그래플러형(테이크다운·컨트롤타임 우세)과 "
            "타격가형(유효타 정확도 우세)의 모양 차이가 한눈에 드러납니다. 위 '전적 · 스탯' 탭의 "
            "**그래플링 지수 / 타격 지수** 배지는 이 레이더 값을 바탕으로 자동 계산됩니다."
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
                st.caption(f"참고: {names} 선수는 기록된 경기 수가 적어(3경기 미만) 참고용으로만 봐주세요.")

            st.markdown("---")
            twin_col1, twin_col2 = st.columns(2)
            with twin_col1:
                render_similar_fighters(fighter_a, metrics)
            with twin_col2:
                render_similar_fighters(fighter_b, metrics)

            render_radar_metric_guide()

    with tab3:
        st.markdown("##### 매치업 하이라이트")
        yt_query = quote(f"{fighter_a} vs {fighter_b} highlights")
        st.markdown(
            f"UFC 기록 데이터만으로는 '보는 재미'가 부족하니, 실제 경기 영상도 바로 찾아볼 수 있게 "
            f"연결했습니다 → [YouTube에서 '{fighter_a} vs {fighter_b}' 하이라이트 검색하기]"
            f"(https://www.youtube.com/results?search_query={yt_query})"
        )

        st.markdown("##### 맞대결 기록")
        h2h = fights[
            ((fights["fighter_1"] == fighter_a) & (fights["fighter_2"] == fighter_b)) |
            ((fights["fighter_1"] == fighter_b) & (fights["fighter_2"] == fighter_a))
        ]
        if h2h.empty:
            st.write("두 선수는 UFC에서 맞붙은 기록이 없습니다.")
        else:
            st.dataframe(h2h[["DATE", "EVENT", "winner", "loser", "METHOD", "weightclass"]])

    with tab4:
        render_career_timeline(fighter_a, fighter_b, fights)

    with tab5:
        st.caption(
            "실제 승부 예측 모델이 아니라, '스타일 레이더' 탭에 쓰인 6개 지표의 전체 선수 대비 "
            "백분위 평균을 단순 비교해 만든 참고용 지표입니다. 스타일 상성 · 부상 · 그날의 컨디션 "
            "같은 요소는 전혀 반영하지 않으니 재미로만 봐주세요."
        )
        pred = predict_matchup(fighter_a, fighter_b, metrics)
        if pred is None:
            st.write("두 선수 중 상세 경기 통계가 없는 선수가 있어 예측할 수 없습니다.")
        else:
            prob_a_pct, prob_b_pct = pred["prob_a"], pred["prob_b"]
            st.markdown(
                f'<div style="display:flex;height:34px;border-radius:8px;overflow:hidden;margin:14px 0 10px 0;">'
                f'<div style="width:{prob_a_pct:.1f}%;background:{FIGHTER_COLORS[0]};display:flex;'
                f'align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:0.85rem;">'
                f'{prob_a_pct:.0f}%</div>'
                f'<div style="width:{prob_b_pct:.1f}%;background:{FIGHTER_COLORS[1]};display:flex;'
                f'align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:0.85rem;">'
                f'{prob_b_pct:.0f}%</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            pc1, pc2 = st.columns(2)
            pc1.metric(fighter_a, f"{prob_a_pct:.0f}%")
            pc2.metric(fighter_b, f"{prob_b_pct:.0f}%")
            st.caption(
                f"{fighter_a}의 6개 지표 백분위 평균은 {pred['avg_a']:.1f}, {fighter_b}는 "
                f"{pred['avg_b']:.1f}로 차이는 {abs(pred['diff']):.1f}점입니다. 이 차이를 완만한 곡선"
                "(로지스틱 함수)으로 눌러서 확률처럼 보여준 것일 뿐, 통계적으로 검증된 승부 예측 "
                "모델이 아닙니다."
            )
            low_sample = [n for n in [(fighter_a, pred["n_a"]), (fighter_b, pred["n_b"])] if n[1] < 3]
            if low_sample:
                names = ", ".join(n[0] for n in low_sample)
                st.caption(f"참고: {names} 선수는 기록된 경기 수가 적어(3경기 미만) 정확도가 낮을 수 있습니다.")

    st.caption("선수 사진 출처: Wikipedia (해당 선수 문서가 없거나 사진이 없으면 이니셜 아바타로 대체됩니다.)")

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

    top_winners = filtered["winner"].value_counts().head(5).reset_index()
    top_winners.columns = ["선수", "승수"]

    if not top_winners.empty:
        section_header(f"{weight_class} 대표 선수")
        st.caption(f"{weight_class} 체급에서 가장 많은 승수를 기록한 선수들입니다. 얼굴과 스타일을 함께 확인해보세요.")
        top3 = top_winners.head(3)
        rep_cols = st.columns(len(top3))
        for col, (_, row) in zip(rep_cols, top3.iterrows()):
            fighter_name = row["선수"]
            with col:
                with st.container(border=True):
                    st.markdown(render_avatar(fighter_name, FIGHTER_COLORS[0], size=80), unsafe_allow_html=True)
                    st.markdown(f"**{fighter_name}**")
                    style = classify_style(fighter_name, metrics)
                    if style:
                        st.markdown(style_badge_html(style["label"]), unsafe_allow_html=True)
                    st.caption(f"{weight_class} 체급 {int(row['승수'])}승")

    section_header(f"{weight_class} 승리 방식 분포")
    method_counts = filtered["method_simple"].value_counts().reset_index()
    method_counts.columns = ["방식", "횟수"]
    fig3 = px.pie(method_counts, names="방식", values="횟수", color="방식", color_discrete_map=METHOD_COLORS)
    fig3 = style_chart(fig3)
    st.plotly_chart(fig3, use_container_width=True)

    section_header(f"{weight_class} 연도별 피니시 비율 변화")
    filtered = filtered.copy()
    filtered["is_finish"] = filtered["method_simple"].isin(["KO/TKO", "Submission"])
    yearly = filtered.groupby(filtered["year"].astype(int)).agg(
        경기수=("method_simple", "count"),
        피니시비율=("is_finish", "mean"),
    ).reset_index()
    yearly["피니시비율"] = (yearly["피니시비율"] * 100).round(1)

    fig4 = px.line(yearly, x="year", y="피니시비율", markers=True,
                    labels={"year": "연도", "피니시비율": "피니시(KO·서브미션) 비율(%)"},
                    color_discrete_sequence=[FIGHTER_COLORS[0]])
    fig4 = style_chart(fig4)
    st.plotly_chart(fig4, use_container_width=True)
    st.caption("판정까지 가지 않고 KO나 서브미션으로 끝난 경기 비율이 시대별로 어떻게 변했는지 보여줍니다.")

    section_header(f"{weight_class} 연도별 승리 방식 비중 변화 (타격 vs 그래플링)")
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

    section_header(f"{weight_class} 체급 내 최다승 TOP 5")
    if top_winners.empty:
        st.write("표시할 데이터가 없습니다.")
    else:
        fig5 = px.bar(
            top_winners.sort_values("승수"), x="승수", y="선수", orientation="h",
            color_discrete_sequence=[FIGHTER_COLORS[0]],
        )
        fig5 = style_chart(fig5)
        st.plotly_chart(fig5, use_container_width=True)
        st.caption(f"{weight_class} 체급 경기에서 UFC 데이터 기준 가장 많은 승수를 기록한 선수 5명입니다.")

    section_header(f"{weight_class} 리치-신장 비율과 승률의 관계")
    st.caption(
        "리치(팔길이)가 신장 대비 긴 선수가 실제로 유리한지 살펴봅니다. 비율이 1.0보다 크면 "
        "신장보다 리치가 긴 선수, 작으면 짧은 선수입니다. (참고: Lucy Liu의 UFC 데이터 분석 글)"
    )
    division_all = fights[fights["weight_division"] == weight_class]
    division_fighters = set(division_all["fighter_1"]).union(division_all["fighter_2"])
    rh_scatter = reach_height[reach_height.index.isin(division_fighters)].dropna(subset=["reach_height_ratio"])
    rh_scatter = rh_scatter.join(metrics[["win_rate", "fights_recorded"]], how="inner")
    rh_scatter = rh_scatter[rh_scatter["fights_recorded"] >= 3].dropna(subset=["win_rate"])
    rh_scatter = rh_scatter.reset_index().rename(columns={"FIGHTER": "선수"})

    if len(rh_scatter) < 5:
        st.write("이 체급은 리치·신장 데이터가 충분하지 않아 분석을 표시할 수 없습니다.")
    else:
        fig7 = px.scatter(
            rh_scatter, x="reach_height_ratio", y="win_rate", hover_name="선수",
            labels={"reach_height_ratio": "리치/신장 비율", "win_rate": "승률(%)"},
            color_discrete_sequence=[FIGHTER_COLORS[0]],
        )
        fig7.add_vline(x=1.0, line_dash="dash", line_color=CHART_AXIS)
        fig7 = style_chart(fig7)
        st.plotly_chart(fig7, use_container_width=True)
        st.caption(
            "점선은 리치와 신장이 같은 지점(비율 1.0)입니다. 점이 오른쪽으로 갈수록 리치가 긴 "
            "선수, 위로 갈수록 승률이 높은 선수입니다. 뚜렷한 우상향 경향이 보이지 않는다면, 이 "
            "체급에서는 리치보다 다른 요인(기술 · 체력 등)이 승패에 더 크게 작용한다고 읽을 수 "
            "있습니다. 상관관계일 뿐 인과관계는 아니라는 점에 유의하세요."
        )

# ==============================================================
# 화면 4. 전체 선수 검색·랭킹
# ==============================================================
elif page == "🔍 전체 선수":
    st.title("🔍 전체 선수 검색 · 랭킹")
    st.caption("데이터에 기록된 전체 선수를 이름 · 체급 · 스타일 · 최소 경기 수 조건으로 검색하고 승률순으로 정렬해서 살펴볼 수 있습니다.")

    roster = build_roster_table(fights, metrics)

    f1, f2, f3 = st.columns([2, 1, 1])
    search = f1.text_input("선수 이름 검색", "", placeholder="예: McGregor")
    division_options = ["전체"] + sorted(roster.loc[roster["주 체급"] != "정보없음", "주 체급"].unique().tolist())
    division_filter = f2.selectbox("체급", division_options)
    style_options = ["전체", "그래플러형", "타격가형", "올라운더형"]
    style_filter = f3.selectbox("스타일", style_options)

    min_fights = st.slider("최소 기록 경기 수", 0, 20, 3)

    view = roster[roster["fights_recorded"] >= min_fights]
    if search:
        view = view[view["FIGHTER"].str.contains(search, case=False, na=False)]
    if division_filter != "전체":
        view = view[view["주 체급"] == division_filter]
    if style_filter != "전체":
        view = view[view["스타일"] == style_filter]
    view = view.sort_values("win_rate", ascending=False)

    st.caption(f"조건에 맞는 선수 {len(view)}명")

    display_cols = view[[
        "FIGHTER", "주 체급", "스타일", "wins", "losses", "win_rate",
        "sig_str_accuracy", "td_accuracy", "fights_recorded",
    ]].rename(columns={
        "FIGHTER": "선수", "wins": "승", "losses": "패", "win_rate": "승률(%)",
        "sig_str_accuracy": "유효타 정확도(%)", "td_accuracy": "테이크다운 정확도(%)",
        "fights_recorded": "기록된 경기 수",
    })
    st.dataframe(display_cols, use_container_width=True, hide_index=True)

    csv_bytes = display_cols.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "현재 조건의 선수 목록 CSV 다운로드",
        data=csv_bytes,
        file_name="ufc_fighters_filtered.csv",
        mime="text/csv",
    )

# ==============================================================
# 화면 5. 한국 파이터
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
            with st.container(border=True):
                st.markdown(render_avatar(name, color, size=92), unsafe_allow_html=True)
                st.subheader(fighter["kor"])
                st.caption(f"{name} · '{fighter['nickname']}'")

                style = classify_style(name, metrics)
                if style:
                    st.markdown(style_badge_html(style["label"]), unsafe_allow_html=True)
                    st.caption(f"그래플링 지수 {style['grapple_score']} · 타격 지수 {style['strike_score']}")

                wins = (fights["winner"] == name).sum()
                losses = (fights["loser"] == name).sum()
                st.metric("전적 (승-패)", f"{wins}승 {losses}패")
                render_recent_form(name, fights)

                career_row = career[career["FIGHTER"] == name]
                if not career_row.empty:
                    cr = career_row.iloc[0]
                    m1, m2 = st.columns(2)
                    m1.metric("유효타 정확도", f"{cr['sig_str_accuracy']:.0f}%" if pd.notna(cr["sig_str_accuracy"]) else "-")
                    m2.metric("테이크다운 정확도", f"{cr['td_accuracy']:.0f}%" if pd.notna(cr["td_accuracy"]) else "-")

        vals, n = radar_values(name, metrics)
        if vals is not None:
            radar_entries.append((fighter["kor"], vals, color))

    section_header("세 선수 스타일 레이더 비교")
    if len(radar_entries) >= 2:
        st.plotly_chart(make_radar_chart(radar_entries), use_container_width=True)
        st.caption(
            "그래플러형 / 타격가형 / 올라운더형 표시는 위 카드의 '그래플링 지수'와 "
            "'타격 지수'(테이크다운·컨트롤타임·서브미션 시도 vs 유효타 정확도·빈도를 각각 전체 "
            "선수 대비 백분위로 평균 낸 값)를 비교해 자동으로 계산한 것입니다. 세 선수의 레이더 "
            "모양이 서로 다르게 나온다면, 실제로 다른 스타일로 UFC에서 활동했다는 뜻입니다."
        )
        render_radar_metric_guide()
    else:
        st.write("레이더 차트를 그릴 만큼 상세 통계가 있는 선수가 부족합니다.")

    section_header("세계 무대에서 닮은꼴 선수 찾기")
    st.caption("한국 파이터 세 명 각각과 스타일이 가장 비슷한 UFC 소속 선수를 데이터로 찾아봤습니다.")
    twin_cols = st.columns(3)
    for col, fighter in zip(twin_cols, KOREAN_FIGHTERS):
        with col:
            render_similar_fighters(fighter["name"], metrics, top_n=2)

    st.caption("선수 사진 출처: Wikipedia")

    st.info(
        "이 페이지는 '한국 팬들이 바로 알아볼 수 있는 선수부터 보여주자'는 피드백을 반영해 "
        "추가했습니다. 더 많은 한국 파이터를 추가하려면 위 코드의 KOREAN_FIGHTERS 리스트에 "
        "선수 이름만 추가하면 됩니다."
    )
