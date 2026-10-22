import json
import re
import sys
import zipfile
from xml.etree import ElementTree as ET

seed = json.load(open('public/knowledge-seed.json', encoding='utf-8'))
ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

def compact(value):
    return re.sub(r'\s+', '', value).casefold()

for path, kind in zip(sys.argv[1:], ('prompts', 'chapters')):
    root = ET.fromstring(zipfile.ZipFile(path).read('word/document.xml'))
    paragraphs = [''.join(node.text or '' for node in p.findall('.//w:t', ns)) for p in root.findall('.//w:p', ns)]
    source = [compact(p) for p in paragraphs if compact(p)]
    target = compact(''.join(item['title'] + item['text'] for item in seed[kind]))
    missing = [(i, paragraphs[i][:90]) for i, p in enumerate(paragraphs) if len(compact(p)) > 8 and compact(p) not in target]
    print(kind, 'source_paragraphs', len(source), 'records', len(seed[kind]), 'missing_paragraphs', len(missing))
    print('first_missing', missing[:8])
    if len(missing) > 5:
        raise SystemExit(1)
