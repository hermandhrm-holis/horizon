"""Deterministic student commentary and an on-demand, one-page PDF report.

Only anonymized test data is bundled; no student values or teacher notes persist.
"""

from datetime import date
from html import escape
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from allocation import SUBJECTS


def student_analysis(student: pd.DataFrame, target: float = 65) -> dict:
    """Describe observations, never estimate a causal benefit or a pass probability."""
    if student.empty or student.student_id.nunique() != 1:
        raise ValueError("Analisis memerlukan data tepat satu siswa.")
    first = student.iloc[0]
    subjects = []
    for subject in SUBJECTS:
        part = student[(student.mapel.astype(str).str.casefold() == subject.casefold()) &
                       student.score.notna()]
        part = part.sort_values("assessment_order", kind="stable")
        values = part.score.to_numpy(float)
        if not len(values):
            subjects.append({"mapel": subject, "n": 0, "mean": None, "all_mean": None, "trend": None,
                             "volatility": None, "last": [], "interpretasi": "Belum ada nilai TO."})
            continue
        recent = values[-3:]
        mean = float(np.mean(recent))
        trend = float((recent[-1] - recent[0]) / 2) if len(recent) >= 3 else None
        volatility = float(np.std(recent, ddof=1)) if len(recent) >= 3 else None
        if len(recent) < 3:
            interpretation = f"Baru {len(recent)} nilai; belum cukup untuk menyimpulkan tren atau kestabilan."
        elif volatility > 12:
            interpretation = (f"Rata-rata tiga TO {mean:.1f}; variasi {volatility:.1f} poin. "
                              "Periksa konsistensi dan perbedaan tingkat kesulitan TO sebelum menentukan tindakan.")
        elif mean < target and trend is not None and trend < -1:
            interpretation = (f"Rata-rata tiga TO {mean:.1f}, di bawah target {target:g}; "
                              f"arah nilai menurun ({trend:+.1f} poin/TO). Tinjau kembali hasil TO berikutnya.")
        elif mean < target and trend is not None and trend >= 1:
            interpretation = (f"Rata-rata tiga TO {mean:.1f}, berjarak {target-mean:.1f} dari target; "
                              f"arah nilai naik ({trend:+.1f} poin/TO). Cocok untuk pemantauan penguatan terarah.")
        elif mean < target:
            interpretation = (f"Rata-rata tiga TO {mean:.1f}, berjarak {target-mean:.1f} dari target; "
                              "belum terlihat kenaikan yang konsisten. Pilih satu fokus belajar untuk diuji pada TO berikutnya.")
        elif trend is not None and trend < -1:
            interpretation = (f"Rata-rata tiga TO {mean:.1f} telah melampaui target, tetapi tren terbaru menurun "
                              f"({trend:+.1f} poin/TO). Jaga agar capaian tidak turun lebih jauh.")
        else:
            interpretation = (f"Rata-rata tiga TO {mean:.1f} telah mencapai target; "
                              "pertahankan latihan dan pantau kestabilannya.")
        subjects.append({"mapel": subject, "n": len(values), "mean": mean,
                         "all_mean": float(np.mean(values)),
                         "trend": trend, "volatility": volatility,
                         "last": [round(float(v), 1) for v in recent], "interpretasi": interpretation})

    reliable = [s for s in subjects if s["n"] >= 3]
    if reliable:
        weakest = min(reliable, key=lambda s: (s["mean"], s["mapel"]))
        weakness = (f"Nilai terendah pada tiga TO terakhir adalah {weakest['mapel']} "
                    f"(rata-rata {weakest['mean']:.1f}). Minta guru mapel meninjau butir/topik yang salah; "
                    "nilai agregat belum menunjukkan topik penyebabnya.")
        opportunity = [s for s in reliable if s["mean"] < target and s["trend"] is not None
                       and s["trend"] >= 0 and s["volatility"] <= 12 and target-s["mean"] <= 15]
        opportunity.sort(key=lambda s: (target-s["mean"], -s["trend"], s["mapel"]))
        if opportunity:
            pick = opportunity[0]
            growth = (f"Indikasi ruang peningkatan yang paling mudah dipantau: {pick['mapel']}. "
                      f"Jarak ke target {target-pick['mean']:.1f} poin; tren {pick['trend']:+.1f} poin/TO. "
                      "Ini bukan perkiraan besarnya kenaikan akibat intervensi.")
        else:
            growth = ("Belum ada mapel yang sekaligus dekat target, stabil, dan tidak menurun. "
                      "Prioritaskan diagnosis guru dan penambahan data sebelum menyebut potensi kenaikan.")
    else:
        weakness = "Belum cukup tiga nilai per mapel untuk membandingkan mapel terlemah secara andal."
        growth = "Belum cukup data untuk mengidentifikasi ruang peningkatan."
    unstable = [s["mapel"] for s in reliable if s["volatility"] > 12]
    caution = ("Nilai berfluktuasi pada " + ", ".join(unstable) + "; cek konsistensi dan kesulitan tes."
               if unstable else "Tidak ada lonjakan fluktuasi besar pada mapel dengan data memadai.")
    return {"student_id": str(first.student_id), "nama": str(first.nama),
            "kelas": str(first.kelas), "status_tka": str(first.status_tka),
            "target": float(target), "subjects": subjects, "weakness": weakness,
            "growth": growth, "caution": caution,
            "complete": len(reliable) == len(SUBJECTS)}


