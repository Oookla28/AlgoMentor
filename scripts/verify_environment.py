import importlib.metadata
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
result={'python':sys.version,'packages':{},'original_pdfs':{p.name:p.stat().st_size for p in (ROOT/'knowledge/original').glob('*.pdf')},'live_ai':'NOT_VERIFIED: use per-user webpage test','live_execution':'See tests/evaluation/execution_probe.json'}
for name in ['Django','langchain','langchain-chroma','chromadb','crewai','sentence-transformers','requests','cryptography','networkx']:
    result['packages'][name]=importlib.metadata.version(name)
print(json.dumps(result,ensure_ascii=False,indent=2))
