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
      -- The script swaps itself into the pane's place, so start it out of sight.
      local _, err = rex.session.new_window({
        focus = false,
        window_label = "thumbs",
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
