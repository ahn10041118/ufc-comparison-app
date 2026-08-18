"""
UFC 데이터 전처리 스크립트
원본: Greco1899/scrape_ufc_stats (ufcstats.com 매일 자동 스크래핑, 2026년 최신 데이터 포함)
출력: app.py가 바로 읽을 수 있는 가공된 CSV 3종
"""
import pandas as pd
import numpy as np
import re

RAW = "raw"  # 원본 csv들이 들어있는 폴더
OUT = "data"  # 가공된 csv를 저장할 폴더

# ------------------------------------------------------------
# 1. 이벤트 + 경기 결과
# ------------------------------------------------------------
events = pd.read_csv(f"{RAW}/ufc_event_details.csv")
events["EVENT"] = events["EVENT"].str.strip()
events["DATE"] = pd.to_datetime(events["DATE"], errors="coerce")

results = pd.read_csv(f"{RAW}/ufc_fight_results.csv")
results["EVENT"] = results["EVENT"].str.strip()
results["BOUT"] = results["BOUT"].str.strip()

# BOUT: "Fighter A vs. Fighter B" -> 분리
split_names = results["BOUT"].str.split(" vs\\. ", n=1, expand=True)
results["fighter_1"] = split_names[0].str.strip()
results["fighter_2"] = split_names[1].str.strip()

# OUTCOME: "W/L" -> fighter_1 승, "L/W" -> fighter_2 승, "D/D" 무승부, "NC/NC" 무효
def parse_outcome(row):
    o = row["OUTCOME"]
    if o == "W/L":
        return row["fighter_1"], row["fighter_2"]
    elif o == "L/W":
        return row["fighter_2"], row["fighter_1"]
    else:
        return None, None  # 무승부/노콘테스트

winners, losers = zip(*results.apply(parse_outcome, axis=1))
results["winner"] = winners
results["loser"] = losers
results["result_type"] = results["OUTCOME"].map({
    "W/L": "승패", "L/W": "승패", "D/D": "무승부", "NC/NC": "노콘테스트"
})

# METHOD 단순화
def simplify_method(m):
    if pd.isna(m):
        return "기타"
    m = m.strip()
    if m.startswith("KO/TKO") or m.startswith("TKO"):
        return "KO/TKO"
    if m.startswith("Submission"):
        return "Submission"
    if m.startswith("Decision"):
        return "Decision"
    if m == "DQ":
        return "DQ"
    return "기타"

results["method_simple"] = results["METHOD"].apply(simplify_method)

# 이벤트 날짜 붙이기
fights = results.merge(events[["EVENT", "DATE", "LOCATION"]], on="EVENT", how="left")
fights["year"] = fights["DATE"].dt.year

fights = fights.rename(columns={"WEIGHTCLASS": "weightclass"})

# weightclass 원문은 "UFC Lightweight Title Bout", "Lightweight Bout" 등으로 파편화되어 있어
# 체급 선택 UI에서 쓸 수 있게 핵심 체급명(weight_division)으로 정규화
DIVISIONS = [
    "Women's Strawweight", "Women's Flyweight", "Women's Bantamweight", "Women's Featherweight",
    "Light Heavyweight", "Flyweight", "Bantamweight", "Featherweight", "Lightweight",
    "Welterweight", "Middleweight", "Heavyweight", "Catch Weight", "Open Weight",
]


def normalize_division(wc):
    if pd.isna(wc):
        return "기타"
    for d in DIVISIONS:
        if d in wc:
            return d
    return "기타"


fights["weight_division"] = fights["weightclass"].apply(normalize_division)

fights_out = fights[[
    "EVENT", "DATE", "year", "fighter_1", "fighter_2", "winner", "loser",
    "result_type", "weightclass", "weight_division", "METHOD", "method_simple", "ROUND", "TIME", "LOCATION"
]]

fights_out.to_csv(f"{OUT}/ufc_fights.csv", index=False)
print("ufc_fights.csv 저장:", fights_out.shape)
print("데이터 기간:", fights_out["DATE"].min(), "~", fights_out["DATE"].max())

