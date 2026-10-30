"""Bangun file dataset dashboard dari pipeline SINTETIS (untuk data nyata: python -m drno.analyze)."""
import sys

from drno.analyze import export_dashboard
from drno.synthetic import generate

d = generate(7)
print(export_dashboard(d["posts"], d["interactions"], sys.argv[1], "synthetic"))
