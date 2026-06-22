"""Append UTF-8 text to docs-log/HSA_Complete_History.md from a payload file."""
import sys, pathlib
target = pathlib.Path(__file__).resolve().parent.parent / "docs-log" / "HSA_Complete_History.md"
payload = pathlib.Path(sys.argv[1])
text = payload.read_text(encoding="utf-8")
mode = "w" if (len(sys.argv) > 2 and sys.argv[2] == "--reset") else "a"
with open(target, mode, encoding="utf-8") as f:
    f.write(text)
print(f"OK wrote {len(text)} chars to {target} (mode={mode})")
