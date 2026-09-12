-- Pandoc 2 uses tagged metadata; Pandoc 3 exposes Lists and plain maps.
-- Keep the compatibility boundary shared by every metadata-consuming filter.
local metadata = {}

function metadata.is_list(value)
  if type(value) ~= 'table' then return false end
  if value.t == 'MetaList' then return true end
  return pandoc.utils.type ~= nil and pandoc.utils.type(value) == 'List'
end

function metadata.is_map(value)
  if type(value) ~= 'table' then return false end
  if value.t == 'MetaMap' then return true end
  return pandoc.utils.type ~= nil and pandoc.utils.type(value) == 'table'
end

return metadata