# ------------------------------------------------------------
# 2. 선수 신체 정보 (Tale of the Tape)
# ------------------------------------------------------------
tott = pd.read_csv(f"{RAW}/ufc_fighter_tott.csv")
tott["FIGHTER"] = tott["FIGHTER"].str.strip()
tott = tott.drop_duplicates(subset="FIGHTER")
tott.to_csv(f"{OUT}/ufc_fighter_bio.csv", index=False)
print("ufc_fighter_bio.csv 저장:", tott.shape)

# ------------------------------------------------------------
# 3. 경기 통계(라운드별) -> 선수별 커리어 합산 스탯
# ------------------------------------------------------------
stats = pd.read_csv(f"{RAW}/ufc_fight_stats.csv")
stats["EVENT"] = stats["EVENT"].str.strip()
stats["BOUT"] = stats["BOUT"].str.strip()
stats["FIGHTER"] = stats["FIGHTER"].str.strip()
stats = stats.dropna(subset=["FIGHTER"])


def split_of(series):
    """'3 of 5' -> (landed=3, attempted=5)"""
    parts = series.astype(str).str.extract(r"(\d+)\s+of\s+(\d+)")
    landed = pd.to_numeric(parts[0], errors="coerce")
    attempted = pd.to_numeric(parts[1], errors="coerce")
    return landed, attempted


stats["sig_landed"], stats["sig_attempted"] = split_of(stats["SIG.STR."])
stats["td_landed"], stats["td_attempted"] = split_of(stats["TD"])
stats["KD"] = pd.to_numeric(stats["KD"], errors="coerce")
stats["SUB.ATT"] = pd.to_numeric(stats["SUB.ATT"], errors="coerce")


def ctrl_to_seconds(t):
    if pd.isna(t) or ":" not in str(t):
        return np.nan
    m, s = str(t).split(":")
    try:
        return int(m) * 60 + int(s)
    except ValueError:
        return np.nan


stats["ctrl_seconds"] = stats["CTRL"].apply(ctrl_to_seconds)

# 라운드 단위 -> 한 경기(EVENT+BOUT+FIGHTER) 단위로 먼저 합산
per_fight = stats.groupby(["EVENT", "BOUT", "FIGHTER"]).agg(
    KD=("KD", "sum"),
    sig_landed=("sig_landed", "sum"),
    sig_attempted=("sig_attempted", "sum"),
    td_landed=("td_landed", "sum"),
    td_attempted=("td_attempted", "sum"),
    sub_att=("SUB.ATT", "sum"),
    ctrl_seconds=("ctrl_seconds", "sum"),
).reset_index()

# 선수별 커리어 합산/평균
career = per_fight.groupby("FIGHTER").agg(
    fights_recorded=("BOUT", "count"),
    total_kd=("KD", "sum"),
    total_sig_landed=("sig_landed", "sum"),
    total_sig_attempted=("sig_attempted", "sum"),
    total_td_landed=("td_landed", "sum"),
    total_td_attempted=("td_attempted", "sum"),
    total_sub_att=("sub_att", "sum"),
    total_ctrl_seconds=("ctrl_seconds", "sum"),
).reset_index()

career["sig_str_per_fight"] = (career["total_sig_landed"] / career["fights_recorded"]).round(1)
career["sig_str_accuracy"] = (
    career["total_sig_landed"] / career["total_sig_attempted"].replace(0, np.nan) * 100
).round(1)
career["td_accuracy"] = (
    career["total_td_landed"] / career["total_td_attempted"].replace(0, np.nan) * 100
).round(1)
career["ctrl_min_per_fight"] = (
    career["total_ctrl_seconds"] / career["fights_recorded"] / 60
).round(1)

career.to_csv(f"{OUT}/ufc_fighter_career_stats.csv", index=False)
print("ufc_fighter_career_stats.csv 저장:", career.shape)
print(career.sort_values("fights_recorded", ascending=False).head(5))
