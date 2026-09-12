# HORIZON TKA — Decision Lab

Aplikasi Streamlit untuk **membaca** data HORIZON dari API Google Apps Script (GAS). Tidak menulis ke Google Sheet. Aplikasi yang diunggah ini tidak berisi daftar nilai siswa. Lima tab utama: **Tindakan Hari Ini**, **Siswa & Rapor**, **Strategi Fu–On**, **Simulasi Skenario**, dan **Kualitas Data**.

## Langkah unggah ke GitHub dan jalankan

1. Ekstrak ZIP, lalu unggah berkas `app.py`, `allocation.py`, `briefing.py`, `engine.py`, `report.py`, `requirements.txt`, dan `README.md` ke **akar** repositori GitHub yang digunakan Streamlit. Pada GitHub: **Add file → Upload files → Commit changes**. Jika ada berkas bernama sama, ganti dengan versi baru. Berkas `gas_endpoint_roster.gs` **bukan berkas Streamlit**; petunjuk penggunaannya ada di bawah. Jangan unggah template CSV, PDF contoh, atau nilai asli siswa.
2. Tunggu Streamlit melakukan deploy ulang. Jika belum berubah, buka pengaturan aplikasi di Streamlit Community Cloud dan pilih **Reboot app**.
3. Di pengaturan aplikasi Streamlit, buka **Settings → Secrets**. Tempel satu kali:

   ```toml
   GAS_API_TOKEN = "ISI_TOKEN_API_YANG_SUDAH_DIPAKAI"
   ```

   Simpan lalu reboot. URL Web App GAS sebelumnya sudah menjadi nilai bawaan di `app.py`; tidak perlu diketik setiap membuka aplikasi. **Jangan unggah token maupun file `.streamlit/secrets.toml` ke GitHub**: keduanya membuka akses ke identitas dan nilai siswa bagi pembaca repositori. Aplikasi yang dapat dibuka publik juga dapat menampilkan data kepada publik; batasi akses Streamlit sesuai kebijakan sekolah.
4. Jika URL deployment berubah permanen, set `HORIZON_API_URL_OVERRIDE = "https://script.google.com/macros/s/.../exec"` pada Secrets; jika token berubah permanen, perbarui `GAS_API_TOKEN` di tempat yang sama. Di sidebar, menu **Ubah koneksi API bila diperlukan** bisa dipakai untuk mengganti URL/token **sementara dalam sesi ini saja**. Klik **Muat ulang nilai dari GAS** untuk membuang cache 3 menit dan membaca data terbaru.

Tidak ada opsi data demo atau unggah CSV di aplikasi. Jika API bermasalah, aplikasi menampilkan pesan kesalahan, bukan angka siswa contoh. **Jangan menempelkan kode API ini pada project GAS HORIZON utama.**

### Supaya siswa tanpa nilai sama sekali tetap muncul

API GAS sebelumnya hanya mengirim siswa yang sudah memiliki sedikitnya satu nilai. Untuk mengenali siswa tanpa nilai sama sekali, proyek Apps Script **HORIZON PYTHON API yang terpisah** juga perlu mengirim daftar siswa dari sheet `Data`:

1. Buka proyek Apps Script **HORIZON PYTHON API**, bukan proyek utama HORIZON. Buka `Code.gs` yang saat ini melayani URL `/exec`.
2. Ganti **isi file endpoint lama** dengan isi `gas_endpoint_roster.gs` dari ZIP. Pastikan tidak ada dua fungsi `doGet` di proyek itu. Jangan jalankan fungsi `setupPesertaTKA` atau menyentuh isi Sheet.
3. Simpan, lalu **Deploy → Manage deployments → Edit (ikon pensil) → Version: New version → Deploy**. URL `/exec` lama biasanya tetap jika deployment lama diedit; jika membuat deployment baru, masukkan URL baru melalui Secrets atau sidebar Streamlit.
4. Token API yang sudah tersimpan di Script Properties (`API_TOKEN`) tetap sama. Setelah deploy, di Streamlit klik **Muat ulang nilai dari GAS**. Jika jumlah siswa tetap kurang, cek apakah nama dan User siswa tersebut memang ada di sheet `Data`.

Kode API ini **hanya membaca** sheet `Data` dan `PesertaTKA`. Tanpa memperbarui endpoint, siswa yang punya **sebagian** nilai dapat dipindahkan ke On, tetapi siswa dengan **nol** nilai tidak dapat diketahui Python karena tidak ada dalam respons API lama.

## Cara memakai lima tab

