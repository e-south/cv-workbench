-- Inline repeated offerings only when each has one evidence paragraph.
function Pandoc(doc)
  if doc.meta['cvw-inline-teaching'] ~= true then return nil end
  local result = pandoc.walk_block(pandoc.Div(doc.blocks), {Div=function(div)
    if not div.classes:includes('teaching-course') or #div.content < 4 then return nil end
    if div.content[1].t ~= 'Header' or div.content[2].t ~= 'Para' then return nil end
    local terms = {}
    for index = 3, #div.content do
      local term = div.content[index]
      if term.t ~= 'Div' or not term.identifier:match('^teaching%-')
          or #term.content ~= 1 or term.content[1].t ~= 'Para' then return nil end
      if #terms > 0 then
        table.insert(terms, pandoc.Str(';'))
        table.insert(terms, pandoc.Space())
      end
      local evidence = pandoc.walk_inline(pandoc.Span(term.content[1].content, term.attr), {
        Span=function(span)
          if not span.classes:includes('entry-date') then return nil end
          local dated = {pandoc.Str('(')}
          for _, inline in ipairs(span.content) do table.insert(dated, inline) end
          table.insert(dated, pandoc.Str(')'))
          span.content = dated
          return span
        end
      })
      table.insert(terms, evidence)
    end
    div.content = {div.content[1], div.content[2], pandoc.Para(terms)}
    div.classes:insert('teaching-inline')
    return div
  end})
  return pandoc.Pandoc(result.content, doc.meta)
end
