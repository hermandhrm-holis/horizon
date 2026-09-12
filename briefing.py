"""Brief, auditable teacher and homeroom worklists from observed TO scores."""

from datetime import date
from html import escape
from io import BytesIO

import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from allocation import SUBJECTS
from report import _font_names


def subject_brief(data: pd.DataFrame, target: float = 65) -> pd.DataFrame:
    """One row per student and core subject; incomplete histories remain visible."""
    records = []
    for sid, student in data.groupby("student_id", sort=True):
        first = student.iloc[0]
        for subject in SUBJECTS:
            scores = (student[student.mapel.astype(str).str.casefold() == subject.casefold()]
                      .sort_values("assessment_order", kind="stable").score.to_numpy(float))
            n = len(scores)
            all_mean = float(np.mean(scores)) if n else np.nan
            recent = float(np.mean(scores[-3:])) if n else np.nan
            prev = float(np.mean(scores[-6:-3])) if n >= 6 else np.nan
            change = recent-prev if n >= 6 else np.nan
            if n < 3:
                kind = "Data terbatas"
                reason = f"Baru {n} nilai; tidak cukup untuk membaca 3 TO terakhir."
                action = "Lengkapi nilai dan konfirmasi peserta TO sebelum memberi label."
            elif recent < target-10:
                kind = "Prioritas tinggi"
                reason = f"Rata semua {all_mean:.1f}; 3 TO terakhir {recent:.1f}, di bawah target {target:g}."
                action = "Periksa butir yang salah; pilih satu fokus penguatan dan cek pada TO berikutnya."
            elif n >= 6 and change <= -5:
                kind = "Peringatan dini"
                reason = f"3 TO terakhir turun {abs(change):.1f} poin dari 3 sebelumnya."
                action = "Periksa penyebab penurunan dan beda kesulitan TO; evaluasi lagi setelah TO berikutnya."
            elif recent < target:
                kind = "Perlu penguatan"
                reason = f"Rata semua {all_mean:.1f}; 3 TO terakhir {recent:.1f}; selisih {target-recent:.1f} ke target."
                action = "Pilih satu fokus dari jawaban salah; latihan terarah, lalu periksa TO berikutnya."
            else:
                kind = "Jaga stabilitas"
                reason = f"Rata semua {all_mean:.1f}; 3 TO terakhir {recent:.1f} telah melampaui target."
                action = "Pertahankan rutinitas dan lihat apakah skor bertahan pada TO berikutnya."
            records.append({"student_id":sid,"nama":str(first.nama),"kelas":str(first.kelas),
                            "status_tka":str(first.status_tka),"mapel":subject,"jumlah_to":n,
                            "rata_semua_to":round(all_mean,1) if n else np.nan,
                            "rata_3_to":round(recent,1) if n else np.nan,
                            "perubahan_3_to":round(change,1) if n >= 6 else np.nan,
                            "kategori":kind,"alasan":reason,"saran_awal":action})
    return pd.DataFrame(records)


def homeroom_brief(subject_rows: pd.DataFrame) -> pd.DataFrame:
    """One record per student; names of weak subjects are a prompt for teachers."""
    records=[]
    for sid, rows in subject_rows.groupby("student_id", sort=True):
        first=rows.iloc[0]
        alerts=int(rows.kategori.isin(["Prioritas tinggi", "Peringatan dini"]).sum())
        flags=int(rows.kategori.isin(["Prioritas tinggi", "Peringatan dini", "Data terbatas"]).sum())
        reliable=rows[rows.jumlah_to >= 3]
        if not reliable.empty:
            weakest=reliable.loc[reliable.rata_3_to.idxmin(), "mapel"]
        else:
            weakest="Data belum ada"
        if alerts>=2:
            kind="Care khusus"
            action=f"Wali kelas koordinasikan dua atau lebih guru mapel; mulai dari {weakest}, cek setelah TO berikutnya."
        elif (rows.kategori == "Data terbatas").any():
            kind="Cek data"
            action="Koordinasikan kelengkapan TO dengan guru terkait sebelum membuat kesimpulan."
        elif flags==1:
            kind="Perlu koordinasi"
            action=f"Pastikan guru {weakest} meninjau jawaban dan melaporkan hasil setelah TO berikutnya."
        else:
            kind="Pantau rutin"
            action="Pertahankan rutinitas; bandingkan tiga TO berikutnya sebelum mengubah strategi."
        records.append({"student_id":sid,"nama":first.nama,"kelas":first.kelas,"status_tka":first.status_tka,
                        "mapel_fokus":weakest,"jumlah_sinyal":flags,"kategori_wk":kind,
                        "langkah_wk":action,"rata_3_mapel":round(float(rows.rata_3_to.mean()),1)
                        if rows.rata_3_to.notna().any() else np.nan,
                        "rata_semua_mapel":round(float(rows.rata_semua_to.mean()),1)
                        if rows.rata_semua_to.notna().any() else np.nan})
    return pd.DataFrame(records)


