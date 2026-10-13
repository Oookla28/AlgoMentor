"""初始化本地开发；使用当前 Python 环境，无 npm、无测试学生假数据。"""
import os
from pathlib import Path
import secrets
import subprocess
import sys
from cryptography.fernet import Fernet
ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT)
# Git does not retain empty data directories; a fresh clone needs SQLite's parent.
(ROOT/'data').mkdir(parents=True,exist_ok=True,mode=0o700)
env=ROOT/'.env'
if not env.exists():
    example=(ROOT/'.env.example').read_text()
    example=example.replace('DJANGO_SECRET_KEY=\n','DJANGO_SECRET_KEY='+secrets.token_urlsafe(48)+'\n').replace('APP_ENCRYPTION_KEY=\n','APP_ENCRYPTION_KEY='+Fernet.generate_key().decode()+'\n')
    env.write_text(example);env.chmod(0o600)
for args in [('migrate',),('seed_knowledge',),('seed_problems',),('prepare_embedding_model',),('ingest_knowledge',),('seed_knowledge',)]:
    subprocess.run([sys.executable,'manage.py',*args],check=True)
print('初始化完成。请通过注册页创建自己的账户，并在设置页配置个人 Key。')
