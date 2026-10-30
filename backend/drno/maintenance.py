"""Pemeliharaan produksi.

  python -m drno.maintenance wait-db     # tunggu PostgreSQL + skema siap (dipakai worker saat start)
  python -m drno.maintenance retention   # hapus unggahan yang melewati retention_until (+ interaksi & anotasi)
  python -m drno.maintenance stats       # ringkasan isi database
"""
from __future__ import annotations

import json
import os
import sys
import time


def _conn():
    import psycopg
    return psycopg.connect(os.environ["DATABASE_URL"])


def wait_db(timeout: int = 180) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with _conn() as c, c.cursor() as cur:
                cur.execute("SELECT 1 FROM post LIMIT 1")
            return True
        except Exception as e:  # noqa: BLE001
            print(f"[wait-db] belum siap: {e.__class__.__name__}", file=sys.stderr)
            time.sleep(3)
    return False


def retention() -> dict:
    with _conn() as c, c.transaction(), c.cursor() as cur:
        cur.execute("CREATE TEMP TABLE expired ON COMMIT DROP AS SELECT post_id FROM post WHERE retention_until < CURRENT_DATE")
        cur.execute("DELETE FROM interaction WHERE post_id IN (SELECT post_id FROM expired)")
        n_i = cur.rowcount
        cur.execute("DELETE FROM machine_annotation WHERE post_id IN (SELECT post_id FROM expired)")
        cur.execute("DELETE FROM manual_annotation WHERE post_id IN (SELECT post_id FROM expired)")
        cur.execute("DELETE FROM post WHERE post_id IN (SELECT post_id FROM expired)")
        n_p = cur.rowcount
        cur.execute("""DELETE FROM author a WHERE NOT EXISTS (SELECT 1 FROM post p WHERE p.author_id_pseudonym = a.author_pseudonym)
                       AND NOT EXISTS (SELECT 1 FROM interaction i WHERE i.source_author = a.author_pseudonym OR i.target_author = a.author_pseudonym)""")
        n_a = cur.rowcount
        cur.execute("INSERT INTO audit_log(actor, action, detail) VALUES ('system', 'retention', %s)",
                    (json.dumps({"posts": n_p, "interactions": n_i, "authors": n_a}),))
    return {"posts_deleted": n_p, "interactions_deleted": n_i, "authors_deleted": n_a}


def stats() -> dict:
    with _conn() as c, c.cursor() as cur:
        out = {}
        for t in ("post", "interaction", "author", "collection_run", "audit_log"):
            cur.execute(f"SELECT count(*) FROM {t}")
            out[t] = cur.fetchone()[0]
        cur.execute("SELECT platform, count(*) FROM post GROUP BY platform ORDER BY 2 DESC")
        out["per_platform"] = dict(cur.fetchall())
        cur.execute("SELECT max(finished_at)::text FROM collection_run WHERE status IN ('success','partial')")
        out["last_successful_run"] = cur.fetchone()[0]
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    if cmd == "wait-db":
        sys.exit(0 if wait_db() else 1)
    if cmd == "has-data":  # kode keluar 0 bila ada unggahan nyata
        sys.exit(0 if stats()["post"] > 0 else 1)
    print(json.dumps(retention() if cmd == "retention" else stats(), indent=2, default=str))
