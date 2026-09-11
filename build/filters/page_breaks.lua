-- Theme-selected heading IDs start new print pages without source blank lines.
function Pandoc(doc)
  local selected = doc.meta['cvw-page-break-before']
  if not selected then return nil end
  if selected.t ~= 'MetaList' then error('cvw-page-break-before must be a list') end
  local targets, seen = {}, {}
  for _, value in ipairs(selected) do
    local id = pandoc.utils.stringify(value)
    if id == '' or targets[id] then error('cvw-page-break-before has an empty or duplicate ID: ' .. id) end
    targets[id] = true
  end
  local result = pandoc.walk_block(pandoc.Div(doc.blocks), {
    Header=function(header)
      if not targets[header.identifier] then return nil end
      if seen[header.identifier] then error('cvw-page-break-before target is ambiguous: ' .. header.identifier) end
      seen[header.identifier] = true
      if FORMAT:match('latex') then
        return {pandoc.RawBlock('latex', '\\newpage'), header}
      elseif FORMAT == 'docx' then
        return {pandoc.RawBlock('openxml', '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'), header}
      elseif FORMAT:match('html') then
        header.attributes.style = (header.attributes.style and header.attributes.style .. '; ' or '')
          .. 'break-before: page'
        return header
      end
    end,
  })
  for id, _ in pairs(targets) do
    if not seen[id] then error('cvw-page-break-before target does not exist: ' .. id) end
  end
  return pandoc.Pandoc(result.content, doc.meta)
end
