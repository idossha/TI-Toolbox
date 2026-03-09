"""Rewrite coverage.xml so Codecov can map files correctly.

pytest-cov inside Docker writes the Docker mount path as <source>.
Codecov needs an empty <source> with repo-relative filenames.
"""

import sys
import xml.etree.ElementTree as ET

path = "/tmp/coverage/coverage.xml"
tree = ET.parse(path)
root = tree.getroot()

for source_el in root.iter("source"):
    source_el.text = ""

# Validate: no absolute paths should remain in filenames
errors = []
for cls in root.iter("class"):
    fn = cls.get("filename", "")
    if fn.startswith("/"):
        errors.append(fn)

if errors:
    print(f"ERROR: {len(errors)} file(s) have absolute paths:", file=sys.stderr)
    for e in errors[:5]:
        print(f"  {e}", file=sys.stderr)
    sys.exit(1)

tree.write(path, xml_declaration=True, encoding="UTF-8")
print(f"Coverage XML ready ({sum(1 for _ in root.iter('class'))} files)")
