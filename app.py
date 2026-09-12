"""HORIZON: read-only, tabbed statistical decision dashboards."""

import math

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from allocation import allocate, attention_count, ranking, select_assessments, student_features
from engine import CORE, SourceError, demo_data, fetch_gas, normalize, simulate

st.set_page_config(page_title="HORIZON TKA • Decision Lab", page_icon="🔭", layout="wide")

st.markdown("""
<style>
  .block-container{max-width:1550px;padding-top:1.2rem}
  .hero{background:linear-gradient(110deg,#355e53,#83aa9b);color:#fff;border-radius:26px;padding:24px 32px;margin-bottom:18px}
  .hero h1{color:#fff!important;margin:0;font-size:2.2rem}.hero p{color:#fff!important;margin:6px 0 0}
  .card{background:#fff;border:1px solid #cbd8d1;border-radius:18px;padding:16px 19px;min-height:110px}
  .card-label{color:#3b5b52;font-size:15px;font-weight:750}.card-value{color:#172c26;font-size:36px;font-weight:800;margin-top:11px}
  .card-note{color:#45675c;font-size:13px;font-weight:600}
  div[data-testid="stMetric"]{background:#fff!important;border:1px solid #cbd8d1;border-radius:16px;padding:14px}
  div[data-testid="stMetric"] *{color:#20332e!important}
</style>
<div class="hero"><div style="letter-spacing:.18em;font-weight:700">HORIZON TKA</div>
<h1>Decision Lab</h1><p>Dashboard kesiapan, prioritas, ranking, dan strategi kelompok.</p></div>
""", unsafe_allow_html=True)


def secret(key):
    try:
        return str(st.secrets.get(key, ""))
    except Exception:
        return ""


def card(label, value, note=""):
    st.markdown(f'<div class="card"><div class="card-label">{label}</div>'
                f'<div class="card-value">{value}</div><div class="card-note">{note}</div></div>',
                unsafe_allow_html=True)


def table(frame, cols=None, key=None):
    if frame is None or frame.empty:
        st.info("Belum ada siswa/data yang memenuhi pilihan ini.")
        return None
    displayed = frame[cols].reset_index(drop=True) if cols else frame.reset_index(drop=True)
    return st.dataframe(displayed, hide_index=True, width="stretch", height=min(440, 42 + 36 * (len(displayed) + 1)),
                        key=key, on_select="rerun" if key else "ignore", selection_mode="single-row" if key else "multi-row")


def chart_style(fig, height=360):
    fig.update_layout(height=height, paper_bgcolor="#fff", plot_bgcolor="#fff", font=dict(color="#20332e", size=13),
                      margin=dict(l=16, r=16, t=30, b=18), legend=dict(font=dict(color="#20332e"), bgcolor="#fff"))
    fig.update_xaxes(tickfont=dict(color="#20332e"), title_font=dict(color="#20332e"), gridcolor="#e1e8e4")
    fig.update_yaxes(tickfont=dict(color="#20332e"), title_font=dict(color="#20332e"), gridcolor="#e1e8e4")
    st.plotly_chart(fig, theme=None, width="stretch")


def profile(data, sid, label="Profil siswa"):
    student = data[data.student_id == sid].sort_values(["mapel", "assessment_order"])
    if student.empty:
        return
    first = student.iloc[0]
    st.subheader(f"{label}: {first['nama']}")
    whole = ranking(student)
    if not whole.empty:
        item = whole.iloc[0]
        st.write(f"**{item['profil']}** · rata-rata {item['skor']:.1f} · tren {item['tren']:+.1f} poin/TO · "
                 f"fluktuasi {item['fluktuasi']:.1f} · penghambat: {item['mapel_terlemah']}.")
        if not item.data_memadai:
            st.warning("Jumlah nilai belum cukup untuk menilai kestabilan dengan yakin.")
    fig = px.line(student, x="assessment_order", y="score", color="mapel", markers=True,
                  hover_data=["assessment_code"] if "assessment_code" in student else None,
                  labels={"assessment_order":"Urutan TO", "score":"Nilai", "mapel":"Mapel"})
    chart_style(fig)


