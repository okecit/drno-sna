"""Rakit situs statis DRNO siap unggah (shared hosting / VPS).

  python scripts/build_static_site.py --data exports_real --out deploy/dist/drno
  python scripts/build_static_site.py --data exports            # data sintetis bawaan

Hasil: index.html + assets/ + data/ (CSV + manifest.json) + .htaccess + robots.txt.
Tidak butuh PHP/Python/Node di server; cukup web server statis (Apache/Nginx/LiteSpeed).
"""
import argparse
import csv
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "deploy" / "static-site"
DATASETS = ["overview", "weekly_platform", "context_counts", "stance_weekly", "keyword_weekly", "nodes", "edges_weekly",
            "temporal", "community_context", "narrative_nodes", "narrative_edges", "position_change", "platform_context",
            "platform_sentiment", "platform_stance", "platform_summary", "broker_nodes", "tie_summary", "homophily",
            "mixing_stance", "identity_markers", "sna_nodes", "sna_edges", "sna_posts"]
# Berkas yang TIDAK pernah diunggah ke web (teks lengkap / antrean internal)
NEVER_PUBLISH = {"posts_REAL.csv", "posts_SYNTHETIC.csv", "manual_review_queue.csv"}

HTML = """<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22%3E%3Ctext y=%22.9em%22 font-size=%2290%22%3E%F0%9F%95%B8%EF%B8%8F%3C/text%3E%3C/svg%3E">
<title>DRNO — Digital Radicalization Network Observatory</title>
<link rel="stylesheet" href="assets/drno-theme.css?v={ver}">
<script src="assets/d3.v7.min.js"></script>
<script src="assets/drno-runtime.js?v={ver}"></script>
</head>
<body>
<div id="dash-root">
<div id="drno-boot-error" role="alert"></div>
<p id="drno-meta"></p>
{body}
</div>
<noscript>DRNO memerlukan JavaScript.</noscript>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "exports"))
    ap.add_argument("--out", default=str(ROOT / "deploy" / "dist" / "drno"))
    ap.add_argument("--mode", choices=["php", "static"], default="php",
                    help="php = dengan halaman login (default, butuh PHP 7.4+ di hosting); static = tanpa login")
    a = ap.parse_args()
    data, out = Path(a.data), Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    (out / "assets").mkdir(parents=True)
    (out / "data").mkdir()
    for f in ["d3.v7.min.js", "drno-runtime.js", "drno-theme.css"]:
        shutil.copy(SRC / "assets" / f, out / "assets" / f)
    ver = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    body = (SRC / "assets" / "page_body.html").read_text(encoding="utf-8")
    html = HTML.replace("{ver}", ver).replace("{body}", body)
    if a.mode == "php":
        html = html.replace('<script src="assets/d3.v7.min.js">',
                            '<link rel="stylesheet" href="assets/login.css?v=' + ver + '">\n<script>window.DRNO_DATA_URL = "data.php?f=";</script>\n<script src="assets/d3.v7.min.js">')
        html = html.replace('<div id="dash-root">', '<div id="dash-root">\n<!--DRNO_USERBAR-->')
        (out / "private").mkdir()
        (out / "private" / "app.html").write_text(html, encoding="utf-8")
        shutil.copy(SRC / "assets" / "login.css", out / "assets" / "login.css")
        for f in (SRC / "php").rglob("*.php"):
            dst = out / f.relative_to(SRC / "php")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(f, dst)
        import secrets
        (out / "private" / "setup_key.txt").write_text(secrets.token_urlsafe(18) + "\n")
        for d in ("private", "inc", "data"):
            shutil.copy(SRC / "deny_all.htaccess", out / d / ".htaccess")
    else:
        (out / "index.html").write_text(html, encoding="utf-8")
    missing, sets = [], []
    for d in DATASETS:
        src = data / f"{d}.csv"
        if not src.exists():
            missing.append(d)
            continue
        shutil.copy(src, out / "data" / src.name)
        sets.append({"id": d, "file": src.name})
    if not sets:
        sys.exit(f"Tidak ada dataset di {data} - situs tidak dirakit (mencegah dashboard kosong).")
    mode = "synthetic"
    ov = data / "overview.csv"
    if ov.exists():
        rows = list(csv.DictReader(ov.open(encoding="utf-8")))
        mode = (rows[0].get("data_mode") or "synthetic") if rows else "synthetic"
    json.dump({"generated_at": datetime.now(timezone.utc).isoformat(), "data_mode": mode, "datasets": sets},
              open(out / "data" / "manifest.json", "w"), ensure_ascii=False, indent=1)
    shutil.copy(SRC / ("htaccess_php.txt" if a.mode == "php" else "htaccess.txt"), out / ".htaccess")
    shutil.copy(SRC / "robots.txt", out / "robots.txt")
    leaked = [p.name for p in (out / "data").iterdir() if p.name in NEVER_PUBLISH]
    assert not leaked, f"Berkas sensitif ikut tersalin: {leaked}"
    info = {"out": str(out), "site_mode": a.mode, "data_mode": mode, "datasets": len(sets), "missing": missing}
    if a.mode == "php":
        info["setup_key"] = (out / "private" / "setup_key.txt").read_text().strip()
    print(json.dumps(info, indent=1))


if __name__ == "__main__":
    main()
