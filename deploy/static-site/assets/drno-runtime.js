/* DRNO runtime mandiri: pengganti runtime dashboard Claude agar halaman berjalan di hosting biasa.
   Membaca data/manifest.json lalu memuat setiap CSV di folder data/. Tanpa server-side code. */
(function () {
  // Format angka & tanggal Indonesia (1.234,5; Jan, Feb, Mar, ...)
  d3.formatDefaultLocale({ decimal: ',', thousands: '.', grouping: [3], currency: ['Rp', ''] });
  d3.timeFormatDefaultLocale({ dateTime: '%A, %e %B %Y %X', date: '%d/%m/%Y', time: '%H.%M.%S', periods: ['AM', 'PM'],
    days: ['Minggu', 'Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu'], shortDays: ['Min', 'Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab'],
    months: ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember'],
    shortMonths: ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des'] });
  // Palet kategori selaras logo (biru, teal, hijau merek); indeks 3 tetap merah untuk makna negatif/kritis
  const PALETTE = ['#1e63b8', '#d97706', '#2fa36b', '#dc2626', '#7c3aed', '#13998c', '#db2777', '#14306b'];
  const state = {};          // id -> {status, data, error}
  const listeners = [];
  let scheduled = false;
  const fire = () => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => { scheduled = false; listeners.forEach((f) => { try { f(); } catch (e) { console.error(e); } }); });
  };
  // Mode PHP (login): data lewat data.php?f=...; mode statis: data/...
  const dataUrl = (f, v) => window.DRNO_DATA_URL
    ? `${window.DRNO_DATA_URL}${encodeURIComponent(f)}&v=${encodeURIComponent(v)}`
    : `data/${f}?v=${encodeURIComponent(v)}`;
  const onAuthFail = (r) => { if (r.status === 401) { location.href = 'login.php?idle=1'; throw new Error('sesi berakhir'); } };
  const ver = () => (window.DRNO_MANIFEST && window.DRNO_MANIFEST.generated_at) || Date.now();

  window.dash = {
    colors: PALETTE,
    data(id) { return state[id] || { status: 'missing', data: [] }; },
    onData(fn) { listeners.push(fn); fire(); },
    setLink(token) { try { history.replaceState(null, '', '#' + token); } catch (e) { /* abaikan */ } },
  };

  async function boot() {
    let manifest;
    try {
      const r = await fetch(dataUrl('manifest.json', Date.now()), { cache: 'no-store', credentials: 'same-origin' });
      onAuthFail(r);
      if (!r.ok) throw new Error('HTTP ' + r.status);
      manifest = await r.json();
    } catch (e) {
      document.getElementById('drno-boot-error').textContent =
        'Gagal memuat data/manifest.json (' + e.message + '). Pastikan folder data/ ikut terunggah, Anda sudah masuk, dan halaman dibuka lewat http(s).';
      document.getElementById('drno-boot-error').style.display = 'block';
      return;
    }
    window.DRNO_MANIFEST = manifest;
    const meta = document.getElementById('drno-meta');
    if (meta) meta.textContent = `Data diperbarui ${new Date(manifest.generated_at).toLocaleString('id-ID')} · mode ${manifest.data_mode}`;
    manifest.datasets.forEach((d) => { state[d.id] = { status: 'loading', data: [] }; });
    fire();
    await Promise.all(manifest.datasets.map(async (d) => {
      try {
        // d3.csv/csvParse memakai new Function (eval) yang diblokir Content-Security-Policy; parse manual.
        const r = await fetch(dataUrl(d.file, ver()), { cache: 'no-store', credentials: 'same-origin' });
        onAuthFail(r);
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const table = d3.csvParseRows((await r.text()).replace(/^\uFEFF/, ''));
        const head = table.shift() || [];
        const rows = table.filter((t) => t.length > 1 || t[0] !== '').map((t) => { const o = {}; head.forEach((h, i) => { o[h] = t[i] ?? ''; }); return o; });
        rows.columns = head;
        state[d.id] = { status: 'ok', data: rows };
      } catch (e) {
        state[d.id] = { status: 'error', data: [], error: String(e) };
      }
      fire();
    }));
  }
  document.addEventListener('DOMContentLoaded', boot);
})();
