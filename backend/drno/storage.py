"""Penyimpanan hasil crawling nyata.

- JsonlStore   : default untuk uji coba lokal (folder data/). Append-only + dedup by post_id.
- PostgresStore: produksi, memakai db/schema.sql (DATABASE_URL). Membutuhkan psycopg 3.
Keduanya menulis audit log setiap run.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


class JsonlStore:
    def __init__(self, root: str = "data"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _ids(self, name, key):
        p = self.root / name
        if not p.exists():
            return set()
        return {json.loads(l)[key] for l in p.open(encoding="utf-8") if l.strip()}

    def _append(self, name, rows):
        with (self.root / name).open("a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def save(self, records, interactions, report, job) -> dict:
        have = self._ids("posts.jsonl", "post_id")
        new = [r for r in records if r["post_id"] not in have]
        new_ids = {r["post_id"] for r in new}
        self._append("posts.jsonl", new)
        self._append("interactions.jsonl", [i for i in interactions if i["post_id"] in new_ids])
        run = {"at": datetime.now(timezone.utc).isoformat(), "platform": job.platform, "query": job.query,
               "query_native": job.query_native, "date_from": job.date_from, "date_to": job.date_to, "legal_basis": job.legal_basis,
               "status": report.status, "fetched": report.fetched, "inserted": len(new),
               "duplicates": report.duplicates + (len(records) - len(new)), "errors": report.errors}
        self._append("runs.jsonl", [run])
        self._append("audit.jsonl", [{"at": run["at"], "actor": os.environ.get("DRNO_ACTOR", "peneliti"), "action": "collect", "detail": run}])
        self._append("authors.jsonl", [{"author": r["author_id_pseudonym"], "type": r["author_type"], "name": r["public_entity_name"]}
                                       for r in records if r.get("public_entity_name") and r.get("author_type") != "individual"])
        return run

    def load_public_names(self) -> dict:
        p = self.root / "authors.jsonl"
        if not p.exists():
            return {}
        rows = [json.loads(l) for l in p.open(encoding="utf-8") if l.strip()]
        return {r["author"]: {"type": r["type"], "name": r["name"]} for r in rows}

    def load(self):
        def rd(n):
            p = self.root / n
            return [json.loads(l) for l in p.open(encoding="utf-8")] if p.exists() else []
        return rd("posts.jsonl"), rd("interactions.jsonl"), rd("runs.jsonl")


class PostgresStore:  # pragma: no cover - memerlukan server PostgreSQL
    def __init__(self, dsn: str | None = None):
        import psycopg
        self.conn = psycopg.connect(dsn or os.environ["DATABASE_URL"])

    def save(self, records, interactions, report, job) -> dict:
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute("""INSERT INTO collection_job(platform, query, language, date_from, date_to, max_records, source_method, legal_basis)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING job_id""",
                        (job.platform, job.query_native or job.query, job.language, job.date_from, job.date_to, job.max_records,
                         records[0]["source_method"] if records else "official_api", job.legal_basis))
            job_id = cur.fetchone()[0]
            cur.execute("""INSERT INTO collection_run(job_id, status, fetched, duplicates, error_message, finished_at)
                           VALUES (%s,%s,%s,%s,%s, now()) RETURNING run_id""",
                        (job_id, report.status, report.fetched, report.duplicates, "; ".join(report.errors) or None))
            run_id = cur.fetchone()[0]
            inserted, new_ids = 0, set()
            for r in records:
                a = r["author_id_pseudonym"]
                atype = r.get("author_type") or ("media" if a.startswith("media:") else "organization_public" if a.startswith("page:") else "individual")
                name = r.get("public_entity_name") if atype != "individual" else None
                # Akun yang sekali terbukti publik (mis. kanal pemilik video) tidak diturunkan lagi menjadi individu
                cur.execute("""INSERT INTO author(author_pseudonym, platform, author_type, public_entity_name, first_seen, last_seen)
                               VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (author_pseudonym) DO UPDATE
                               SET last_seen = GREATEST(author.last_seen, EXCLUDED.last_seen),
                                   author_type = CASE WHEN EXCLUDED.author_type <> 'individual' THEN EXCLUDED.author_type ELSE author.author_type END,
                                   public_entity_name = COALESCE(EXCLUDED.public_entity_name, author.public_entity_name)""",
                            (a, r["platform"], atype, name, r["timestamp"], r["timestamp"]))
                cur.execute("""INSERT INTO post(post_id, platform, timestamp, text, url, author_id_pseudonym, language, keyword_matched,
                               reply_to, mention, repost_of, engagement_count, source_method, is_synthetic, run_id, content_hash, retention_until)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,false,%s,%s,%s) ON CONFLICT DO NOTHING""",
                            (r["post_id"], r["platform"], r["timestamp"], r["text"], r["url"], a, r["language"], r["keyword_matched"],
                             r["reply_to"], r["mention"], r["repost_of"], r["engagement_count"], r["source_method"], run_id,
                             r["content_hash"], r["retention_until"]))
                if cur.rowcount:
                    inserted += 1
                    new_ids.add(r["post_id"])
            for i in interactions:
                if i["post_id"] not in new_ids:
                    continue  # interaksi dari unggahan yang sudah tersimpan tidak digandakan
                cur.execute("""INSERT INTO author(author_pseudonym, platform) VALUES (%s,%s) ON CONFLICT DO NOTHING""", (i["target"], i["platform"]))
                cur.execute("""INSERT INTO interaction(source_author, target_author, interaction_type, post_id, timestamp, platform)
                               SELECT %s,%s,%s,%s,%s,%s WHERE EXISTS (SELECT 1 FROM post WHERE post_id=%s)""",
                            (i["source"], i["target"], i["type"], i["post_id"], i["timestamp"], i["platform"], i["post_id"]))
            cur.execute("UPDATE collection_run SET inserted=%s WHERE run_id=%s", (inserted, run_id))
            cur.execute("INSERT INTO audit_log(actor, action, object_ref, detail) VALUES (%s,'collect',%s,%s)",
                        (os.environ.get("DRNO_ACTOR", "peneliti"), f"run:{run_id}", json.dumps({"status": report.status, "inserted": inserted})))
        return {"run_id": run_id, "status": report.status, "inserted": inserted, "fetched": report.fetched}

    def load(self):
        with self.conn.cursor() as cur:
            cur.execute("""SELECT post_id, platform, timestamp::text, text, url, author_id_pseudonym, language, keyword_matched,
                           reply_to, mention, repost_of, engagement_count, source_method, is_synthetic FROM post WHERE is_synthetic = false""")
            cols = [d.name for d in cur.description]
            posts = [dict(zip(cols, r)) for r in cur.fetchall()]
            cur.execute("""SELECT source_author AS source, target_author AS target, interaction_type AS type, post_id, timestamp::text, platform FROM interaction""")
            cols = [d.name for d in cur.description]
            inter = [dict(zip(cols, r)) for r in cur.fetchall()]
        return posts, inter, []

    def load_public_names(self) -> dict:
        with self.conn.cursor() as cur:
            cur.execute("""SELECT author_pseudonym, author_type, public_entity_name FROM author
                           WHERE author_type <> 'individual' AND public_entity_name IS NOT NULL""")
            return {a: {"type": t, "name": n} for a, t, n in cur.fetchall()}


def get_store():
    return PostgresStore() if os.environ.get("DRNO_STORE") == "postgres" else JsonlStore(os.environ.get("DRNO_DATA_DIR", "data"))
