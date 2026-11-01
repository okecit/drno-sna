"""Pemeliharaan produksi.

  python -m drno.maintenance wait-db     # tunggu PostgreSQL + skema siap (dipakai worker saat start)
  python -m drno.maintenance retention   # hapus unggahan yang melewati retention_until (+ interaksi & anotasi)
  python -m drno.maintenance stats       # ringkasan isi database
  python -m drno.maintenance label-channels  # isi nama publik kanal pemilik video YouTube yang sudah tersimpan
  python -m drno.maintenance fb-pages bnptri https://www.facebook.com/kemenag.ri   # cari ID Page untuk FB_PAGE_IDS
  python -m drno.maintenance discover-pages  # usulkan Page publik bernada serupa (ScrapeCreators) untuk ditinjau
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


def is_public_channel(stats: dict, min_subs: int) -> bool:
    """Kanal dianggap aktor publik bila subscriber >= ambang. Jumlah yang disembunyikan pemilik = bukan publik."""
    if stats.get("hiddenSubscriberCount"):
        return False
    return int(stats.get("subscriberCount") or 0) >= min_subs


def label_channels(min_subs: int | None = None) -> dict:
    """Beri nama publik HANYA pada kanal pemilik video yang memenuhi ambang aktor publik
    (DRNO_PUBLIC_CHANNEL_MIN_SUBS, default 10.000 subscriber); kanal di bawah ambang dikembalikan
    menjadi pseudonim. Kuota: videos.list + channels.list, 1 unit per 50 ID.
    Nama hanya ditempel bila pseudonim(channelId) cocok dengan penulis video yang tersimpan."""
    import httpx
    from .privacy import pseudonymize
    key = os.environ["YOUTUBE_API_KEY"]
    min_subs = int(min_subs if min_subs is not None else os.environ.get("DRNO_PUBLIC_CHANNEL_MIN_SUBS", 10000))
    get = lambda path, ids, part: httpx.get(f"https://www.googleapis.com/youtube/v3/{path}",
                                            params={"part": part, "id": ",".join(ids), "key": key}, timeout=30)
    with _conn() as c, c.transaction(), c.cursor() as cur:
        cur.execute("SELECT post_id, author_id_pseudonym FROM post WHERE platform = 'youtube' AND reply_to IS NULL")
        videos = {pid.split(":", 1)[1]: author for pid, author in cur.fetchall()}
        owner, mismatch, ids = {}, 0, list(videos)          # pseudonim -> channelId
        for i in range(0, len(ids), 50):
            r = get("videos", ids[i:i + 50], "snippet"); r.raise_for_status()
            for it in r.json().get("items", []):
                cid, author = it["snippet"]["channelId"], videos[it["id"]]
                if pseudonymize("youtube", cid) != author:
                    mismatch += 1
                else:
                    owner[author] = cid
        cids = sorted(set(owner.values()))
        info = {}
        for i in range(0, len(cids), 50):
            r = get("channels", cids[i:i + 50], "snippet,statistics"); r.raise_for_status()
            for it in r.json().get("items", []):
                info[it["id"]] = (it["snippet"]["title"], it.get("statistics", {}))
        public = private = 0
        for author, cid in owner.items():
            title, stats = info.get(cid, (None, {}))
            if title and is_public_channel(stats, min_subs):
                cur.execute("UPDATE author SET author_type = 'channel', public_entity_name = %s WHERE author_pseudonym = %s", (title, author))
                public += 1
            else:
                cur.execute("UPDATE author SET author_type = 'individual', public_entity_name = NULL WHERE author_pseudonym = %s AND author_type = 'channel'", (author,))
                private += 1
        detail = {"videos": len(videos), "channels": len(owner), "public": public, "pseudonymous": private, "min_subs": min_subs, "mismatch": mismatch}
        cur.execute("INSERT INTO audit_log(actor, action, detail) VALUES ('system', 'label-channels', %s)", (json.dumps(detail),))
    return detail


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    if cmd == "label-channels":
        print(json.dumps(label_channels(), indent=2))
        sys.exit(0)
    if cmd == "discover-pages":
        from .page_discovery import discover
        print(json.dumps(discover(), indent=2))
        sys.exit(0)
    if cmd == "fb-pages":
        from .collectors.base import NotConfigured
        from .collectors.facebook import resolve_pages
        try:
            rows = resolve_pages(sys.argv[2:])
        except NotConfigured as e:
            print(f"[DRNO] {e}. Isi token lewat skrip pengisi kunci setelah Page Public Content Access disetujui (lihat docs/FACEBOOK_PPCA.md).")
            sys.exit(2)
        for r in rows:
            print(f"{r['input']:<45} {r['id'] or '-':<20} {r['name'] or r['error']}")
        ok = [r["id"] for r in rows if r["id"]]
        print(f"\nFB_PAGE_IDS={','.join(ok)}" if ok else "\nTidak ada Page yang ditemukan (cek token & izin Page Public Content Access).")
        sys.exit(0 if ok else 1)
    if cmd == "wait-db":
        sys.exit(0 if wait_db() else 1)
    if cmd == "has-data":  # kode keluar 0 bila ada unggahan nyata
        sys.exit(0 if stats()["post"] > 0 else 1)
    print(json.dumps(retention() if cmd == "retention" else stats(), indent=2, default=str))
