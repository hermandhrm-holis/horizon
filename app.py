"""HORIZON: four decision-focused dashboards, exclusively backed by the GAS API."""

import re
from html import escape

import pandas as pd
import plotly.express as px
import streamlit as st

from allocation import (allocate, assessment_chart_data, attention_count, ranking, select_assessments,
                        student_features, triage)
from briefing import homeroom_brief, remaining_to, role_pdf, subject_brief
from engine import CORE, SourceError, fetch_gas, simulate, simulation_guidance
from report import build_report, student_analysis


# The endpoint is not a credential; the data access token belongs in Streamlit Secrets.
GAS_API_URL = ("https://script.google.com/macros/s/"
               "AKfycbxR426Jyr8XO6SF52Yi5d8_BcnsbzD_dwXnR0wzjrFJYXrSlCesO46SMifMKezPH1SdnA/exec")
st.set_page_config(page_title="HORIZON TKA | Decision Lab", page_icon="🔭", layout="wide")
st.markdown("""
<style>
  .block-container{max-width:1530px;padding-top:1.2rem}
  .hero{background:linear-gradient(110deg,#355e53,#83aa9b);color:white;border-radius:25px;padding:23px 32px;margin-bottom:18px}
  .hero h1,.hero p{color:white!important;margin:0}.hero h1{font-size:2.2rem}
  .hero p{margin-top:7px}.card{background:#fff;border:1px solid #cbd8d1;border-radius:16px;padding:16px 19px;min-height:100px}
  .card-label{color:#365348;font-weight:750;font-size:15px}.card-value{color:#152b24;font-weight:800;font-size:32px;margin-top:8px}
  .card-note{color:#45675c;font-size:12px}
  div[data-testid="stMetric"]{background:#fff!important;border:1px solid #cbd8d1;border-radius:16px;padding:14px}
  div[data-testid="stMetric"] *{color:#20332e!important}
</style>
<div class="hero"><div style="letter-spacing:.15em;font-weight:700">HORIZON TKA</div>
<h1>Decision Lab</h1><p>Siapa perlu dibantu, apa langkah berikutnya, dan kapan diperiksa lagi.</p></div>
""", unsafe_allow_html=True)


PERSISTENT_KEYS = {
    'chart_provider',
    'daily_audience',
    'filter_daftar_tindakan',
    'filter_jendela_ranking',
    'filter_kelas_asal',
    'filter_lihat_kelompok',
    'filter_minimum_siswa_terbawah_di_on_termasuk_data_kurang',
    'filter_persentase_dari_cakupan_ini',
    'filter_siswa',
    'filter_sumber_to',
    'filter_tampilkan',
    'filter_target_nilai',
    'filter_token_api',
    'filter_top_per_kelas',
    'filter_url_web_app_gas',
    'quality_provider',
    'report_student',
    'run_scenario',
    'simulation_future',
    'simulation_provider',
    'teacher_class',
    'teacher_subject',
    'wk_class',
}

# Keep only assignable filter state while its lazy tab is hidden.
# data_editor state is read-only: never assign placement_editor or form_* here.
for _state_key in list(st.session_state):
    if _state_key in PERSISTENT_KEYS or _state_key.startswith(("size_", "scenario_lift_")):
        st.session_state[_state_key] = st.session_state[_state_key]


def open_student(click_key, student_ids):
    click = st.session_state.get(click_key)
    if click is None:
        return
    row = click["row"]
    if not isinstance(row, int) or not 0 <= row < len(student_ids):
        return
    current_tab = st.session_state.get("decision_tab", "Tindakan Hari Ini")
    if current_tab != "Siswa & Rapor" or not st.session_state.get("report_focus"):
        st.session_state["report_return_tab"] = current_tab
    st.session_state["report_student"] = student_ids[row]
    st.session_state["report_focus"] = True
    st.session_state["decision_tab"] = "Siswa & Rapor"


def return_to_list():
    st.session_state["decision_tab"] = st.session_state.pop("report_return_tab", "Tindakan Hari Ini")
    st.session_state["report_focus"] = False


def student_name_column(frame, key):
    # Capture the exact displayed row order, including tables with hidden IDs.
    return st.column_config.ButtonColumn(
        "Nama siswa ↗", width="large", pinned=True, alignment="left", type="tertiary",
        help="Klik nama untuk membuka rapor siswa.", key=key,
        on_click=open_student, args=(key, tuple(frame.student_id.tolist())))


def card(label, value, note=""):
    st.markdown(f'<div class="card"><div class="card-label">{label}</div>'
                f'<div class="card-value">{value}</div><div class="card-note">{note}</div></div>',
                unsafe_allow_html=True)


def overview_card(label, value, note, accent):
    st.markdown('<div class="card" style="border-top:4px solid ' + accent + ';min-height:130px">'
                '<div class="card-label">' + escape(str(label)) + '</div>'
                '<div class="card-value">' + escape(str(value)) + '</div>'
                '<div class="card-note">' + escape(str(note)) + '</div></div>',
                unsafe_allow_html=True)


