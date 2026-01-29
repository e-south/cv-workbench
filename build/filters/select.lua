--[[
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/build/filters/select.lua

Selects bullet blocks based on include/exclude tags and removes tag attributes.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
]]

local include_tags = {}
local exclude_tags = {}

local function to_list(meta, key)
  local value = meta[key]
  if not value then
    return {}
  end
  if value.t == "MetaList" then
    local items = {}
    for _, item in ipairs(value) do
      table.insert(items, pandoc.utils.stringify(item))
    end
    return items
  end
  return { pandoc.utils.stringify(value) }
end

local function to_set(items)
  local set = {}
  for _, item in ipairs(items) do
    if item ~= "" then
      set[item] = true
    end
  end
  return set
end

local function clean_div(div)
  local attr = div.attr
  local classes = {}
  for _, class in ipairs(attr.classes) do
    if not class:match("^tag%-") then
      table.insert(classes, class)
    end
  end
  attr.classes = classes
  div.attr = attr
end

local function tags_from_div(div)
  local tags = {}
  for _, class in ipairs(div.attr.classes) do
    local tag = class:match("^tag%-(.+)")
    if tag then
      tags[tag] = true
    end
  end
  return tags
end

local function has_any(tags, set)
  for tag, _ in pairs(tags) do
    if set[tag] then
      return true
    end
  end
  return false
end

function Meta(meta)
  include_tags = to_set(to_list(meta, "include_tags"))
  exclude_tags = to_set(to_list(meta, "exclude_tags"))
  return meta
end

function Div(div)
  local has_bullet = false
  for _, class in ipairs(div.attr.classes) do
    if class == "bullet" then
      has_bullet = true
      break
    end
  end
  if not has_bullet then
    return nil
  end

  local use_includes = next(include_tags) ~= nil
  local tags = tags_from_div(div)
  if has_any(tags, exclude_tags) then
    return {}
  end
  if use_includes and not has_any(tags, include_tags) then
    return {}
  end

  clean_div(div)
  return div
end
