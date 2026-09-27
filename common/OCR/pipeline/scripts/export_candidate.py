"""Explicit export, source-attribute repair, and released-runtime equivalence."""
import argparse,json
from pathlib import Path
from multilingual_verify import export
from file_utils import sha
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--checkpoint',type=Path,required=True);p.add_argument('--config',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--kind',choices=['word','char'],required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    rows=[json.loads(l) for l in a.manifest.read_text().splitlines() if l]
    if not rows:raise ValueError('equivalence needs real inputs')
    for r in rows:
        r['image']=str((a.manifest.parent/r['image']).resolve())
        if sha(Path(r['image']))!=r['sha256']:raise ValueError('input changed')
    a.output.mkdir(parents=True,exist_ok=False)
    # Randomness only separates artifact names, not model/data contents.
    import uuid
    variant='export-'+uuid.uuid4().hex[:12];pack,gate=export(a.checkpoint.resolve(),a.config.resolve(),variant,a.output.resolve(),rows,a.kind)
    (a.output/'result.json').write_text(json.dumps({'pack':str(pack),'gate':gate,'release_approved':False},indent=2)+'\n')
    raise SystemExit(0 if gate['passed'] else 1)
