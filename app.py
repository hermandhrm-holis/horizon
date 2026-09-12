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
    demo = pd.DataFrame(rows, columns=COLUMNS)
    demo["status_tka"] = np.where(demo["student_id"].isin(["D001", "D002", "D004", "D006"]), "Ikut", "Tidak Ikut")
    return demo


def secret_or_blank(key: str) -> str:
    try:
        return str(st.secrets.get(key, ""))
    except Exception:
        return ""


def metric_card(label: str, value: str, note: str = ""):
    note_html = f'<div style="margin-top:8px;color:#527066;font-size:14px;font-weight:600">{note}</div>' if note else ""
    st.markdown(
        f'''<div style="background:#ffffff;border:1px solid #cbd8d1;border-radius:20px;
        padding:20px 22px;min-height:122px;box-shadow:0 2px 8px rgba(32,51,46,.06)">
        <div style="color:#45645b;font-size:15px;font-weight:750;line-height:1.3">{label}</div>
        <div style="color:#172c26;font-size:42px;font-weight:800;line-height:1.15;margin-top:12px">{value}</div>
        {note_html}</div>''', unsafe_allow_html=True
    )


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError("Kolom belum tersedia: " + ", ".join(sorted(missing)))
    if "status_tka" not in df.columns:
        df["status_tka"] = "Belum diatur"
    df["status_tka"] = df["status_tka"].fillna("Belum diatur").astype(str).str.strip()
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


