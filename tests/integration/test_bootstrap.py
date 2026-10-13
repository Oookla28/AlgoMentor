"""Fresh clone initialization must create SQLite's directory and preserve secrets."""
from pathlib import Path
import runpy
from unittest.mock import patch


def test_fresh_bootstrap_creates_private_data_directory_and_prepares_model(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    entry = scripts / 'bootstrap.py'
    entry.write_text((root / 'scripts/bootstrap.py').read_text())
    (tmp_path / '.env.example').write_text((root / '.env.example').read_text())
    monkeypatch.chdir(root)
    with patch('subprocess.run') as run:
        runpy.run_path(str(entry), run_name='__main__')
    assert (tmp_path / 'data').is_dir()
    assert (tmp_path / 'data').stat().st_mode & 0o777 == 0o700
    assert (tmp_path / '.env').stat().st_mode & 0o777 == 0o600
    commands = [call.args[0][2] for call in run.call_args_list]
    assert commands.index('prepare_embedding_model') < commands.index('ingest_knowledge')


def test_existing_bootstrap_keeps_environment_and_database_contents(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    (tmp_path / 'scripts').mkdir()
    entry = tmp_path / 'scripts/bootstrap.py'
    entry.write_text((root / 'scripts/bootstrap.py').read_text())
    environment = tmp_path / '.env'
    environment.write_text('existing local configuration\n')
    (tmp_path / 'data').mkdir()
    database = tmp_path / 'data/db.sqlite3'
    database.write_bytes(b'existing database fixture')
    monkeypatch.chdir(root)
    with patch('subprocess.run'):
        runpy.run_path(str(entry), run_name='__main__')
    assert environment.read_text() == 'existing local configuration\n'
    assert database.read_bytes() == b'existing database fixture'