def cohort_chart(frame, provider):
    grouped = assessment_chart_data(frame, provider)
    if grouped.empty:
        st.info("Belum ada kode dan nilai TO " + provider + " yang dapat digambar pada cakupan ini.")
        return
    fig = px.bar(grouped, x="TO", y="rerata", color="mapel", barmode="group",
                 hover_data={"siswa": True, "rerata": ":.2f", "TO": False},
                 labels={"rerata": "Rata-rata nilai", "mapel": "Mata pelajaran", "siswa": "Siswa bernilai"},
                 color_discrete_map={"Bahasa Inggris": "#FFC842", "Bahasa Indonesia": "#35D3A1",
                                     "Matematika": "#8899FF"},
                 category_orders={"mapel": ["Bahasa Inggris", "Bahasa Indonesia", "Matematika"],
                                  "TO": ["TO " + str(i) for i in sorted(grouped.putaran.unique())]})
    fig.update_traces(texttemplate="%{y:.2f}", textposition="outside", cliponaxis=False,
                      textfont=dict(size=11))
    fig.update_layout(height=420, paper_bgcolor="#152032", plot_bgcolor="#152032",
                      font=dict(color="#F2F6FF", size=13), legend=dict(orientation="h", y=1.12,
                      x=0, title_text="", font=dict(color="#F2F6FF")),
                      margin=dict(l=25, r=25, t=80, b=55), bargap=.24)
    fig.update_xaxes(showgrid=False, linecolor="#526078", tickfont=dict(color="#DFE8FA"),
                     title_text="")
    fig.update_yaxes(range=[0, 110], gridcolor="#354159", zeroline=False,
                     tickfont=dict(color="#DFE8FA"), title_font=dict(color="#F2F6FF"))
    st.plotly_chart(fig, theme=None, width="stretch")


def table(frame, cols=None, key=None, height=430):
    if frame is None or frame.empty:
        st.info("Belum ada siswa atau data pada pilihan ini.")
        return None
    shown = frame[cols].reset_index(drop=True) if cols else frame.reset_index(drop=True)
    averages = {"rata_terkini", "rata_semua_to", "rata_3_to", "rata_semua_mapel",
                "rata_3_mapel", "skor", "Median nilai", "Median", "Rata semua TO",
                "Rata 3 terakhir", "Proyeksi", "Rentang 10–90%"}
    display_format = {col: st.column_config.NumberColumn(col, format="%.2f")
                      for col in shown.columns if col in averages and pd.api.types.is_numeric_dtype(shown[col])}
    if "nama" in shown and "student_id" in frame:
        key = key or "students_" + "_".join(shown.columns)
        display_format["nama"] = student_name_column(frame, key + "_name_click")
    return st.dataframe(shown, hide_index=True, width="stretch", height=min(height, 45+36*(len(shown)+1)),
                        column_config=display_format, key=key, on_select="ignore",
                        selection_mode="single-row" if key else "multi-row")


def plot(fig):
    fig.update_layout(paper_bgcolor="#fff", plot_bgcolor="#fff", height=320,
                      font=dict(color="#20332e", size=13),
                      margin=dict(l=18, r=18, t=24, b=20),
                      legend=dict(font=dict(color="#20332e"), bgcolor="#fff"))
    fig.update_xaxes(tickfont=dict(color="#20332e"), title_font=dict(color="#20332e"), gridcolor="#e1e8e4")
    fig.update_yaxes(tickfont=dict(color="#20332e"), title_font=dict(color="#20332e"), gridcolor="#e1e8e4")
    st.plotly_chart(fig, theme=None, width="stretch")


def secret(name):
    try:
        return str(st.secrets.get(name, "")).strip()
    except Exception:
        return ""


@st.cache_data(ttl=180, show_spinner="Membaca nilai dari HORIZON...")
def load_data(url, token):
    return fetch_gas(url, token)


with st.sidebar:
    st.header("Cakupan")
    population = st.selectbox("Siswa", ["Peserta TKA", "Semua Siswa", "Tidak Ikut"], key='filter_siswa')
    with st.expander("Pengaturan analisis"):
        target = st.number_input("Target nilai", 0., 100., 65., 1., key='filter_target_nilai')
    stored_token = secret("GAS_API_TOKEN")
    with st.expander("Ubah koneksi API bila diperlukan", expanded=not bool(stored_token)):
        api_url = st.text_input("URL Web App GAS", value=secret("HORIZON_API_URL_OVERRIDE") or GAS_API_URL, key='filter_url_web_app_gas')
        token = st.text_input("Token API", value=stored_token, type="password", key='filter_token_api')
        st.caption("Alamat/token dalam kotak ini hanya berlaku pada sesi aktif. Untuk mengubahnya permanen, gunakan pengaturan Secrets aplikasi Streamlit.")
    st.caption("Sumber selalu API Google Apps Script (hanya baca).")
    if st.button("Muat ulang nilai dari GAS"):
        load_data.clear()
        st.rerun()

if not token:
    st.error("Koneksi belum diatur: tambahkan GAS_API_TOKEN ke Secrets aplikasi Streamlit satu kali. Tidak perlu memasukkan lagi setiap membuka dashboard.")
    st.code('GAS_API_TOKEN = "token-lama-bapak"', language="toml")
    st.stop()
try:
    data = load_data(api_url, token)
except SourceError as exc:
    st.error("Tidak bisa membaca API HORIZON: " + str(exc))
    st.info("Aplikasi tidak menampilkan angka demo sebagai pengganti data asli. Periksa alamat deployment API dan aksesnya.")
    st.stop()

