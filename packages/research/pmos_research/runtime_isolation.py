from __future__ import annotations

import os
import resource
from dataclasses import dataclass

SAFE_EXACT={"PATH","HOME","LANG","TZ","TMPDIR","SSL_CERT_FILE","SSL_CERT_DIR","PYTHONPATH"}
SAFE_PREFIXES=("LC_","PMOS_")
DENIED_FRAGMENTS=("TOKEN","SECRET","PASSWORD","COOKIE","CREDENTIAL","PRIVATE_KEY","ACCESS_KEY")
DENIED_EXACT={"HTTP_PROXY","HTTPS_PROXY","ALL_PROXY","NO_PROXY","GITHUB_TOKEN","GH_TOKEN"}

def sanitized_environment(source:dict[str,str]|None=None)->dict[str,str]:
    source=dict(os.environ if source is None else source);result={}
    for key,value in source.items():
        upper=key.upper()
        if upper in DENIED_EXACT or any(part in upper for part in DENIED_FRAGMENTS):continue
        if upper in SAFE_EXACT or upper.startswith(SAFE_PREFIXES):result[key]=value
    return result

@dataclass(frozen=True)
class ResourceLimits:
    cpu_seconds:int=900
    file_bytes:int=536_870_912
    open_files:int=256
    # macOS accounts this per user, so leave room for the host while bounding forks.
    processes:int=512

def apply_resource_limits(limits:ResourceLimits=ResourceLimits())->None:
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_CPU,(limits.cpu_seconds,limits.cpu_seconds))
    resource.setrlimit(resource.RLIMIT_FSIZE,(limits.file_bytes,limits.file_bytes))
    resource.setrlimit(resource.RLIMIT_NOFILE,(limits.open_files,limits.open_files))
    if hasattr(resource,"RLIMIT_NPROC"):resource.setrlimit(resource.RLIMIT_NPROC,(limits.processes,limits.processes))
