# Conda environment overlays

When `run.conda_env` names an existing host environment, each run creates a
small writable Python virtual environment over that configured base. It does
not clone the Conda environment or discover dependencies in previous runs.
The base interpreter and installed packages remain in their original location.
New installations, package upgrades and the current Program runtime go into the
run's own `program-environment/env` directory.

```yaml
run:
  conda_env: my-prepared-environment
```

Agents and Programs mount the configured base read-only. This protection is
applied after writable mounts, including Setup's Conda-root grant, so a writable
parent cannot make the base writable. As with the existing confinement, disabling
`resources.sandbox.enable` disables filesystem mount protection.

Python console entry points use the overlay interpreter and honor `PYTHONPATH`.
The run's own installed versions take precedence. Other base commands remain on
`PATH`. The interpreter's `sys.prefix` points to the overlay. Packages that look
for data in `sys.prefix/share` or `sys.prefix/etc` may not find data installed only
in the base. For example, `jupyter kernelspec list` may omit a kernel installed
only under the base's `share/jupyter/kernels`.

Pip can uninstall packages installed in the overlay. An inherited package stays
importable from the base after an uninstall attempt. Install the required
replacement in the overlay when needed. Setup still verifies the task, data,
packages and scoring contract.

Resume records and validates the configured base in `program-environment/overlay.json`.
An interrupted overlay creation is rebuilt. If a recorded base disappears or
resolves to a different prefix, Resume reports the missing/changed base instead
of silently discarding the run's installations. The run records the base path.
Its packages remain live, so changes to that base affect all overlays, including
a resumed run. Keep the configured environment
available while using its runs; **no other run directory is required**. Deleting
an older run therefore cannot remove a newer run's dependency base.

When `run.conda_env` is unset, the existing behavior is preserved: look for the
environment named by `run.task_name`, clone it when available, otherwise create
a fresh Python 3.11 environment with the owned tooling. An explicitly named base
that does not exist also retains the existing fresh-environment fallback.
