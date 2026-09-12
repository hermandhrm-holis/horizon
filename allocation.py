"""Read-only, auditable placement suggestions for the HORIZON TKA cohort."""

import math

import numpy as np
import pandas as pd

SUBJECTS = ("Matematika", "Bahasa Indonesia", "Bahasa Inggris")
GROUPS = ("Fu", "Ch", "Am", "Pi", "On")


def student_features(data: pd.DataFrame) -> pd.DataFrame:
    """Use the recent three scores per subject; missing subjects never become zero."""
    records = []
    for sid, student in data.groupby("student_id", sort=True):
        scores, trends, coverage = [], [], 0
        by_subject = {}
        for subject in SUBJECTS:
            s = student[student["mapel"].str.casefold() == subject.casefold()].sort_values("assessment_order")
            if s.empty:
                continue
            recent = s["score"].tail(3).to_numpy(float)
            scores.append(float(np.mean(recent)))
            trends.append(float(recent[-1] - recent[0]) / max(len(recent) - 1, 1))
            coverage += min(len(s), 3)
            by_subject[subject] = round(float(np.mean(recent)), 1)
        first = student.iloc[0]
        complete = len(scores) == 3 and coverage >= 6
        avg = float(np.mean(scores)) if scores else np.nan
        trend = float(np.mean(trends)) if trends else 0.0
        records.append({
            "student_id": sid, "nama": first["nama"], "kelas_asal": first["kelas"],
            "status_tka": first["status_tka"], "rata_terkini": avg,
            "tren": trend, "mapel_tersedia": len(scores), "data_memadai": complete,
            "skor_penempatan": float(np.clip(avg + np.clip(trend, -5, 5) * 0.4, 0, 100)) if scores else np.nan,
            "mapel_terlemah": min(by_subject, key=by_subject.get) if by_subject else "—",
        })
    return pd.DataFrame(records)


def capacities(n: int) -> dict:
    if n != 140:
        raise ValueError(f"Rancangan Fu 21, Ch 30, Am 30, Pi 30, On 29 membutuhkan tepat 140 siswa; data saat ini {n}.")
    return {"Fu": 21, "Ch": 30, "Am": 30, "Pi": 30, "On": 29}


def allocate(features: pd.DataFrame, bottom_on: int = 10, overrides: dict | None = None) -> pd.DataFrame:
    """Place TKA students first; enforce capacities, On bottom block and manual locks."""
    df = features.copy()
    if df["student_id"].duplicated().any():
        raise ValueError("ID siswa ganda; penempatan dibatalkan.")
    caps = capacities(len(df))
    status = df["status_tka"].astype(str).str.casefold()
    if (~status.isin(["ikut", "tidak ikut"])).any():
        raise ValueError("Ada status TKA belum diatur; lengkapi PesertaTKA dahulu.")
    if df["skor_penempatan"].isna().any():
        raise ValueError("Ada siswa tanpa nilai tiga mapel utama; lengkapi data sebelum mengelompokkan.")
    if bottom_on < 0 or bottom_on > caps["On"]:
        raise ValueError("Jumlah siswa terbawah untuk On harus 0–29.")
    participants = df[status == "ikut"].sort_values(["skor_penempatan", "student_id"], ascending=[False, True])
    others = df[status == "tidak ikut"].sort_values(["skor_penempatan", "student_id"], ascending=[False, True])
    if len(participants) > sum(caps[g] for g in ("Fu", "Ch", "Am")):
        raise ValueError("Peserta TKA melebihi kapasitas Fu + Ch + Am (81).")

    assigned = {}
    for _, row in participants.iterrows():
        group = next(g for g in ("Fu", "Ch", "Am") if sum(v == g for v in assigned.values()) < caps[g])
        assigned[row.student_id] = group
    remaining_am = caps["Am"] - sum(v == "Am" for v in assigned.values())
    for sid in others.head(remaining_am)["student_id"]:
        assigned[sid] = "Am"
    lower = others.iloc[remaining_am:]
    if len(lower) != caps["Pi"] + caps["On"]:
        raise ValueError("Jumlah siswa kelompok bawah tidak sesuai kapasitas.")
    bottom_ids = set(lower.tail(bottom_on)["student_id"])
    for sid in bottom_ids:
        assigned[sid] = "On"
    remaining_lower = lower[~lower["student_id"].isin(bottom_ids)]
    # Balanced alternation: Pi and On each receive a mix of higher/lower students.
    for _, row in remaining_lower.iterrows():
        choices = [g for g in ("Pi", "On") if sum(v == g for v in assigned.values()) < caps[g]]
        group = min(choices, key=lambda g: (sum(v == g for v in assigned.values()) / caps[g], g))
        assigned[row.student_id] = group

    overrides = overrides or {}
    unknown = set(overrides) - set(df["student_id"])
    if unknown:
        raise ValueError(f"ID pada perubahan manual tidak ditemukan: {', '.join(sorted(unknown)[:5])}")
    if len(set(overrides)) != len(overrides) or any(g not in GROUPS for g in overrides.values()):
        raise ValueError("Perubahan manual harus memakai ID unik dan kelompok Fu/Ch/Am/Pi/On.")
    tka_ids = set(participants["student_id"])
    if any(sid in tka_ids and group in ("Pi", "On") for sid, group in overrides.items()):
        raise ValueError("Peserta TKA tidak boleh dipindahkan ke Pi atau On.")
    # Swaps preserve exact capacities. Locked assignments cannot themselves be moved.
    locked = set(overrides)
    for sid, desired in overrides.items():
        current = assigned[sid]
        if current == desired:
            continue
        candidates = df[(df["student_id"].map(assigned) == desired) & ~df["student_id"].isin(locked)]
        if current in ("Pi", "On"):
            candidates = candidates[candidates["status_tka"].str.casefold() == "tidak ikut"]
        if candidates.empty:
            raise ValueError(f"Tidak ada pertukaran aman untuk {sid} → {desired}; ubah daftar kunci.")
        ranks = candidates["skor_penempatan"] - float(df.loc[df.student_id == sid, "skor_penempatan"].iloc[0])
        other = candidates.iloc[int(np.argmin(np.abs(ranks.to_numpy())))].student_id
        assigned[sid], assigned[other] = desired, current

    df["rekomendasi"] = df["student_id"].map(assigned)
    df["alasan"] = df.apply(lambda r: (
        "Penempatan manual (pertukaran aman)" if r.student_id in locked else
        "Peserta TKA; skor terkini dan tren" if r.status_tka.casefold() == "ikut" else
        "Kelompok dasar; termasuk blok terbawah On" if r.student_id in bottom_ids else
        "Nonpeserta; skor terkini dan tren"
    ), axis=1)
    if df["rekomendasi"].value_counts().to_dict() != caps:
        raise AssertionError("Kapasitas penempatan tidak terpenuhi.")
    if (df["status_tka"].str.casefold().eq("ikut") & df["rekomendasi"].isin(["Pi", "On"])).any():
        raise AssertionError("Peserta TKA masuk kelompok bawah.")
    return df.sort_values(["rekomendasi", "skor_penempatan"], ascending=[True, False])