def remaining_to(data: pd.DataFrame, planned: int = 14) -> tuple[int,int]:
    """Use the furthest observed round in Mathematics / Bahasa Indonesia only."""
    eligible=data[data.mapel.isin(["Matematika","Bahasa Indonesia"])]
    if eligible.empty:
        return 0,planned
    if "assessment_code" in eligible:
        counts=eligible.groupby("mapel").assessment_code.nunique()
    else:
        counts=eligible.groupby("mapel").assessment_order.nunique()
    completed=min(int(counts.max()),planned)
    return completed,max(planned-completed,0)


def role_pdf(rows: pd.DataFrame, role: str, scope: str, completed: int, remaining: int,
             actions: dict | None = None, printed_on: date | None = None) -> bytes:
    """Downloadable, static paper form for a teacher or homeroom teacher."""
    actions=actions or {}
    printed_on=printed_on or date.today()
    regular,bold=_font_names()
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name="BriefTitle",fontName=bold,fontSize=15,leading=20,
                              textColor=colors.HexColor("#25463c"),spaceAfter=6))
    styles.add(ParagraphStyle(name="BriefSmall",fontName=regular,fontSize=8,leading=12,
                              textColor=colors.HexColor("#4e6458"),spaceAfter=7))
    styles.add(ParagraphStyle(name="BriefBody",fontName=regular,fontSize=9,leading=13,
                              textColor=colors.HexColor("#24342e"),spaceAfter=4))
    styles.add(ParagraphStyle(name="BriefBold",parent=styles["BriefBody"],fontName=bold))
    p=lambda value,style="BriefBody":Paragraph(escape(str(value)).replace("\n","<br/>"),styles[style])
    stream=BytesIO()
    doc=SimpleDocTemplate(stream,pagesize=A4,leftMargin=18*mm,rightMargin=18*mm,
                          topMargin=24*mm,bottomMargin=18*mm,
                          title=f"Lembar tindak lanjut {role} HORIZON TKA")
    story=[p(f"Lembar tindak lanjut - {role}","BriefTitle"),
           p(f"{scope} | {completed} TO tercatat | sekitar {remaining} dari rencana 14 tersisa | Dicetak {printed_on:%d-%m-%Y}","BriefSmall"),
           p("Urutan ini memberi tanda untuk diperiksa guru. Rata semua TO dan rata 3 TO terakhir tidak menyatakan sebab perubahan.","BriefSmall")]
    if rows.empty:
        story.append(p("Belum ada siswa yang sesuai pilihan ini."))
    for i,(_,row) in enumerate(rows.iterrows(),start=1):
        sid=str(row.student_id)
        note=str(actions.get(sid,"")).strip() or "........................................................................"
        if role == "Wali Kelas":
            all_mean=f"{row.rata_semua_mapel:.1f}" if pd.notna(row.rata_semua_mapel) else "-"
            latest=f"{row.rata_3_mapel:.1f}" if pd.notna(row.rata_3_mapel) else "-"
            line=f"{row.kategori_wk} | Semua TO: {all_mean} | 3 terakhir: {latest} | Fokus: {row.mapel_fokus}"
            reason=row.langkah_wk
        else:
            before=f"{row.rata_semua_to:.1f}" if pd.notna(row.rata_semua_to) else "-"
            after=f"{row.rata_3_to:.1f}" if pd.notna(row.rata_3_to) else "-"
            line=f"{row.kategori} | Semua TO: {before} | 3 terakhir: {after}"
            reason=f"{row.alasan} {row.saran_awal}"
        block=Table([[p(f"{i}. {row.nama} - {row.kelas}  ({row.status_tka})","BriefBold")],
                     [p(line)], [p(reason)], [p("Keputusan guru/WK: "+note)]],colWidths=[174*mm])
        block.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#e6f0eb")),
                                   ("BOX",(0,0),(-1,-1),.5,colors.HexColor("#c9d9d0")),
                                   ("VALIGN",(0,0),(-1,-1),"TOP"),
                                   ("TOPPADDING",(0,0),(-1,-1),5),
                                   ("BOTTOMPADDING",(0,0),(-1,-1),5)]))
        story.append(KeepTogether([block,Spacer(1,3*mm)]))
    story.append(p("Pemeriksaan berikutnya: setelah TO selanjutnya. Topik spesifik harus dikonfirmasi dari jawaban per butir.","BriefSmall"))

    def decorate(canvas,document):
        canvas.saveState()
        width,height=A4
        canvas.setFillColor(colors.HexColor("#355e53"))
        canvas.rect(0,height-13*mm,width,13*mm,fill=1,stroke=0)
        canvas.setFont(bold,8)
        canvas.setFillColor(colors.white)
        canvas.drawString(18*mm,height-8.5*mm,"HORIZON TKA  /  BRIEF TINDAKAN")
        canvas.setFont(regular,7)
        canvas.setFillColor(colors.HexColor("#4e6458"))
        canvas.drawString(18*mm,10*mm,"Dokumen kerja sementara; catatan tidak disimpan permanen di aplikasi.")
        canvas.drawRightString(width-18*mm,10*mm,f"Hal. {document.page}")
        canvas.restoreState()
    doc.build(story,onFirstPage=decorate,onLaterPages=decorate)
    return stream.getvalue()