def selected_profile(frame, data, key):
    if frame.empty:
        st.info("Tidak ada siswa pada filter ini.")
        return
    selection = table(frame, key=key)
    selected = selection.selection.rows if selection else []
    sid = frame.iloc[selected[0]].student_id if selected else frame.iloc[0].student_id
    st.caption("Klik satu baris siswa untuk membuka profilnya. Baris pertama terbuka sebagai contoh.")
    profile(data, sid)


def scope_filter(df, population, school_class):
    out = df.copy()
    if population == "Peserta TKA":
        out = out[out.status_tka.str.casefold() == "ikut"]
    elif population == "Tidak Ikut":
        out = out[out.status_tka.str.casefold() == "tidak ikut"]
    if school_class != "Semua Kelas":
        out = out[out.kelas.astype(str) == school_class]
    return out


with st.sidebar:
    st.header("Sumber data")
    source = st.radio("Pilih sumber", ["API Google Apps Script", "Data demo", "Unggah CSV"])
    url = st.text_input("URL Web App GAS", value=secret("GAS_API_URL")) if source == "API Google Apps Script" else ""
    token = st.text_input("Token", value=secret("GAS_API_TOKEN"), type="password") if source == "API Google Apps Script" else ""
    uploaded = st.file_uploader("CSV nilai", type="csv") if source == "Unggah CSV" else None

connection_error = None
if source == "API Google Apps Script":
    if not url or not token:
        connection_error = "Isi URL /exec dan token. Dashboard menampilkan data DEMO hingga koneksi siap."
    else:
        try:
            data = fetch_gas(url, token)
        except SourceError as exc:
            connection_error = str(exc)
elif source == "Unggah CSV":
    if uploaded is None:
        connection_error = "Unggah CSV; sementara dashboard menampilkan data DEMO."
    else:
        try:
            data = normalize(pd.read_csv(uploaded))
        except (ValueError, SourceError) as exc:
            connection_error = str(exc)

demo_mode = source == "Data demo" or connection_error is not None
if demo_mode:
    data = demo_data()
    st.warning("MODE DEMO — seluruh nama dan angka di bawah ini adalah contoh, BUKAN data siswa HORIZON.")
if connection_error:
    st.error("Koneksi data asli belum berhasil: " + connection_error)
else:
    st.success(f"Sumber: {'DATA DEMO' if demo_mode else 'Data HORIZON'} · {data.student_id.nunique()} siswa teridentifikasi.")

with st.sidebar:
    st.divider(); st.header("Cakupan dashboard")
    population = st.selectbox("Siswa", ["Peserta TKA", "Semua Siswa", "Tidak Ikut"])
    school_class = st.selectbox("Kelas asal", ["Semua Kelas"] + sorted(data.kelas.astype(str).unique().tolist()))
    category = st.selectbox("Kesiapan", ["Semua Status", "Prioritas tinggi", "Perlu dipantau", "Relatif siap", "Data terbatas"])
    attention_pct = st.number_input("Perhatian khusus (%)", min_value=1, max_value=100, value=25)
    st.divider(); st.header("Simulasi (ilustratif)")
    target = st.number_input("Target nilai", 0., 100., 65., 1.)
    future = st.slider("TO tersisa", 1, 8, 3)
    runs = st.select_slider("Jumlah skenario", [1000, 3000, 5000], value=3000)

cohort = scope_filter(data, population, school_class)
if cohort.empty:
    st.warning("Belum ada nilai pada cakupan ini. Pilih Semua Siswa atau cek status PesertaTKA.")
    st.stop()

@st.cache_data(ttl=180, show_spinner=False)
def cached_simulation(frame, t, n, repetitions, lifts):
    return simulate(frame, t, n, repetitions, dict(lifts))

risk_all, details = cached_simulation(cohort, target, future, runs, ())
if risk_all.empty:
    st.warning("Data nilai belum cukup untuk analisis.")
    st.stop()
risk = risk_all if category == "Semua Status" else risk_all[risk_all.status == category]
eligible_ids = set(risk.student_id)
visible_data = cohort[cohort.student_id.isin(eligible_ids)]

