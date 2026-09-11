-- Optional presentation only: keep source IDs, links and all selected wording.
-- Themes opt in with metadata.cvw-compact-entries: true.
local function simple_list_items(block)
  if block.t ~= 'BulletList' then return nil end
  for _, item in ipairs(block.content) do
    if #item ~= 1 or (item[1].t ~= 'Para' and item[1].t ~= 'Plain') then return nil end
  end
  return block.content
end

local function aligned_entry(div, concise)
  if not (div.classes:includes('section') or div.classes:includes('role')
      or div.classes:includes('teaching-course')) then
    return nil
  end
  local blocks = div.content
  if #blocks < 2 or blocks[1].t ~= 'Header' or blocks[1].level ~= 3
      or blocks[2].t ~= 'Para' then return nil end
  local details, location, date, found = {}, nil, nil, false
  local position, issuer = nil, nil
  for _, inline in ipairs(blocks[2].content) do
    if inline.t == 'Span' and inline.classes:includes('entry-detail') then
      table.insert(details, inline)
      found = true
    elseif inline.t == 'Span' and inline.classes:includes('entry-role') then
      if position then return nil end
      position, found = inline, true
      if not concise then table.insert(details, inline) end
    elseif inline.t == 'Span' and inline.classes:includes('entry-issuer') then
      if issuer then return nil end
      issuer, found = inline, true
      if not concise then table.insert(details, inline) end
    elseif inline.t == 'Span' and inline.classes:includes('entry-location') then
      if location then return nil end
      location, found = inline, true
    elseif inline.t == 'Span' and inline.classes:includes('entry-date') then
      if date then return nil end
      date, found = inline, true
    elseif inline.t ~= 'Space' and not (inline.t == 'Str' and inline.text == '|') then
      -- Unknown content is not ours to restructure or discard.
      return nil
    end
  end
  if not found then return nil end
  local last_block = #blocks
  if concise and div.identifier:match('^education%-') and #details > 0 then
    local highlights = simple_list_items(blocks[last_block])
    if highlights then
      for _, item in ipairs(highlights) do
        table.insert(details[1].content, pandoc.Str(';'))
        table.insert(details[1].content, pandoc.Space())
        for _, inline in ipairs(item[1].content) do table.insert(details[1].content, inline) end
      end
      last_block = last_block - 1
    end
  end
  local heading_content = blocks[1].content
  local organization, role = nil, nil
  if div.classes:includes('role') then
    for _, inline in ipairs(heading_content) do
      if inline.t == 'Span' and inline.classes:includes('entry-organization') then
        if organization then return nil end
        organization = inline
      elseif inline.t == 'Span' and inline.classes:includes('entry-role') then
        if role then return nil end
        role = inline
      elseif inline.t ~= 'Space' and not (inline.t == 'Str' and inline.text == '-') then
        return nil
      end
    end
    if organization and role then
      heading_content = {organization}
      table.insert(details, 1, pandoc.Span({role}, pandoc.Attr('', {'entry-detail'})))
    end
  end
  local identity = {pandoc.Span({pandoc.Strong(heading_content)}, blocks[1].attr)}
  if concise and position then
    identity = {pandoc.Strong(position), pandoc.Str(','), pandoc.Space(),
                pandoc.Span(heading_content, blocks[1].attr)}
  end
  if concise and issuer then
    table.insert(identity, pandoc.Str(','))
    table.insert(identity, pandoc.Space())
    table.insert(identity, issuer)
  end
  if location then
    table.insert(identity, pandoc.Str(','))
    table.insert(identity, pandoc.Space())
    table.insert(identity, location)
  end
  local row = {pandoc.Span(identity, pandoc.Attr('', {'entry-identity'}))}
  if date then
    if FORMAT:match('latex') then
      table.insert(row, pandoc.RawInline('latex', '\\quad\\hfill\\mbox{'))
      table.insert(row, date)
      table.insert(row, pandoc.RawInline('latex', '}'))
    elseif FORMAT == 'docx' then
      table.insert(row, pandoc.RawInline('openxml', '<w:r><w:tab/></w:r>'))
      table.insert(row, date)
    else
      table.insert(row, pandoc.Space())
      table.insert(row, date)
    end
  end
  local heading = pandoc.Div({pandoc.Para(row)},
    pandoc.Attr('', {'entry-heading'}, {['custom-style']='Entry Heading'}))
  local result = {heading}
  if FORMAT:match('latex') then
    table.insert(result, 1, pandoc.RawBlock('latex', '\\ifdefined\\cvwentryspace\\cvwentryspace\\fi'))
    table.insert(result, pandoc.RawBlock('latex', '\\nopagebreak[4]'))
  end
  local detail_start = #result + 1
  if #details > 0 then
    local text = {}
    for _, detail in ipairs(details) do
      if #text > 0 then
        table.insert(text, pandoc.Space())
        table.insert(text, pandoc.Str('|'))
        table.insert(text, pandoc.Space())
      end
      table.insert(text, detail)
    end
    table.insert(result, pandoc.Para(text))
    if FORMAT:match('latex') then
      table.insert(result, pandoc.RawBlock('latex', '\\nopagebreak[4]'))
    end
  end
  for index = 3, last_block do table.insert(result, blocks[index]) end
  if concise and div.identifier:match('^education%-') and #result >= detail_start then
    local body = {}
    for index = detail_start, #result do table.insert(body, result[index]) end
    for index = #result, detail_start, -1 do table.remove(result, index) end
    if FORMAT:match('latex') then
      table.insert(body, 1, pandoc.RawBlock('latex',
        '\\begingroup\\ifdefined\\cvweducationdetails\\cvweducationdetails\\fi'))
      table.insert(body, pandoc.RawBlock('latex', '\\par\\endgroup'))
    end
    table.insert(result, pandoc.Div(body,
      pandoc.Attr('', {'education-details'}, {['custom-style']='Education Details'})))
  end
  div.content = result
  return div
