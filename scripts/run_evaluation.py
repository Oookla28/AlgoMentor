import os,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
os.chdir(root)
subprocess.run([sys.executable,'manage.py','evaluate_system',*sys.argv[1:]],check=True)