all_features = triage(student_features(data), target)
to_completed, to_remaining = remaining_to(data)
subject_work = subject_brief(data, target)
homeroom_work = homeroom_brief(subject_work)
global_rank = ranking(data, 3)
rank_map = (global_rank.set_index("student_id").peringkat.to_dict() if not global_rank.empty else {})
all_features["Peringkat sekolah (3 TO)"] = all_features.student_id.map(rank_map)
class_options = ["Semua kelas"] + sorted(data.kelas.astype(str).unique().tolist())
with st.sidebar:
    school_class = st.selectbox("Kelas asal", class_options, key='filter_kelas_asal')
    st.caption(f"{data.student_id.nunique()} siswa tercatat di sumber HORIZON.")
    st.metric("Perkiraan sisa TO", to_remaining, help=f"Rencana 14 putaran; {to_completed} putaran teridentifikasi dari Matematika/Bahasa Indonesia. Bahasa Inggris tidak digunakan untuk hitungan ini.")

scoped = all_features.copy()
if population == "Peserta TKA":
    scoped = scoped[scoped.status_tka.str.casefold() == "ikut"]
elif population == "Tidak Ikut":
    scoped = scoped[scoped.status_tka.str.casefold() == "tidak ikut"]
if school_class != "Semua kelas":
    scoped = scoped[scoped.kelas_asal.astype(str) == school_class]

tabs = st.tabs(["Tindakan Hari Ini", "Siswa & Rapor", "Strategi Fu–On", "Simulasi Skenario", "Kualitas Data"],
               key="decision_tab", on_change="rerun")

if tabs[0].open:
    with tabs[0]:
        st.subheader("Siapa melakukan apa setelah TO berikutnya?")
        audience = st.segmented_control("Pandangan", ["Sekolah", "Wali Kelas", "Guru Mapel"],
                                        default="Sekolah", key="daily_audience")
        if audience == "Sekolah":
            st.caption("Urutan ini berasal dari nilai, jarak target, tren, dan fluktuasi; bukan probabilitas lulus atau prediksi dampak pengajaran.")
            a, b, c, d, e = st.columns(5)
            with a: card("Siswa cakupan", str(len(scoped)), f"{population}, {school_class}")
            with b: card("Prioritas tinggi", str(int(scoped.status.eq("Prioritas tinggi").sum())))
            with c: card("Perlu dipantau", str(int(scoped.status.eq("Perlu dipantau").sum())))
            with d: card("Data terbatas", str(int(scoped.status.eq("Data terbatas").sum())))
            with e: card("TO tersisa", str(to_remaining), "dari rencana 14")
            p1, p2, p3 = st.columns([1.2, 1, 1])
            mode = p1.selectbox("Daftar tindakan", ["Semua perhatian", "Prioritas tinggi", "Perlu dipantau",
                                                  "Relatif siap", "Potensi naik", "Peringatan dini", "Data terbatas"], key='filter_daftar_tindakan')
            top_n = p2.selectbox("Tampilkan", [5, 10], key='filter_tampilkan')
            per_class = p3.toggle("Top per kelas", value=False, key='filter_top_per_kelas')
            candidates = scoped.copy()
            if mode == "Semua perhatian":
                candidates = candidates[candidates.status.isin(["Prioritas tinggi", "Perlu dipantau", "Data terbatas"])]
            elif mode in ["Prioritas tinggi", "Perlu dipantau", "Relatif siap", "Data terbatas"]:
                candidates = candidates[candidates.status == mode]
            elif mode == "Potensi naik":
                candidates = candidates[candidates.potensi_naik]
            else:
                candidates = candidates[candidates.peringatan_dini]
            if mode == "Potensi naik":
                candidates = candidates.sort_values(["potensi_pengembangan", "student_id"], ascending=[False, True])
            elif mode == "Peringatan dini":
                candidates = candidates.sort_values(["tren", "fluktuasi", "student_id"], ascending=[True, False, True])
            else:
                candidates = candidates.sort_values(["urutan_perhatian", "student_id"], ascending=[False, True])
            shown = (candidates.groupby("kelas_asal", sort=True).head(top_n)
                     if per_class and school_class == "Semua kelas" else candidates.head(top_n))
            cols = ["student_id", "nama", "kelas_asal", "status_tka", "status", "Peringkat sekolah (3 TO)",
                    "rata_terkini", "mapel_terlemah", "alasan_utama", "langkah_berikutnya"]
            st.write(f"**{len(shown)} siswa** pada daftar ini. Klik nama untuk membuka rapor siswa.")
            table(shown, cols, key="daily_student")
            with st.expander("Kuota perhatian berdasarkan persentase"):
                percentage = st.number_input("Persentase dari cakupan ini", 1, 100, 25, key='filter_persentase_dari_cakupan_ini')
                number = attention_count(len(scoped), int(percentage))
                pool = scoped.sort_values(["urutan_perhatian", "student_id"], ascending=[False, True]).head(number)
                st.write(f"{percentage}% dari {len(scoped)} siswa = **{number} siswa** (dibulatkan ke atas).")
                table(pool, ["nama", "kelas_asal", "status", "mapel_terlemah", "langkah_berikutnya"])
        else:
            role = "Wali Kelas" if audience == "Wali Kelas" else "Guru Mapel"
            a,b,c = st.columns(3)
            options = sorted(scoped.kelas_asal.astype(str).unique().tolist())
            if not options:
                options = sorted(data.kelas.astype(str).unique().tolist())
            if audience == "Wali Kelas":
                role_class = a.selectbox("Kelas wali", options, key="wk_class")
                subject = None
            else:
                subject = a.selectbox("Mata pelajaran", CORE, key="teacher_subject")
                role_class = b.selectbox("Kelas yang diajar", ["Semua kelas"]+options, key="teacher_class")
            list_size = c.selectbox("Jumlah siswa", [5, 10], key=f"size_{audience}")
            ids = set(scoped.student_id)
            if role_class != "Semua kelas":
                ids &= set(all_features.loc[all_features.kelas_asal.astype(str) == role_class, "student_id"])
            if audience == "Wali Kelas":
                work = homeroom_work[homeroom_work.student_id.isin(ids)].copy()
                priority = {"Care khusus":4,"Cek data":3,"Perlu koordinasi":2,"Pantau rutin":1}
                work["urutan"] = work.kategori_wk.map(priority)
                work = work.sort_values(["urutan","jumlah_sinyal","student_id"],ascending=[False,False,True])
                visible = work.head(list_size)
                columns = ["student_id","nama","kelas","status_tka","kategori_wk","rata_semua_mapel",
                           "rata_3_mapel","mapel_fokus","langkah_wk"]
                st.caption("Wali kelas melihat sinyal dari tiga mapel. 'Care khusus' berarti dua atau lebih sinyal yang perlu ditinjau guru, bukan diagnosis siswa.")
            else:
                work = subject_work[(subject_work.student_id.isin(ids)) & (subject_work.mapel == subject)].copy()
                priority = {"Prioritas tinggi":5,"Peringatan dini":4,"Data terbatas":3,
                            "Perlu penguatan":2,"Jaga stabilitas":1}
                work["urutan"] = work.kategori.map(priority)
                work = work.sort_values(["urutan","rata_3_to","student_id"],ascending=[False,True,True])
                visible = (work.groupby("kelas",sort=True).head(list_size)
                           if role_class == "Semua kelas" else work.head(list_size))
                columns = ["student_id","nama","kelas","status_tka","kategori","rata_semua_to",
                           "rata_3_to","perubahan_3_to","alasan","saran_awal"]
                st.caption("Angka semua TO dan 3 TO terakhir per siswa. Perubahan hanya dihitung jika ada sedikitnya enam nilai; penyebab harus dicek dari jawaban soal.")
            st.write(f"**{len(visible)} siswa** untuk {role} - {subject or role_class}.")
            table(visible, columns)
            if not visible.empty:
                with st.expander("Form tindakan dan cetak untuk " + role):
                    st.caption("Saran otomatis boleh diubah oleh guru. Catatan di kolom terakhir tidak disimpan permanen; unduh PDF sebelum menutup sesi.")
                    edit = visible[columns].copy()
                    edit["Keputusan guru/WK"] = ""
                    edited = st.data_editor(edit, hide_index=True, width="stretch", height=380,
                                            disabled=columns, column_config={"nama": student_name_column(edit, "action_form_name_click")}, key=f"form_{audience}_{subject}_{role_class}_{population}")
                    actions = dict(zip(edited.student_id, edited["Keputusan guru/WK"].fillna("")))
                    label = (f"{role} {role_class}" if subject is None else
                             f"Guru {subject} - {role_class}")
                    pdf = role_pdf(visible, role, label, to_completed, to_remaining, actions)
                    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", label)
                    st.download_button("Unduh lembar tindakan (PDF)", pdf,
                                       file_name=f"tindakan_{safe}.pdf", mime="application/pdf")

