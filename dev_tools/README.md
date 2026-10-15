# Developer tools

## `release.py`: making a SoCo release

`release.py` takes a maintainer through a SoCo release, from the version
bump to the GitHub release. It runs the routine steps itself, waits for you
on the steps that need judgement (milestone review, release notes,
cherry-picks), and asks before anything that can't be undone (pushes,
tags, the PyPI upload, GitHub changes).

It supports two kinds of release:

- **main**: `X.Y.0` from `master`. This also creates the `vX.Y.fixes`
  branch and starts the next development version on `master`.
- **fix**: `X.Y.N` from `vX.Y.fixes`.

### Requirements

- Push access to `SoCo/SoCo`, with your clone's `origin` pointing at it.
- The GitHub CLI, installed and logged in: `brew install gh`, then
  `gh auth login`.
- `build` and `twine`, from `pip install -r requirements-dev.txt`.
- PyPI upload rights for `soco`, with credentials in `~/.pypirc` or your
  keyring, as twine expects. The script never handles credentials itself.

### Usage

Run from the repository root:

```
python dev_tools/release.py main 0.32.0 --dry-run   # see what would happen
python dev_tools/release.py main 0.32.0             # do it
python dev_tools/release.py fix 0.32.1              # a fix release
```

`--dry-run` runs the pre-flight checks and lists each step as `done`,
`would run` or `manual`, with the commands it would run. It changes
nothing. It does fetch from origin, and reads milestones and releases from
GitHub and versions from PyPI.

### Pre-flight checks

Before doing anything, the script checks the following:

- `origin` is `SoCo/SoCo` on GitHub.
- You're on the right branch (`master`, or `vX.Y.fixes` for a fix release)
  and not behind `origin`.
- There are no uncommitted changes to tracked files, apart from the files
  the script edits itself (`soco/__init__.py`, `doc/releases/index.rst`
  and the CI workflow). Untracked files are fine.
- `gh` is logged in, and `build` and `twine` are installed.
- For a main release, every entry in `doc/releases/index.rst` has a
  matching file.

It also checks the version you asked for. A main release must match the
`X.Y.0-dev` version on `master`. A fix release must be the next patch after
the latest `vX.Y.*` tag.

### Steps

**Main release** (`main X.Y.0`, on `master`):

1. Create milestone `vX.Y+1.0` if it doesn't exist (confirm).
2. Review milestone `X.Y.0`: the script shows its open and closed issue
   counts while you move any unfinished issues on (manual).
3. Write the release notes: the script creates `doc/releases/X.Y.0.rst`
   from a template and adds it to `doc/releases/index.rst`, then waits
   until you have edited it (manual).
4. Set `__version__` to `X.Y.0` and commit the notes, index and version as
   `Release vX.Y.0`.
5. Push `master` (confirm; the prompt lists the commits being pushed).
6. Tag the `Release vX.Y.0` commit as `vX.Y.0` and push the tag (confirm;
   the prompt shows the commit).
7. Build the sdist and wheel from a clean checkout of the tag.
8. Upload to PyPI with twine (confirm).
9. Create the GitHub release with auto-generated notes (confirm).
10. Close milestone `X.Y.0` (confirm).
11. Create `vX.Y.fixes` from the tag and push it (confirm).
12. On `master`, set `__version__` to `X.Y+1.0-dev` and switch the CI
    workflow from `vX.Y-1.fixes` to `vX.Y.fixes`, then commit.
13. Push `master` (confirm).

**Fix release** (`fix X.Y.N`, on `vX.Y.fixes`):

1. Cherry-picks: the script lists the commits on `master` that have no
   equivalent on the fixes branch, then waits while you cherry-pick the
   fixes you want (manual; the working tree must be clean to continue).
2. Set `__version__` to `X.Y.N` and commit it as `Bump version to vX.Y.N`.
3. Push the fixes branch (confirm).
4. Tag, build, upload and create the GitHub release, as in main steps 6–9.

### Prompts

- **Confirm steps** show the exact commands, then ask `[y/n/q]`:
  - `y` runs the step.
  - `n` skips it. Any later step that depends on it then stops with an
    error instead of running out of order.
  - `q` stops the script.
- **Manual steps** wait for Enter, then check that the step is really
  done, for example that the release notes differ from the template.
  `q` stops the script.
- Ctrl-C and Ctrl-D also stop the script cleanly.

### Resuming

If the script stops for any reason (a quit, an error, a failed upload),
fix the cause and run **the same command** again. There is no state file:
each step checks the real state of the repository, GitHub and PyPI, and
skips itself if it's already done. Nothing is ever rolled back, because a
pushed tag or a PyPI upload can't be undone, so resuming is always the way
to recover.

### Safety

- **The tag goes on the release commit.** It's placed on the commit on
  `origin/<branch>` whose subject is `Release vX.Y.0` (or
  `Bump version to vX.Y.N`), not on whatever `HEAD` happens to be. So if a
  PR is merged between runs, it's not included in the release. If a local
  tag already exists and points at a different commit, the script stops
  and tells you how to delete it.
- **The build comes from the tag.** It's made in a temporary worktree of
  the tag, so uncommitted or untracked files in your clone can't end up in
  the release. Files left in `dist/` from an earlier build are never
  uploaded: the build always runs again unless the version is already on
  PyPI.
- **Pushes show what they push.** Each push prompt lists the commits that
  will go to `origin`.
- **Everything goes to SoCo/SoCo.** `gh` calls use `-R SoCo/SoCo`, and the
  pre-flight check makes sure `origin` points there too.

### Troubleshooting

- **`... is N commit(s) behind origin: pull first`.** Run `git pull`, then
  run the command again. If the release commit is already pushed, the tag
  still goes on it.
- **`Local tag vX.Y.Z points at ..., not the release commit ...`.** A stale
  tag is left over from an earlier attempt. Delete it with
  `git tag -d vX.Y.Z` and run the command again.
- **twine reports `File already exists`.** The upload succeeded on an
  earlier run, but PyPI's CDN hadn't caught up when the script checked.
  Wait a minute and run the command again: the upload step then shows as
  done.
- **`needs '<step>', which is not done`.** An earlier step was skipped with
  `n`. Run the command again and answer `y` to it.

### Tests

`tests/test_release_script.py` tests the script's logic against a
simulated repository. Before a real release, run the command with
`--dry-run` and check the step list.
