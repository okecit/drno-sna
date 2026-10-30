import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_build_static_site_excludes_sensitive(tmp_path):
    data = tmp_path / "exp"
    data.mkdir()
    for f in (ROOT / "exports").glob("*.csv"):
        (data / f.name).write_bytes(f.read_bytes())
    (data / "posts_REAL.csv").write_text("post_id,text\n1,rahasia\n")
    out = tmp_path / "site"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_static_site.py"), "--data", str(data), "--out", str(out), "--mode", "static"], check=True)
    assert (out / "index.html").exists() and (out / ".htaccess").exists() and (out / "assets" / "d3.v7.min.js").exists()
    assert not (out / "data" / "posts_REAL.csv").exists()
    m = json.loads((out / "data" / "manifest.json").read_text())
    assert len(m["datasets"]) == 24
    html = (out / "index.html").read_text()
    assert "noindex" in html and "https://" not in html.split("<body>")[0]  # tanpa CDN eksternal
    assert "d3.csv(" not in (out / "assets" / "drno-runtime.js").read_text()  # patuh CSP (tanpa eval)


def test_build_php_login_site(tmp_path):
    out = tmp_path / "site"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_static_site.py"), "--data", str(ROOT / "exports"), "--out", str(out)], check=True)
    for f in ["index.php", "login.php", "logout.php", "data.php", "setup.php", "users.php", "inc/auth.php", "private/app.html",
              "private/setup_key.txt", "private/.htaccess", "data/.htaccess", "inc/.htaccess"]:
        assert (out / f).exists(), f
    assert not (out / "index.html").exists()  # dashboard hanya lewat index.php (login)
    assert not (out / "private" / "users.php").exists()  # akun tidak pernah ikut paket
    app = (out / "private" / "app.html").read_text()
    assert 'DRNO_DATA_URL = "data.php?f="' in app and "<!--DRNO_USERBAR-->" in app
