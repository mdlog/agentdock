# Rencana menang — hasil audit 3 juri simulasi + 4 investigasi (2026-08-16)

Tiga agen juri independen menilai situs live persis seperti rubrik penyelenggara,
dengan instruksi keras dan verifikasi sendiri (mereka benar-benar meng-hire agent
lewat marketplace kita). Empat investigasi paralel memeriksa Altana, jalur juri,
kelayakan Agent Advantage Report TermiX, dan opsi PancakeSwap. Sisa waktu build:
**24 hari** (tutup 9 Sep 12:00 UTC).

## Skor hari ini

| Kriteria utama | Skor | Vonis singkat |
|---|---|---|
| Functionality | **6/10** | Perjalanan inti bekerja nyata (land → kategori → paham → aktivasi tanpa wallet, jawaban MCP asli 5,6 dtk) — tapi ada jebakan terverifikasi |
| Data Quality | **6/10** | Real-time terbukti, vonis probe per-agent adalah pembeda — tapi angka "ready" menggelembung secara substansi |
| Agent Diversity | **4/10** | Empat kategori setara secara struktur, TIDAK setara secara kedalaman: Grid Trading dead end total |

Ketiga juri memuji hal yang sama: *"honesty engineering yang kebanyakan submission
hackathon dipalsukan, AgentDock tidak"*. Dan ketiganya menemukan lubang yang sama.

## Temuan yang menjatuhkan skor (semuanya direproduksi live oleh juri)

1. **Error dirender sebagai sukses.** Agent unggulan Rebalancing #265375 (BNB LP
   Range Rebalancer) mengembalikan `{"error": "unknown skill: None"}` dan task
   ditampilkan `completed`. Agent A2A tanpa tool "selesai" dengan
   `{"status": "OK"}`. Pengguna awam tak bisa membedakannya dari hasil nyata.
   *Ini persis kelas bug yang produk ini ada untuk mengoreksi — di lapisan task
   kita sendiri.*
2. **230 klon Singularry.** 34 dari 60 kartu pertama halaman ready adalah klon
   satu gateway; meng-hire "Jarvis" dan "007" menghasilkan keluaran byte-identik
   (daftar platform generik). Hanya ~12 agent yang benar-benar terdiferensiasi.
   **Koreksi atas dugaan sebelumnya:** membuka argumen `nfaTokenId` TIDAK
   menolong hari ini — keempat tool data Singularry (`get_agent_pnl`,
   `get_agent_strategies`, `get_recent_decisions`, `get_agent_portfolio`)
   adalah **stub** ("pending tool-data API consolidation"); route PnL asli ada
   tapi di balik auth (401). Jadi perlakuannya: kolaps/label sebagai satu
   penyedia gateway-bersama, dan hitung ulang angka "ready" per kapabilitas
   terdiferensiasi.
3. **Grid Trading = dead end total.** 0 callable dari 345, 0 payable, 0 dari 34
   resource b402. Satu dari empat kartu kategori — klik pertama 1-banding-4
   seorang juri — tidak menghasilkan apa pun. Tidak ada strategi Singularry
   yang berupa grid; tidak ada jalan pintas dari registry.
4. **Padding kategori.** "Fly Marketing Agent" (tool: `generate_marketing_plan`,
   `get_payment_link`) terhitung di Yield Optimisation. Guardian Health Factor
   #266933 memantau posisi kosong (collateral 0, debt 0, HF null).
5. **Friksi kecil:** `POST /api/tasks` 422 dua kali (objective wajib, ≥12 char,
   tak terdokumentasi); resource b402 bortagent 404; halaman explorer default
   mencampur baris error/payment.

## Peluang partner track (hasil investigasi)

**TermiX** — Agent Advantage Report **bisa diproduksi hari ini**: Task A = audit
risiko lending Aave via HeyAnon #45381 (slot *trading/stock/security*, dibingkai
security/risk; manual ~20–40 mnt vs ~detik), Task B = scan APR Venus #43129,
Task C = OpenOdds #49637 (odds 3 bandar + analitik xG same-day; manual 30–60
mnt), Task D cadangan = ClawdMint. Catatan jujur: rekam jejak trading
(win-rate/window/risk) belum tersedia dari agent publik mana pun — OpenOdds punya
177 prediksi settled tapi `win_rate=null`; posisi V3 si rebalancer nyata tapi
skala demo (TVL ~$0,81).

