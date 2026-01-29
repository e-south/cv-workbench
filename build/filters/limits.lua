--[[
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/build/filters/limits.lua

Limits bullet count per role section and flattens bullet blocks.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
]]

local max_bullets = nil

local function to_number(meta, key)
  local value = meta[key]
  if not value then
    return nil
  end
  local text = pandoc.utils.stringify(value)
  local number = tonumber(text)
  if number and number > 0 then
    return number
  end
  return nil
end

local function has_class(element, class_name)
  for _, class in ipairs(element.attr.classes) do
    if class == class_name then
      return true
    end
  end
  return false
end

function Meta(meta)
  max_bullets = to_number(meta, "max_bullets_per_role")
  return meta
end

function Div(div)
  if not has_class(div, "role") then
    return nil
  end

  local bullets = {}
  local new_content = {}

  for _, block in ipairs(div.content) do
    if block.t == "Div" and has_class(block, "bullet") then
      for _, inner in ipairs(block.content) do
        if inner.t == "BulletList" then
          for _, item in ipairs(inner.c) do
            table.insert(bullets, item)
          end
        end
      end
    else
      table.insert(new_content, block)
    end
  end

  if #bullets > 0 then
    local limited = bullets
    if max_bullets then
      limited = {}
      for index, item in ipairs(bullets) do
        if index > max_bullets then
          break
        end
        table.insert(limited, item)
      end
    end
    table.insert(new_content, pandoc.BulletList(limited))
  end

  div.content = new_content
  return div
end
