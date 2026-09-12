# HORIZON TKA — Decision Lab

Aplikasi Streamlit untuk **membaca** data HORIZON dari API Google Apps Script (GAS). Tidak menulis ke Google Sheet. Aplikasi yang diunggah ini tidak berisi daftar nilai siswa. Empat tab utama: **Tindakan Hari Ini**, **Siswa & Rapor**, **Strategi Fu–On**, dan **Kualitas Data**.

## Langkah unggah ke GitHub dan jalankan

1. Ekstrak ZIP, lalu unggah berkas `app.py`, `allocation.py`, `briefing.py`, `engine.py`, `report.py`, `requirements.txt`, dan `README.md` ke **akar** repositori GitHub yang digunakan Streamlit. Pada GitHub: **Add file → Upload files → Commit changes**. Jika ada berkas bernama sama, ganti dengan versi baru. Tidak perlu mengunggah berkas `.gs`, template CSV, PDF contoh, atau nilai asli siswa.
2. Tunggu Streamlit melakukan deploy ulang. Jika belum berubah, buka pengaturan aplikasi di Streamlit Community Cloud dan pilih **Reboot app**.
3. Di pengaturan aplikasi Streamlit, buka **Settings → Secrets**. Tempel satu kali:

   ```toml
   GAS_API_TOKEN = "ISI_TOKEN_API_YANG_SUDAH_DIPAKAI"
   ```

   Simpan lalu reboot. URL Web App GAS sebelumnya sudah menjadi nilai bawaan di `app.py`; tidak perlu diketik setiap membuka aplikasi. **Jangan unggah token maupun file `.streamlit/secrets.toml` ke GitHub**: keduanya membuka akses ke identitas dan nilai siswa bagi pembaca repositori. Aplikasi yang dapat dibuka publik juga dapat menampilkan data kepada publik; batasi akses Streamlit sesuai kebijakan sekolah.
4. Jika URL deployment berubah permanen, set `HORIZON_API_URL_OVERRIDE = "https://script.google.com/macros/s/.../exec"` pada Secrets; jika token berubah permanen, perbarui `GAS_API_TOKEN` di tempat yang sama. Di sidebar, menu **Ubah koneksi API bila diperlukan** bisa dipakai untuk mengganti URL/token **sementara dalam sesi ini saja**. Klik **Muat ulang nilai dari GAS** untuk membuang cache 3 menit dan membaca data terbaru.

Tidak ada opsi data demo atau unggah CSV di aplikasi. Jika API bermasalah, aplikasi menampilkan pesan kesalahan, bukan angka siswa contoh. Hanya endpoint GAS yang sudah di-deploy yang digunakan; **jangan menempelkan kode ini pada project GAS HORIZON utama**.

## Cara memakai empat tab

1. Sidebar: pilih **Peserta TKA**, **Semua Siswa**, atau **Tidak Ikut**; bisa pilih kelas asal. Nilai TO diambil dari GAS setiap maksimal tiga menit atau saat tombol muat ulang ditekan.
2. **Tindakan Hari Ini → Sekolah**: top 5/10 siswa yang membutuhkan perhatian, sekolah atau per kelas, dengan kategori serta langkah berikutnya. Bisa memilih satu kategori dan persentase cakupan perhatian.
3. **Tindakan Hari Ini → Wali Kelas**: pilih kelas, tinjau ringkasan tiga mapel dan sinyal *care khusus*, isi kolom *Keputusan guru/WK* jika perlu, lalu unduh **lembar tindakan PDF**. **Guru Mapel**: pilih Matematika, Bahasa Indonesia, atau Bahasa Inggris; bandingkan rata seluruh TO dan tiga terakhir, lalu unduh lembar PDF per mapel. Catatan edit ini tidak disimpan: unduh sebelum menutup halaman.
4. **Siswa & Rapor**: ranking seluruh TO, 5 terakhir, atau 3 terakhir; pilih Gabungan, PENABUR (`MT/BI/BIG`), atau HOLIS (`MTH/BIH/BIGH`). Klik siswa dan unduh rapor statistik PDF. **Rapor siswa tidak berisi form perhatian**.
5. **Strategi Fu–On**: rancangan 21 Fu, 30 Ch, 30 Am, 30 Pi, 29 On untuk **tepat 140 siswa**. Semua peserta TKA ditempatkan hanya di Fu, Ch, atau sebagian Am. Kolom peringkat ada di samping kelompok yang direkomendasikan; peringkat dan kecocokan Ch adalah dua hal berbeda. Usulan ini bukan keputusan akhir sekolah.
6. **Kualitas Data**: cek nilai yang kurang, status peserta yang belum lengkap dan sebaran TO; simulasi ilustratif disembunyikan dalam panel lanjutan karena **belum dikalibrasi dengan hasil TKA nyata**.

**TO tersisa** = `14 - jumlah putaran Matematika atau Bahasa Indonesia yang teridentifikasi`, minimum nol. Ini perkiraan jadwal berdasarkan kolom nilai yang sudah muncul pada API, **bukan** kepastian seluruh TO benar-benar telah dilaksanakan. Perbedaan rencana Bahasa Inggris (11) sengaja tidak dimasukkan.

Label perhatian dan potensi berkembang adalah *indikasi berdasarkan angka*, bukan diagnosis, peluang lulus, atau bukti dampak intervensi. Topik latihan harus dipastikan guru dari jawaban per butir. Guru/WK membandingkan rata semua TO dan tiga terakhir; perubahan terhadap tiga TO sebelumnya baru dihitung jika tersedia sedikitnya enam nilai per mapel.

## Berkas

- `app.py`: tampilan empat tab dan konfigurasi API.
- `engine.py`: pembaca GAS (GET saja), validasi data, simulasi lanjutan.
- `allocation.py`: ranking, prioritas dan usulan Fu–On.
- `briefing.py`: daftar tindakan guru/WK dan PDF-nya.
- `report.py`: analisis dan PDF rapor siswa.
- `requirements.txt`: dependensi Streamlit Cloud.

API GAS lama yang sudah berhasil membaca HORIZON tetap digunakan. Jangan mem-publish daftar siswa, CSV, screenshot nilai, atau token dalam repositori GitHub.
