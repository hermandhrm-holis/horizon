"""HORIZON: four decision-focused dashboards, exclusively backed by the GAS API."""

import re

import pandas as pd
import plotly.express as px
import streamlit as st

from allocation import (allocate, attention_count, ranking, select_assessments,
                        student_features, triage)
from briefing import homeroom_brief, remaining_to, role_pdf, subject_brief
from engine import CORE, SourceError, fetch_gas, simulate
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


def card(label, value, note=""):
    st.markdown(f'<div class="card"><div class="card-label">{label}</div>'
                f'<div class="card-value">{value}</div><div class="card-note">{note}</div></div>',
                unsafe_allow_html=True)


def table(frame, cols=None, key=None, height=430):
    if frame is None or frame.empty:
        st.info("Belum ada siswa atau data pada pilihan ini.")
        return None
    shown = frame[cols].reset_index(drop=True) if cols else frame.reset_index(drop=True)
    return st.dataframe(shown, hide_index=True, width="stretch", height=min(height, 45+36*(len(shown)+1)),
                        key=key, on_select="rerun" if key else "ignore",
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
    population = st.selectbox("Siswa", ["Peserta TKA", "Semua Siswa", "Tidak Ikut"])
    with st.expander("Pengaturan analisis"):
        target = st.number_input("Target nilai", 0., 100., 65., 1.)
    stored_token = secret("GAS_API_TOKEN")
    with st.expander("Ubah koneksi API bila diperlukan", expanded=not bool(stored_token)):
        api_url = st.text_input("URL Web App GAS", value=secret("HORIZON_API_URL_OVERRIDE") or GAS_API_URL)
        token = st.text_input("Token API", value=stored_token, type="password")
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
    school_class = st.selectbox("Kelas asal", class_options)
    st.caption(f"{data.student_id.nunique()} siswa tercatat di sumber HORIZON.")
    st.metric("Perkiraan sisa TO", to_remaining, help=f"Rencana 14 putaran; {to_completed} putaran teridentifikasi dari Matematika/Bahasa Indonesia. Bahasa Inggris tidak digunakan untuk hitungan ini.")

scoped = all_features.copy()
if population == "Peserta TKA":
    scoped = scoped[scoped.status_tka.str.casefold() == "ikut"]
elif population == "Tidak Ikut":
    scoped = scoped[scoped.status_tka.str.casefold() == "tidak ikut"]
if school_class != "Semua kelas":
    scoped = scoped[scoped.kelas_asal.astype(str) == school_class]

tabs = st.tabs(["Tindakan Hari Ini", "Siswa & Rapor", "Strategi Fu–On", "Kualitas Data"],
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
                                                  "Relatif siap", "Potensi naik", "Peringatan dini", "Data terbatas"])
            top_n = p2.selectbox("Tampilkan", [5, 10])
            per_class = p3.toggle("Top per kelas", value=False)
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
            st.write(f"**{len(shown)} siswa** pada daftar ini. Klik baris untuk penjelasan lebih rinci.")
            event = table(shown, cols, key="daily_student")
            if event is not None and len(event.selection.rows):
                selected_id = shown.reset_index(drop=True).iloc[event.selection.rows[0]].student_id
                analysis = student_analysis(data[data.student_id == selected_id], target)
                st.write("**Perhatian utama:** " + analysis["weakness"])
                st.write("**Ruang peningkatan:** " + analysis["growth"])
            with st.expander("Kuota perhatian berdasarkan persentase"):
                percentage = st.number_input("Persentase dari cakupan ini", 1, 100, 25)
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
                                            disabled=columns, key=f"form_{audience}_{subject}_{role_class}_{population}")
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
        a,b = st.columns(2)
        provider = a.selectbox("Sumber TO", ["Gabungan", "PENABUR", "HOLIS"])
        window = b.selectbox("Jendela ranking", ["3 TO terakhir", "5 TO terakhir", "Semua TO"])
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
        if not cohort_ids:
            st.info("Tidak ada siswa pada cakupan peserta/kelas yang dipilih.")
        else:
            directory = (scoped[["student_id", "nama", "kelas_asal"]]
                         .drop_duplicates("student_id").sort_values(["nama", "student_id"]).set_index("student_id"))
            selected = st.selectbox("Pilih siswa untuk analisis dan rapor", directory.index.tolist(),
                                    format_func=lambda sid: f"{directory.loc[sid, 'nama']} ({directory.loc[sid, 'kelas_asal']})",
                                    key="report_student")
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
        st.caption("Seluruh 140 siswa digunakan agar kapasitas tidak berubah mengikuti filter sidebar. Peringkat menunjukkan capaian; usulan kelas mempertimbangkan kecocokan tujuan kelompok.")
        n_tka = int(all_features.status_tka.str.casefold().eq("ikut").sum())
        st.write(f"**{len(all_features)} siswa**, **{n_tka} peserta TKA** teridentifikasi.")
        if len(all_features) != 140 or not all_features.status_tka.str.casefold().isin(["ikut", "tidak ikut"]).all():
            st.warning("Usulan kelas ditahan sampai 140 siswa dan status peserta TKA seluruh siswa lengkap.")
        else:
            bottom = st.slider("Skor terbawah wajib di On", 0, 29, 10)
            try:
                features = student_features(data)
                original = allocate(features, bottom)
                overall = global_rank[["student_id", "peringkat"]].rename(columns={"peringkat":"Peringkat sekolah (3 TO)"})
                original = original.merge(overall, on="student_id", how="left")
                summary = (original.groupby("rekomendasi").agg(Siswa=("student_id", "size"),
                           Peserta_TKA=("status_tka", lambda v:int(v.str.casefold().eq("ikut").sum())),
                           Median_nilai=("rata_terkini", "median"))
                           .reindex(["Fu", "Ch", "Am", "Pi", "On"]).round(1).reset_index())
                table(summary)
                group = st.selectbox("Lihat kelompok", ["Semua", "Fu", "Ch", "Am", "Pi", "On"])
                view = original if group == "Semua" else original[original.rekomendasi == group]
                table(view, ["nama", "kelas_asal", "status_tka", "Peringkat sekolah (3 TO)",
                             "rata_terkini", "tren", "fluktuasi", "potensi_pengembangan", "rekomendasi", "alasan"])
                with st.expander("Sesuaikan siswa tanpa menulis ke Google Sheet"):
                    editor = original[["student_id", "nama", "Peringkat sekolah (3 TO)", "rekomendasi"]].copy()
                    editor["Pilihan Bapak"] = editor.rekomendasi
                    edited = st.data_editor(editor, disabled=["student_id", "nama", "Peringkat sekolah (3 TO)", "rekomendasi"],
                                            hide_index=True, width="stretch", height=380,
                                            column_config={"Pilihan Bapak": st.column_config.SelectboxColumn(
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
                    Jumlah="size", Median="median", Sebaran="std").round(1).reset_index()
                table(stats)
                st.caption("Median dan sebaran merupakan sinyal memeriksa perbedaan kesulitan, bukan bukti soal buruk. Analisis butir memerlukan jawaban per nomor.")
            else:
                st.info("Tidak ada kode TO untuk pilihan ini.")
        with st.expander("Analisis lanjutan: simulasi ilustratif"):
            st.warning("Simulasi belum dikalibrasi dengan hasil TKA nyata. Jangan pakai peluang persentase atau perubahan skenario untuk memberi label kesiapan maupun memutuskan kelas.")
            if st.toggle("Jalankan simulasi", value=False):
                if scoped.empty:
                    st.info("Tidak ada siswa dalam cakupan yang dipilih.")
                elif to_remaining == 0:
                    st.info("Rencana 14 TO telah teridentifikasi. Tidak ada TO tersisa untuk skenario ini.")
                else:
                    future = st.slider("TO tersisa", 1, to_remaining, min(3, to_remaining))
                    lifts = {subject: st.slider("Asumsi kenaikan " + subject, 0, 15, 0,
                                                 key="lift_" + str(i)) for i, subject in enumerate(CORE)}
                    @st.cache_data(ttl=180)
                    def cached_simulation(frame, threshold, remaining, assumptions):
                        return simulate(frame, threshold, remaining, 1000, dict(assumptions))
                    scenario, _ = cached_simulation(data[data.student_id.isin(scoped.student_id)],
                                                     target, future, tuple(lifts.items()))
                    table(scenario, ["nama", "kelas", "mapel_penghambat", "proyeksi", "tren"])
                    st.caption("1000 skenario acak per siswa; ilustrasi sensitivitas asumsi, bukan prediksi TKA tervalidasi.")
        st.info("Panel sebelum-sesudah intervensi belum ditampilkan karena memerlukan log tindakan yang konsisten. Rapor siswa berisi analisis otomatis; lembar tindakan guru dan wali kelas diunduh terpisah tanpa penyimpanan.")
