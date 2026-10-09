"""Bounded host-only benchmark. Never opens physical serial/camera or an HTTP port."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import resource

parser=argparse.ArgumentParser()
parser.add_argument('--root',default=str(Path(__file__).resolve().parents[1]))
parser.add_argument('--duration',type=float,default=5)
parser.add_argument('--waiting',action='store_true')
args=parser.parse_args()
script='''
import sys
sys.path.insert(0,sys.argv[1])
from main import Pipeline, setup_logging
config={"api":{"enabled":False},"camera":{"width":320,"height":240,"fps":10},"duration_s":float(sys.argv[2])}
if sys.argv[3]=="active": config["simulation"]={"start_after_s":.3,"clear_after_s":float(sys.argv[2])-1}
setup_logging(config)
p=Pipeline(config,"mock")
raise SystemExit(p.run() if p.setup() else 1)
'''
start=time.monotonic()
result=subprocess.run([sys.executable,'-B','-c',script,str(Path(args.root).resolve()/'poc_raspberry'),str(args.duration),'waiting' if args.waiting else 'active'],capture_output=True)
elapsed=time.monotonic()-start
usage=resource.getrusage(resource.RUSAGE_CHILDREN)
print(json.dumps({"exit_code":result.returncode,"host_only":True,"mode":"waiting" if args.waiting else "active", "elapsed_s":round(elapsed,3),"cpu_s":round(usage.ru_utime+usage.ru_stime,3),"cpu_percent_one_core":round((usage.ru_utime+usage.ru_stime)/elapsed*100,2),"peak_rss_kib":usage.ru_maxrss,"stdout_bytes":len(result.stdout),"stderr_bytes":len(result.stderr),"log_lines":len(result.stdout.splitlines())+len(result.stderr.splitlines())}))
if result.returncode: print(result.stderr.decode(),file=sys.stderr)
raise SystemExit(result.returncode)
