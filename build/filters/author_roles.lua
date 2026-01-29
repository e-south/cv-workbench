--[[
--------------------------------------------------------------------------------
cv-workbench
cv-workbench/build/filters/author_roles.lua

Annotates author spans with role markers.

Module Author(s): Eric J. South
--------------------------------------------------------------------------------
]]

local ROLE_MARKERS = {
  ["role-co-first"] = "*",
  ["role-corresponding"] = "†",
  ["role-senior"] = "‡",
}

local ROLE_ORDER = { "role-co-first", "role-corresponding", "role-senior" }

local function to_set(items)
  local set = {}
  for _, item in ipairs(items) do
    if item ~= "" then
      set[item] = true
    end
  end
  return set
end

local function has_class(element, class_name)
  for _, class in ipairs(element.attr.classes) do
    if class == class_name then
      return true
    end
  end
  return false
end

function Span(span)
  if not has_class(span, "author") then
    return nil
  end

  local class_set = to_set(span.attr.classes)
  local markers = {}
  for _, role in ipairs(ROLE_ORDER) do
    if class_set[role] then
      table.insert(markers, ROLE_MARKERS[role])
    end
  end

  if #markers == 0 then
    return nil
  end

  local marker_text = table.concat(markers, "")
  local content = span.content
  table.insert(content, pandoc.Str(marker_text))
  span.content = content
  return span
end