if tabs[1].open:
    with tabs[1]:
        st.subheader("Ranking, profil, dan rapor siswa")
        focused = st.session_state.get("report_focus", False)
        if focused:
            st.button("← Kembali ke daftar sebelumnya", on_click=return_to_list)
        ranking_area = st.expander("Lihat daftar peringkat", expanded=not focused)
        with ranking_area:
            a,b = st.columns(2)
            provider = a.selectbox("Sumber TO", ["Gabungan", "PENABUR", "HOLIS"], key='filter_sumber_to')
            window = b.selectbox("Jendela ranking", ["3 TO terakhir", "5 TO terakhir", "Semua TO"], key='filter_jendela_ranking')
            limit = {"3 TO terakhir": 3, "5 TO terakhir": 5, "Semua TO": None}[window]
            cohort_ids = set(scoped.student_id)
            cohort_data = data[data.student_id.isin(cohort_ids)]
            to_data = select_assessments(cohort_data, provider)
            ranked = ranking(to_data, limit)
            if provider != "Gabungan" and "assessment_code" not in data:
                st.warning("Kode TO tidak tersedia: ranking menurut penyelenggara belum dapat dihitung.")
            if not ranked.empty:
                st.caption(f"Peringkat di bawah dihitung ulang untuk {len(ranked)} siswa dengan ketiga mapel di cakupan ini. MT/BI/BIG = PENABUR; MTH/BIH/BIGH = HOLIS.")
                table(ranked, ["peringkat", "nama", "kelas", "status_tka", "skor", "tren", "fluktuasi", "profil", "mapel_terlemah"])
            else:
                st.info("Belum ada tiga mapel lengkap untuk ranking pada pilihan ini.")
        report_ids = set(scoped.student_id)
        requested_id = st.session_state.get("report_student")
        if requested_id in set(all_features.student_id):
            report_ids.add(requested_id)
        if not report_ids:
            st.info("Tidak ada siswa pada cakupan peserta/kelas yang dipilih.")
        else:
            directory = (all_features[all_features.student_id.isin(report_ids)][["student_id", "nama", "kelas_asal"]]
                         .drop_duplicates("student_id").sort_values(["nama", "student_id"]).set_index("student_id"))
            if requested_id not in directory.index:
                st.session_state.pop("report_student", None)
            if requested_id in report_ids and requested_id not in set(scoped.student_id):
                st.caption("Siswa yang dibuka berada di luar filter daftar. Filter sebelumnya tetap dipertahankan.")
            selected = st.selectbox("Pilih siswa untuk analisis dan rapor", directory.index.tolist(),
                                    format_func=lambda sid: f"{directory.loc[sid, 'nama']} ({directory.loc[sid, 'kelas_asal']})",
                                    key="report_student")
            st.subheader(f"{directory.loc[selected, 'nama']} · {directory.loc[selected, 'kelas_asal']}")
            selected_data = data[data.student_id == selected]
            analysis = student_analysis(selected_data, target)
            school_position = rank_map.get(selected)
            if school_position:
                st.write(f"**Peringkat sekolah 3 TO: {school_position} dari {len(global_rank)} siswa.** "
                         "Peringkat ini memakai gabungan TO dan seluruh siswa, tidak mengikuti filter ranking di atas.")
            st.write("**Mapel yang perlu ditinjau:** " + analysis["weakness"])
            st.write("**Ruang peningkatan:** " + analysis["growth"])
            st.caption(analysis["caution"])
            subject_rows = []
            for subject in analysis["subjects"]:
                subject_rows.append({"Mapel": subject["mapel"], "Jumlah TO": subject["n"],
                                     "3 nilai terakhir": " / ".join(map(str, subject["last"])),
                                     "Rata semua TO": subject["all_mean"],
                                     "Rata 3 terakhir": subject["mean"], "Arah per TO": subject["trend"],
                                     "Catatan": subject["interpretasi"]})
            table(pd.DataFrame(subject_rows))
            line = px.line(selected_data.sort_values("assessment_order"), x="assessment_order", y="score",
                           color="mapel", markers=True,
                           labels={"assessment_order":"Urutan TO per mapel", "score":"Nilai", "mapel":"Mapel"})
            plot(line)
            pdf = build_report(analysis, scope=f"Seluruh sekolah, {len(global_rank)} siswa dengan tiga mapel")
            filename = "rapor_horizon_" + re.sub(r"[^a-zA-Z0-9_-]", "_", selected) + ".pdf"
            st.download_button("Unduh rapor siswa (PDF)", pdf, file_name=filename,
                               mime="application/pdf", key=f"pdf_{selected}")
            st.caption("Rapor hanya menampilkan analisis otomatis. Form tindakan untuk Wali Kelas dan Guru Mapel ada di Tindakan Hari Ini.")

