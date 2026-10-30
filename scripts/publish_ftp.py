"""Unggah situs statis DRNO ke hosting via FTPS (FTP over TLS) — default cPanel.

  set -a; source .env; set +a
  python scripts/publish_ftp.py --site deploy/dist/drno            # unggah penuh
  python scripts/publish_ftp.py --site deploy/dist/drno --data-only # hanya perbarui data/

Variabel .env: FTP_HOST, FTP_USER, FTP_PASS, FTP_DIR (mis. /public_html/drno), FTP_PORT (21), FTP_TLS (1)
Aman terhadap pengunjung yang sedang membuka halaman: setiap berkas diunggah sebagai .tmp lalu
di-rename, dan manifest.json diunggah PALING AKHIR sehingga halaman tidak pernah membaca data setengah jadi.
"""
import argparse
import ftplib
import os
import sys
from pathlib import Path


def connect():
    host, user, pw = (os.environ.get(k) for k in ("FTP_HOST", "FTP_USER", "FTP_PASS"))
    if not all([host, user, pw]):
        sys.exit("Isi FTP_HOST, FTP_USER, FTP_PASS di .env")
    port = int(os.environ.get("FTP_PORT", 21))
    use_tls = os.environ.get("FTP_TLS", "1") != "0"
    ftp = ftplib.FTP_TLS() if use_tls else ftplib.FTP()
    ftp.connect(host, port, timeout=60)
    ftp.login(user, pw)
    if use_tls:
        ftp.prot_p()  # enkripsi kanal data
    ftp.set_pasv(True)
    return ftp


def ensure_dir(ftp, path):
    parts = [p for p in path.strip("/").split("/") if p]
    cur = ""
    for p in parts:
        cur += "/" + p
        try:
            ftp.mkd(cur)
        except ftplib.error_perm:
            pass  # sudah ada


def put(ftp, local: Path, remote: str):
    tmp = remote + ".tmp"
    with open(local, "rb") as f:
        ftp.storbinary(f"STOR {tmp}", f)
    try:
        ftp.delete(remote)
    except ftplib.error_perm:
        pass
    ftp.rename(tmp, remote)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="deploy/dist/drno")
    ap.add_argument("--data-only", action="store_true")
    a = ap.parse_args()
    site = Path(a.site)
    if not (site / "data" / "manifest.json").exists():
        sys.exit("Jalankan dulu scripts/build_static_site.py")
    base = os.environ.get("FTP_DIR", "/public_html/drno").rstrip("/")
    ftp = connect()
    # Jangan pernah menimpa akun & log di server
    files = sorted(p for p in site.rglob("*") if p.is_file() and not (p.parent.name == "private" and p.name in ("users.php", "access_log.tsv")))
    if a.data_only:
        files = [p for p in files if p.parent.name == "data"]
    manifest = site / "data" / "manifest.json"
    files = [p for p in files if p != manifest] + [manifest]
    n = 0
    for p in files:
        rel = p.relative_to(site).as_posix()
        if p.name == ".htaccess" and a.data_only:
            continue
        ensure_dir(ftp, f"{base}/{Path(rel).parent.as_posix()}" if "/" in rel else base)
        put(ftp, p, f"{base}/{rel}")
        n += 1
        print("✓", rel)
    ftp.quit()
    print(f"Selesai: {n} berkas ke {base}")


if __name__ == "__main__":
    main()
