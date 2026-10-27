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

-- The pane's window comes back with its bounds, so the layer opens there and not in the active window.
local _, window_id = thumbs.pane_bounds("session:a", "block:b")
assert(window_id == "window:w", "returns the pane's window")

-- Rex's rects, already fractions of the window, win over split ratios.
tree.rect = { 0, 0, 1, 1 }
tree.split.before.rect = { 0, 0, 0.59, 1 }
near(thumbs.pane_bounds("session:a", "block:a"), { 0, 0, 0.59, 1 })

-- Float sums that overshoot the window by a hair are clamped, since new_layer refuses them.
tree.split.after.split.after.rect = { 0.63, 0.6699999999999999, 0.37, 0.33000000000000017 }
local bounds = thumbs.pane_bounds("session:a", "block:b")
assert(bounds[1] + bounds[3] <= 1 and bounds[2] + bounds[4] <= 1, "bounds stay inside the window")

-- A zoomed pane fills the window.
view.windows[1].zoomed_block_id = "block:b"
near(thumbs.pane_bounds("session:a", "block:b"), { 0, 0, 1, 1 })
view.windows[1].zoomed_block_id = nil

-- A pane in a floating layer: without rects, ratios divide the layer's bounds.
table.insert(view.windows, {
  window_id = "window:f",
  layers = {
    { kind = "tiled", layout = { block_id = "block:t" } },
    {
      kind = "floating",
      bounds = { 0.2, 0.1, 0.5, 0.6 },
      layout = { split = { direction = "horizontal", ratio = 0.4, before = { block_id = "block:f1" }, after = { block_id = "block:f2" } } },
    },
  },
})
near(thumbs.pane_bounds("session:a", "block:f2"), { 0.4, 0.1, 0.3, 0.6 })
assert(select(2, thumbs.pane_bounds("session:a", "block:f2")) == "window:f", "finds panes in other windows")

thumbs.setup({ root = "/r" })
local action = assert(defined.thumbs, "setup defines the thumbs action")
assert(not pcall(action.run, {}), "fails without a focused pane")

-- The script draws in a floating layer over the pane.
action.run({ session_id = "session:a", block_id = "block:a" })
local layer = layers[#layers]
assert(layer.focus, "the layer takes focus")
assert(layer.window_id == "window:w", "the layer opens in the pane's window")
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
