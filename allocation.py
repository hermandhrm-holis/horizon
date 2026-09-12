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
        scores, trends, dispersions, subject_counts = [], [], [], []
        counts_by_subject = {}
        by_subject = {}
        for subject in SUBJECTS:
            s = student[(student["mapel"].str.casefold() == subject.casefold()) &
                        student["score"].notna()].sort_values("assessment_order")
            counts_by_subject[subject] = len(s)
            if s.empty:
                continue
            recent = s["score"].tail(3).to_numpy(float)
            scores.append(float(np.mean(recent)))
            trends.append(float(recent[-1] - recent[0]) / max(len(recent) - 1, 1))
            if len(recent) >= 2:
                dispersions.append(float(np.std(recent, ddof=1)))
            subject_counts.append(len(s))
            by_subject[subject] = round(float(np.mean(recent)), 1)
        first = student.iloc[0]
        complete = len(scores) == 3 and all(count >= 3 for count in subject_counts)
        missing_reason = ("Data kurang: " + "; ".join(
            f"{subject} {counts_by_subject[subject]}/3 nilai minimum"
            for subject in SUBJECTS if counts_by_subject[subject] < 3)
            + f". Total {sum(counts_by_subject.values())} nilai tercatat; perlu minimal 3 per mapel."
            if not complete else "")
        avg = float(np.mean(scores)) if scores else np.nan
        trend = float(np.mean(trends)) if trends else 0.0
        volatility = float(np.mean(dispersions)) if dispersions else np.nan
        # Descriptive suitability scores, not measured treatment effects.
        potential = (12 - min(abs(avg - 65) * 0.6, 12) + 3 * min(max(trend, 0), 5)
                     + 0.2 * max(100 - avg, 0) - 0.3 * (volatility if np.isfinite(volatility) else 15)) if scores else np.nan
        fu_fit = avg - 0.5 * (volatility if np.isfinite(volatility) else 15) - 1.5 * max(trend, 0) if scores else np.nan
        records.append({
            "student_id": sid, "nama": first["nama"], "kelas_asal": first["kelas"],
            "status_tka": first["status_tka"], "rata_terkini": avg,
            "tren": trend, "mapel_tersedia": len(scores), "data_memadai": complete,
            "jumlah_nilai": sum(counts_by_subject.values()), "alasan_data": missing_reason,
            "fluktuasi": volatility, "potensi_pengembangan": potential, "kecocokan_fu": fu_fit,
            "skor_penempatan": float(np.clip(avg + np.clip(trend, -5, 5) * 0.4, 0, 100)) if scores else np.nan,
            "mapel_terlemah": min(by_subject, key=by_subject.get) if by_subject else "—",
        })
    return pd.DataFrame(records)


def capacities(n: int) -> dict:
    if n != 140:
        raise ValueError(f"Rancangan Fu 21, Ch 30, Am 30, Pi 30, On 29 membutuhkan tepat 140 siswa; data saat ini {n}.")
    return {"Fu": 21, "Ch": 30, "Am": 30, "Pi": 30, "On": 29}


