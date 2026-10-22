-- Run from the repository root with lua5.1, luajit or nvim -l: lua tests/test_lua.lua
local defined, windows = {}, {}
rex = {
  action = function(def)
    defined[def.name] = def
  end,
  layout = {
    block = function(block)
      return { block = block }
    end,
  },
  session = {
    new_window = function(args)
      windows[#windows + 1] = args
      return { block_ids = { "block:thumbs" } }
    end,
  },
}
package.path = "lua/?.lua;" .. package.path
local thumbs = require("rex_thumbs")

local function same(actual, expected)
  assert(#actual == #expected, ("length %d, expected %d: %s"):format(#actual, #expected, table.concat(actual, " ")))
  for index = 1, #expected do
    assert(actual[index] == expected[index], ("[%d] %s, expected %s"):format(index, tostring(actual[index]), expected[index]))
  end
end

-- Flags come out sorted; Lua-only options, false and nil are left out.
same(
  thumbs.command_for({
    root = "/opt/rex-thumbs",
    action = "hints",
    python = "/usr/bin/python3",
    fg_color = "yellow",
    reverse = true,
    unique = false,
    regexp = { "[A-Z]+-%d+", "foo" },
  }, "session:a", "block:b"),
  {
    "/usr/bin/python3", "/opt/rex-thumbs/rex_thumbs.py",
    "--fg-color", "yellow",
    "--regexp", "[A-Z]+-%d+", "--regexp", "foo",
    "--reverse",
    "session:a", "block:b",
  }
)
same(thumbs.command_for({ root = "/r", regexp = "x" }, "s", "b"), { "python3", "/r/rex_thumbs.py", "--regexp", "x", "s", "b" })

-- Loaded by a relative path, the module can't know its root and asks for one.
local ok, err = pcall(thumbs.command_for, {}, "s", "b")
assert(not ok and err:find("pass root"), "a relative load needs root")

-- Loaded by an absolute path, the module finds its own root.
local checkout = assert(os.getenv("PWD"), "run from the repository root")
local absolute = dofile(checkout .. "/lua/rex_thumbs.lua")
same(absolute.command_for({}, "s", "b"), { "python3", checkout .. "/rex_thumbs.py", "s", "b" })

thumbs.setup({ root = "/r" })
local action = assert(defined.thumbs, "setup defines the thumbs action")
assert(not pcall(action.run, {}), "fails without a focused pane")
action.run({ session_id = "session:a", block_id = "block:b" })
local window = windows[#windows]
assert(window.focus == false, "the script starts in a hidden window")
same(window.layout.block.options.command, { "python3", "/r/rex_thumbs.py", "session:a", "block:b" })

rex.session.new_window = function()
  return nil, "no session"
end
local ok, err = pcall(action.run, { session_id = "session:a", block_id = "block:b" })
assert(not ok and err == "no session", "reports Rex errors")

thumbs.setup({ root = "/r", action = "hints" })
assert(defined.hints, "setup takes the action name")

print("lua tests passed")
