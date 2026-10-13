"""Install the optional offline translator and official Argos language models."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import venv
import zipfile

ROOT=Path(__file__).resolve().parent.parent


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--languages',nargs='+',default=['en','fr','de','es'])
    args=parser.parse_args()
    runtime=ROOT/'.venv-translation'
    venv.EnvBuilder(with_pip=True).create(runtime)
    subprocess.run([str(runtime/'bin/python'),'-m','pip','install','-r',str(ROOT/'requirements-translation.txt')],check=True)
    with urllib.request.urlopen('https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json',timeout=30) as response:
        index=json.load(response)
    pairs=[('en','zh')]+[(language,'en') for language in args.languages if language!='en']
    for source,target in pairs:
        destination=ROOT/'data/translation-models'/f'{source}_{target}'
        if (destination/'model/model.bin').exists():continue
        entry=next(p for p in index if p['from_code']==source and p['to_code']==target)
        url=next(u for u in entry['links'] if u.startswith('https://argos-net.com/'))
        print(f'Downloading {source} → {target}',flush=True)
        with tempfile.TemporaryDirectory() as temporary:
            archive=Path(temporary)/'model.zip'
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=120) as response,archive.open('wb') as output:shutil.copyfileobj(response,output)
            with zipfile.ZipFile(archive) as package:
                for member in package.infolist():
                    path=(Path(temporary)/member.filename).resolve()
                    if not path.is_relative_to(Path(temporary).resolve()):raise ValueError('Invalid model archive path')
                package.extractall(temporary)
            folder=next(p.parent for p in Path(temporary).rglob('metadata.json') if (p.parent/'model/model.bin').exists())
            metadata=json.loads((folder/'metadata.json').read_text())
            if metadata['from_code']!=source or metadata['to_code']!=target:raise ValueError('Invalid language model')
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.move(str(folder),str(destination))
    print('Local Chinese translation is ready. Restart DAOLOOK.',flush=True)


if __name__=='__main__':main()