1. Sidebar: pilih **Peserta TKA**, **Semua Siswa**, atau **Tidak Ikut**; bisa pilih kelas asal. Data dibaca ulang dari GAS bila halaman dijalankan kembali setelah cache tiga menit kedaluwarsa, atau segera saat tombol muat ulang ditekan. Halaman yang dibiarkan terbuka tanpa interaksi tidak memperbarui dirinya sendiri.
2. **Tindakan Hari Ini → Sekolah**: top 5/10 siswa yang membutuhkan perhatian, sekolah atau per kelas, dengan kategori serta langkah berikutnya. Bisa memilih satu kategori dan persentase cakupan perhatian.
3. **Tindakan Hari Ini → Wali Kelas**: pilih kelas, tinjau ringkasan tiga mapel dan sinyal *care khusus*, isi kolom *Keputusan guru/WK* jika perlu, lalu unduh **lembar tindakan PDF**. **Guru Mapel**: pilih Matematika, Bahasa Indonesia, atau Bahasa Inggris; bandingkan rata seluruh TO dan tiga terakhir, lalu unduh lembar PDF per mapel. Catatan edit ini tidak disimpan: unduh sebelum menutup halaman.
4. **Siswa & Rapor**: ranking seluruh TO, 5 terakhir, atau 3 terakhir; pilih Gabungan, PENABUR (`MT/BI/BIG`), atau HOLIS (`MTH/BIH/BIGH`). Klik siswa dan unduh rapor statistik PDF. **Rapor siswa tidak berisi form perhatian**.
5. **Strategi Fu–On**: rancangan **21 Fu, 31 Ch, 30 Am, 29 Pi, 29 On** untuk **tepat 140 siswa**. **Fu dan Ch wajib 100% peserta TKA yang memiliki data memadai** (52 orang); tidak boleh diisi nonpeserta. Peserta TKA berdata memadai yang tersisa masuk **Am** lebih dahulu. **Peserta TKA dengan data kurang juga masuk Am sementara**, ditandai jumlah nilai per mapel dan alasan; tidak dihitung bernilai nol dan tidak ditafsirkan sebagai kemampuan rendah. Jika sekarang ada 58 peserta, tepat **6 peserta** berada di Am (termasuk yang masuk sementara). Sisa kursi Am diisi nonpeserta; Pi dan On membagi rata 58 siswa. **Nonpeserta** dengan kurang dari 3 nilai per mapel utama masuk **On sementara**, disertai jumlah nilai dan alasan. Jika peserta TKA dengan data memadai kurang dari 52, jumlah peserta TKA melebihi kapasitas Fu/Ch/Am, atau lebih dari 29 nonpeserta harus berada di On sementara, aplikasi menampilkan penyebab dan tidak menerbitkan usulan. Ringkasan membedakan **Total siswa** dari **Ikut TKA (bagian dari total)**. Grafik **dipisahkan per sumber**: BPK PENABUR TO 1/2/3 berasal dari `MT01–03` dan `BI01–03` tanpa mengarang nilai Bahasa Inggris; HOLIS memiliki urutan sendiri. Usulan ini bukan keputusan akhir sekolah.
6. **Simulasi Skenario**: jalankan 5.000 percobaan per siswa pada nilai yang tersedia; pilih sumber gabungan/PENABUR/HOLIS, jumlah TO mendatang, serta asumsi kenaikan per mapel. Tabel menampilkan persentase **skenario rata-rata TO mendatang di bawah target**, median, rentang 10–90%, dan tindakan awal. Panduan internal: <35% pertahankan rutinitas; 35–49% pantau dan cek satu mapel; 50–69% penguatan terarah; ≥70% wali kelas berkoordinasi dengan guru mapel. **Persentase bukan peluang gagal TKA, bukan tingkat efektivitas latihan, dan belum dikalibrasi terhadap hasil TKA nyata.** Siswa dengan kurang dari tiga nilai pada salah satu mapel utama tidak diberi persentase atau proyeksi gabungan semu. Jika gabungan mencampur PENABUR dan HOLIS, tingkat kesulitan yang berbeda dapat membiaskan tren.
7. **Kualitas Data**: cek nilai yang kurang, status peserta yang belum lengkap, dan sebaran TO. Simulasi tidak lagi tersembunyi di sini.

**TO tersisa** = `14 - jumlah putaran Matematika atau Bahasa Indonesia yang teridentifikasi`, minimum nol. Ini perkiraan jadwal berdasarkan kolom nilai yang sudah muncul pada API, **bukan** kepastian seluruh TO benar-benar telah dilaksanakan. Perbedaan rencana Bahasa Inggris (11) sengaja tidak dimasukkan.

Label perhatian dan potensi berkembang adalah *indikasi berdasarkan angka*, bukan diagnosis, peluang lulus, atau bukti dampak intervensi. Topik latihan harus dipastikan guru dari jawaban per butir. Guru/WK membandingkan rata semua TO dan tiga terakhir; perubahan terhadap tiga TO sebelumnya baru dihitung jika tersedia sedikitnya enam nilai per mapel. Nilai rata-rata yang disajikan pada dashboard dan rapor dibulatkan ke dua angka di belakang koma.

## Berkas

- `app.py`: tampilan lima tab dan konfigurasi API.
- `engine.py`: pembaca GAS (GET saja), validasi data, simulasi lanjutan.
- `allocation.py`: ranking, prioritas dan usulan Fu–On.
- `briefing.py`: daftar tindakan guru/WK dan PDF-nya.
- `report.py`: analisis dan PDF rapor siswa.
- `requirements.txt`: dependensi Streamlit Cloud.

Web App GAS terpisah yang sudah berhasil membaca HORIZON tetap dipakai; hanya kode endpoint-nya diperluas agar daftar siswa tanpa nilai turut dikirim. Jangan mem-publish daftar siswa, CSV, screenshot nilai, atau token dalam repositori GitHub.

**Perubahan status Ikut/Tidak Ikut**: ubah kolom `Status TKA` pada sheet `PesertaTKA` yang dibaca endpoint API (bukan CSV atau pengaturan Streamlit). GAS membaca status setiap permintaan; Streamlit akan menampilkan perubahan setelah **Muat ulang nilai dari GAS** ditekan, atau ketika halaman dijalankan ulang sesudah cache tiga menit habis. Jika nama/User dalam daftar peserta tidak cocok dengan sheet `Data`, status bisa muncul `Belum diatur`.