end

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

local function concise_publication_note(div)
  if not div.identifier:match('^publication%-') then return nil end
  local blocks = div.content
  if #blocks < 3 then return nil end
  local note, metadata = blocks[#blocks], blocks[#blocks - 1]
  if note.t ~= 'Para' or metadata.t ~= 'Para' or #note.content ~= 1 then return nil end
  local span = note.content[1]
  if span.t ~= 'Span' or not span.classes:includes('entry-note') then return nil end
  local first = metadata.content[1]
  if first and first.t == 'Span' and first.classes:includes('entry-authors') then
    -- Keep author/contribution context together before the venue metadata.
    table.insert(metadata.content, 2, pandoc.Str(';'))
    table.insert(metadata.content, 3, pandoc.Space())
    table.insert(metadata.content, 4, span)
  else
    table.insert(metadata.content, pandoc.Str(';'))
    table.insert(metadata.content, pandoc.Space())
    table.insert(metadata.content, span)
  end
  blocks:remove(#blocks)
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
  if doc.meta['cvw-concise-entries'] == true then
    local transformed = pandoc.walk_block(pandoc.Div(doc.blocks), {Div = concise_publication_note})
    doc = pandoc.Pandoc(transformed.content, doc.meta)
  end
  if doc.meta['cvw-aligned-entries'] == true then
    local concise = doc.meta['cvw-concise-entries'] == true
    local transformed = pandoc.walk_block(pandoc.Div(doc.blocks), {
      Div = function(div) return aligned_entry(div, concise) end,
    })
    doc = pandoc.Pandoc(transformed.content, doc.meta)
  end
  if doc.meta['cvw-compact-entries'] == true then
    local transformed = pandoc.walk_block(pandoc.Div(doc.blocks), {
      Div = compact_entry,
    })
    doc = pandoc.Pandoc(transformed.content, doc.meta)
  end
  if doc.meta['cvw-compact-entries'] == true or doc.meta['cvw-aligned-entries'] == true then
    local transformed = pandoc.walk_block(pandoc.Div(doc.blocks), {
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