def simulate(df: pd.DataFrame, target: float, future_tests: int, runs: int, lifts=None) -> tuple[pd.DataFrame, dict]:
    lifts = lifts or {subject: 0 for subject in CORE}
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
            expected = intercept + slope * future_x + float(lifts.get(subject, 0))
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
            "status_tka": first.get("status_tka", "Belum diatur"),
            "peluang_belum_target": probability, "proyeksi_median": float(np.median(combined)),
            "batas_bawah": float(np.percentile(combined, 10)),
            "batas_atas": float(np.percentile(combined, 90)),
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
div[data-testid="stMetricLabel"],div[data-testid="stMetricLabel"] *,div[data-testid="stMetricValue"],div[data-testid="stMetricValue"] *{color:#20332e!important;opacity:1!important}
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
    st.caption("Jumlah kemungkinan nilai masa depan yang dihitung per siswa. 3.000 sudah cukup untuk keputusan sekolah.")
    with st.expander("Bagaimana jika nilai naik?"):
        lift_math = st.slider("Kenaikan Matematika", 0, 15, 0)
        lift_bi = st.slider("Kenaikan Bahasa Indonesia", 0, 15, 0)
        lift_english = st.slider("Kenaikan Bahasa Inggris", 0, 15, 0)

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

    with st.sidebar:
        st.divider()
        st.header("Filter siswa")
        population = st.selectbox("Peserta", ["Peserta TKA", "Semua Siswa", "Tidak Ikut TKA"])
        class_options = ["Semua Kelas"] + sorted(data["kelas"].dropna().astype(str).unique().tolist())
        selected_class = st.selectbox("Kelas", class_options)

    filtered = data.copy()
    if population == "Peserta TKA":
        filtered = filtered[filtered["status_tka"].str.casefold() == "ikut"]
    elif population == "Tidak Ikut TKA":
        filtered = filtered[filtered["status_tka"].str.casefold() == "tidak ikut"]
    if selected_class != "Semua Kelas":
        filtered = filtered[filtered["kelas"].astype(str) == selected_class]
    if filtered.empty:
        st.warning("Tidak ada data pada filter ini. Pastikan sheet PesertaTKA sudah tersambung ke API.")
        st.stop()

    lifts = {"Matematika": lift_math, "Bahasa Indonesia": lift_bi, "Bahasa Inggris": lift_english}
    baseline_risk, _ = simulate(filtered, target, future_tests, runs)
    risk, detail = simulate(filtered, target, future_tests, runs, lifts)
    if risk.empty:
        st.warning("Belum ada data yang dapat dianalisis.")
        st.stop()

    baseline_ready = float((1-baseline_risk.peluang_belum_target).sum())
    scenario_ready = float((1-risk.peluang_belum_target).sum())
    c1, c2, c3, c4 = st.columns(4)
    with c1: metric_card("Siswa dianalisis", str(len(risk)))
    with c2: metric_card("Prioritas tinggi", str(int((risk.status == "Prioritas tinggi").sum())))
    with c3: metric_card("Perlu dipantau", str(int((risk.status == "Perlu dipantau").sum())))
    with c4: metric_card("Perkiraan mencapai target", f"{scenario_ready:.1f}", f"{scenario_ready-baseline_ready:+.1f} dari skenario")

    left, right = st.columns([1.25, 1])
    with left:
        st.subheader("5 siswa paling membutuhkan perhatian")
        shown = risk.head(5).copy()
        shown["Peluang belum target"] = (shown["peluang_belum_target"] * 100).round(1).astype(str) + "%"
        shown["Proyeksi"] = shown["proyeksi_median"].round(1)
        shown["Rentang 80%"] = shown.apply(lambda r: f"{r['batas_bawah']:.1f}–{r['batas_atas']:.1f}", axis=1)
        st.dataframe(shown[["nama", "kelas", "status_tka", "Peluang belum target", "Proyeksi", "Rentang 80%", "faktor_utama"]],
                     hide_index=True, width="stretch")
    with right:
        st.subheader("Peta risiko dan potensi")
        fig = px.scatter(risk, x="nilai_terakhir", y="peluang_belum_target", color="status", hover_name="nama",
                         color_discrete_map={"Prioritas tinggi":"#d96c5f","Perlu dipantau":"#e4ad4d","Relatif siap":"#5d9380"},
                         labels={"nilai_terakhir":"Nilai terakhir", "peluang_belum_target":"Peluang belum target"})
        fig.add_vline(x=target, line_dash="dot", line_color="#456f63")
        fig.update_xaxes(tickfont=dict(color="#20332e",size=13),title_font=dict(color="#20332e",size=15),gridcolor="#d7e0dc",linecolor="#82958e")
        fig.update_yaxes(tickformat=".0%",range=[0,1],tickfont=dict(color="#20332e",size=13),title_font=dict(color="#20332e",size=15),gridcolor="#d7e0dc",linecolor="#82958e")
        fig.update_layout(height=430,legend_title_text="",margin=dict(l=10,r=10,t=10,b=10),paper_bgcolor="#ffffff",plot_bgcolor="#ffffff",
                          font=dict(color="#20332e",size=13),legend=dict(font=dict(color="#20332e",size=13),bgcolor="rgba(255,255,255,.9)"))
        st.plotly_chart(fig, theme=None, width="stretch")

    st.subheader("Mengapa siswa masuk prioritas?")
    selected_name = st.selectbox("Pilih siswa", risk["nama"].tolist())
    row = risk[risk["nama"] == selected_name].iloc[0]
    d = detail[row["student_id"]]
    a, b = st.columns([1, 1.3])
    with a:
        st.metric("Peluang belum mencapai target", f"{row['peluang_belum_target']:.1%}")
        st.write(f"**Rentang proyeksi 80%:** {row['batas_bawah']:.1f}–{row['batas_atas']:.1f}")
        st.caption(f"Hasil {runs:,} simulasi, {future_tests} asesmen tersisa, target {target:g}.")
        st.dataframe(pd.DataFrame(d["subjects"]), hide_index=True, width="stretch")
    with b:
        sim = d["simulation"]
        hist = px.histogram(x=sim, nbins=28, labels={"x":"Proyeksi rata-rata akhir", "count":"Skenario"},
                            color_discrete_sequence=["#6f988b"])
        hist.add_vline(x=target, line_dash="dash", line_color="#d96c5f", annotation_text="Target")
        hist.update_xaxes(tickfont=dict(color="#20332e"),title_font=dict(color="#20332e"),gridcolor="#d7e0dc")
        hist.update_yaxes(tickfont=dict(color="#20332e"),title_font=dict(color="#20332e"),gridcolor="#d7e0dc")
        hist.update_layout(height=330,margin=dict(l=10,r=10,t=20,b=10),showlegend=False,paper_bgcolor="#ffffff",plot_bgcolor="#ffffff",font=dict(color="#20332e"))
        st.plotly_chart(hist, theme=None, width="stretch")

    st.warning("Model ini adalah alat triase. Keputusan intervensi tetap harus mempertimbangkan konteks guru, kualitas soal, kondisi siswa, dan kelengkapan data.")

except Exception as exc:
    st.error(f"Data belum dapat diproses: {exc}")
