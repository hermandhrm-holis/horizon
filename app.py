import io
from urllib.parse import urlencode

import numpy as np
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

st.set_page_config(page_title="HORIZON Risk Lab", page_icon="🔭", layout="wide")

CORE = ["Matematika", "Bahasa Indonesia", "Bahasa Inggris"]
REQUIRED = {"student_id", "nama", "kelas", "mapel", "assessment_order", "score"}
COLUMNS = ["student_id", "nama", "kelas", "mapel", "assessment_order", "score"]


def demo_data() -> pd.DataFrame:
    rng = np.random.default_rng(20260912)
    profiles = [
        ("D001", "SISWA DEMO 01", "12A", 56, -1.8),
        ("D002", "SISWA DEMO 02", "12A", 64, 1.2),
        ("D003", "SISWA DEMO 03", "12B", 70, -0.4),
        ("D004", "SISWA DEMO 04", "12C", 61, 0.2),
        ("D005", "SISWA DEMO 05", "12D", 76, 0.8),
        ("D006", "SISWA DEMO 06", "12D", 67, -2.1),
    ]
    offsets = {"Matematika": -6, "Bahasa Indonesia": 6, "Bahasa Inggris": 0}
    rows = []
    for sid, nama, kelas, base, trend in profiles:
        for mapel in CORE:
            for order in range(1, 6):
                score = base + offsets[mapel] + trend * (order - 1) + rng.normal(0, 4.5)
                rows.append([sid, nama, kelas, mapel, order, round(float(np.clip(score, 0, 100)), 2)])
    return pd.DataFrame(rows, columns=COLUMNS)


def secret_or_blank(key: str) -> str:
    try:
        return str(st.secrets.get(key, ""))
    except Exception:
        return ""


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError("Kolom belum tersedia: " + ", ".join(sorted(missing)))
    df["assessment_order"] = pd.to_numeric(df["assessment_order"], errors="coerce")
    df["score"] = pd.to_numeric(df["score"], errors="coerce")
    return df.dropna(subset=["student_id", "mapel", "assessment_order", "score"])


@st.cache_data(ttl=300, show_spinner=False)
def load_gas(url: str, token: str) -> pd.DataFrame:
    joiner = "&" if "?" in url else "?"
    response = requests.get(url + joiner + urlencode({"action": "riskLab", "token": token}), timeout=25)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise ValueError(payload.get("error", "Respons GAS tidak valid"))
    return normalize(pd.DataFrame(payload.get("rows", [])))


def simulate(df: pd.DataFrame, target: float, future_tests: int, runs: int) -> tuple[pd.DataFrame, dict]:
    rng = np.random.default_rng(42)
    results, detail = [], {}
    for sid, student in df.groupby("student_id"):
        sims_by_subject, subject_summary = [], []
        for subject in CORE:
            part = student[student["mapel"].str.casefold() == subject.casefold()].sort_values("assessment_order")
            if part.empty:
                continue
            x = part["assessment_order"].to_numpy(float)
            y = part["score"].to_numpy(float)
            if len(part) >= 2:
                slope, intercept = np.polyfit(x, y, 1)
                residual = y - (intercept + slope * x)
                sigma = max(float(np.std(residual, ddof=1)) if len(part) > 2 else 6.0, 3.0)
            else:
                slope, intercept, sigma = 0.0, float(y[-1]), 9.0
            future_x = np.arange(x.max() + 1, x.max() + future_tests + 1)
            expected = intercept + slope * future_x
            simulated_path = rng.normal(expected, sigma, size=(runs, future_tests))
            projected = np.clip(simulated_path.mean(axis=1), 0, 100)
            sims_by_subject.append(projected)
            subject_summary.append({
                "mapel": subject,
                "nilai_terakhir": round(float(y[-1]), 1),
                "tren_per_asesmen": round(float(slope), 2),
                "proyeksi_median": round(float(np.median(projected)), 1),
                "ketidakpastian": round(float(sigma), 1),
            })
        if not sims_by_subject:
            continue
        combined = np.mean(np.vstack(sims_by_subject), axis=0)
        probability = float(np.mean(combined < target))
        latest_avg = float(student.groupby("mapel")["score"].last().mean())
        low_subject = min(subject_summary, key=lambda x: x["proyeksi_median"])
        status = "Prioritas tinggi" if probability >= .70 else "Perlu dipantau" if probability >= .35 else "Relatif siap"
        first = student.iloc[0]
        results.append({
            "student_id": sid, "nama": first["nama"], "kelas": first["kelas"],
            "peluang_belum_target": probability, "proyeksi_median": float(np.median(combined)),
            "nilai_terakhir": latest_avg, "status": status,
            "faktor_utama": f"{low_subject['mapel']} · proyeksi {low_subject['proyeksi_median']}",
        })
        detail[sid] = {"simulation": combined, "subjects": subject_summary}
    return pd.DataFrame(results).sort_values("peluang_belum_target", ascending=False), detail


