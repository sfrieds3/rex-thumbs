-- Run from the repository root with lua5.1, luajit or nvim -l: lua tests/test_lua.lua
local defined, layers = {}, {}
local view = { windows = {} }
rex = {
  action = function(def)
    defined[def.name] = def
  end,
  call = function(method)
    assert(method == "session.view", "unexpected call " .. method)
    return view
  end,
  layout = {
    block = function(args)
      return args
    end,
  },
  session = {
    new_layer = function(args)
      layers[#layers + 1] = args
      return { block_id = "block:thumbs" }
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
same(thumbs.command_for({ root = "/r" }, "s", "b"), { "python3", "/r/rex_thumbs.py", "s", "b" })
same(thumbs.command_for({ root = "/r", regexp = "x" }, "s", "b"), { "python3", "/r/rex_thumbs.py", "--regexp", "x", "s", "b" })

-- Loaded by a relative path, the module can't know its root and asks for one.
local ok, err = pcall(thumbs.command_for, {}, "s", "b")
assert(not ok and err:find("pass root"), "a relative load needs root")

-- Loaded by an absolute path, the module finds its own root.
local checkout = assert(os.getenv("PWD"), "run from the repository root")
local absolute = dofile(checkout .. "/lua/rex_thumbs.lua")
same(absolute.command_for({}, "s", "b"), { "python3", checkout .. "/rex_thumbs.py", "s", "b" })

local function near(actual, expected)
  assert(actual, "no bounds")
  for index = 1, 4 do
    assert(math.abs(actual[index] - expected[index]) < 1e-9, ("[%d] %s, expected %s"):format(index, actual[index], expected[index]))
  end
end

-- Bounds from split ratios: block:b is the bottom of the right 40%.
local tree = {
  split = {
    direction = "horizontal",
    ratio = 0.6,
    before = { block_id = "block:a" },
    after = { split = { direction = "vertical", ratio = 0.25, before = { block_id = "block:c" }, after = { block_id = "block:b" } } },
  },
}
view = { windows = { { window_id = "window:w", layers = { { kind = "tiled", layout = tree } } } } }
near(thumbs.pane_bounds("session:a", "block:b"), { 0.6, 0.25, 0.4, 0.75 })
near(thumbs.pane_bounds("session:a", "block:a"), { 0, 0, 0.6, 1 })
assert(thumbs.pane_bounds("session:a", "block:gone") == nil, "an unknown pane has no bounds")

-- Rex's rects win when the layout has them, relative to the layer's root.
tree.rect = { 10, 20, 200, 100 }
tree.split.before.rect = { 10, 20, 118, 100 }
near(thumbs.pane_bounds("session:a", "block:a"), { 0, 0, 0.59, 1 })

-- A zoomed pane fills the window.
view.windows[1].zoomed_block_id = "block:b"
near(thumbs.pane_bounds("session:a", "block:b"), { 0, 0, 1, 1 })
view.windows[1].zoomed_block_id = nil

thumbs.setup({ root = "/r" })
local action = assert(defined.thumbs, "setup defines the thumbs action")
assert(not pcall(action.run, {}), "fails without a focused pane")

-- The script draws in a floating layer over the pane.
action.run({ session_id = "session:a", block_id = "block:a" })
local layer = layers[#layers]
assert(layer.focus, "the layer takes focus")
near(layer.bounds, { 0, 0, 0.59, 1 })
assert(layer.layout.flavor == "com.superlogical.terminal.shell", "the layer holds a shell block")
same(layer.layout.options.command, { "python3", "/r/rex_thumbs.py", "session:a", "block:a" })

-- An unknown pane still gets a layer, over the whole window.
action.run({ session_id = "session:a", block_id = "block:gone" })
near(layers[#layers].bounds, { 0, 0, 1, 1 })

rex.session.new_layer = function()
  return nil, "no session"
end
local ok, err = pcall(action.run, { session_id = "session:a", block_id = "block:b" })
assert(not ok and err == "no session", "reports Rex errors")

thumbs.setup({ root = "/r", action = "hints" })
assert(defined.hints, "setup takes the action name")

print("lua tests passed")
