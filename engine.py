"""Read-only HORIZON data adapter and explicitly heuristic simulations."""

import json
from urllib.parse import urlencode

import numpy as np
import pandas as pd
import requests

CORE = ("Matematika", "Bahasa Indonesia", "Bahasa Inggris")
REQUIRED = {"student_id", "nama", "kelas", "mapel", "assessment_order", "score"}


class SourceError(Exception):
    """A safe, user-facing connection message without returning private content."""


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = REQUIRED - set(df.columns)
    if missing:
        raise SourceError("Kolom data belum tersedia: " + ", ".join(sorted(missing)))
    if "status_tka" not in df:
        df["status_tka"] = "Belum diatur"
    df["status_tka"] = df["status_tka"].fillna("Belum diatur").astype(str).str.strip()
    df["student_id"] = df["student_id"].fillna("").astype(str).str.strip()
    df["score"] = pd.to_numeric(df["score"].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    df["assessment_order"] = pd.to_numeric(df["assessment_order"], errors="coerce")
    df = df[df.student_id.ne("") & df.mapel.isin(CORE)].copy()
    if df.empty:
        raise SourceError("Tidak ada daftar siswa atau nilai tiga mapel utama yang dapat dibaca.")
    return df


def fetch_gas(url: str, token: str) -> pd.DataFrame:
    if not url.startswith("https://script.google.com/macros/s/") or "/exec" not in url:
        raise SourceError("URL harus alamat Web App Apps Script yang berakhir /exec.")
    try:
        response = requests.get(url + ("&" if "?" in url else "?") + urlencode({"token": token}), timeout=30)
        response.raise_for_status()
        payload = response.json()
    except (json.JSONDecodeError, requests.exceptions.JSONDecodeError, ValueError) as exc:
        raise SourceError("GAS mengembalikan halaman HTML/teks, bukan JSON. Periksa deployment Web App, hak akses sesuai kebijakan sekolah, URL /exec, dan izin akun pemilik untuk membaca Sheet. Log instalasi Python di samping bukan penyebab pesan ini.") from exc
    except requests.RequestException as exc:
        raise SourceError("GAS tidak dapat dijangkau. Periksa URL deployment dan koneksi.") from exc
    if not isinstance(payload, dict):
        raise SourceError("Respons GAS bukan objek data yang diharapkan.")
    if not payload.get("ok"):
        error = str(payload.get("error", "Respons GAS belum berhasil"))
        raise SourceError("GAS menolak permintaan: " + error[:120])
    values = payload.get("rows", [])
    roster = payload.get("students", [])
    if not isinstance(values, list) or not isinstance(roster, list):
        raise SourceError("Format daftar nilai atau siswa dari GAS tidak sesuai.")
    known = {str(row.get("student_id", "")).strip() for row in values if isinstance(row, dict)}
    records = list(values)
    for student in roster:
        if not isinstance(student, dict):
            continue
        sid = str(student.get("student_id", "")).strip()
        if sid and sid not in known:
            records.append({"student_id": sid, "nama": student.get("nama", ""),
                            "kelas": student.get("kelas", ""), "status_tka": student.get("status_tka", "Belum diatur"),
                            "mapel": "Matematika", "assessment_order": None,
                            "assessment_code": None, "score": None})
            known.add(sid)
    if not records:
        raise SourceError("API belum mengirim nilai maupun daftar siswa.")
    return normalize(pd.DataFrame(records))


def demo_data() -> pd.DataFrame:
    rng = np.random.default_rng(20260912)
    rows = []
    codes = {"Matematika": "MT", "Bahasa Indonesia": "BI", "Bahasa Inggris": "BIG"}
    for i in range(140):
        base = 34 + (139 - i) * 0.38
        trend = ((i * 7) % 13 - 6) * 0.45
        for j, subject in enumerate(CORE):
            for order in range(1, 9):
                internal = order % 3 == 0
                code = codes[subject] + ("H" if internal else "") + f"{order:02d}"
                score = np.clip(base + (j - 1) * 5 + trend * order + rng.normal(0, 4 + i % 4), 0, 100)
                rows.append({"student_id": f"DEMO-{i+1:03}", "nama": f"SISWA DEMO {i+1:03}",
                             "kelas": f"12{'ABCD'[i%4]}", "mapel": subject,
                             "assessment_order": order, "assessment_code": code,
                             "score": round(float(score), 2), "status_tka": "Ikut" if i < 58 else "Tidak Ikut"})
    return normalize(pd.DataFrame(rows))


def simulate(data: pd.DataFrame, target: float, future: int, runs: int, lifts=None):
    """Illustrative Monte Carlo: not calibrated to actual TKA outcomes."""
    rng = np.random.default_rng(42)
    lifts = lifts or {}
    output, details = [], {}
    for sid, s in data.groupby("student_id", sort=True):
        sims, summary, trend_values, volatility_values = [], [], [], []
        for subject in CORE:
            part = s[s.mapel == subject].sort_values("assessment_order")
            if part.empty:
                continue
            y = part.score.to_numpy(float)
            x = np.arange(len(y), dtype=float)
            recent_y = y[-5:]; recent_x = x[-5:]
            if len(recent_y) >= 2:
                slope = float(np.clip(np.polyfit(recent_x, recent_y, 1)[0], -4, 4))
                volatility = float(np.std(recent_y, ddof=1))
            else:
                slope, volatility = 0.0, 12.0
            uncertainty = max(5.0, volatility)
            expected = float(recent_y[-1]) + slope * np.arange(1, future + 1) + float(lifts.get(subject, 0))
            projected = np.clip(rng.normal(expected, uncertainty, size=(runs, future)).mean(axis=1), 0, 100)
            sims.append(projected); trend_values.append(slope); volatility_values.append(volatility)
            summary.append({"Mapel": subject, "Nilai terakhir": round(float(y[-1]), 1),
                            "Tren": round(slope, 1), "Proyeksi": round(float(np.median(projected)), 1),
                            "Jumlah TO": len(y)})
        if not sims:
            continue
        combined = np.mean(np.vstack(sims), axis=0)
        probability = float(np.mean(combined < target))
        complete = len(sims) == 3 and all(row["Jumlah TO"] >= 3 for row in summary)
        category = ("Data terbatas" if not complete else "Prioritas tinggi" if probability >= .7
                    else "Perlu dipantau" if probability >= .35 else "Relatif siap")
        first = s.iloc[0]
        output.append({"student_id": sid, "nama": first["nama"], "kelas": first["kelas"],
                       "status_tka": first["status_tka"], "peluang_belum_target": probability,
                       "proyeksi": float(np.median(combined)), "batas_bawah": float(np.percentile(combined, 10)),
                       "batas_atas": float(np.percentile(combined, 90)), "status": category,
                       "tren": float(np.mean(trend_values)), "fluktuasi": float(np.mean(volatility_values)),
                       "mapel_penghambat": min(summary, key=lambda item: item["Proyeksi"])["Mapel"]})
        details[sid] = {"distribution": combined, "subjects": summary}
    return pd.DataFrame(output), details
