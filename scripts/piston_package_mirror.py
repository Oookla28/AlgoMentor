"""Serve only a checksum-verified official Python package on host loopback.

This repository cache handles macOS proxy DNS limits. Student code is still
executed exclusively by official Piston/Isolate in the mount-free Linux VM.
"""
from pathlib import Path
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import requests

CACHE=Path.home()/'.cache/algomentor-execution/piston-repo'
VERSION='3.12.0'
NAME=f'python-{VERSION}.pkg.tar.gz'
SHA='abc40b3231fc7e713799da2cd79844545c72b3904a4d2ffcc28c4d133ed21d0b'
URL='https://github.com/engineer-man/piston/releases/download/pkgs/'+NAME
INDEX=f'python,{VERSION},{SHA},http://192.168.5.2:2099/{NAME}\n'.encode()


def prepare():
    CACHE.mkdir(parents=True,exist_ok=True)
    archive=CACHE/NAME
    if not archive.exists():
        temporary=archive.with_suffix(archive.suffix+'.part')
        print('Downloading official Python '+VERSION+' package',flush=True)
        with requests.get(URL,stream=True,timeout=(15,60)) as response:
            response.raise_for_status()
            with temporary.open('wb') as stream:
                size=0;reported=0
                for block in response.iter_content(1024*1024):
                    stream.write(block);size+=len(block)
                    if size-reported>=16*1024*1024:
                        print(f'Python archive: {size//(1024*1024)} MiB',flush=True);reported=size
        temporary.replace(archive)
    digest=hashlib.sha256()
    with archive.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    if digest.hexdigest()!=SHA: raise RuntimeError('Official Python package SHA-256 mismatch')
    print('Official Python archive checksum verified',flush=True)
    return archive


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        route=self.path.split('?',1)[0]
        if route=='/index':
            self.send_response(200);self.send_header('Content-Length',str(len(INDEX)));self.end_headers();self.wfile.write(INDEX)
        elif route=='/'+NAME:
            archive=CACHE/NAME
            self.send_response(200);self.send_header('Content-Length',str(archive.stat().st_size));self.end_headers()
            with archive.open('rb') as stream:
                for block in iter(lambda:stream.read(1024*1024),b''):self.wfile.write(block)
        else: self.send_error(404)
    def log_message(self,*args): pass


if __name__=='__main__':
    prepare()
    print('Official package cache listening on 127.0.0.1:2099',flush=True)
    ThreadingHTTPServer(('127.0.0.1',2099),Handler).serve_forever()