**PancakeSwap** — separuh sudah ada. Rebalancer #265375 mengelola posisi
PancakeSwap V3 BNB/USDT nyata di mainnet (NFT 7116214, tick -65080/-63070) dan
punya REST operator publik (`/status`: harga pool 607,46, range 548–670,
in-range true). Sumber data terverifikasi: `explorer.pancakeswap.com/api/cached`
tanpa key (TVL $4,57 jt, fee APR ~4,85% untuk pool itu) — perlu proxy backend
kecil (tanpa header CORS; pola `icon_proxy.py` sudah ada). Irisan 1,5–2 hari:
panel konteks pool + widget status rebalancer. **Dobel manfaat** dengan TermiX.

**Altana** — nyata dan terdokumentasi baik. KeyStore terverifikasi ter-deploy di
BSC mainnet & testnet (cek bytecode langsung), SDK TypeScript (viem ^2.21)
kompatibel dengan frontend wagmi/viem kita, tanpa API key, testnet lengkap
(relay + explorer + faucet). Integrasi terkecil yang memenuhi bar track
(wallet agent + session dengan limit on-chain + terdaftar KeyStore + tx nyata
via session key + lihat/cabut dalam produk): **3–4 hari**, hampir seluruhnya
frontend. Jebakan: jangan rutekan EIP-3009 b402 lewat smart account (ERC-1271 di
facilitator Binance belum terverifikasi) — pakai rel `execute`/ERC-8183 Altana.

## Urutan pengerjaan yang direkomendasikan

**Minggu 1 — P0 main track** (menaikkan ketiga skor sekaligus):
1. **Gerbang kejujuran hasil task** — payload error / `{"status":"OK"}` kosong =
   task gagal dengan alasan, bukan `completed`. (Fix yang diminta juri
   Functionality secara eksplisit.)
2. **Kolaps/label klon gateway-bersama** — satu kartu per layanan
   terdiferensiasi, lencana "endpoint dipakai N registrasi", hitung ulang
   headline + ready per kategori. (Diminta juri Data Quality.)
3. **Perbaiki interop #265375** — cari format skill A2A yang benar (lane
   PancakeSwap berhasil mendapat quote ERC-8183 bertanda tangan via
   `negotiate`, jadi agent-nya hidup; jalur run kita yang salah kirim).
4. Bersihkan miskategorisasi (marketing→keluar dari yield) + friksi 422 +
   singkirkan resource b402 yang 404.
5. **Keputusan grid** *(butuh keputusan Anda)*: bangun + registrasi agent Grid
   Trading milik kita (monitor/simulator grid-order read-only atas pasangan
   PancakeSwap, ERC-8004 di BSC mainnet, di-host seperti layanan kita yang
   lain). Juri Diversity menyebut ini fix tunggal terbesar; tanpa ini skor 4/10
   sulit naik.

**Minggu 2 — bukti nilai:**
6. Agent Advantage Report (Task A–C di atas, ukur waktu/biaya/kualitas dua arah,
   lampirkan keluaran asli) — 1–2 hari.
7. Irisan PancakeSwap 1,5–2 hari (panel pool + status rebalancer).

**Minggu 2–3 — Altana** (3–4 hari, testnet dulu, mainnet bila lancar), lalu
buffer + polish + submission packaging.

Total estimasi: ~13–16 hari kerja dari 24 hari tersisa — muat, dengan buffer.

## Keputusan yang menunggu

1. Bangun agent Grid Trading sendiri? (rekomendasi: **ya** — penentu Diversity)
2. Komit track mana di form (TermiX masih tercentang; PancakeSwap kini punya
   dasar nyata; Altana layak bila waktunya cukup — ketiganya tidak eksklusif)
3. Dana kecil untuk demo mainnet (settlement b402 pertama ±1 USD1; funding job
   ERC-8183 0,1 $U) — memperkuat Functionality dan bukti TermiX
