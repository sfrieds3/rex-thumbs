-- rex-thumbs: tmux-thumbs for Rex. See README.md for setup.
local M = {}

-- Rex may load this without a file name, so setup also takes the checkout as opts.root. Only an absolute
-- module path gives a usable root: a relative one would resolve against the new pane's directory.
local default_root = (debug.getinfo(1, "S").source or ""):match("^@(/.*)/lua/[^/]*$")

-- Option names match the script's long flags, with _ for -.
local function command_for(opts, session_id, block_id)
  local root = opts.root or default_root
  if not root then
    error("rex-thumbs: pass root, the checkout directory, to setup", 0)
  end
  local command = { opts.python or "python3", root .. "/rex_thumbs.py" }
  local names = {}
  for name in pairs(opts) do
    names[#names + 1] = name
  end
  table.sort(names)
  for _, name in ipairs(names) do
    local value = opts[name]
    local flag = "--" .. name:gsub("_", "-")
    if name == "python" or name == "action" or name == "root" then
      -- not script flags
    elseif name == "regexp" then
      for _, regexp in ipairs(type(value) == "table" and value or { value }) do
        table.insert(command, flag)
        table.insert(command, regexp)
      end
    elseif value == true then
      table.insert(command, flag)
    elseif value ~= false then
      table.insert(command, flag)
      table.insert(command, tostring(value))
    end
  end
  table.insert(command, session_id)
  table.insert(command, block_id)
  return command
end
M.command_for = command_for

local function find(node, block, box)
  if type(node) ~= "table" then
    return
  end
  if node.block_id == block then
    return node, box
  end
  local split = node.split
  if type(split) == "table" then
    local x, y, w, h = box[1], box[2], box[3], box[4]
    local ratio = split.ratio or 0.5
    local before, after
    if split.direction == "horizontal" then
      before, after = { x, y, w * ratio, h }, { x + w * ratio, y, w * (1 - ratio), h }
    else
      before, after = { x, y, w, h * ratio }, { x, y + h * ratio, w, h * (1 - ratio) }
    end
    local leaf, found = find(split.before, block, before)
    if leaf then
      return leaf, found
    end
    return find(split.after, block, after)
  end
end

-- The pane's place in its window, as the fractions new_layer takes: x, y, width, height. Rex's own rects
-- (which count gutters) win over split ratios when the layout has them.
local function pane_bounds(session_id, block_id)
  local view = rex.call("session.view", { session_id = session_id })
  for _, window in ipairs(view and view.windows or {}) do
    if window.zoomed_block_id == block_id then
      return { 0, 0, 1, 1 }
    end
    for _, layer in ipairs(window.layers or {}) do
      local root = layer.layout
      local leaf, box = find(root, block_id, { 0, 0, 1, 1 })
      if leaf then
        local outer, rect = type(root) == "table" and root.rect, leaf.rect
        if type(outer) == "table" and type(rect) == "table" and outer[3] > 0 and outer[4] > 0 then
          box = {
            (rect[1] - outer[1]) / outer[3],
            (rect[2] - outer[2]) / outer[4],
            rect[3] / outer[3],
            rect[4] / outer[4],
          }
        end
        return box
      end
    end
  end
end
M.pane_bounds = pane_bounds

-- Defines the action (default name "thumbs"); bind it like any other action.
function M.setup(opts)
  opts = opts or {}
  rex.action({
    name = opts.action or "thumbs",
    title = "Hint and Copy Text From This Pane",
    keywords = "thumbs hints copy url path sha hash ip tmux-thumbs",
    run = function(ctx)
      if not ctx.block_id then
        error("no focused pane", 0)
      end
      -- A floating layer over the pane: the pane keeps its size and place, and the layer hides it.
      local _, err = rex.session.new_layer({
        bounds = pane_bounds(ctx.session_id, ctx.block_id) or { 0, 0, 1, 1 },
        focus = true,
        layout = rex.layout.block({
          flavor = "com.superlogical.terminal.shell",
          options = { command = command_for(opts, ctx.session_id, ctx.block_id) },
        }),
      })
      if err ~= nil then
        error(err, 0)
      end
    end,
  })
end

return M
