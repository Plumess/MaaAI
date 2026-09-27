"""Explicit entry points; every expensive operation is an opt-in subcommand."""
import argparse,os,subprocess,sys
from pathlib import Path

COMMANDS={'setup':'setup_runtime.py','export-check':'export_candidate.py','fetch':'source_assets.py','corpus':'source_corpus.py','generate':'recipe_dataset.py','scene':'scene_dataset.py','prepare-model':'prepare_model.py','plan':'prepare_training_plan.py','train':'run_training_plan.py','export':'export_model.py','doctor':'doctor.py','capture-unpack':'capture_archive.py','capture-import':'capture_intake.py','calibrate':'calibrate.py','audit-pool':'audit_pool.py','warm-symbols':'warm_korean_symbols.py','evaluate':'evaluate.py','package':'package_candidate.py','freeze-evaluation':'freeze_evaluation.py','inspect-rules':'inspect_rules.py','review':'capture_annotations.py'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runtime',type=Path,required=True);p.add_argument('command',choices=COMMANDS);p.add_argument('arguments',nargs=argparse.REMAINDER);a=p.parse_args()
    runtime=a.runtime.expanduser().resolve()
    if not runtime.is_dir():p.error('runtime must be an existing external directory')
    env=dict(os.environ,MAA_OCR_RUNTIME=str(runtime),PYTHONPYCACHEPREFIX=str(runtime/'cache/pipeline-pycache'),MPLCONFIGDIR=str(runtime/'cache/matplotlib'))
    args=a.arguments[1:] if a.arguments[:1]==['--'] else a.arguments
    result=subprocess.run([sys.executable,str(Path(__file__).parent/'scripts'/COMMANDS[a.command]),*args],env=env)
    raise SystemExit(result.returncode)
if __name__=='__main__':main()