labels = ["Ringkasan", "Prioritas 5/10", "Perhatian %", "Potensi Naik", "Peringatan Dini",
          "Simulasi", "Mapel", "Stabilitas", "Kelas", "Kualitas TO", "Ranking & Profil", "Fu–On", "Intervensi"]
tabs = st.tabs(labels, key="dashboard_tab", on_change="rerun")

if tabs[0].open:
    with tabs[0]:
        st.subheader("Kondisi sekolah saat ini")
        c1,c2,c3,c4 = st.columns(4)
        with c1: card("Siswa dalam cakupan", str(len(risk)), f"Dari {len(risk_all)} siswa pada filter kelas/peserta")
        with c2: card("Prioritas tinggi", str(int(risk.status.eq("Prioritas tinggi").sum())))
        with c3: card("Perlu dipantau", str(int(risk.status.eq("Perlu dipantau").sum())))
        with c4: card("Perkiraan capai target", f"{(1-risk.peluang_belum_target).sum():.1f}", "Jumlah harapan, bukan jumlah pasti")
        if not risk.empty:
            counts = risk.status.value_counts().rename_axis("Kategori").reset_index(name="Siswa")
            chart_style(px.bar(counts, x="Kategori", y="Siswa", color="Kategori", text="Siswa", color_discrete_sequence=["#d6685b", "#e8b65b", "#6c9b88"]))
            st.write("**Tindakan hari ini:** buka tab Prioritas 5/10 untuk melihat siswa dan mapel penghambatnya.")
        st.caption("Kategori risiko didasarkan pada simulasi heuristik; belum dikalibrasi dengan hasil TKA sesungguhnya.")

if tabs[1].open:
    with tabs[1]:
        st.subheader("Siswa yang perlu perhatian dahulu")
        top_n = st.selectbox("Jumlah siswa", [5, 10], key="priority_n")
        st.caption(f"Cakupan: {population}, {school_class}, {category}. Semua TO bernilai dipertimbangkan.")
        top = risk.sort_values(["peluang_belum_target", "tren"], ascending=[False, True]).head(top_n).copy()
        if not top.empty:
            top["Risiko"] = top.peluang_belum_target.map(lambda x:f"{x:.1%}")
            top["Proyeksi"] = top.proyeksi.round(1)
            display = top[["student_id","nama","kelas","status_tka","Risiko","Proyeksi","tren","mapel_penghambat"]]
            selected_profile(display, visible_data, "priority_rows")
        else: st.info("Tidak ada siswa pada filter ini.")

if tabs[2].open:
    with tabs[2]:
        st.subheader("Kelompok perhatian berdasarkan kuota")
        total = attention_count(len(risk_all), int(attention_pct))
        candidates = risk_all.sort_values(["peluang_belum_target", "tren"], ascending=[False, True]).head(total)
        selected = candidates if category == "Semua Status" else candidates[candidates.status == category]
        st.write(f"**{attention_pct}% dari {len(risk_all)} = {total} siswa** masuk daftar perhatian. "
                 f"Yang terlihat setelah filter kategori: {len(selected)}.")
        selected_profile(selected[["student_id","nama","kelas","status_tka","status","peluang_belum_target","mapel_penghambat"]], cohort, "attention_rows")

if tabs[3].open:
    with tabs[3]:
        st.subheader("Siswa yang berpeluang naik dengan penguatan terarah")
        ranked = ranking(visible_data, 3)
        if not ranked.empty:
            potential = ranked[(ranked.skor < target) & (ranked.tren > 0)].copy()
            potential["Jarak target"] = (target - potential.skor).round(1)
            potential = potential.sort_values(["Jarak target","tren"], ascending=[True,False])
            selected_profile(potential[["student_id","nama","kelas","skor","Jarak target","tren","profil","mapel_terlemah"]].head(30), visible_data, "potential_rows")
        st.caption("Ini kandidat berdasarkan dekatnya target dan tren; bukan estimasi efektivitas intervensi.")

