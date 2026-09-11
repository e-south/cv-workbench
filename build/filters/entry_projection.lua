-- Explicit presentation references. Canonical records and selection stay upstream.
local function fail(message) error('cvw-entry-layout: ' .. message) end
local function append(target, content)
  for _, inline in ipairs(content) do table.insert(target, inline) end
end
local function separator(content, punctuation)
  if #content > 0 then
    -- Avoid a sentence period immediately followed by a semicolon.
    local last = content[#content]
    if last.t == 'Span' then last = last.content[#last.content] end
    if last and last.t == 'Str' and last.text:sub(-1) == '.' then
      table.insert(content, pandoc.Space())
      return
    end
    table.insert(content, pandoc.Str(punctuation))
    table.insert(content, pandoc.Space())
  end
end
local allowed_fields = {heading=true, role=true, issuer=true, location=true, detail=true,
                        date=true, summary=true}

local function record_span(div, fields)
  if not (div.identifier:match('^service%-') or div.identifier:match('^honor%-')
      or div.identifier:match('^conference%-')) then
    fail('only simple service, honor and conference records can be compacted: ' .. div.identifier)
  end
  local blocks = div.content
  if #blocks < 1 or blocks[1].t ~= 'Header' or blocks[1].level ~= 3 then
    fail('expected a simple source heading: ' .. div.identifier)
  end
  local values = {heading={pandoc.Span(blocks[1].content, blocks[1].attr)}}
  local default_fields = {'heading'}
  for index = 2, #blocks do
    local block = blocks[index]
    if block.t ~= 'Para' then fail('unsupported record body: ' .. div.identifier) end
    if index == 2 then
      for _, inline in ipairs(block.content) do
        local field
        if inline.t == 'Span' then
          for name, _ in pairs(allowed_fields) do
            if inline.classes:includes('entry-' .. name) then field = name end
          end
        end
        if field then
          if values[field] then fail('duplicate field: ' .. div.identifier .. '/' .. field) end
          values[field] = {inline}
          table.insert(default_fields, field)
        elseif inline.t ~= 'Space' and not (inline.t == 'Str' and inline.text == '|') then
          fail('unsupported metadata: ' .. div.identifier)
        end
      end
    else
      if values.summary then fail('multiple summary paragraphs: ' .. div.identifier) end
      values.summary = block.content
      table.insert(default_fields, 'summary')
    end
  end
  local content = {}
  for _, field in ipairs(fields or default_fields) do
    local value = values[field]
    if not value and field ~= 'date' then fail('missing requested field: ' .. div.identifier .. '/' .. field) end
    if not value then
      -- Unknown dates remain absent; a group must never lend another record its date.
    elseif field == 'date' then
      for _, inline in ipairs(value) do
        if inline.t == 'Span' then inline.classes:insert('keep-together') end
      end
      if #content > 0 then table.insert(content, pandoc.Space()) end
      table.insert(content, pandoc.Str('('))
      append(content, value)
      table.insert(content, pandoc.Str(')'))
    else
      separator(content, field == 'summary' and ':' or ',')
      append(content, value)
    end
  end
  return pandoc.Span(content, div.attr)
end

local function attach(target, content)
  -- Preserve the semantic role/degree span expected by presentation.lua.
  for _, block in ipairs(target.content) do
    if block.t == 'Header' or block.t == 'Para' then
      for _, inline in ipairs(block.content) do
        if inline.t == 'Span' and (
            (target.identifier:match('^role%-') and block.t == 'Header'
              and inline.classes:includes('entry-role'))
            or (target.identifier:match('^education%-') and inline.classes:includes('entry-detail'))) then
          separator(inline.content, ';')
          append(inline.content, content)
          return
        end
      end
    end
  end
  fail('details target must have a semantic role or degree: ' .. target.identifier)
end

local function shared_citation(sources)
  if #sources < 2 then fail('shared_citation requires at least two manuscripts') end
  local citation, items = nil, {}
  for _, source in ipairs(sources) do
    local blocks = source.content
    if not source.identifier:match('^publication%-')
        or not source.classes:includes('publication-in-preparation')
        or not source.classes:includes('publication-citation-complete')
        or #blocks ~= 2 or blocks[1].t ~= 'Header' or blocks[1].level ~= 3
        or blocks[2].t ~= 'Para' or #blocks[2].content == 0 then
      fail('shared_citation requires simple in-preparation citations: ' .. source.identifier)
    end
    if citation and not pandoc.utils.equals(citation, blocks[2]) then
      fail('shared citations differ: ' .. source.identifier)
    end
    citation = blocks[2]
    table.insert(items, {pandoc.Plain({pandoc.Span({pandoc.Span(blocks[1].content,
      blocks[1].attr)}, source.attr)})})
  end
  citation = pandoc.walk_block(citation, {Str=function(str)
    if str.text == 'Manuscript' then return pandoc.Str('Manuscripts') end
  end})
  return pandoc.Div({citation, pandoc.BulletList(items)}, pandoc.Attr('', {'entry-group'}))
end

function Pandoc(doc)
  local rules = doc.meta['cvw-entry-layout']
  if not rules then return nil end
  if rules.t ~= 'MetaList' then fail('must be a list') end
  local records, sections, consumed, targets, owners, current_section = {}, {}, {}, {}, {}, nil
  for _, block in ipairs(doc.blocks) do
    if block.t == 'Div' and block.identifier ~= '' then
      if records[block.identifier] or sections[block.identifier] then fail('duplicate ID: ' .. block.identifier) end
      records[block.identifier] = block
      owners[block.identifier] = current_section
    elseif block.t == 'Header' and block.level == 2 then
      if sections[block.identifier] or records[block.identifier] then fail('duplicate ID: ' .. block.identifier) end
      sections[block.identifier] = block
      current_section = block.identifier
    end
  end
  local parsed = {}
  for _, rule in ipairs(rules) do
    if rule.t ~= 'MetaMap' then fail('each rule must be a mapping') end
    for key, _ in pairs(rule) do
      if key ~= 'sources' and key ~= 'target' and key ~= 'placement' and key ~= 'label' and key ~= 'fields' then
        fail('unknown rule key: ' .. key)
      end
    end
    if not rule.sources or rule.sources.t ~= 'MetaList' or #rule.sources == 0 then
      fail('sources must be a nonempty list')
    end
    local target = pandoc.utils.stringify(rule.target or '')
    local placement = pandoc.utils.stringify(rule.placement or '')
    if placement == 'details' then
      if not records[target] then fail('missing target record: ' .. target) end
    elseif placement == 'section' or placement == 'shared_citation' then
      if not sections[target] then fail('missing target section: ' .. target) end
    else fail('unknown placement: ' .. placement) end
    targets[target] = true
    local sources = {}
    for _, value in ipairs(rule.sources) do
      local id = pandoc.utils.stringify(value)
      if not records[id] then fail('missing source record: ' .. id) end
      if consumed[id] then fail('source used more than once: ' .. id) end
      consumed[id] = true
      table.insert(sources, records[id])
      if placement == 'shared_citation' and owners[id] ~= target then
        fail('shared citation must stay in its source section: ' .. id)
      end
    end
    local label = rule.label and pandoc.utils.stringify(rule.label) or nil
    if label and (placement ~= 'section' or label == '' or label:find('[\r\n]')) then
      fail('labels require a section and nonempty single-line text')
    end
    local fields
    if placement == 'shared_citation' and (rule.fields or rule.label) then
      fail('shared_citation cannot omit fields or override its citation label')
    end
    if rule.fields then
      if rule.fields.t ~= 'MetaList' or #rule.fields == 0 then fail('fields must be a nonempty list') end
      fields = {}
      local seen = {}
      for _, item in ipairs(rule.fields) do
        local field = pandoc.utils.stringify(item)
        if not allowed_fields[field] or seen[field] then fail('invalid or duplicate field: ' .. field) end
        seen[field] = true
        table.insert(fields, field)
      end
    end
    table.insert(parsed, {sources=sources, target=target, placement=placement, label=label, fields=fields})
  end
  for id, _ in pairs(consumed) do
    if targets[id] then fail('target is also consumed: ' .. id) end
  end
  local groups, replacements = {}, {}
  for _, rule in ipairs(parsed) do
    if rule.placement == 'shared_citation' then
      replacements[rule.sources[1].identifier] = shared_citation(rule.sources)
    else
      local content = {}
      if rule.label then
        append(content, {pandoc.Strong({pandoc.Str(rule.label)}), pandoc.Str(':'), pandoc.Space()})
      end
      for index, source in ipairs(rule.sources) do
        if index > 1 then separator(content, ';') end
        table.insert(content, record_span(source, rule.fields))
      end
      if rule.placement == 'details' then attach(records[rule.target], content)
      else
        groups[rule.target] = groups[rule.target] or {}
        local group = pandoc.Div({pandoc.BulletList({{pandoc.Para(content)}})},
          pandoc.Attr('', {'entry-group'}))
        if owners[rule.sources[1].identifier] == rule.target then
          replacements[rule.sources[1].identifier] = group
        else table.insert(groups[rule.target], group) end
      end
    end
  end
  local result, current, body = {}, nil, {}
  local function flush()
    if current then
      for _, group in ipairs(groups[current.identifier] or {}) do table.insert(body, group) end
      if #body > 0 then table.insert(result, current) end
    end
    for _, block in ipairs(body) do table.insert(result, block) end
    body = {}
  end
  for _, block in ipairs(doc.blocks) do
    if block.t == 'Header' and block.level == 2 then
      flush()
      current = block
    elseif block.t == 'Div' and replacements[block.identifier] then
      table.insert(body, replacements[block.identifier])
    elseif not (block.t == 'Div' and consumed[block.identifier]) then table.insert(body, block) end
  end
  flush()
  return pandoc.Pandoc(result, doc.meta)
end