def _font_names():
    normal = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    bold = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    if normal.exists() and bold.exists():
        if "HorizonRegular" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("HorizonRegular", str(normal)))
            pdfmetrics.registerFont(TTFont("HorizonBold", str(bold)))
        return "HorizonRegular", "HorizonBold"
    return "Helvetica", "Helvetica-Bold"


def build_report(analysis: dict, printed_on: date | None = None,
                 scope: str = "Semua siswa", demo: bool = False) -> bytes:
    """Return a one-page student analysis PDF without teacher input fields."""
    printed_on = printed_on or date.today()
    buffer = BytesIO()
    regular, bold = _font_names()
    ink, sage, gray = colors.HexColor("#233b33"), colors.HexColor("#eaf2ed"), colors.HexColor("#5a6d63")
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=19*mm, rightMargin=19*mm,
                            topMargin=23*mm, bottomMargin=18*mm,
                            title="Rapor Analisis HORIZON TKA", author="HORIZON TKA")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="H1Lab", fontName=bold, fontSize=17, leading=22,
                              textColor=ink, spaceAfter=8))
    styles.add(ParagraphStyle(name="H2Lab", fontName=bold, fontSize=11.5, leading=16,
                              textColor=ink, spaceBefore=14, spaceAfter=7))
    styles.add(ParagraphStyle(name="BodyLab", fontName=regular, fontSize=9.1, leading=14,
                              textColor=ink, spaceAfter=7))
    styles.add(ParagraphStyle(name="SmallLab", fontName=regular, fontSize=8, leading=12,
                              textColor=gray, spaceAfter=6))
    styles.add(ParagraphStyle(name="CellLab", fontName=regular, fontSize=8.5, leading=12,
                              textColor=ink))
    styles.add(ParagraphStyle(name="CellBoldLab", parent=styles["CellLab"], fontName=bold))
    p = lambda value, style="BodyLab": Paragraph(escape(str(value)).replace("\n", "<br/>"), styles[style])

    def frame(canvas, document):
        canvas.saveState()
        width, height = A4
        canvas.setFillColor(colors.HexColor("#355e53"))
        canvas.rect(0, height-13*mm, width, 13*mm, fill=1, stroke=0)
        canvas.setFont(bold, 9)
        canvas.setFillColor(colors.white)
        canvas.drawString(19*mm, height-8.5*mm,
                          "HORIZON TKA  /  CONTOH DATA DEMO" if demo else "HORIZON TKA  /  RAPOR ANALISIS")
        canvas.setStrokeColor(colors.HexColor("#d8e3dc"))
        canvas.line(19*mm, 15*mm, width-19*mm, 15*mm)
        canvas.setFont(regular, 7.5)
        canvas.setFillColor(gray)
        canvas.drawString(19*mm, 10*mm, "Analisis statistik, bukan vonis atau janji kelulusan")
        canvas.drawRightString(width-19*mm, 10*mm, f"{printed_on:%d-%m-%Y}  |  Hal. {document.page}")
        canvas.restoreState()

    story = ([p("MODE DEMO - BUKAN DATA SISWA ASLI", "H2Lab")] if demo else []) + [p(analysis["nama"], "H1Lab"),
             p(f"Kelas {analysis['kelas']}  |  Status TKA: {analysis['status_tka']}  |  "
               f"Target {analysis['target']:g}  |  ID: {analysis['student_id']}", "SmallLab"),
             p("Ringkasan tiga mata pelajaran", "H2Lab")]
    headings = ["Mapel", "3 TO terakhir", "Semua", "Terakhir", "Arah"]
    rows = [[p(x, "CellBoldLab") for x in headings]]
    for s in analysis["subjects"]:
        rows.append([p(s["mapel"], "CellLab"), p(" / ".join(f"{v:g}" for v in s["last"]) or "-", "CellLab"),
                     p(f"{s['all_mean']:.1f}" if s["all_mean"] is not None else "-", "CellLab"),
                     p(f"{s['mean']:.1f}" if s["mean"] is not None else "-", "CellLab"),
                     p(f"{s['trend']:+.1f}/TO" if s["trend"] is not None else "Belum cukup", "CellLab")])
    grid = Table(rows, colWidths=[40*mm, 48*mm, 24*mm, 25*mm, 31*mm], repeatRows=1)
    grid.setStyle(TableStyle([("BACKGROUND", (0,0),(-1,0),sage),
                              ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, colors.HexColor("#f7faf8")]),
                              ("LINEBELOW",(0,-1),(-1,-1),.5,colors.HexColor("#cbd8d1")),
                              ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                              ("TOPPADDING",(0,0),(-1,-1),8),
                              ("BOTTOMPADDING",(0,0),(-1,-1),8)]))
    story.extend([grid, p("Yang perlu diperhatikan", "H2Lab"), p(analysis["weakness"]),
                  p(analysis["growth"]), p(analysis["caution"]),
                  p("Catatan untuk guru mapel", "H2Lab")])
    for s in analysis["subjects"]:
        story.append(KeepTogether([p(s["mapel"], "CellBoldLab"), p(s["interpretasi"])]))
    story.extend([Spacer(1,4*mm),
                  p("Metode: rata-rata semua TO dan 3 TO terakhir per mapel. Perbedaan kesulitan TO "
                    "PENABUR dan HOLIS tidak dikoreksi. Sebelum menentukan topik latihan, "
                    "guru perlu meninjau jawaban per butir.", "SmallLab"),
                  p(f"Cakupan ranking/dashboard: {scope}. Tanggal cetak: {printed_on:%d-%m-%Y}.", "SmallLab")])
    doc.build(story, onFirstPage=frame, onLaterPages=frame)
    return buffer.getvalue()