if tabs[2].open:
    with tabs[2]:
        st.subheader("Strategi penempatan Fu-Ch-Am-Pi-On")
        st.caption("Ringkasan dan grafik mengikuti filter sidebar; penempatan kelas tetap memakai semua siswa agar kapasitas tidak berubah. Peringkat menunjukkan capaian, bukan potensi perkembangan.")
        graded = data[data.score.notna() & data.student_id.isin(scoped.student_id)]
        a,b,c,d,e = st.columns(5)
        with a: overview_card("Siswa terdaftar", len(scoped), population, "#6461e8")
        with b: overview_card("Sudah ada nilai", graded.student_id.nunique(), "minimal satu nilai TO", "#28be89")
        with c: overview_card("Belum ada nilai", len(scoped)-graded.student_id.nunique(), "butuh pemeriksaan", "#f6a51f")
        with d: overview_card("Mencapai target", int((scoped.data_memadai & scoped.rata_terkini.ge(target)).sum()),
                              f"rata 3 TO ≥ {target:g}; data memadai", "#229e91")
        with e: overview_card("Perlu perhatian", int(scoped.status.isin(["Prioritas tinggi", "Perlu dipantau"]).sum()),
                              "indikasi, bukan vonis TKA", "#e8636b")
        chart_source = st.selectbox("Sumber grafik TO", ["PENABUR", "HOLIS"],
                                    format_func=lambda source: "BPK PENABUR" if source == "PENABUR" else "Internal HOLIS",
                                    key="chart_provider")
        st.markdown('<div style="background:#152032;border-radius:18px;padding:18px 25px 2px;'
                    'margin-top:16px"><div style="color:#fff;font-size:20px;font-weight:750">'
                    'Tren skor TO ' + ('BPK PENABUR' if chart_source == 'PENABUR' else 'internal HOLIS') +
                    '</div><div style="color:#cbd5e4">Rata-rata siswa yang punya nilai; '
                    'mapel tanpa nilai tidak ditampilkan.</div></div>',
                    unsafe_allow_html=True)
        cohort_chart(data[data.student_id.isin(scoped.student_id)], chart_source)
        st.caption("PENABUR: MT/BI/BIG 01, 02, 03; HOLIS: MTH/BIH/BIGH menurut nomor TO masing-masing. "
                   "Jika Bahasa Inggris belum ada pada TO PENABUR 1–3, grafik hanya menampilkan Matematika dan Bahasa Indonesia. "
                   "Perubahan rerata juga dipengaruhi peserta, jumlah nilai, dan kesulitan TO.")
        n_tka = int(all_features.status_tka.str.casefold().eq("ikut").sum())
        n_ready_tka = int((all_features.status_tka.str.casefold().eq("ikut") &
                           all_features.data_memadai).sum())
        st.write(f"**{len(all_features)} siswa**, **{n_tka} peserta TKA** teridentifikasi; "
                 f"**{n_ready_tka} peserta** memiliki minimal 3 nilai di masing-masing mapel utama.")
        st.caption("Fu (21) dan Ch (31) harus 100% peserta TKA. Sisa peserta TKA masuk Am lebih dahulu; "
                   "hanya nonpeserta yang mengisi kekurangan Am, lalu Pi dan On.")
        if len(all_features) != 140 or not all_features.status_tka.str.casefold().isin(["ikut", "tidak ikut"]).all():
            st.warning("Usulan kelas ditahan sampai 140 siswa dan status peserta TKA seluruh siswa lengkap.")
        else:
            bottom = st.slider("Minimum siswa terbawah di On (termasuk data kurang)", 0, 29, 10, key='filter_minimum_siswa_terbawah_di_on_termasuk_data_kurang')
            try:
                features = student_features(data)
                original = allocate(features, bottom)
                overall = (global_rank[["student_id", "peringkat"]].rename(
                    columns={"peringkat":"Peringkat sekolah (3 TO)"}) if not global_rank.empty
                    else pd.DataFrame(columns=["student_id", "Peringkat sekolah (3 TO)"]))
                original = original.merge(overall, on="student_id", how="left")
                incomplete = original[~original.data_memadai]
                if not incomplete.empty:
                    sparse_tka = int(incomplete.status_tka.str.casefold().eq("ikut").sum())
                    sparse_non = len(incomplete) - sparse_tka
                    st.warning(f"Data kurang: {sparse_tka} peserta TKA masuk Am sementara; "
                               f"{sparse_non} nonpeserta masuk On sementara. "
                               "Keduanya bukan penilaian kemampuan. Lengkapi nilai untuk meninjau ulang usulan.")
                    with st.expander("Lihat alasan penempatan sementara", expanded=True):
                        table(incomplete, ["nama", "kelas_asal", "status_tka", "jumlah_nilai",
                                           "Peringkat sekolah (3 TO)", "rekomendasi", "alasan"])
                summary = (original.groupby("rekomendasi").agg(Siswa=("student_id", "size"),
                           Peserta_TKA=("status_tka", lambda v:int(v.str.casefold().eq("ikut").sum())),
                           Median_nilai=("rata_terkini", "median"))
                           .reindex(["Fu", "Ch", "Am", "Pi", "On"]).round(2).reset_index())
                summary.insert(1, "Target kursi", summary.rekomendasi.map(
                    {"Fu":21, "Ch":31, "Am":30, "Pi":29, "On":29}))
                summary = summary.rename(columns={"rekomendasi":"Kelompok", "Siswa":"Total siswa",
                                                  "Peserta_TKA":"Ikut TKA (bagian dari total)",
                                                  "Median_nilai":"Median nilai"})
                st.caption("Kolom Total siswa = penghuni kelas. Fu dan Ch wajib seluruhnya ikut TKA; "
                           "kolom Ikut TKA adalah bagian dari total tersebut di Am/Pi/On.")
                table(summary)
                group = st.selectbox("Lihat kelompok", ["Semua", "Fu", "Ch", "Am", "Pi", "On"], key='filter_lihat_kelompok')
                view = original if group == "Semua" else original[original.rekomendasi == group]
                st.write(f"**{group}: {len(view)} siswa**" +
                         (" (target Fu 21, Ch 31, Am 30, Pi 29, On 29)" if group == "Semua" else ""))
                table(view, ["nama", "kelas_asal", "status_tka", "Peringkat sekolah (3 TO)",
                             "jumlah_nilai", "rata_terkini", "tren", "fluktuasi",
                             "potensi_pengembangan", "rekomendasi", "alasan"])
                with st.expander("Sesuaikan siswa tanpa menulis ke Google Sheet"):
                    editor = original[["student_id", "nama", "Peringkat sekolah (3 TO)", "rekomendasi"]].copy()
                    editor["Pilihan Bapak"] = editor.rekomendasi
                    edited = st.data_editor(editor, disabled=["student_id", "nama", "Peringkat sekolah (3 TO)", "rekomendasi"],
                                            hide_index=True, width="stretch", height=380,
                                            column_config={"nama": student_name_column(editor, "placement_name_click"), "Pilihan Bapak": st.column_config.SelectboxColumn(
                                                "Pilihan Bapak", options=["Fu", "Ch", "Am", "Pi", "On"], required=True)},
                                            key="placement_editor")
                    changes = edited[edited["Pilihan Bapak"] != edited.rekomendasi]
                    result = original
                    if not changes.empty:
                        try:
                            result = allocate(features, bottom, dict(zip(changes.student_id, changes["Pilihan Bapak"])))
                            result = result.merge(overall, on="student_id", how="left")
                            st.success("Pertukaran aman menjaga kapasitas kelas dan aturan peserta TKA.")
                        except ValueError as exc:
                            st.error("Pilihan manual belum dapat diterapkan: " + str(exc))
                    st.download_button("Unduh usulan kelas CSV", result.to_csv(index=False).encode("utf-8-sig"),
                                       "usulan_kelas_fu_on.csv", "text/csv")
                st.caption("Ch dapat berisi siswa berperingkat tinggi yang berindikasi masih bisa berkembang. Skor kecocokan adalah aturan transparan, bukan jaminan kenaikan nilai.")
            except ValueError as exc:
                st.error("Penempatan belum bisa dihitung: " + str(exc))

