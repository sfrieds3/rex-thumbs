# rex-thumbs

[![CI](https://github.com/sfrieds3/rex-thumbs/actions/workflows/ci.yml/badge.svg)](https://github.com/sfrieds3/rex-thumbs/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/sfrieds3/rex-thumbs?sort=semver)](https://github.com/sfrieds3/rex-thumbs/releases)

Copy anything on screen in [Rex](https://www.superlogical.com/rex) with two keystrokes. rex-thumbs is a port of [tmux-thumbs](https://github.com/fcsonline/tmux-thumbs). It labels every URL, path, git hash, IP address and long number on a pane with a short hint. Type the hint to copy the text, or Shift+hint to copy it and paste it at the prompt.

```text
$ git log --oneline -2                  $ git log --oneline -2
9f2c4e1 fix: handle empty input         af2c4e1 fix: handle empty input
3b7d0a2 feat: add parser    ─ thumbs ─▶ sb7d0a2 feat: add parser
$ curl https://example.com/api          $ curl dttps://example.com/api

press s to copy 3b7d0a2, or S to copy it and paste it at the prompt
```

## Features

- Hints sit right on the text. The picker takes the pane's place in the layout, so nothing moves.
- It finds the same things tmux-thumbs does: markdown links, URLs, `git diff` paths, docker digests, paths, hex colors, UUIDs, IPFS hashes, git SHAs, IPv4 and IPv6 addresses, hex addresses, and numbers of four or more digits.
- You can add your own patterns, and they're tried before the built-in ones.
- Shift+hint copies and pastes. Space selects several matches. Everything has an option: the actions, alphabets, hint placement and colors.
- Copying uses `pbcopy`, or `wl-copy` or `xclip` when `WAYLAND_DISPLAY` or `DISPLAY` is set, and falls back to OSC 52. Pasting goes through Rex, so bracketed paste works.

## Requirements

- Rex with Lua configuration (`~/.config/rex/init.lua`)
- Python 3.10 or newer (standard library only)
- `rex` on the pane's `PATH` (Rex adds it to the panes it starts)

## Install

Clone the repository, or download a [release](https://github.com/sfrieds3/rex-thumbs/releases):

```sh
git clone https://github.com/sfrieds3/rex-thumbs ~/code/rex-thumbs
```

Load it from `~/.config/rex/init.lua` and bind the `thumbs` action:

```lua
local root = os.getenv("HOME") .. "/code/rex-thumbs"
package.path = root .. "/lua/?.lua;" .. package.path
require("rex_thumbs").setup({ root = root })

rex.bind("cmd+shift+space", "thumbs")
```

Then run `rex config reload`. `setup` defines the action, and you bind it like any other Rex action: directly, or inside a mode such as a tmux-style prefix:

```lua
rex.mode("prefix", { exclusive = true })
rex.bind("ctrl+space", "client.mode.enter", { name = "prefix", once = true })
rex.bind("prefix/space", "thumbs")
```

The action also shows up in the command palette as "Hint and Copy Text From This Pane".

## Usage

| Key | Action |
| --- | --- |
| hint | run `command` on the text (copy, by default) |
| Shift+hint | run `upcase_command` (copy and paste into the pane, by default) |
| Space | start selecting several matches; Space again runs `multi_command` on them, joined by spaces |
| Arrows, then Enter | move the highlight and choose the highlighted match |
| Backspace | delete the last letter typed |
| Esc, Ctrl-C | cancel |

Matching text is drawn in `fg_color` and its hint in `hint_fg_color`. Repeated text gets a hint each, unless you set `unique = true`.

## Configuration

Pass options to `setup`. Names follow tmux-thumbs' `@thumbs-*` options, with `_` in place of `-`, so a tmux config translates directly:

```lua
require("rex_thumbs").setup({
  root = root,
  alphabet = "colemak-homerow",
  reverse = true,                 -- shortest hints at the bottom, nearest the prompt
  unique = true,
  fg_color = "yellow",
  hint_fg_color = "red",
  regexp = { "[A-Z]+-[0-9]+" },   -- ticket ids
  upcase_command = "open",
})
```

| Option | Default | Notes |
| --- | --- | --- |
| `root` | | Checkout directory. Required: Rex doesn't give modules their file name. |
| `action` | `thumbs` | Name of the action to define. Call `setup` twice for two variants. |
| `alphabet` | `qwerty` | A tmux-thumbs alphabet name, or the letters themselves. |
| `reverse` | `false` | Give the shortest hints to the bottom of the screen. |
| `unique` | `false` | Give repeated text the same hint. |
| `position` | `left` | Where hints go: `left`, `right`, `off_left` or `off_right`. |
| `contrast` | `false` | Wrap matches and hints in brackets. |
| `multi` | `false` | Start in multi-selection mode. |
| `regexp` | | A pattern or a list of patterns (Python syntax), tried before the built-ins. A named group `match` picks the part to copy. |
| `command` | `copy` | What a hint does. |
| `upcase_command` | `copy-paste` | What Shift+hint does. |
| `multi_command` | `copy` | What a multi-selection does. |
| `fg_color`, `bg_color` | `green`, `default` | Matches. |
| `hint_fg_color`, `hint_bg_color` | `yellow`, `default` | Hints. |
| `select_fg_color`, `select_bg_color` | `blue`, `default` | The highlighted match. |
| `multi_fg_color`, `multi_bg_color` | `yellow`, `default` | Chosen matches and typed letters. |
| `python` | `python3` | Interpreter for the script. |

Alphabets: `numeric`, `abcd`, and the full, `-homerow`, `-left-hand` and `-right-hand` sets for `qwerty`, `azerty`, `qwertz`, `dvorak` and `colemak`.

Colors: `black`, `red`, `green`, `yellow`, `blue`, `magenta`, `cyan`, `white`, `bright` + a name (`brightred`), `default`, or `#rrggbb`.

### Commands

`command`, `upcase_command` and `multi_command` take a built-in or a shell command:

| Value | Does |
| --- | --- |
| `copy` | copy to the clipboard |
| `paste` | paste into the pane |
| `copy-paste` | both |
| `open` | `open` (macOS) or `xdg-open` |
| anything else | run with `sh -c`. The text is in `$THUMB` and on stdin, and `{}` is shorthand for `${THUMB}`, as in tmux-thumbs: the shell expands it as data and never runs the text. Write `"{}"` to pass it as one argument. `$REX_THUMBS_SESSION` and `$REX_THUMBS_BLOCK` name the pane. |

```lua
command = "printf '%s\\n' \"{}\" >> ~/clips.txt",                 -- keep a log of copies
upcase_command = 'rex split -b "$REX_THUMBS_BLOCK" -- nvim "{}"', -- open in Neovim beside the pane
```

## How it works

1. The `thumbs` action starts `rex_thumbs.py` in a detached block, which belongs to no window, so no tab appears.
2. The script reads the pane's size and text over the `rex` CLI and finds the matches. If there are none, it exits.
3. It takes the pane's place: `session.move_block` puts it beside the pane and `session.detach_block` takes the pane out, so the script gets the pane's exact size and position. Then it draws the text with hints.
4. Once you choose (or cancel), it puts the pane back the same way, focuses it again and runs the command. The script's block closes when it exits.

tmux-thumbs works the same way with `swap-pane`. Rex can't swap a detached block, so for a moment the pane and the script share the pane's space, and the pane's program gets one resize. A floating layer over the pane would avoid that, but its text grid doesn't line up with a tiled pane's, so the hints would be off by a row.

## Troubleshooting

- **Nothing happens.** There may be nothing to hint. Otherwise check `rex config check` and make sure `root` points at the checkout.
- **A "thumbs" pane opens with an error.** When the script fails (a bad `regexp`, a misspelled option, `rex` unreachable), it places itself beside the focused pane and waits for a key. If nothing opens at all, `python3` may be missing from the pane's `PATH`; set `python` to an absolute path.
- **A pane disappeared.** If the script is killed outright (`kill -9`) while the hints are up, it can't put the pane back, and the pane is left running but detached. `rex api call session.list_blocks` lists it with `"placement": "detached"`; put it back beside another pane with `rex api call session.move_block '{"block_id": "<pane>", "anchor_block_id": "<other>"}'`.
- **The hints don't match what you were looking at.** thumbs hints the live screen, not a scrolled-back view of the history. Use the find bar or a picker such as [rextracto](https://github.com/sfrieds3/rextracto) for older output.

## Development

```sh
python3 -m unittest discover -s tests -v   # matching, hints, rendering, keys, swapping
lua tests/test_lua.lua                     # the Rex action (lua5.1, luajit or nvim -l)
ruff check . && ruff format --check .
```

CI runs these on Linux and macOS for every push and pull request. Each push to `main` that has a `feat`, `fix` or breaking commit is tagged and released. The version bump follows [Conventional Commits](https://www.conventionalcommits.org): `fix` is a patch, `feat` a minor and `!`/`BREAKING CHANGE` a major.

## Credits

The patterns, alphabets and hint algorithm come from [tmux-thumbs](https://github.com/fcsonline/tmux-thumbs) by Ferran Basora.

## License

[MIT](LICENSE)
