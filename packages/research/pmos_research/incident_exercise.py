from __future__ import annotations

import hashlib,json,os,shutil,subprocess,tempfile
from datetime import datetime,timezone
from pathlib import Path
from sqlalchemy import select

from .audit_ledger import append_ledger_event
from .backup import encrypted_storage_active
from .db import IncidentResponseExerciseRun

class IncidentExerciseError(RuntimeError):pass
def _canonical(value):return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)

def _run(command:list[str],cwd:Path,timeout:int=30):return subprocess.run(command,cwd=cwd,capture_output=True,text=True,timeout=timeout,check=False)
def _init_repo(path:Path):
    path.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(path,0o700)
    for command in (["git","init","-q"],["git","config","user.email","synthetic-drill@example.invalid"],["git","config","user.name","PMOS Synthetic Drill"]):
        result=_run(command,path)
        if result.returncode:raise IncidentExerciseError("synthetic exercise repository initialization failed")

def run_public_leak_exercise(session,repo_root:Path,exercise_root:Path,actor:str="incident-exercise-worker")->tuple[IncidentResponseExerciseRun,dict]:
    actor=actor.strip();repo_root=repo_root.resolve();exercise_root=exercise_root.expanduser()
    if not actor:raise IncidentExerciseError("exercise actor is required")
    if not encrypted_storage_active():raise IncidentExerciseError("encrypted storage could not be verified")
    if exercise_root.exists() and exercise_root.is_symlink():raise IncidentExerciseError("exercise root cannot be a symlink")
    exercise_root=exercise_root.resolve();exercise_root.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(exercise_root,0o700)
    if repo_root==exercise_root or repo_root in exercise_root.parents or exercise_root in repo_root.parents:raise IncidentExerciseError("exercise root must be separate from the public repository")
    compromised=Path(tempfile.mkdtemp(prefix="pmos-leak-exercise-",dir=exercise_root));recovered=None
    try:
        _init_repo(compromised);(compromised/"README.md").write_text("Synthetic incident exercise repository.\n",encoding="utf-8");_run(["git","add","README.md"],compromised);baseline=_run(["git","commit","-q","-m","safe baseline"],compromised)
        if baseline.returncode:raise IncidentExerciseError("synthetic baseline commit failed")
        canary_email="synthetic.contact"+"@example.invalid";canary_secret="api_"+"key="+"Q7mN2vK9xP4rT8wZ";(compromised/"private-seed.csv").write_text("name,email\nSynthetic Person,"+canary_email+"\n",encoding="utf-8");(compromised/"credentials.txt").write_text(canary_secret+"\n",encoding="utf-8");(compromised/"synthetic.db").write_bytes(b"SQLite format 3\x00synthetic exercise only")
        worktree=_run([os.fspath(repo_root/".venv/bin/python"),os.fspath(repo_root/"scripts/public_release_check.py"),"--root",os.fspath(compromised)],repo_root,60);worktree_output=worktree.stdout+worktree.stderr
        detections={"blocked_artifact":"blocked artifact:" in worktree_output,"private_path":"private/suspicious path:" in worktree_output,"email_csv":"email-bearing CSV:" in worktree_output,"possible_secret":"possible secret:" in worktree_output}
        if worktree.returncode==0 or not all(detections.values()):raise IncidentExerciseError("release gate did not detect every synthetic worktree canary")
        _run(["git","add","private-seed.csv","credentials.txt","synthetic.db"],compromised);leak_commit=_run(["git","commit","-q","-m","synthetic leak canary"],compromised)
        if leak_commit.returncode:raise IncidentExerciseError("synthetic leak commit failed")
        historical=_run([os.fspath(repo_root/".venv/bin/python"),os.fspath(repo_root/"scripts/public_release_check.py"),"--root",os.fspath(compromised)],repo_root,60);history_detected=historical.returncode!=0 and "historical blocked artifact:" in (historical.stdout+historical.stderr) and "historical email-bearing CSV:" in (historical.stdout+historical.stderr)
        if not history_detected:raise IncidentExerciseError("release gate did not detect synthetic Git-history leakage")
        shutil.rmtree(compromised);containment=not compromised.exists()
        recovered=Path(tempfile.mkdtemp(prefix="pmos-recovered-exercise-",dir=exercise_root));_init_repo(recovered);(recovered/"README.md").write_text("Synthetic clean recovery repository.\n",encoding="utf-8");_run(["git","add","README.md"],recovered);_run(["git","commit","-q","-m","clean recovery"],recovered);clean=_run([os.fspath(repo_root/".venv/bin/python"),os.fspath(repo_root/"scripts/public_release_check.py"),"--root",os.fspath(recovered)],repo_root,60);recovery=clean.returncode==0
        shutil.rmtree(recovered);recovered=None
    finally:
        if compromised.exists():shutil.rmtree(compromised)
        if recovered and recovered.exists():shutil.rmtree(recovered)
    report={"classification":"PMOS PRIVATE AGGREGATE INCIDENT EXERCISE — SYNTHETIC CANARIES ONLY","completed_at":datetime.now(timezone.utc).isoformat(),"status":"PASS" if containment and recovery else "FAIL","scenario":"PUBLIC_RELEASE_LEAK_RESPONSE","method":"synthetic_canary_release_gate_exercise_v1","detections":detections,"history_leak_detected":history_detected,"detection_count":sum(detections.values())+int(history_detected),"containment_verified":containment,"recovery_verified":recovery,"encrypted_storage_verified":True,"limitations":["Exercises the local public-release gate and containment procedure, not external alert delivery or personnel response times.","Synthetic canaries contain no private intelligence or operational credentials."]}
    digest=hashlib.sha256(_canonical(report).encode()).hexdigest();existing=session.scalar(select(IncidentResponseExerciseRun).where(IncidentResponseExerciseRun.report_hash==digest))
    if existing:return existing,report
    run=IncidentResponseExerciseRun(status=report["status"],scenario=report["scenario"],report_hash=digest,report_json=_canonical(report),detection_count=report["detection_count"],containment_verified=containment,recovery_verified=recovery,actor=actor,completed_at=datetime.fromisoformat(report["completed_at"]));session.add(run);session.flush();append_ledger_event(session,"INCIDENT_EXERCISE",run.id,actor,"SYSTEM","EXERCISE_COMPLETED",{"status":run.status,"scenario":run.scenario,"report_hash":digest,"detection_count":run.detection_count,"containment_verified":containment,"recovery_verified":recovery});return run,report
