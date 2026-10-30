"""Uji validitas klasifier baseline terhadap label sintetis.

PERHATIAN: akurasi pada data sintetis bersifat SIRKULER (templat memuat penanda yang
dicari klasifier). Angka ini hanya menguji bahwa pipeline berjalan benar, BUKAN validitas
pada data nyata. Validitas nyata memerlukan gold standard anotasi manual dua pengode.
"""
from collections import Counter

from drno import nlp
from drno.synthetic import ARCHETYPES, generate

d = generate(7)
clf = nlp.BaselineClassifier()
cm, tot = Counter(), Counter()
for p in d["posts"]:
    truth = ARCHETYPES[p["archetype"]][2]
    pred = clf.context(p["text"]).label
    cm[(truth, pred)] += 1
    tot[truth] += 1
print(f"{'kategori':28s} {'n':>5s} {'sesuai':>7s} {'tak pasti':>9s}")
for t in tot:
    print(f"{t:28s} {tot[t]:5d} {cm[(t, t)]:7d} {cm[(t, 'tidak_dapat_dipastikan')]:9d}")