if tabs[4].open:
    with tabs[4]:
        st.subheader("Siswa yang mulai menurun")
        changes=[]
        for sid,s in visible_data.groupby("student_id"):
            diffs=[]
            for subject in CORE:
                y=s[s.mapel==subject].sort_values("assessment_order").score.to_numpy(float)
                if len(y)>=6: diffs.append(float(y[-3:].mean()-y[-6:-3].mean()))
            if len(diffs)==3: changes.append({"student_id":sid,"nama":s.iloc[0]["nama"],"kelas":s.iloc[0]["kelas"],"Perubahan":round(float(np.mean(diffs)),1)})
        df=pd.DataFrame(changes)
        if not df.empty: selected_profile(df.sort_values("Perubahan").head(30), visible_data, "warning_rows")
        else: st.info("Belum ada enam nilai per mapel untuk membandingkan 3 TO terbaru dengan 3 sebelumnya.")
        st.caption("Perubahan nilai bisa disebabkan perbedaan tingkat kesulitan TO, bukan hanya perubahan kemampuan.")

if tabs[5].open:
    with tabs[5]:
        st.subheader("Bagaimana jika nilai meningkat?")
        cols=st.columns(3)
        lifts={subject:cols[i].slider(f"Kenaikan {subject}",0,15,0,key=f"lift_{i}") for i,subject in enumerate(CORE)}
        after,after_details=cached_simulation(cohort,target,future,runs,tuple(lifts.items()))
        after=after[after.student_id.isin(eligible_ids)]
        baseline_ready=float((1-risk.peluang_belum_target).sum())
        scenario_ready=float((1-after.peluang_belum_target).sum())
        st.write(f"**Sebelum: {baseline_ready:.1f}** → **Skenario: {scenario_ready:.1f}** siswa diperkirakan mencapai target. "
                 f"Selisih **{scenario_ready-baseline_ready:+.1f}** (jumlah harapan statistik).")
        if not after.empty:
            item=st.selectbox("Lihat siswa",after.student_id.tolist(),format_func=lambda sid:after.loc[after.student_id==sid,"nama"].iloc[0])
            row=after[after.student_id==item].iloc[0]
            st.write(f"{row['nama']} · proyeksi {row.proyeksi:.1f} · rentang 80% {row.batas_bawah:.1f}–{row.batas_atas:.1f} · peluang di bawah target {row.peluang_belum_target:.1%}")
            chart_style(px.histogram(x=after_details[item]["distribution"],nbins=30,labels={"x":"Proyeksi","count":"Skenario"},color_discrete_sequence=["#568e7d"]))
        st.warning("Kenaikan nilai pada slider adalah asumsi, bukan dampak yang sudah terbukti dari suatu program.")

if tabs[6].open:
    with tabs[6]:
        st.subheader("Mata pelajaran yang paling menghambat")
        if not risk.empty:
            summary=risk.mapel_penghambat.value_counts().rename_axis("Mapel").reset_index(name="Siswa")
            chart_style(px.bar(summary,x="Mapel",y="Siswa",text="Siswa",color_discrete_sequence=["#6e9d8e"]))
            selected_profile(risk[["student_id","nama","kelas","mapel_penghambat","status"]].sort_values("mapel_penghambat"),visible_data,"bottleneck_rows")
        st.caption("Mapel terendah ditentukan dari proyeksi rata-rata, bukan diagnosis kompetensi spesifik.")

if tabs[7].open:
    with tabs[7]:
        st.subheader("Stabilitas dan fluktuasi nilai")
        ranked=ranking(visible_data,5)
        if not ranked.empty:
            selected_profile(ranked.sort_values("fluktuasi",ascending=False)[["student_id","nama","kelas","skor","fluktuasi","tren","profil"]],visible_data,"volatility_rows")
        st.caption("Fluktuasi dihitung dalam mapel; hasil tetap dipengaruhi perbedaan kesulitan tiap TO.")

