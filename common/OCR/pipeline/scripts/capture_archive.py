"""Verify and unpack a local capture ZIP into a new directory; never execute its contents."""
import argparse
import hashlib
import json
from pathlib import Path,PurePosixPath
import shutil
import stat
import tempfile
import zipfile
from capture_intake import inspect_package
from file_utils import sha


def unpack(archive,output):
    if output.exists():raise FileExistsError('choose a new archive version')
    output.parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix='.capture-archive-',dir=output.parent))
    try:
        with zipfile.ZipFile(archive) as z:
            infos=z.infolist();seen=set();roots=set()
            if len(infos)>10000 or sum(i.file_size for i in infos)>2*1024**3:raise ValueError('capture package exceeds intake budget')
            for info in infos:
                name=info.filename;path=PurePosixPath(name)
                if '\\' in name or path.is_absolute() or '..' in path.parts or not path.parts:raise ValueError('unsafe archive path')
                if name.casefold() in seen:raise ValueError('duplicate archive member')
                seen.add(name.casefold());roots.add(path.parts[0])
                if stat.S_ISLNK(info.external_attr>>16):raise ValueError('archive symlink is not supported')
                dest=staging.joinpath(*path.parts)
                if info.is_dir():dest.mkdir(parents=True,exist_ok=True);continue
                dest.parent.mkdir(parents=True,exist_ok=True)
                with z.open(info) as source,dest.open('xb') as target:shutil.copyfileobj(source,target)
            if len(roots)!=1:raise ValueError('expected a single capture package directory')
        package=staging/next(iter(roots));records=inspect_package(package)
        declared=json.loads((package/'image-checksums.json').read_text())
        checks={r['file']:r for r in declared}
        if len(checks)!=len(declared) or set(checks)!={r['source_file'] for r in records}:raise ValueError('checksum/image catalogue mismatch')
        if {str(p.relative_to(package)) for p in (package/'images').rglob('*') if p.is_file()}!=set(checks):raise ValueError('unindexed image files')
        for r in records:
            c=checks[r['source_file']];p=package/r['source_file']
            if any(c[k]!=r[k] for k in ['sha256','width','height']) or c['bytes']!=p.stat().st_size:raise ValueError('image checksum or dimensions mismatch')
        report={'archive':str(archive.resolve()),'archive_sha256':sha(archive),'members':len(infos),'images':len(records),
                'image_checksums_verified':True,'csv_dimensions_verified':True,'zip_crc_verified':True,
                'source_claims_independently_reviewed':False,'package_directory':next(iter(roots)),
                'files':{str(p.relative_to(staging)):sha(p) for p in staging.rglob('*') if p.is_file()}}
        (staging/'archive-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        staging.rename(output);return report
    finally:
        if staging.exists():shutil.rmtree(staging)


def main():
    p=argparse.ArgumentParser();p.add_argument('--archive',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    r=unpack(a.archive,a.output);print(json.dumps({k:v for k,v in r.items() if k!='files'},ensure_ascii=False))
if __name__=='__main__':main()
