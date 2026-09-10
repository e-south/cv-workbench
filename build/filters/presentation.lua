-- Optional presentation only: keep source IDs, links and all selected wording.
-- Themes opt in with metadata.cvw-compact-entries: true.
local function compact_entry(div)
  if not (div.classes:includes('section') or div.classes:includes('role')) then
    return nil
  end
  local blocks = div.content
  if #blocks < 2 or blocks[1].t ~= 'Header' or blocks[1].level ~= 3
      or blocks[2].t ~= 'Para' then return nil end
  local heading = pandoc.Span({pandoc.Strong(blocks[1].content)}, blocks[1].attr)
  local text = {heading, pandoc.Space(),
                pandoc.Str('—'), pandoc.Space()}
  for _, inline in ipairs(blocks[2].content) do table.insert(text, inline) end
  local result = {pandoc.Para(text)}
  for index = 3, #blocks do
    local block = blocks[index]
    local education_highlight = div.identifier:match('^education%-')
      and block.t == 'BulletList'
    if education_highlight then
      for _, item in ipairs(block.content) do
        if #item ~= 1 or (item[1].t ~= 'Para' and item[1].t ~= 'Plain') then
          education_highlight = false
        end
      end
    end
    if education_highlight then
      for _, item in ipairs(block.content) do
        table.insert(result[1].content, pandoc.Str(';'))
        table.insert(result[1].content, pandoc.Space())
        for _, inline in ipairs(item[1].content) do table.insert(result[1].content, inline) end
      end
    else
      table.insert(result, block)
    end
  end
  div.content = result
  return div
end

local function contact_rows(blocks)
  if #blocks < 2 or blocks[1].t ~= 'Header' or blocks[1].level ~= 1
      or blocks[2].t ~= 'Para' then return end
  local inlines, count, split = blocks[2].content, 0, nil
  for i, inline in ipairs(inlines) do
    if inline.t == 'Link' then
      count = count + 1
      if count == 2 then split = i end
    end
  end
  if count < 3 then return end
  local first, second = {}, {}
  for i = 1, split do table.insert(first, inlines[i]) end
  local rest = split + 1
  while rest <= #inlines and (inlines[rest].t == 'Space'
      or (inlines[rest].t == 'Str' and inlines[rest].text == '|')) do
    rest = rest + 1
  end
  for i = rest, #inlines do table.insert(second, inlines[i]) end
  local rows = {pandoc.Para(first), pandoc.Para(second)}
  if FORMAT:match('latex') then
    table.insert(rows, 1, pandoc.RawBlock('latex', '\\begingroup\\centering'))
    table.insert(rows, pandoc.RawBlock('latex', '\\par\\endgroup'))
  end
  blocks[2] = pandoc.Div(rows, pandoc.Attr('', {'contact-block'}, {['custom-style']='Contact'}))
end

function Pandoc(doc)
  if doc.meta['cvw-compact-entries'] == true then
    local transformed = pandoc.walk_block(pandoc.Div(doc.blocks), {
      Div = compact_entry,
      Span = function(span)
        if span.classes:includes('author') and span.classes:includes('role-self') then
          span.content = {pandoc.Strong(span.content)}
          return span
        end
      end,
    })
    doc = pandoc.Pandoc(transformed.content, doc.meta)
  end
  if doc.meta['cvw-contact-rows'] == true then contact_rows(doc.blocks) end
  return doc
end