if tabs[8].open:
    with tabs[8]:
        st.subheader("Perbandingan antar kelas asal")
        ranked=ranking(visible_data,3)
        if not ranked.empty:
            summary=ranked.groupby("kelas").agg(Siswa=("student_id","size"),Median=("skor","median"),Rata_rata=("skor","mean"),Fluktuasi=("fluktuasi","median")).round(1).reset_index()
            table(summary)
            chart_style(px.bar(summary,x="kelas",y="Median",color="kelas",text="Median",color_discrete_sequence=["#6d9e8d","#e4b764","#d78778","#94b4a8"]))
        st.caption("Perbandingan mengikuti cakupan peserta dan kategori yang sedang dipilih.")

if tabs[9].open:
    with tabs[9]:
        st.subheader("Pemeriksaan distribusi nilai TO")
        kind=st.selectbox("Sumber TO",["Gabungan","PENABUR","HOLIS"],key="quality_source")
        qa=select_assessments(visible_data,kind)
        if "assessment_code" not in qa: st.info("Data ini belum memiliki kode TO; hanya gabungan asesmen yang bisa ditinjau.")
        else:
            stats=qa.groupby(["mapel","assessment_code"]).score.agg(Jumlah="size",Median="median",Sebaran="std").round(1).reset_index()
            table(stats)
            st.caption("Sebaran atau median mencurigakan adalah sinyal untuk memeriksa tes, bukan bukti bahwa soal buruk. Analisis butir membutuhkan jawaban tiap nomor.")

if tabs[10].open:
    with tabs[10]:
        st.subheader("Ranking semua, 5, atau 3 TO terakhir")
        a,b=st.columns(2)
        provider=a.selectbox("Sumber",["Gabungan","PENABUR","HOLIS"],key="rank_provider")
        choice=b.selectbox("Jendela",["Semua TO","5 TO terakhir","3 TO terakhir"],key="rank_window")
        n={"Semua TO":None,"5 TO terakhir":5,"3 TO terakhir":3}[choice]
        subset=select_assessments(visible_data,provider)
        ranked=ranking(subset,n)
        if ranked.empty: st.info("Tidak ada tiga mapel untuk pilihan ini.")
        else:
            st.caption("Peringkat dihitung ulang dalam cakupan filter. Setiap mapel berbobot sama; 3/5 terakhir dipilih per mapel. Klik baris untuk profil.")
            selected_profile(ranked[["student_id","peringkat","nama","kelas","status_tka","skor","tren","fluktuasi","profil","mapel_terlemah"]],subset,"ranking_rows")

