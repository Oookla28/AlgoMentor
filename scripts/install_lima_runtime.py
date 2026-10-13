"""Install an official, pinned user-local Lima release; no system package manager."""
import hashlib
from pathlib import Path
import tarfile
import requests

VERSION='2.2.1'
CHECKSUM_FILE_HASH='4805ceeb791229ecaddcde32bf04b14742f4d036b343ad5d8c478ba5d220fff2'
PREFIX=Path.home()/'.local/share/algomentor-execution/lima'
CACHE=Path.home()/'.cache/algomentor-execution'
BASE=f'https://github.com/lima-vm/lima/releases/download/v{VERSION}'


def download(name):
    path=CACHE/name
    if path.exists(): return path
    temporary=path.with_suffix(path.suffix+'.part')
    print(f'Downloading official {name}',flush=True)
    with requests.get(BASE+'/'+name,stream=True,timeout=(15,60)) as response:
        response.raise_for_status()
        with temporary.open('wb') as stream:
            count=0;reported=0
            for block in response.iter_content(1024*1024):
                stream.write(block);count+=len(block)
                if count-reported>=8*1024*1024:
                    print(f'{name}: {count//(1024*1024)} MiB',flush=True);reported=count
    temporary.replace(path)
    return path


def main():
    CACHE.mkdir(parents=True,exist_ok=True)
    PREFIX.mkdir(parents=True,exist_ok=True)
    checksums=download('SHA256SUMS')
    if hashlib.sha256(checksums.read_bytes()).hexdigest()!=CHECKSUM_FILE_HASH:
        raise RuntimeError('Official release checksum file does not match its published digest.')
    values={line.split()[-1].lstrip('*'):line.split()[0] for line in checksums.read_text().splitlines() if line.strip()}
    for name in [f'lima-{VERSION}-Darwin-arm64.tar.gz',f'lima-additional-guestagents-{VERSION}-Darwin-arm64.tar.gz']:
        archive=download(name)
        if hashlib.sha256(archive.read_bytes()).hexdigest()!=values[name]:
            raise RuntimeError('Archive checksum verification failed: '+name)
        with tarfile.open(archive) as tar:
            tar.extractall(PREFIX,filter='data')
        print('Verified and installed '+name,flush=True)
    print('Lima installed at '+str(PREFIX),flush=True)

if __name__=='__main__': main()