def attention_count(n: int, percent: int) -> int:
    return math.ceil(n * percent / 100)


def select_assessments(data: pd.DataFrame, provider: str) -> pd.DataFrame:
    """Classify HORIZON codes; ignore other assessment codes in TO rankings."""
    if "assessment_code" not in data.columns:
        if provider != "Gabungan":
            return data.iloc[0:0].copy()
        return data.copy()  # demo/legacy CSV only: visibly disclosed by the UI.
    codes = data["assessment_code"].fillna("").astype(str).str.strip().str.upper()
    holis = codes.str.match(r"^(MTH|BIH|BIGH)\d+$")
    penabur = codes.str.match(r"^(MT|BI|BIG)\d+$")
    if provider == "HOLIS":
        return data[holis].copy()
    if provider == "PENABUR":
        return data[penabur].copy()
    return data[holis | penabur].copy()


def ranking(data: pd.DataFrame, last_n: int | None = None) -> pd.DataFrame:
    """Equal subject weight; most recent N observations *per subject*."""
    records = []
    for sid, student in data.groupby("student_id", sort=True):
        per_subject, series = [], {}
        for subject in SUBJECTS:
            observed = student[student["mapel"].str.casefold() == subject.casefold()].sort_values("assessment_order")
            if last_n is not None:
                observed = observed.tail(last_n)
            values = observed["score"].to_numpy(float)
            if len(values):
                series[subject] = values
                per_subject.append(float(values.mean()))
        if len(series) != len(SUBJECTS):
            continue  # Never rank a student on fewer subjects against fully scored students.
        trend = float(np.mean([(v[-1] - v[0]) / (len(v) - 1) if len(v) >= 2 else 0 for v in series.values()]))
        volatility = float(np.mean([np.std(v, ddof=1) for v in series.values() if len(v) >= 2])) if any(len(v) >= 2 for v in series.values()) else np.nan
        lowest = min(series, key=lambda subject: np.mean(series[subject]))
        first = student.iloc[0]
        enough = all(len(v) >= 3 for v in series.values())
        if not enough:
            profile = "Data terbatas"
        elif volatility >= 15:
            profile = "Rentan fluktuasi"
        elif trend < -3:
            profile = "Perlu dijaga (menurun)"
        elif trend >= 2 and np.mean(per_subject) < 75:
            profile = "Berpotensi meningkat"
        elif volatility <= 8 and trend >= -2:
            profile = "Stabil"
        else:
            profile = "Perlu ditinjau"
        records.append({
            "student_id": sid, "nama": first["nama"], "kelas": first["kelas"],
            "status_tka": first["status_tka"], "skor": round(float(np.mean(per_subject)), 2),
            "tren": round(trend, 2), "fluktuasi": round(volatility, 2) if np.isfinite(volatility) else np.nan,
            "data_memadai": enough, "profil": profile, "mapel_terlemah": lowest,
            "jumlah_nilai": sum(len(v) for v in series.values()),
        })
    out = pd.DataFrame(records)
    if out.empty:
        return out
    out = out.sort_values(["skor", "student_id"], ascending=[False, True]).reset_index(drop=True)
    out.insert(0, "peringkat", np.arange(1, len(out) + 1))
    return out