if tabs[11].open:
    with tabs[11]:
        st.subheader("Rekomendasi Fu–Ch–Am–Pi–On")
        st.caption("Penempatan memakai seluruh angkatan, tidak dibatasi filter kelas/status di sidebar. Fu: prestasi kuat dan stabil. Ch: indikator ruang berkembang. Am: jaga dan kuatkan. Pi/On: campuran, siswa terbawah di On.")
        features=student_features(data)
        n_tka=int(features.status_tka.str.casefold().eq("ikut").sum())
        st.write(f"Teridentifikasi: **{len(features)} siswa**, **{n_tka} peserta TKA**.")
        if len(features)!=140 or features.status_tka.str.casefold().isin(["belum diatur",""]).any():
            st.warning("Rekomendasi ditahan sampai 140 siswa dan status TKA seluruh siswa lengkap. Jangan memakai data demo sebagai keputusan kelas nyata.")
        else:
            bottom=st.slider("Jumlah skor terbawah wajib di On",0,29,10,key="bottom_on")
            try:
                auto=allocate(features,bottom)
                overall=ranking(data,3)[["student_id","peringkat"]].rename(columns={"peringkat":"Peringkat 3 TO"})
                auto=auto.merge(overall,on="student_id",how="left")
                st.write("**Komposisi otomatis**")
                counts=auto.groupby("rekomendasi").agg(Siswa=("student_id","size"),Peserta_TKA=("status_tka",lambda s:int(s.str.casefold().eq("ikut").sum())),Median=("rata_terkini","median")).reindex(["Fu","Ch","Am","Pi","On"]).round(1)
                table(counts.reset_index())
                selected_group=st.selectbox("Lihat kelas rekomendasi",["Semua","Fu","Ch","Am","Pi","On"])
                view=auto if selected_group=="Semua" else auto[auto.rekomendasi==selected_group]
                selected_profile(view[["student_id","nama","kelas_asal","status_tka","Peringkat 3 TO","rata_terkini","tren","fluktuasi","potensi_pengembangan","rekomendasi","alasan"]],data,"placement_rows")
                st.write("**Sesuaikan pilihan siswa (tanpa mengubah Google Sheet)**")
                editor=auto[["student_id","nama","Peringkat 3 TO","rekomendasi"]].copy()
                editor["Pilihan Bapak"]=editor.rekomendasi
                edited=st.data_editor(editor,disabled=["student_id","nama","Peringkat 3 TO","rekomendasi"],hide_index=True,width="stretch",height=350,
                    column_config={"Pilihan Bapak":st.column_config.SelectboxColumn("Pilihan Bapak",options=["Fu","Ch","Am","Pi","On"],required=True)},key="placement_editor")
                changes=edited[edited["Pilihan Bapak"]!=edited.rekomendasi]
                if not changes.empty:
                    try:
                        manual=allocate(features,bottom,dict(zip(changes.student_id,changes["Pilihan Bapak"]))).merge(overall,on="student_id",how="left")
                        st.success("Pilihan manual diterapkan melalui pertukaran aman; kapasitas dan aturan peserta TKA terjaga.")
                        table(manual[["nama","Peringkat 3 TO","status_tka","rata_terkini","potensi_pengembangan","rekomendasi","alasan"]].round(1))
                        result=manual
                    except ValueError as exc:
                        st.error("Pilihan tidak dapat diterapkan: "+str(exc)); result=auto
                else: result=auto
                st.download_button("Unduh usulan kelas CSV",result.to_csv(index=False).encode("utf-8-sig"),"usulan_kelas_fu_on.csv","text/csv")
                st.warning("Peringkat dan kecocokan kelompok adalah dua ukuran berbeda. Skor kecocokan merupakan aturan transparan berbasis nilai, tren, dan fluktuasi—belum bukti bahwa siswa akan meningkat jika dipindahkan ke Ch.")
            except ValueError as exc: st.error("Belum dapat membagi kelas: "+str(exc))

if tabs[12].open:
    with tabs[12]:
        st.subheader("Pantau intervensi sebelum–sesudah")
        st.caption("Unggah catatan tindakan agar tab ini dapat merangkum perubahan nilai. Ini hubungan deskriptif, bukan bukti sebab-akibat.")
        interventions=st.file_uploader("CSV: student_id,intervensi,assessment_order_awal",type="csv",key="interventions")
        if interventions is None:
            st.info("Belum ada log intervensi. Siapkan CSV dengan ID siswa, nama tindakan, dan nomor urut TO saat dimulai. Dashboard tidak akan membuat klaim dampak tanpa catatan tersebut.")
        else:
            try:
                log=pd.read_csv(interventions,dtype={"student_id":str})
                if not {"student_id","intervensi","assessment_order_awal"}.issubset(log.columns):
                    raise ValueError("Kolom wajib: student_id, intervensi, assessment_order_awal")
                log["assessment_order_awal"]=pd.to_numeric(log.assessment_order_awal,errors="coerce")
                results=[]
                for _,event in log.iterrows():
                    s=visible_data[visible_data.student_id==str(event.student_id)]
                    before=s[s.assessment_order<event.assessment_order_awal].sort_values("assessment_order").groupby("mapel").tail(3)
                    after=s[s.assessment_order>=event.assessment_order_awal].sort_values("assessment_order").groupby("mapel").head(3)
                    if len(before)>=6 and len(after)>=6:
                        results.append({"Siswa":s.iloc[0]["nama"],"Intervensi":event.intervensi,
                                        "Sebelum":round(float(before.score.mean()),1),"Sesudah":round(float(after.score.mean()),1),
                                        "Selisih":round(float(after.score.mean()-before.score.mean()),1)})
                table(pd.DataFrame(results))
                if not results: st.info("Nilai sebelum/sesudah belum cukup atau ID tidak cocok dengan cakupan siswa.")
            except (ValueError,KeyError,IndexError) as exc: st.error("CSV intervensi belum valid: "+str(exc))
