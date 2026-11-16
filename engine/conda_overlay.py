"""A run-owned Python overlay over one explicitly configured host environment."""

from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
import shlex

from infra.process.command import run_captured
from infra.util.paths import is_within


async def create_conda_overlay(
    base_python: str, prefix: Path, remaining_s: Callable[[], float]
) -> Path:
    """Use the named interpreter and its packages without copying its prefix."""
    executable = Path(base_python)
    base_python = str(executable.parent.resolve() / executable.name)
    base = Path(base_python).parent.resolve().parent
    probe = await run_captured(
        [
            base_python, "-I", "-B", "-c",
            "import json, sysconfig\n"
            "from importlib.metadata import entry_points\n"
            "commands = {}\n"
            "for entry in entry_points(group='console_scripts'):\n"
            "    commands.setdefault(entry.name, (entry.module, entry.attr))\n"
            "sites = list(dict.fromkeys(sysconfig.get_path(name) "
            "for name in ('purelib', 'platlib')))\n"
            "print(json.dumps({'sites': sites, 'commands': commands}))",
        ],
        remaining_s(),
    )
    if probe.returncode:
        raise ValueError("could not inspect the configured Conda environment")
    info = json.loads(probe.stdout)
    sites = info["sites"]
    if not sites or any(not is_within(path, base) for path in sites):
        raise ValueError("configured environment package paths escape its prefix")
    created = await run_captured(
        [base_python, "-I", "-B", "-m", "venv", "--system-site-packages", str(prefix)],
        remaining_s(),
    )
    if created.returncode:
        raise ValueError(f"could not create Conda overlay: {(created.stderr or created.stdout)[-2000:]}")
    python = prefix / "bin" / "python"
    probe = await run_captured(
        [str(python), "-I", "-B", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
        remaining_s(),
    )
    site = Path(probe.stdout.strip())
    if probe.returncode or not is_within(site, prefix):
        raise ValueError("overlay interpreter does not use its own package directory")
    (site / "_aibuildai_conda_base.pth").write_text(
        "".join(f"import site; site.addsitedir({path!r})\n" for path in sites)
    )
    # Use pip's shell/Python shebang form for paths the kernel cannot parse directly.
    shebang = f"#!{python}\n"
    if any(char.isspace() for char in str(python)) or len(shebang.encode()) > 127:
        shebang = f"#!/bin/sh\n'''exec' {shlex.quote(str(python))} \"$0\" \"$@\"\n' '''\n"
    for name, (module, attribute) in sorted(info["commands"].items()):
        if not name or Path(name).name != name or "\\" in name:
            raise ValueError("invalid configured environment console command")
        target = prefix / "bin" / name
        if target.exists():
            continue
        if (not attribute or not all(part.isidentifier() for part in module.split("."))
                or not all(part.isidentifier() for part in attribute.split("."))):
            raise ValueError(f"invalid entry point for configured environment console command {name!r}")
        root = attribute.split(".", 1)[0]
        target.write_text(
            f"{shebang}import sys\nfrom {module} import {root}\n\n"
            f"if __name__ == '__main__':\n    sys.exit({attribute}())\n"
        )
        target.chmod(0o755)
    return base
