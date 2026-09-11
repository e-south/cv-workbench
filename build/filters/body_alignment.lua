-- Opt-in prose-list alignment. Headings and dates are outside this boundary.
local function justify(div, style)
  if FORMAT == 'docx' then
    -- Tight lists otherwise force Word's Compact style.
    div = pandoc.walk_block(div, {Plain=function(p) return pandoc.Para(p.content) end})
  end
  div.classes:insert('body-justified')
  div.attributes['custom-style'] = style
  if FORMAT:match('latex') then
    div.content:insert(1, pandoc.RawBlock('latex',
      '\\begingroup\\ifdefined\\cvwjustifiedlist\\cvwjustifiedlist\\fi'))
    div.content:insert(pandoc.RawBlock('latex', '\\par\\endgroup'))
  end
  return div
end

function Pandoc(doc)
  local settings = doc.meta['cvw-justify-lists']
  if not settings then return nil end
  if settings.t ~= 'MetaList' then error('cvw-justify-lists must be a list') end
  local selected = {}
  for _, value in ipairs(settings) do
    local key = pandoc.utils.stringify(value)
    if key ~= 'skills' and key ~= 'experience' then
      error('Unsupported cvw-justify-lists section: ' .. key)
    end
    selected[key] = true
  end
  local result = pandoc.walk_block(pandoc.Div(doc.blocks), {Div=function(div)
    if selected.skills and div.classes:includes('skills-list') then
      return justify(div, 'Justified List')
    end
    if selected.experience and div.classes:includes('entry-kind-experience') then
      return pandoc.walk_block(div, {Div=function(body)
        if body.classes:includes('entry-items') then
          return justify(body, 'Justified Entry Bullet')
        end
      end})
    end
  end})
  return pandoc.Pandoc(result.content, doc.meta)
end
