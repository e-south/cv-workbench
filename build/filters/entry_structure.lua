-- Optional record hierarchy. Source selection and wording remain upstream.
local kinds = {
  education='education', role='experience', publication='publications',
  teaching='teaching', service='service', conference='conferences', honor='honors',
  project='projects',
}

local function entry_kind(div)
  if div.classes:includes('teaching-course') then return 'teaching' end
  return kinds[div.identifier:match('^([a-z]+)%-')]
end

local function entry_details(blocks)
  if FORMAT:match('latex') then
    table.insert(blocks, 1, pandoc.RawBlock('latex',
      '\\begingroup\\ifdefined\\cvwentrydetails\\cvwentrydetails\\fi'))
    table.insert(blocks, pandoc.RawBlock('latex', '\\par\\endgroup'))
  end
  return pandoc.Div(blocks,
    pandoc.Attr('', {'entry-details'}, {['custom-style']='Entry Details'}))
end

local function structure_entry(div, bulleted)
  local kind = entry_kind(div)
  if not kind then return nil end
  local blocks = div.content
  if #blocks == 0 then return nil end
  local first = blocks[1]
  local heading = first.t == 'Div' and first.classes:includes('entry-heading')
  if first.t == 'Header' and first.level == 3 then
    blocks[1] = pandoc.Div({pandoc.Para({pandoc.Span({pandoc.Strong(first.content)}, first.attr)})},
      pandoc.Attr('', {'entry-heading'}, {['custom-style']='Entry Heading'}))
    heading = true
  end
  local grouped_term = kind == 'teaching' and not heading
  if not heading and not grouped_term then return nil end
  local result = grouped_term and blocks or {blocks[1]}
  if heading and #blocks > 1 then
    local body = {}
    for index = 2, #blocks do table.insert(body, blocks[index]) end
    table.insert(result, entry_details(body))
  end
  if bulleted[kind] and not div.classes:includes('teaching-course') then
    result = {pandoc.BulletList({result})}
    div.classes:insert('entry-bulleted')
  end
  if FORMAT:match('latex') and not grouped_term then
    table.insert(result, 1, pandoc.RawBlock('latex', '\\ifdefined\\cvwentryspace\\cvwentryspace\\fi'))
  end
  div.classes:insert('cv-entry')
  div.classes:insert('entry-kind-' .. kind)
  div.content = result
  return div
end

local function keep_together(span)
  if not span.classes:includes('keep-together') then return nil end
  if FORMAT:match('latex') then
    span.content:insert(1, pandoc.RawInline('latex', '\\mbox{'))
    span.content:insert(pandoc.RawInline('latex', '}'))
  elseif FORMAT == 'docx' then
    -- Use Word's native nonbreaking hyphen, avoiding font-specific Unicode glyphs.
    span = pandoc.walk_inline(span, {
      Space=function() return pandoc.Str('\u{00a0}') end,
      Str=function(str)
        local result, start = {}, 1
        while true do
          local index = str.text:find('-', start, true)
          if not index then
            table.insert(result, pandoc.Str(str.text:sub(start)))
            return result
          end
          table.insert(result, pandoc.Str(str.text:sub(start, index - 1)))
          table.insert(result, pandoc.RawInline('openxml', '<w:r><w:noBreakHyphen/></w:r>'))
          start = index + 1
        end
      end,
    })
  elseif FORMAT:match('html') then
    span.attributes.style = (span.attributes.style and span.attributes.style .. '; ' or '')
      .. 'white-space: nowrap'
  end
  return span
end

function Pandoc(doc)
  if doc.meta['cvw-entry-structure'] ~= true then return nil end
  local selected = doc.meta['cvw-bulleted-entries']
  if selected and selected.t ~= 'MetaList' then error('cvw-bulleted-entries must be a list') end
  local allowed, bulleted = {}, {}
  for _, kind in pairs(kinds) do allowed[kind] = true end
  for _, value in ipairs(selected or {}) do
    local kind = pandoc.utils.stringify(value)
    if not allowed[kind] then error('Unknown cvw-bulleted-entries kind: ' .. kind) end
    bulleted[kind] = true
  end
  local transformed = pandoc.walk_block(pandoc.Div(doc.blocks), {
    Span=keep_together,
    Div=function(div) return structure_entry(div, bulleted) end,
  })
  return pandoc.Pandoc(transformed.content, doc.meta)
end
