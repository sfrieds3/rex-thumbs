#!/usr/bin/env python3
"""Hint and copy text from a Rex pane, like tmux-thumbs.

usage: rex_thumbs.py [options] SESSION BLOCK

Run from the Lua action in lua/rex_thumbs.lua. It starts this script in a
hidden window; the script captures BLOCK, swaps itself into BLOCK's place so
the hints line up with the text, and swaps back when a hint is chosen.
"""

import argparse
import fcntl
import json
import os
import re
import select
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import termios
import time
import tty
import unicodedata

REX = os.environ.get("REX_BIN") or "rex"
TIMEOUT = os.environ.get("REX_THUMBS_TIMEOUT", "2s")

# Same priority order as tmux-thumbs: excludes first, then custom, then built-ins.
EXCLUDE_PATTERNS = [("bash", r"[\x00-\x1f]\[([0-9]{1,2};)?([0-9]{1,2})?m")]
PATTERNS = [
    ("markdown_url", r"\[[^]]*\]\(([^)]+)\)"),
    ("url", r"(?P<match>(https?://|git@|git://|ssh://|ftp://|file:///)[^ ]+)"),
    ("diff_summary", r"diff --git a/([.\w\-@~\[\]]+?/[.\w\-@\[\]]+) b/([.\w\-@~\[\]]+?/[.\w\-@\[\]]+)"),
    ("diff_a", r"--- a/([^ ]+)"),
    ("diff_b", r"\+\+\+ b/([^ ]+)"),
    ("docker", r"sha256:([0-9a-f]{64})"),
    ("path", r"(?P<match>([.\w\-@$~\[\]]+)?(/[.\w\-@$\[\]]+)+)"),
    ("color", r"#[0-9a-fA-F]{6}"),
    ("uid", r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"),
    ("ipfs", r"Qm[0-9a-zA-Z]{44}"),
    ("sha", r"[0-9a-f]{7,40}"),
    ("ip", r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}"),
    ("ipv6", r"[A-Fa-f0-9:]+:+[A-Fa-f0-9:]+[%\w]+"),
    ("address", r"0x[0-9a-fA-F]+"),
    ("number", r"[0-9]{4,}"),
]

ALPHABETS = {
    "numeric": "1234567890",
    "abcd": "abcd",
    "qwerty": "asdfqwerzxcvjklmiuopghtybn",
    "qwerty-homerow": "asdfjklgh",
    "qwerty-left-hand": "asdfqwerzcxv",
    "qwerty-right-hand": "jkluiopmyhn",
    "azerty": "qsdfazerwxcvjklmuiopghtybn",
    "azerty-homerow": "qsdfjkmgh",
    "azerty-left-hand": "qsdfazerwxcv",
    "azerty-right-hand": "jklmuiophyn",
    "qwertz": "asdfqweryxcvjkluiopmghtzbn",
    "qwertz-homerow": "asdfghjkl",
    "qwertz-left-hand": "asdfqweryxcv",
    "qwertz-right-hand": "jkluiopmhzn",
    "dvorak": "aoeuqjkxpyhtnsgcrlmwvzfidb",
    "dvorak-homerow": "aoeuhtnsid",
    "dvorak-left-hand": "aoeupqjkyix",
    "dvorak-right-hand": "htnsgcrlmwvz",
    "colemak": "arstqwfpzxcvneioluymdhgjbk",
    "colemak-homerow": "arstneiodh",
    "colemak-left-hand": "arstqwfpzxcv",
    "colemak-right-hand": "neioluymjhk",
}

COLORS = {"black": 0, "red": 1, "green": 2, "yellow": 3, "blue": 4, "magenta": 5, "cyan": 6, "white": 7}


class Match:
    def __init__(self, x, y, pattern, text):
        self.x, self.y, self.pattern, self.text = x, y, pattern, text
        self.hint = None

    def __repr__(self):
        return f"Match({self.x}, {self.y}, {self.pattern!r}, {self.text!r}, hint={self.hint!r})"


def hints_for(alphabet, count):
    """Shortest-first hints with no hint a prefix of another (tmux-thumbs' expansion)."""
    letters = list(ALPHABETS.get(alphabet, alphabet))
    expansion, expanded = letters[:], []
    while expansion and len(expansion) + len(expanded) < count:
        prefix = expansion.pop()
        take = count - len(expansion) - len(expanded)
        expanded[0:0] = [prefix + letter for letter in letters[:take]]
    return expansion[: max(count - len(expanded), 0)] + expanded


def find_matches(lines, *, alphabet="qwerty", custom=(), reverse=False, unique=False):
    patterns = [(name, re.compile(regex)) for name, regex in EXCLUDE_PATTERNS]
    patterns += [("custom", re.compile(regex)) for regex in custom]
    patterns += [(name, re.compile(regex)) for name, regex in PATTERNS]

    matches = []
    for y, line in enumerate(lines):
        offset = 0
        while offset <= len(line):
            first = None
            for name, regex in patterns:
                found = regex.search(line, offset)
                if found and found.end() > found.start() and (first is None or found.start() < first[1].start()):
                    first = (name, found)
            if first is None:
                break
            name, found = first
            if name != "bash":
                if "match" in found.re.groupindex:
                    groups = [found.span("match")]
                elif found.re.groups:
                    groups = [
                        found.span(index) for index in range(1, found.re.groups + 1) if found.group(index) is not None
                    ]
                else:
                    groups = [found.span()]
                for start, end in groups:
                    matches.append(Match(start, y, name, line[start:end]))
            offset = found.end()

    hints = hints_for(alphabet, len(matches))
    ordered = list(reversed(matches)) if reverse else matches
    seen = {}
    for match in ordered:
        if unique and match.text in seen:
            match.hint = seen[match.text]
        elif hints:
            match.hint = hints.pop(0)
            seen[match.text] = match.hint
    return matches


def cell_width(text):
    """Columns Rex draws TEXT in: one width per code point, without grapheme clustering."""
    width = 0
    for char in text:
        if unicodedata.combining(char) or unicodedata.category(char) in ("Mn", "Me", "Cf"):
            continue
        # Regional indicators (flag halves) are East Asian "neutral", but Rex draws each one two columns wide.
        wide = unicodedata.east_asian_width(char) in ("W", "F") or 0x1F1E6 <= ord(char) <= 0x1F1FF
        width += 2 if wide else 1
    return width


def sgr_color(name, background=False):
    name = (name or "default").lower()
    if name.startswith("#") and len(name) == 7:
        red, green, blue = (int(name[index : index + 2], 16) for index in (1, 3, 5))
        return f"{48 if background else 38};2;{red};{green};{blue}"
    bright = name.startswith("bright")
    base = COLORS.get(name[6:].lstrip("-_") if bright else name)
    if base is None:
        return "49" if background else "39"
    return str((100 if background else 90) + base if bright else (40 if background else 30) + base)


def style(fg, bg):
    return f"\x1b[0;{sgr_color(fg)};{sgr_color(bg, True)}m"


# Rex


def rex(*args, input=None):
    result = subprocess.run(
        [REX, "--autostart=false", "--timeout", TIMEOUT, *args],
        input=input,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"rex {args[0]} failed")
    return json.loads(result.stdout or "null")


def api(method, **params):
    return rex("api", "call", method, json.dumps(params)) or {}


def block_call(session, block, method, params=None):
    return rex("block", "call", "-s", session, "-b", block, method, json.dumps(params or {})) or {}


CURSOR = re.compile(r"\x1b\[(\d+);(\d+)H$")


def screen_lines(content, rows, cursor=None):
    """The rows on screen, from Rex's text of the scrollback and screen.

    The text leaves out blank rows below the last line with text, so after a clear-screen that keeps the
    scrollback (Ctrl-L) the last ROWS lines start inside the scrollback. When the cursor sits at or past the
    end of the last line, nothing is drawn below it, and the screen ends on the cursor's row. Otherwise (a
    status line under a TUI's input, say) the screen is taken as full.
    """
    if content.endswith("\n"):
        content = content[:-1]
    lines = content.split("\n")
    if not rows:
        return lines
    top = max(len(lines) - rows, 0)
    if cursor:
        row, column = cursor
        if cell_width(lines[-1].rstrip()) <= column - 1:
            top = max(len(lines) - row, 0)
    return lines[top : top + rows]


def capture(session, block):
    size = block_call(session, block, "size")
    content = block_call(session, block, "format", {"format": "text"}).get("content", "")
    vt = block_call(session, block, "format", {"format": "vt", "extra_cursor": True}).get("content", "")
    found = CURSOR.search(vt)
    cursor = (int(found[1]), int(found[2])) if found else None
    rows, columns = size.get("rows") or 0, size.get("columns") or 0
    return screen_lines(content, rows, cursor), rows, columns


# Actions


def copy_text(text):
    for tool in (
        ["pbcopy"],
        ["wl-copy"] if os.environ.get("WAYLAND_DISPLAY") else None,
        ["xclip", "-selection", "clipboard"] if os.environ.get("DISPLAY") else None,
    ):
        if tool and shutil.which(tool[0]):
            subprocess.run(tool, input=text, text=True, check=False)
            return
    import base64

    with open("/dev/tty", "w") as tty_out:
        tty_out.write("\x1b]52;c;" + base64.b64encode(text.encode()).decode() + "\a")


def run_command(command, text, session, block):
    if command in ("copy", "copy-paste"):
        copy_text(text)
    if command in ("paste", "copy-paste"):
        api("block.event", session_id=session, block_id=block, event={"type": "paste", "payload": {"text": text}})
    elif command == "open":
        subprocess.Popen(
            ["open" if sys.platform == "darwin" else "xdg-open", text],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    elif command not in ("copy", "copy-paste"):
        env = dict(os.environ, THUMB=text, REX_THUMBS_SESSION=session, REX_THUMBS_BLOCK=block)
        subprocess.run(
            ["sh", "-c", command.replace("{}", shlex.quote(text))], input=text, text=True, env=env, check=False
        )


# Terminal UI


def terminal_size(fd):
    rows, columns, _, _ = struct.unpack("HHHH", fcntl.ioctl(fd, termios.TIOCGWINSZ, b"\0" * 8))
    return rows, columns


def read_key(fd):
    data = os.read(fd, 64).decode("utf-8", "ignore")
    if data.startswith("\x1b") and len(data) > 1:
        return {
            "\x1b[A": "up",
            "\x1b[B": "down",
            "\x1b[C": "right",
            "\x1b[D": "left",
            "\x1bOA": "up",
            "\x1bOB": "down",
            "\x1bOC": "right",
            "\x1bOD": "left",
        }.get(data, "")
    return {
        "\x1b": "esc",
        "\r": "enter",
        "\n": "enter",
        "\x7f": "backspace",
        "\x08": "backspace",
        "\x03": "esc",
        " ": "space",
    }.get(data, data[:1])


class View:
    def __init__(self, lines, matches, options):
        self.lines, self.matches, self.options = lines, matches, options
        self.multi = options.multi
        self.selected = 0
        self.chosen = []  # (text, upcase)

    def render(self, typed, out):
        options = self.options
        buffer = ["\x1b[?25l\x1b[?7l\x1b[0m\x1b[H\x1b[2J"]
        for y, line in enumerate(self.lines):
            if line.strip():
                buffer.append(f"\x1b[{y + 1};1H{line.rstrip()}")
        chosen = {text for text, _ in self.chosen}
        for index, match in enumerate(self.matches):
            if match.text in chosen:
                colors = (options.multi_fg_color, options.multi_bg_color)
            elif index == self.selected:
                colors = (options.select_fg_color, options.select_bg_color)
            else:
                colors = (options.fg_color, options.bg_color)
            x = cell_width(self.lines[match.y][: match.x])
            text = f"[{match.text}]" if options.contrast else match.text
            buffer.append(f"\x1b[{match.y + 1};{x + 1}H{style(*colors)}{text}\x1b[0m")
            if not match.hint:
                continue
            hint = f"[{match.hint}]" if options.contrast else match.hint
            shift = {"right": cell_width(text) - len(hint), "off_left": -len(hint), "off_right": cell_width(text)}
            hx = max(x + shift.get(options.position, 0), 0)
            buffer.append(f"\x1b[{match.y + 1};{hx + 1}H{style(options.hint_fg_color, options.hint_bg_color)}{hint}")
            if typed and match.hint.startswith(typed):
                buffer.append(
                    f"\x1b[{match.y + 1};{hx + 1}H{style(options.multi_fg_color, options.multi_bg_color)}{typed}"
                )
            buffer.append("\x1b[0m")
        out.write("".join(buffer))
        out.flush()

    def run(self, fd, out):
        """Returns [(text, upcase)], empty when cancelled."""
        if not self.matches:
            return []
        longest = max(len(match.hint or "") for match in self.matches)
        typed = ""
        self.render(typed, out)
        while True:
            key = read_key(fd)
            if key == "esc":
                if self.multi and typed:
                    typed = ""
                else:
                    return []
            elif key in ("up", "left"):
                self.selected = max(self.selected - 1, 0)
            elif key in ("down", "right"):
                self.selected = min(self.selected + 1, len(self.matches) - 1)
            elif key == "backspace":
                typed = typed[:-1]
            elif key == "enter":
                self.chosen.append((self.matches[self.selected].text, False))
                if not self.multi:
                    return self.chosen
            elif key == "space":
                if self.multi:
                    return self.chosen
                self.multi = True
            elif len(key) == 1 and key.isprintable():
                typed += key.lower()
                match = next((match for match in self.matches if match.hint == typed), None)
                if match:
                    self.chosen.append((match.text, key != key.lower()))
                    if not self.multi:
                        return self.chosen
                    typed = ""
                elif not any(m.hint and m.hint.startswith(typed) for m in self.matches):
                    if not self.multi and len(typed) >= longest:
                        return []
                    typed = ""
            self.render(typed, out)


def wait_for_size(fd, rows, columns, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if terminal_size(fd) == (rows, columns):
            return
        select.select([], [], [], 0.02)


def present(view, rows, columns):
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    out = sys.stdout
    try:
        tty.setraw(fd)
        out.write("\x1b[?1049h")
        wait_for_size(fd, rows, columns)
        signal.signal(signal.SIGWINCH, lambda *_: None)
        return view.run(fd, out)
    finally:
        out.write("\x1b[0m\x1b[?7h\x1b[?25h\x1b[?1049l")
        out.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("session")
    parser.add_argument("block")
    parser.add_argument("--alphabet", default="qwerty")
    parser.add_argument("--reverse", action="store_true", help="assign the shortest hints from the bottom")
    parser.add_argument("--unique", action="store_true", help="give repeated text the same hint")
    parser.add_argument("--regexp", action="append", default=[], help="extra pattern, tried before the built-ins")
    parser.add_argument("--position", default="left", choices=["left", "right", "off_left", "off_right"])
    parser.add_argument("--contrast", action="store_true")
    parser.add_argument("--multi", action="store_true", help="start in multi-selection mode")
    parser.add_argument(
        "--command", default="copy", help="copy, paste, copy-paste, open, or a shell command ({} is the text)"
    )
    parser.add_argument("--upcase-command", default="copy-paste")
    parser.add_argument("--multi-command", default="copy")
    for name, fg, bg in (
        ("", "green", "default"),
        ("hint-", "yellow", "default"),
        ("select-", "blue", "default"),
        ("multi-", "yellow", "default"),
    ):
        parser.add_argument(f"--{name}fg-color", default=fg)
        parser.add_argument(f"--{name}bg-color", default=bg)
    parser.add_argument("--no-swap", action="store_true", help="draw in this terminal instead of over BLOCK")
    return parser.parse_args(argv)


def main(argv):
    options = parse_args(argv)
    session, target = options.session, options.block
    me = os.environ.get("REX_BLOCK")
    lines, rows, columns = capture(session, target)
    matches = find_matches(
        lines, alphabet=options.alphabet, custom=options.regexp, reverse=options.reverse, unique=options.unique
    )
    if not matches:
        return 0

    swapped = False
    try:
        if not options.no_swap and me:
            api("session.swap_blocks", session_id=session, block_id=target, other_block_id=me)
            swapped = True
            api("session.focus_block", session_id=session, block_id=me)
        else:
            rows, columns = terminal_size(sys.stdin.fileno())
        chosen = present(View(lines, matches, options), rows, columns)
    finally:
        if swapped:
            api("session.swap_blocks", session_id=session, block_id=target, other_block_id=me)
            api("session.focus_block", session_id=session, block_id=target)

    if not chosen:
        return 0
    if len(chosen) > 1:
        run_command(options.multi_command, " ".join(text for text, _ in chosen), session, target)
    else:
        text, upcase = chosen[0]
        run_command(options.upcase_command if upcase else options.command, text, session, target)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
        print(f"rex-thumbs: {exc}", file=sys.stderr)
        time.sleep(2)
        sys.exit(1)
