"""Assemble the viewer page from template.html + one or more strategy data files.
usage (from backend/):  venv/bin/python analysis/strategy_viewer/build_page.py OUT.html DATA1.json [DATA2.json ...]
Publish OUT.html as an Artifact. The page must stay under 16 MB (about 6-7 MB per strategy with 21 entry strikes)."""
import json, os, sys
here = os.path.dirname(__file__)
data = [json.load(open(p)) for p in sys.argv[2:]]
html = open(os.path.join(here, "template.html")).read().replace("__DATA__", json.dumps(data, separators=(",", ":")))
open(sys.argv[1], "w").write(html)
print(f"{sys.argv[1]}: {len(html) / 1e6:.1f} MB, strategies: {[d['name'] for d in data]}")
