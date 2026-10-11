"""Print what the code-layer defense keeps and removes for each document (debug helper)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from defenses import clean_document, labeled_fields
for f in sys.argv[1:]:
    d = clean_document(Path(f))
    print("=" * 20, f); print(d.text); print("-- flags:"); [print("  ", x) for x in d.flags]
    print("-- labeled:", labeled_fields(d.text))
