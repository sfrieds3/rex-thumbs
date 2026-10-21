# rex-thumbs

tmux-thumbs for Rex. See `README.md` for what it does and how users set it up.

## Layout

- `rex_thumbs.py`: everything that runs in the pane: capture over the `rex` CLI, matching (`PATTERNS`, `find_matches`), hints (`hints_for`), the raw-mode UI (`View`), commands (`run_command`) and the swap in `main`. Standard library only, Python 3.10+.
- `lua/rex_thumbs.lua`: the Rex module. `setup(opts)` defines the action; `command_for` turns options into the script's flags (option `foo_bar` becomes `--foo-bar`). It runs in Rex's server Lua (Lua 5.1, gopher-lua), so it must stay plain 5.1.
- `tests/test_thumbs.py`: unittest, with Rex calls and keys mocked. `tests/test_lua.lua`: stubs the `rex` global and checks the action.

## Behavior to keep

- Matching, alphabets and hint order follow tmux-thumbs; its own tests are ported in `MatchTests` and `HintTests`. Change them only on purpose.
- `main` swaps back in `finally`. Every path out of the UI must restore the pane's place and focus.
- The script starts in a hidden window (`new_window` with `focus = false`) and captures before swapping, because the swap resizes the pane.
- Rex doesn't give modules their file name, so `setup` needs `opts.root`; the `debug.getinfo` fallback only works when loaded from a checkout.
- New `setup` options need a matching argparse flag, a README row, and a test.

## Checks

```sh
python3 -m unittest discover -s tests -v
lua tests/test_lua.lua
ruff check . && ruff format --check .
```

For a live check, create a throwaway session (`rex new`), start the script with `rex api call session.new_window` as the Lua action does, drive it with `rex send`, and destroy the session afterwards. Don't use the user's visible sessions.

## Commits and releases

- Use Conventional Commits: `<type>(<scope>): <description>` with `feat`, `fix`, `refactor`, `docs`, `test`, `chore` or `ci`.
- Each push to `main` runs CI; when it passes, `feat`, `fix` and breaking commits (`!` or `BREAKING CHANGE`) since the last tag produce a new tag and GitHub release. Other types don't release.
- Use generic names and fixtures in tests and docs; never reference real projects, hosts or people.