st.markdown("""
<style>
.block-container {padding-top: 1.4rem;}
.hero {background:linear-gradient(110deg,#365f54,#91b4a7);padding:30px 34px;border-radius:28px;color:white;margin-bottom:18px}
.hero h1 {margin:0;font-size:2.35rem}.hero p{margin:.45rem 0 0;opacity:.9}
[data-testid="stMetric"] {background:#fff;border:1px solid #d9e3dd;padding:14px;border-radius:18px}
</style>
<div class="hero"><div style="letter-spacing:.18em;font-weight:700">HORIZON TKA</div>
<h1>Risk & Scenario Lab</h1><p>Simulasi probabilistik untuk keputusan intervensi—bukan vonis kelulusan.</p></div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("Sumber data")
    source = st.radio("Pilih sumber", ["Data demo", "Unggah CSV", "API Google Apps Script"])
    uploaded = st.file_uploader("CSV format panjang", type="csv") if source == "Unggah CSV" else None
    if source == "API Google Apps Script":
        default_url = secret_or_blank("GAS_API_URL")
        default_token = secret_or_blank("GAS_API_TOKEN")
        gas_url = st.text_input("URL Web App GAS", value=default_url)
        gas_token = st.text_input("Token", value=default_token, type="password")
    st.divider()
    st.header("Skenario")
    target = st.number_input("Target TKA", 0.0, 100.0, 65.0, 1.0)
    future_tests = st.slider("Asesmen tersisa", 1, 8, 3)
    runs = st.select_slider("Jumlah simulasi", [1000, 3000, 5000, 10000], value=5000)

try:
    if source == "Data demo":
        data = normalize(demo_data())
    elif source == "Unggah CSV":
        if uploaded is None:
            st.info("Unggah CSV untuk memulai.")
            st.stop()
        data = normalize(pd.read_csv(uploaded))
    else:
        if not gas_url or not gas_token:
            st.info("Masukkan URL dan token API GAS.")
            st.stop()
        data = load_gas(gas_url, gas_token)

    risk, detail = simulate(data, target, future_tests, runs)
    if risk.empty:
        st.warning("Belum ada data yang dapat dianalisis.")
        st.stop()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Siswa dianalisis", len(risk))
    c2.metric("Prioritas tinggi", int((risk.status == "Prioritas tinggi").sum()))
    c3.metric("Perlu dipantau", int((risk.status == "Perlu dipantau").sum()))
    c4.metric("Simulasi per siswa", f"{runs:,}".replace(",", "."))

    left, right = st.columns([1.25, 1])
    with left:
        st.subheader("Siapa yang paling membutuhkan perhatian?")
        shown = risk.copy()
        shown["Peluang belum target"] = (shown["peluang_belum_target"] * 100).round(1).astype(str) + "%"
        st.dataframe(shown[["nama", "kelas", "Peluang belum target", "proyeksi_median", "faktor_utama", "status"]],
                     hide_index=True, width="stretch")
    with right:
        st.subheader("Peta risiko dan potensi")
        fig = px.scatter(risk, x="nilai_terakhir", y="peluang_belum_target", color="status", hover_name="nama",
                         color_discrete_map={"Prioritas tinggi":"#d96c5f","Perlu dipantau":"#e4ad4d","Relatif siap":"#5d9380"},
                         labels={"nilai_terakhir":"Nilai terakhir", "peluang_belum_target":"Peluang belum target"})
        fig.add_vline(x=target, line_dash="dot", line_color="#456f63")
        fig.update_yaxes(tickformat=".0%", range=[0,1])
        fig.update_layout(height=430, legend_title_text="", margin=dict(l=10,r=10,t=10,b=10))
        st.plotly_chart(fig, width="stretch")

    st.subheader("Mengapa siswa masuk prioritas?")
    selected_name = st.selectbox("Pilih siswa", risk["nama"].tolist())
    row = risk[risk["nama"] == selected_name].iloc[0]
    d = detail[row["student_id"]]
    a, b = st.columns([1, 1.3])
    with a:
        st.metric("Peluang belum mencapai target", f"{row['peluang_belum_target']:.1%}")
        st.caption(f"Hasil {runs:,} simulasi, {future_tests} asesmen tersisa, target {target:g}.")
        st.dataframe(pd.DataFrame(d["subjects"]), hide_index=True, width="stretch")
    with b:
        sim = d["simulation"]
        hist = px.histogram(x=sim, nbins=28, labels={"x":"Proyeksi rata-rata akhir", "count":"Skenario"},
                            color_discrete_sequence=["#6f988b"])
        hist.add_vline(x=target, line_dash="dash", line_color="#d96c5f", annotation_text="Target")
        hist.update_layout(height=330, margin=dict(l=10,r=10,t=20,b=10), showlegend=False)
        st.plotly_chart(hist, width="stretch")

    st.warning("Model ini adalah alat triase. Keputusan intervensi tetap harus mempertimbangkan konteks guru, kualitas soal, kondisi siswa, dan kelengkapan data.")

except Exception as exc:
    st.error(f"Data belum dapat diproses: {exc}")
