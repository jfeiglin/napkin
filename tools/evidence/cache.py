"""The shared content cache follows the main checkout, including in linked worktrees."""

import os
import subprocess
from pathlib import Path

from ..catalogue import ROOT


def evidence_cache(root=ROOT):
    override = os.environ.get('EVIDENCE_CACHE')
    if override:
        return Path(override).expanduser().resolve()
    root = Path(root)
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--git-common-dir'],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        common = Path(result.stdout.strip())
        if not common.is_absolute():
            common = root / common
        common = common.resolve()
        if common.is_dir() and common.name == '.git':
            return common.parent / '.evidence-cache'
    except (OSError, subprocess.CalledProcessError):
        pass
    return root / '.evidence-cache'
