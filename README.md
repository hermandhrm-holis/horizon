# HORIZON Risk & Scenario Lab

Contoh aplikasi Python untuk melengkapi HORIZON yang sudah berjalan di Google Apps Script.
Aplikasi menjalankan ribuan simulasi kemungkinan hasil asesmen berikutnya, menghitung peluang
belum mencapai target, dan menunjukkan mata pelajaran yang paling memengaruhi risiko.

> Ini alat triase dan simulasi, bukan vonis kelulusan siswa.

## Mengapa Python?

GAS tetap unggul untuk Sheet, formulir, login sekolah, dan operasi harian. Python dipakai untuk
komputasi numerik, simulasi, model statistik/ML, dan pengolahan data besar dengan pustaka yang matang.
Analisis serupa secara teori dapat ditulis dalam JavaScript, tetapi jauh lebih rumit dan dibatasi
kuota/waktu eksekusi Apps Script.

## Hubungan sistem

1. Google Sheet tetap menjadi sumber data utama.
2. `gas_endpoint.gs` menerbitkan data format JSON secara read-only.
3. Aplikasi Streamlit mengambil JSON dari GAS secara server-side.
4. GitHub menyimpan versi kode; Streamlit Community Cloud menjalankan Python dari repository.

## Format sheet `RiskLab_Data`

Gunakan format panjang—satu baris untuk satu nilai:

| student_id | nama | kelas | mapel | assessment_order | score |
|---|---|---|---|---:|---:|
| 12A001 | SISWA A | 12A | Matematika | 1 | 52.5 |
| 12A001 | SISWA A | 12A | Bahasa Indonesia | 1 | 78.0 |

Nama mapel utama harus: `Matematika`, `Bahasa Indonesia`, dan `Bahasa Inggris`.

## Menjalankan lokal

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Windows memakai `.venv\\Scripts\\activate` pada langkah aktivasi.

## Menghubungkan GAS

1. Tambahkan isi `gas_endpoint.gs` ke project Apps Script HORIZON.
2. Pada fungsi `doGet(e)` HORIZON yang sudah ada, tambahkan routing berikut sebelum respons default:

```javascript
if (e.parameter.action === 'riskLab') return apiRiskLab_(e);
```

   Jangan menambahkan fungsi `doGet()` kedua.
3. Buat sheet `RiskLab_Data` dengan kolom sesuai tabel di atas. Data dapat dihasilkan otomatis
   dari struktur sheet HORIZON Bapak.
4. Apps Script: **Project Settings → Script properties**. Tambahkan `API_TOKEN` berisi token panjang acak.
5. **Deploy → Manage deployments → Edit → New version**. Jalankan sebagai pemilik dan tentukan akses sesuai kebijakan sekolah.
6. Salin URL deployment `/exec`.
7. Di Streamlit Community Cloud, buka **App settings → Secrets**, lalu isi:

```toml
GAS_API_URL = "https://script.google.com/macros/s/DEPLOYMENT_ID/exec"
GAS_API_TOKEN = "token-yang-sama-dengan-script-properties"
```

Jangan commit `.streamlit/secrets.toml`; file tersebut sudah dimasukkan ke `.gitignore`.

## Menaruh di GitHub

```bash
git init
git add .
git commit -m "Initial HORIZON Risk Lab"
git branch -M main
git remote add origin https://github.com/USERNAME/horizon-risk-lab.git
git push -u origin main
```

Kemudian hubungkan repository tersebut di Streamlit Community Cloud dan pilih `app.py` sebagai
entry point. GitHub Pages tidak dapat menjalankan aplikasi Python ini.

## Sebelum memakai data nyata

- Repository sebaiknya private.
- Jangan simpan CSV siswa, token, password, atau URL rahasia di GitHub.
- Endpoint contoh memakai token sederhana dan cocok sebagai prototipe internal. Untuk produksi,
  tambahkan autentikasi pengguna/role atau letakkan analisis di lingkungan sekolah yang terkontrol.
- Gunakan ID siswa internal; minimalkan data identitas yang dikirim ke aplikasi analitik.
