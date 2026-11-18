from pathlib import Path
import json, hashlib
root=Path(__file__).resolve().parent
media=root/'seed_media'; media.mkdir(exist_ok=True)
for name, info in json.loads((root/'media_manifest.json').read_text()).items():
    target=media/name; temp=target.with_suffix('.tmp'); digest=hashlib.sha256()
    with temp.open('wb') as out:
        for part in info['parts']:
            with (root/'media_parts'/part).open('rb') as f:
                while chunk:=f.read(1024*1024):
                    out.write(chunk); digest.update(chunk)
    if temp.stat().st_size != info['bytes'] or digest.hexdigest() != info['sha256']:
        raise RuntimeError(f'Corrupt video: {name}')
    temp.replace(target)
    print(f'Validated {name}', flush=True)
