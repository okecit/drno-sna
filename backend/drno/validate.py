"""Validasi manual klasifikasi mesin (tahap 9).

1) Sampel untuk anotasi dua pengode (bertingkat per platform x label mesin; label mesin DISEMBUNYIKAN):
   python -m drno.validate sample --n 400 --out validasi/
   -> validasi/coder_A.csv, validasi/coder_B.csv (urutan acak berbeda), validasi/_kunci.csv (label mesin, untuk peneliti)
2) Setelah kedua pengode mengisi kolom context/stance/sentiment/emotion:
   python -m drno.validate score validasi/coder_A.csv validasi/coder_B.csv --key validasi/_kunci.csv
   -> Cohen's kappa antarpengode per tugas, lalu precision/recall/F1 mesin vs label yang disepakati.

Ambang kerja yang umum dipakai: kappa >= 0,70 sebelum label dipakai sebagai gold standard.
Unggahan yang tidak disepakati harus diadjudikasi peneliti; tidak dihitung sebagai gold.
"""
from __future__ import annotations

import argparse
import csv
import random
from collections import Counter, defaultdict
from pathlib import Path

TASKS = ["context", "stance", "sentiment", "emotion"]
CODEBOOK = {
    "context": "diskusi_keagamaan_umum | kajian_akademik | kritik_politik_sosial | pemberitaan | dukungan_kekerasan | penolakan_kekerasan | kontra_narasi | tidak_dapat_dipastikan",
    "stance": "mendukung | menolak | netral | tidak_dapat_ditentukan",
    "sentiment": "positif | netral | negatif",
    "emotion": "anger | fear | sadness | anticipation | joy | trust | surprise | disgust | netral",
}


def cohen_kappa(a: list, b: list) -> float | None:
    pairs = [(x, y) for x, y in zip(a, b) if x and y]
    n = len(pairs)
    if not n:
        return None
    po = sum(x == y for x, y in pairs) / n
    ca, cb = Counter(x for x, _ in pairs), Counter(y for _, y in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return 1.0 if pe == 1 else round((po - pe) / (1 - pe), 4)


def prf(gold: list, pred: list) -> list[dict]:
    labels = sorted(set(gold) | set(pred))
    out = []
    for lab in labels:
        tp = sum(g == lab and p == lab for g, p in zip(gold, pred))
        fp = sum(g != lab and p == lab for g, p in zip(gold, pred))
        fn = sum(g == lab and p != lab for g, p in zip(gold, pred))
        pr = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * pr * rc / (pr + rc) if pr + rc else 0.0
        out.append({"label": lab, "support": sum(g == lab for g in gold), "precision": round(pr, 3), "recall": round(rc, 3), "f1": round(f1, 3)})
    return out


def stratified_sample(posts: list[dict], n: int, seed: int = 42) -> list[dict]:
    """Bertingkat per (platform, label konteks mesin) agar kategori langka — termasuk
    'dukungan_kekerasan' dan 'tidak_dapat_dipastikan' — ikut tervalidasi."""
    rng = random.Random(seed)
    strata = defaultdict(list)
    for p in posts:
        strata[(p["platform"], p.get("context"))].append(p)
    per = max(1, n // max(1, len(strata)))
    pick = []
    for k in sorted(strata, key=str):
        g = strata[k][:]
        rng.shuffle(g)
        pick.extend(g[:per])
    rest = [p for p in posts if p not in pick]
    rng.shuffle(rest)
    pick.extend(rest[: max(0, n - len(pick))])
    return pick[:n]


def write_sample(posts, n, out_dir, seed=42):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    smp = stratified_sample(posts, n, seed)
    base = [{"item_id": f"V{i:04d}", "post_id": p["post_id"], "platform": p["platform"], "text": " ".join(p["text"].split())} for i, p in enumerate(smp)]
    for coder, s in (("A", seed + 1), ("B", seed + 2)):
        rows = base[:]
        random.Random(s).shuffle(rows)
        with open(out / f"coder_{coder}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["item_id", "platform", "text", *TASKS, "catatan"])
            w.writeheader()
            for r in rows:
                w.writerow({"item_id": r["item_id"], "platform": r["platform"], "text": r["text"]})
    with open(out / "_kunci.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["item_id", "post_id", *[f"mesin_{t}" for t in TASKS]])
        w.writeheader()
        for r, p in zip(base, smp):
            w.writerow({"item_id": r["item_id"], "post_id": p["post_id"], **{f"mesin_{t}": p.get(t, "") for t in TASKS}})
    (out / "PANDUAN_KODING.txt").write_text("Pilihan label per kolom:\n" + "\n".join(f"- {t}: {v}" for t, v in CODEBOOK.items()) +
                                           "\nKoding mandiri; jangan berdiskusi sebelum kedua berkas selesai.\n", encoding="utf-8")
    return len(smp)


def score(file_a, file_b, key=None):
    rd = lambda f: {r["item_id"]: r for r in csv.DictReader(open(f, encoding="utf-8"))}
    A, B = rd(file_a), rd(file_b)
    ids = sorted(set(A) & set(B))
    K = rd(key) if key else {}
    report = {}
    for t in TASKS:
        a = [A[i].get(t, "").strip() for i in ids]
        b = [B[i].get(t, "").strip() for i in ids]
        rep = {"kappa": cohen_kappa(a, b), "n_coded": sum(1 for x, y in zip(a, b) if x and y)}
        if K:
            agreed = [(i, x) for i, x, y in zip(ids, a, b) if x and x == y]
            gold = [x for _, x in agreed]
            pred = [K[i].get(f"mesin_{t}", "") for i, _ in agreed]
            rep.update(n_gold=len(gold), accuracy=round(sum(g == p for g, p in zip(gold, pred)) / len(gold), 3) if gold else None, per_label=prf(gold, pred))
        report[t] = rep
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(prog="drno.validate")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s1 = sub.add_parser("sample"); s1.add_argument("--n", type=int, default=400); s1.add_argument("--out", default="validasi")
    s2 = sub.add_parser("score"); s2.add_argument("coder_a"); s2.add_argument("coder_b"); s2.add_argument("--key")
    a = ap.parse_args(argv)
    if a.cmd == "sample":
        from .analyze import annotate_all
        from .storage import get_store
        posts, _, _ = get_store().load()
        posts = [p for p in posts if not p.get("is_synthetic")]
        annotate_all(posts)
        print(f"{write_sample(posts, a.n, a.out)} item ditulis ke {a.out}/")
    else:
        import json
        print(json.dumps(score(a.coder_a, a.coder_b, a.key), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