if tabs[3].open:
    with tabs[3]:
        st.subheader("Simulasi 5.000 skenario: siapa perlu tindakan?")
        st.info("Angka seperti 64% berarti 3.200 dari 5.000 skenario **rata-rata TO mendatang** "
                "berada di bawah target, **bukan 64% peluang gagal TKA resmi**. "
                "Model memakai arah dan variasi lima nilai terakhir tiap mapel. "
                "Hasil bergantung pada asumsi, bukan jaminan hasil intervensi.")
        with st.expander("Bagaimana 5.000 skenario dihitung?", expanded=False):
            st.write("Untuk setiap siswa dan mapel, model membaca paling banyak lima nilai terakhir, "
                     "memperkirakan arah serta variasinya, lalu membuat 5.000 kemungkinan nilai TO mendatang. "
                     "Rata-rata TO mendatang dari tiga mapel dibandingkan dengan target. "
                     "Median dan rentang 10–90% menggambarkan sebaran skenario, bukan nilai ujian TKA resmi.")
            st.write("Perubahan asumsi kenaikan hanya menunjukkan **bagaimana hasil model bergeser jika nilai "
                     "mendatang naik sejumlah poin**; bukan bukti bahwa latihan tertentu akan menaikkannya.")
            st.caption("Lebih banyak percobaan menstabilkan perhitungan, bukan memperbaiki asumsi atau "
                       "mengkalibrasi probabilitas terhadap hasil TKA sebenarnya. Hasil tetap sama jika data dan pengaturan sama.")
        st.markdown("**Cara membaca angka untuk tindakan**")
        a, b, c = st.columns(3)
        with a: overview_card("40% di bawah target", "Pantau + satu fokus", "Guru cek satu mapel; evaluasi TO berikutnya", "#27a68e")
        with b: overview_card("64% di bawah target", "Penguatan terarah", "Guru pilih topik dari jawaban salah; cek TO berikutnya", "#df9c25")
        with c: overview_card("75% di bawah target", "Koordinasi segera", "Wali kelas + guru mapel; tindak lanjut dan cek TO", "#dd6670")
        st.caption("40% dan 64% sama-sama perlu dipantau, tetapi 64% ditindak lebih aktif. "
                   "Batas kerja: <35% jaga stabilitas; 35–49% pantau; 50–69% penguatan; ≥70% koordinasi segera. "
                   "Ini aturan prioritas internal, bukan ambang kelulusan TKA atau ukuran keberhasilan terapi belajar.")
        if scoped.empty:
            st.info("Tidak ada siswa dalam cakupan sidebar.")
        elif to_remaining == 0:
            st.info("Rencana 14 TO sudah teridentifikasi; tidak ada TO tersisa untuk disimulasikan.")
        else:
            provider = st.selectbox("Gunakan nilai TO", ["Gabungan", "PENABUR", "HOLIS"],
                                    key="simulation_provider", help="Gabungan memakai dua sumber dengan tingkat kesulitan yang mungkin berbeda.")
            if provider == "Gabungan":
                st.warning("Tren gabungan mencampur TO PENABUR (MT/BI/BIG) dan internal HOLIS (MTH/BIH/BIGH). "
                           "Bila kesulitannya berbeda, arah dan persentase skenario bisa menyesatkan. "
                           "Bandingkan dengan pilihan sumber tunggal.")
            future = st.slider("Berapa TO mendatang untuk diuji?", 1, to_remaining, min(3, to_remaining),
                               key="simulation_future")
            with st.expander("Uji asumsi kenaikan (opsional)"):
                lifts = {subject: st.slider("Jika " + subject + " naik sebanyak (poin)", 0, 15, 0,
                                             key="scenario_lift_" + str(i)) for i, subject in enumerate(CORE)}
            if st.toggle("Jalankan 5.000 skenario", value=False, key="run_scenario"):
                source = select_assessments(data[data.student_id.isin(scoped.student_id)], provider)
                if source.empty:
                    st.info("Belum ada nilai yang sesuai sumber TO dan cakupan ini.")
                else:
                    @st.cache_data(ttl=180, show_spinner="Menghitung 5.000 skenario per siswa...")
                    def cached_simulation(frame, threshold, remaining, assumptions):
                        return simulate(frame, threshold, remaining, 5000, dict(assumptions))

                    scenario, _ = cached_simulation(source, target, future, tuple(lifts.items()))
                    # Preserve students with no scored record under the selected provider.
                    roster = scoped[["student_id", "nama", "kelas_asal", "status_tka"]].drop_duplicates("student_id")
                    scenario = roster.merge(scenario.drop(columns=["nama", "status_tka", "kelas"], errors="ignore"),
                                            on="student_id", how="left")
                    scenario["status"] = scenario.status.fillna("Data terbatas")
                    scenario["mapel_penghambat"] = scenario.mapel_penghambat.fillna("Belum ada nilai")
                    scenario["Tindakan awal"] = scenario.apply(
                        lambda row: simulation_guidance(row.peluang_belum_target, row.mapel_penghambat), axis=1)
                    scenario["Skenario di bawah target"] = scenario.peluang_belum_target.map(
                        lambda v: f"{v:.1%}" if pd.notna(v) else "Data kurang")
                    scenario["Proyeksi"] = scenario.proyeksi.round(2)
                    scenario["Rentang 10–90%"] = scenario.apply(
                        lambda row: (f"{row.batas_bawah:.2f}–{row.batas_atas:.2f}"
                                     if pd.notna(row.batas_bawah) else "Data kurang"), axis=1)
                    ranked = scenario.sort_values(["peluang_belum_target", "student_id"],
                                                  ascending=[False, True], na_position="last")
                    a, b, c = st.columns(3)
                    valid = scenario.peluang_belum_target.notna()
                    with a: card("Siswa dianalisis", str(int(valid.sum())), "memiliki min. 3 nilai per mapel")
                    with b: card("Koordinasi segera", str(int(scenario.peluang_belum_target.ge(.70).sum())), "≥70% skenario di bawah target")
                    with c: card("Data perlu diperiksa", str(int((~valid).sum())), "tidak diberi persentase semu")
                    if valid.any():
                        chart = px.scatter(scenario.loc[valid], x="proyeksi", y="peluang_belum_target",
                                           color="status", hover_name="nama", hover_data={"kelas_asal": True,
                                           "mapel_penghambat": True, "proyeksi": ":.2f",
                                           "peluang_belum_target": ":.1%"},
                                           labels={"proyeksi": "Median rata-rata TO mendatang",
                                                   "peluang_belum_target": "Skenario di bawah target",
                                                   "kelas_asal": "Kelas asal", "mapel_penghambat": "Mapel fokus"},
                                           color_discrete_map={"Prioritas tinggi": "#d65762",
                                                               "Perlu dipantau": "#c88616",
                                                               "Relatif siap": "#128367"})
                        chart.update_yaxes(range=[0, 1.05], tickformat=".0%")
                        chart.add_hline(y=.70, line_dash="dot", line_color="#a8434f")
                        chart.add_vline(x=target, line_dash="dot", line_color="#386d5a")
                        plot(chart)
                    table(ranked, ["nama", "kelas_asal", "status_tka", "status", "Skenario di bawah target",
                                   "Proyeksi", "Rentang 10–90%", "mapel_penghambat", "Tindakan awal"], height=580)
                    st.caption(f"{len(scenario)} siswa dalam cakupan; 5.000 skenario acak per siswa. "
                               "Persentase belum dikalibrasi memakai hasil TKA nyata; gunakan bersama review butir oleh guru.")
                    if any(lifts.values()):
                        st.caption("Angka pada tabel sudah memasukkan asumsi kenaikan yang Bapak atur. "
                                   "Ubah slider ke 0 untuk membandingkan kondisi tanpa asumsi tambahan; "
                                   "selisihnya bukan dampak intervensi yang terbukti.")