def allocate(features: pd.DataFrame, bottom_on: int = 10, overrides: dict | None = None) -> pd.DataFrame:
    """Place incomplete records in On; use available scores for all other placements."""
    df = features.copy()
    if df["student_id"].duplicated().any():
        raise ValueError("ID siswa ganda; penempatan dibatalkan.")
    caps = capacities(len(df))
    status = df["status_tka"].astype(str).str.casefold()
    if (~status.isin(["ikut", "tidak ikut"])).any():
        raise ValueError("Ada status TKA belum diatur; lengkapi PesertaTKA dahulu.")
    if bottom_on < 0 or bottom_on > caps["On"]:
        raise ValueError("Jumlah siswa terbawah untuk On harus 0–29.")
    incomplete = df[~df["data_memadai"] | df["skor_penempatan"].isna()].copy()
    if len(incomplete) > caps["On"]:
        raise ValueError(f"{len(incomplete)} siswa memiliki data kurang, sedangkan On hanya {caps['On']} kursi. "
                         "Tidak ada penempatan yang memenuhi keduanya; periksa kapasitas atau lengkapi data.")
    ready = df[~df.student_id.isin(incomplete.student_id)]
    participants = ready[ready["status_tka"].str.casefold() == "ikut"].sort_values(
        ["kecocokan_fu", "skor_penempatan", "student_id"], ascending=[False, False, True])
    others = ready[ready["status_tka"].str.casefold() == "tidak ikut"].sort_values(
        ["skor_penempatan", "student_id"], ascending=[False, True])
    if len(participants) > sum(caps[g] for g in ("Fu", "Ch", "Am")):
        raise ValueError("Peserta TKA melebihi kapasitas Fu + Ch + Am (81).")

    assigned = {sid: "On" for sid in incomplete.student_id}
    for sid in participants.head(caps["Fu"])["student_id"]:
        assigned[sid] = "Fu"
    remaining_tka = participants[~participants["student_id"].isin(assigned)].sort_values(
        ["potensi_pengembangan", "skor_penempatan", "student_id"], ascending=[False, False, True])
    for sid in remaining_tka.head(caps["Ch"])["student_id"]:
        assigned[sid] = "Ch"
    for sid in remaining_tka.iloc[caps["Ch"]:]["student_id"]:
        assigned[sid] = "Am"
    offset = 0
    for group in ("Fu", "Ch", "Am"):
        vacancies = caps[group] - sum(v == group for v in assigned.values())
        for sid in others.iloc[offset:offset + vacancies].student_id:
            assigned[sid] = group
        offset += vacancies
    lower = others.iloc[offset:]
    if len(lower) != caps["Pi"] + caps["On"] - len(incomplete):
        raise ValueError("Jumlah siswa kelompok bawah tidak sesuai kapasitas.")
    bottom_ids = set(lower.tail(min(len(lower), max(0, bottom_on - len(incomplete)))).student_id)
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
    incomplete_ids = set(incomplete.student_id)
    if any(sid in incomplete_ids and group != "On" for sid, group in overrides.items()):
        raise ValueError("Siswa dengan data kurang tetap di On sampai datanya memadai.")
    if any(sid in tka_ids and group in ("Pi", "On") for sid, group in overrides.items()):
        raise ValueError("Peserta TKA dengan data memadai tidak boleh ke Pi atau On.")
    # Swaps preserve exact capacities. Locked assignments cannot themselves be moved.
    locked = set(overrides)
    for sid, desired in overrides.items():
        current = assigned[sid]
        if current == desired:
            continue
        candidates = df[(df["student_id"].map(assigned) == desired) &
                        ~df["student_id"].isin(locked | incomplete_ids)]
        if current in ("Pi", "On"):
            candidates = candidates[candidates["status_tka"].str.casefold() == "tidak ikut"]
        if candidates.empty:
            raise ValueError(f"Tidak ada pertukaran aman untuk {sid} → {desired}; ubah daftar kunci.")
        ranks = candidates["skor_penempatan"] - float(df.loc[df.student_id == sid, "skor_penempatan"].iloc[0])
        other = candidates.iloc[int(np.argmin(np.abs(ranks.to_numpy())))].student_id
        assigned[sid], assigned[other] = desired, current

    df["rekomendasi"] = df["student_id"].map(assigned)
    df["alasan"] = df.apply(lambda r: (
        "On sementara karena " + r.alasan_data +
        (" Status TKA: ikut; pengecualian sementara yang perlu ditinjau sekolah."
         if r.status_tka.casefold() == "ikut" else "") if r.student_id in incomplete_ids else
        "Penempatan manual (pertukaran aman)" if r.student_id in locked else
        "Fu: skor kuat dan stabil" if r.rekomendasi == "Fu" else
        "Ch: indikator ruang berkembang" if r.rekomendasi == "Ch" else
        "Peserta TKA; perlu penguatan stabil" if r.status_tka.casefold() == "ikut" else
        "Kelompok dasar; termasuk blok terbawah On" if r.student_id in bottom_ids else
        "Nonpeserta; skor terkini dan tren"
    ), axis=1)
    if df["rekomendasi"].value_counts().to_dict() != caps:
        raise AssertionError("Kapasitas penempatan tidak terpenuhi.")
    if (df["status_tka"].str.casefold().eq("ikut") & df["data_memadai"] &
            df["rekomendasi"].isin(["Pi", "On"])).any():
        raise AssertionError("Peserta TKA dengan data lengkap masuk kelompok bawah.")
    return df.sort_values(["rekomendasi", "skor_penempatan"], ascending=[True, False])


def attention_count(n: int, percent: int) -> int:
    return math.ceil(n * percent / 100)


def triage(features: pd.DataFrame, target: float = 65) -> pd.DataFrame:
    """Transparent descriptive priority; never present heuristic probabilities."""
    out = features.copy()
    observations = []
    for row in out.itertuples():
        score = row.rata_terkini
        trend = row.tren
        volatility = row.fluktuasi
        gap = target - score if np.isfinite(score) else np.nan
        if not row.data_memadai:
            level, reason, action = ("Data terbatas", "Tiga nilai per mapel utama belum lengkap.",
                                     "Lengkapi TO terlebih dahulu; jangan simpulkan kesiapan siswa.")
        elif gap > 10 or (gap > 0 and trend < -3):
            level = "Prioritas tinggi"
            reason = f"Rata-rata {score:.1f}; selisih {gap:.1f} dari target; tren {trend:+.1f}/TO."
            action = f"Guru {row.mapel_terlemah}: periksa kesalahan TO, tentukan satu fokus, cek ulang setelah TO berikutnya."
        elif gap > 0 or trend < -2 or (np.isfinite(volatility) and volatility >= 12):
            level = "Perlu dipantau"
            reason = f"Rata-rata {score:.1f}; tren {trend:+.1f}/TO; fluktuasi {volatility:.1f}."
            action = f"Guru {row.mapel_terlemah}: tinjau nilai terakhir dan tetapkan satu langkah pada TO berikutnya."
        else:
            level = "Relatif siap"
            reason = f"Rata-rata {score:.1f}; tren {trend:+.1f}/TO; fluktuasi {volatility:.1f}."
            action = "Jaga konsistensi, jangan menambah latihan tanpa indikasi kebutuhan."
        potential = bool(row.data_memadai and 0 < gap <= 15 and trend >= 0
                         and np.isfinite(volatility) and volatility <= 12)
        warning = bool(row.data_memadai and (trend < -2 or
                       (np.isfinite(volatility) and volatility >= 12)))
        category_weight = {"Prioritas tinggi": 3, "Perlu dipantau": 2,
                           "Data terbatas": 1, "Relatif siap": 0}[level]
        urgency = (category_weight * 100 + min(max(gap, 0), 30) if np.isfinite(gap) else 100)
        if row.data_memadai and trend < 0:
            urgency += min(abs(trend), 10)
        observations.append((level, reason, action, potential, warning, urgency))
    out[["status", "alasan_utama", "langkah_berikutnya", "potensi_naik",
         "peringatan_dini", "urutan_perhatian"]] = pd.DataFrame(observations, index=out.index)
    return out


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
            observed = student[(student["mapel"].str.casefold() == subject.casefold()) &
                               student["score"].notna()].sort_values("assessment_order")
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
