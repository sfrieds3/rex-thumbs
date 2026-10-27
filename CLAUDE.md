# rex-thumbs

tmux-thumbs for Rex. See `README.md` for what it does and how users set it up.

## Layout

- `rex_thumbs.py`: everything that runs in the pane: capture over the `rex` CLI, matching (`PATTERNS`, `find_matches`), hints (`hints_for`), the raw-mode UI (`View`), commands (`run_command`) and `main`. Standard library only, Python 3.10+.
- `lua/rex_thumbs.lua`: the Rex module. `setup(opts)` defines the action; `command_for` turns options into the script's flags (option `foo_bar` becomes `--foo-bar`). It runs in Rex's server Lua (Lua 5.1, gopher-lua), so it must stay plain 5.1.
- `tests/test_thumbs.py`: unittest, with Rex calls and keys mocked. `tests/test_lua.lua`: stubs the `rex` global and checks the action.

## Behavior to keep

- Matching, alphabets and hint order follow tmux-thumbs; its own tests are ported in `MatchTests` and `HintTests`. Change them only on purpose.
- The action opens the script in a floating layer over the pane (`new_layer` with `pane_bounds`), and the script draws the pane's text with hints in its own terminal. Never move, detach or resize the user's pane.
- Always pass the pane's `window_id` to `new_layer`; without it the layer opens in the session's active window, which may not be the pane's, and nothing shows. Rex's rects are already fractions of the window; clamp them, since `new_layer` rejects bounds that leave the window.
- Rex can size the layer's terminal after the script starts (for example when its tab isn't on screen yet), so the view redraws on `SIGWINCH`.
- Rex doesn't give modules their file name, so `setup` needs `opts.root`; the `debug.getinfo` fallback only works when loaded from a checkout.
- New `setup` options need a matching argparse flag (unless Lua-only, like `python`), a README row, and a test.

## Checks

```sh
python3 -m unittest discover -s tests -v
lua tests/test_lua.lua
ruff check . && ruff format --check .
```

For a live check, create a throwaway session (`rex new`), open the script with `rex api call session.new_layer` as the Lua action does, drive it with `rex send`, and destroy the session afterwards. Don't use the user's visible sessions.

## Commits and releases

- Use Conventional Commits: `<type>(<scope>): <description>` with `feat`, `fix`, `refactor`, `docs`, `test`, `chore` or `ci`.
- Each push to `main` runs CI; when it passes, `feat`, `fix` and breaking commits (`!` or `BREAKING CHANGE`) since the last tag produce a new tag and GitHub release. Other types don't release.
- Use generic names and fixtures in tests and docs; never reference real projects, hosts or people.