if tabs[4].open:
    with tabs[3]:
        st.subheader("Apakah data sudah cukup untuk dipakai mengambil keputusan?")
        a,b,c = st.columns(3)
        with a: card("Siswa data memadai", str(int(all_features.data_memadai.sum())),
                     f"dari {len(all_features)} siswa, min. 3 TO per mapel")
        with b: card("Perlu dilengkapi", str(int((~all_features.data_memadai).sum())))
        with c: card("Status TKA belum pasti", str(int((~all_features.status_tka.str.casefold().isin(["ikut", "tidak ikut"])).sum())))
        missing = all_features[~all_features.data_memadai]
        if not missing.empty:
            st.write("**Siswa dengan data belum cukup**")
            table(missing, ["nama", "kelas_asal", "status_tka", "mapel_tersedia", "status"])
        st.caption("Nilai tanpa tiga TO di salah satu mapel utama diberi label Data terbatas, bukan dianggap nilai nol.")
        with st.expander("Periksa distribusi TO PENABUR / HOLIS"):
            provider = st.selectbox("Sumber", ["Gabungan", "PENABUR", "HOLIS"], key="quality_provider")
            qa = select_assessments(data, provider)
            if "assessment_code" not in qa:
                st.info("Kode TO tidak tersedia dalam data API.")
            elif not qa.empty:
                stats = qa.groupby(["mapel", "assessment_code"]).score.agg(
                    Jumlah="size", Median="median", Sebaran="std").round(2).reset_index()
                table(stats)
                st.caption("Median dan sebaran merupakan sinyal memeriksa perbedaan kesulitan, bukan bukti soal buruk. Analisis butir memerlukan jawaban per nomor.")
            else:
                st.info("Tidak ada kode TO untuk pilihan ini.")
        st.caption("Simulasi 5.000 skenario dan langkah tindak lanjut kini ada di tab Simulasi Skenario.")
        st.info("Panel sebelum-sesudah intervensi belum ditampilkan karena memerlukan log tindakan yang konsisten. Rapor siswa berisi analisis otomatis; lembar tindakan guru dan wali kelas diunduh terpisah tanpa penyimpanan.")
