"""Pipeline NLP (Bagian 5 dan Extended Module B).

Arsitektur dua lapis:
1. BaselineClassifier — berbasis aturan, transparan, sengaja konservatif. Dipakai untuk
   prototipe dan sebagai pembanding. Bila sinyal lemah, hasilnya 'tidak_dapat_dipastikan'.
2. TransformerClassifier — kerangka untuk model IndoBERT/XLM-R yang di-fine-tune pada
   gold standard anotasi manual. TIDAK boleh diaktifkan sebelum reliabilitas antarpengode
   (Cohen's kappa) dan performa pada data uji dilaporkan.

Aturan: kemunculan istilah (jihad, kaffah, khilafah, dst.) TIDAK PERNAH cukup untuk label
'dukungan_kekerasan'. Label itu memerlukan penanda eksplisit ajakan/pembenaran kekerasan
dan selalu masuk antrean validasi manual.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .keywords import normalize

CONTEXT_LABELS = [
    "diskusi_keagamaan_umum", "kajian_akademik", "kritik_politik_sosial", "pemberitaan",
    "dukungan_kekerasan", "penolakan_kekerasan", "kontra_narasi", "tidak_dapat_dipastikan",
]
STANCE_FROM_CONTEXT = {
    "dukungan_kekerasan": "mendukung", "penolakan_kekerasan": "menolak", "kontra_narasi": "menolak",
    "pemberitaan": "netral", "kajian_akademik": "netral", "diskusi_keagamaan_umum": "netral",
    "kritik_politik_sosial": "netral", "tidak_dapat_dipastikan": "tidak_dapat_ditentukan",
}
UNCERTAIN_THRESHOLD = 0.6

_URL = re.compile(r"https?://\S+")
_MENTION = re.compile(r"@\w+")
_ID_STOP = {"yang", "dan", "di", "ini", "itu", "dengan", "untuk", "tidak", "dari", "dalam", "akan", "pada", "juga", "kita"}
_EN_STOP = {"the", "and", "is", "of", "to", "in", "that", "for", "with", "this"}


def clean(text: str) -> str:
    t = _URL.sub(" ", text)
    t = _MENTION.sub(" ", t)
    t = re.sub(r"[^\w\s#'-]", " ", t)
    return normalize(t)


def detect_language(text: str) -> str:
    w = set(clean(text).split())
    i, e = len(w & _ID_STOP), len(w & _EN_STOP)
    if i == e == 0:
        return "und"
    return "id" if i >= e else "en"


# Penanda kontekstual (dapat diperluas & diaudit). Bobot sederhana, bukan model statistik.
CUES = {
    "pemberitaan": ["menurut polisi", "dilaporkan", "kepolisian", "densus", "bnpt", "sidang", "ditangkap", "jaksa", "berita"],
    "kajian_akademik": ["penelitian", "jurnal", "seminar", "kajian akademik", "teori", "dosen", "mahasiswa", "studi"],
    "kontra_narasi": ["kontra-narasi", "kontra narasi", "moderasi beragama", "islam rahmatan", "meluruskan makna", "toleransi"],
    "penolakan_kekerasan": ["menolak kekerasan", "mengecam", "kekerasan bukan jalan", "tidak dibenarkan", "kutuk"],
    "kritik_politik_sosial": ["pemerintah", "kebijakan", "dpr", "korupsi", "demokrasi kita", "ketidakadilan"],
    "diskusi_keagamaan_umum": ["kajian", "ustaz", "pengajian", "hijrah", "sholat", "tauhid", "dakwah"],
    # Penanda eksplisit; sengaja sempit
    "dukungan_kekerasan": ["serang mereka", "halal darahnya", "angkat senjata", "bunuh mereka"],
}


@dataclass
class Prediction:
    task: str
    label: str
    confidence: float
    model_name: str = "baseline-rules"
    model_version: str = "0.1"

    @property
    def is_uncertain(self) -> bool:
        return self.confidence < UNCERTAIN_THRESHOLD or self.label in ("tidak_dapat_dipastikan", "tidak_dapat_ditentukan")


class BaselineClassifier:
    def context(self, text: str) -> Prediction:
        t = clean(text)
        scores = {lab: sum(1 for c in cues if c in t) for lab, cues in CUES.items()}
        best = max(scores, key=scores.get)
        total = sum(scores.values())
        if scores[best] == 0:
            return Prediction("context", "tidak_dapat_dipastikan", 0.0)
        conf = round(min(0.9, 0.35 + 0.15 * scores[best]) * (scores[best] / total), 2)
        # Label paling sensitif: confidence dibatasi agar selalu masuk validasi manual
        if best == "dukungan_kekerasan":
            conf = min(conf, 0.55)
        if conf < 0.3:
            return Prediction("context", "tidak_dapat_dipastikan", conf)
        return Prediction("context", best, conf)

    def stance(self, ctx: Prediction) -> Prediction:
        return Prediction("stance", STANCE_FROM_CONTEXT[ctx.label], ctx.confidence)

    POS = {"damai", "baik", "setuju", "dukung", "toleransi", "satu", "syukur", "apresiasi", "indah", "sejuk", "mantap",
           "penting", "rahmat", "teguh", "istiqamah", "lurus", "kenal"}
    NEG = {"benci", "marah", "kecam", "takut", "buruk", "zalim", "ancam", "tolak", "kutuk", "represif", "korupsi",
           "adil", "serang", "bunuh", "uji", "picu", "lemah", "henti"}
    _PREF = ("meng", "meny", "mem", "men", "me", "di", "ber", "ter", "pen", "pem", "pe", "ke")
    _SUF = ("kannya", "nya", "kan", "an", "i")

    @classmethod
    def _roots(cls, w):
        """Kandidat kata dasar, termasuk peluluhan meN-/peN- (menolak->tolak, mengecam->kecam)."""
        out = {w}
        for s in cls._SUF:
            if w.endswith(s) and len(w) - len(s) >= 4:
                w = w[: -len(s)]
                out.add(w)
                break
        for p in cls._PREF:
            if w.startswith(p) and len(w) - len(p) >= 3:
                r = w[len(p):]
                out.add(r)
                if r[:1] in "aeiou":
                    out.update({"t" + r, "k" + r, "p" + r, "s" + r})
                break
        return out

    def sentiment(self, text: str) -> Prediction:
        """Leksikon kecil + stemming kasar. Baseline transparan; ganti dengan model tervalidasi untuk data nyata."""
        words = clean(text).split()
        roots = set().union(*(self._roots(x) for x in words)) if words else set()
        pos = len(roots & self.POS)
        neg = len(roots & self.NEG) + (1 if "ketidakadilan" in words else 0)
        if "adil" in roots and "ketidakadilan" not in words:
            neg -= 1  # 'adil' saja bukan negatif
        if pos == neg:
            return Prediction("sentiment", "netral", 0.5)
        lab = "positif" if pos > neg else "negatif"
        return Prediction("sentiment", lab, round(min(0.85, 0.5 + 0.12 * abs(pos - neg)), 2))


EMOTIONS = ["anger", "fear", "sadness", "anticipation", "joy", "trust", "surprise", "disgust"]  # Plutchik
EMO_LEX = {
    "anger": {"marah", "benci", "kesal", "geram", "murka", "kecam", "kutuk", "korupsi", "zalim", "serang"},
    "fear": {"takut", "ancam", "cemas", "khawatir", "waspada", "bahaya", "teror", "represif", "tangkap", "awas"},
    "sadness": {"sedih", "duka", "prihatin", "hilang", "korban", "pilu", "derita"},
    "anticipation": {"harap", "tunggu", "semoga", "rencana", "yuk", "sidang", "penting", "mulai"},
    "joy": {"senang", "bahagia", "syukur", "gembira", "indah", "mantap", "sejuk"},
    "trust": {"percaya", "yakin", "dukung", "setuju", "aman", "damai", "toleransi", "rahmat", "teguh", "lurus"},
    "surprise": {"kaget", "heran", "terkejut", "ternyata", "viral"},
    "disgust": {"jijik", "muak", "busuk", "tolak", "hina"},
}


def emotion(text: str) -> Prediction:
    """Emosi dominan (8 emosi Plutchik) via leksikon kecil + stemming kasar. BASELINE, wajib divalidasi.
    Tanpa penanda -> 'netral'."""
    words = clean(text).split()
    roots = set().union(*(BaselineClassifier._roots(w) for w in words)) if words else set()
    scores = {e: len(roots & lex) for e, lex in EMO_LEX.items()}
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return Prediction("emotion", "netral", 0.5)
    tot = sum(scores.values())
    return Prediction("emotion", best, round(0.4 + 0.5 * scores[best] / tot, 2))


class TransformerClassifier:  # pragma: no cover - memerlukan model terlatih
    """Kerangka untuk model fine-tuned (mis. indobenchmark/indobert-base-p1).

    Contoh penggunaan setelah model dilatih dan divalidasi:
        from transformers import pipeline
        self.pipe = pipeline("text-classification", model=path, top_k=None)
    """

    def __init__(self, model_path: str, validated: bool = False):
        if not validated:
            raise RuntimeError("Model belum divalidasi pada gold standard; gunakan BaselineClassifier.")
        from transformers import pipeline
        self.pipe = pipeline("text-classification", model=model_path, top_k=None)
        self.name = model_path


def annotate(post: dict, clf: BaselineClassifier | None = None) -> list[Prediction]:
    clf = clf or BaselineClassifier()
    ctx = clf.context(post["text"])
    return [Prediction("language", detect_language(post["text"]), 0.7), ctx, clf.stance(ctx), clf.sentiment(post["text"])]


def manual_review_queue(annotations: dict[str, list[Prediction]]) -> list[str]:
    """Post yang wajib divalidasi manual: semua hasil tidak pasti + semua label 'dukungan_kekerasan'."""
    q = []
    for pid, preds in annotations.items():
        ctx = next(p for p in preds if p.task == "context")
        if ctx.is_uncertain or ctx.label == "dukungan_kekerasan":
            q.append(pid)
    return q


def fit_topics(texts: list[str], min_topic_size: int = 15):  # pragma: no cover - dependensi berat
    """Topic modeling BERTopic dengan embedding multilingual. Laporkan seed & parameter."""
    from bertopic import BERTopic
    from sentence_transformers import SentenceTransformer
    emb = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    model = BERTopic(embedding_model=emb, language="multilingual", min_topic_size=min_topic_size,
                     calculate_probabilities=False, verbose=False)
    topics, _ = model.fit_transform(texts)
    return model, topics


def semantic_keyword_candidates(seeds: list[str], vocabulary: list[str], top_k: int = 10):  # pragma: no cover
    """Semantic Keyword Discovery: kandidat istilah serupa. Hasil = USULAN, bukan daftar crawling."""
    from sentence_transformers import SentenceTransformer, util
    m = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    se, ve = m.encode(seeds, convert_to_tensor=True), m.encode(vocabulary, convert_to_tensor=True)
    sims = util.cos_sim(se, ve)
    out = []
    for i, s in enumerate(seeds):
        for j in sims[i].argsort(descending=True)[:top_k]:
            out.append({"seed": s, "term": vocabulary[int(j)], "similarity": float(sims[i][j])})
    return out
