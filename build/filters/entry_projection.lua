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

local function conference_series(div)
  if not div.identifier:match('^conference%-') then
    fail('series grouping requires conference records: ' .. div.identifier)
  end
  local series, topic
  local heading = div.content[1]
  if not heading or heading.t ~= 'Header' then fail('missing conference heading') end
  for _, inline in ipairs(heading.content) do
    if inline.t == 'Span' then
      if inline.classes:includes('entry-series') then series = inline end
      if inline.classes:includes('entry-topic') then topic = inline end
    end
  end
  if (series ~= nil) ~= (topic ~= nil) then fail('incomplete conference series heading') end
  return series, topic
end

local function record_span(div, fields, labelled, right_date, topic_only)
  if not (div.identifier:match('^service%-') or div.identifier:match('^honor%-')
      or div.identifier:match('^conference%-')) then
    fail('only simple service, honor and conference records can be compacted: ' .. div.identifier)
  end
  local blocks = div.content
  if #blocks < 1 or blocks[1].t ~= 'Header' or blocks[1].level ~= 3 then
    fail('expected a simple source heading: ' .. div.identifier)
  end
  local values = {heading={pandoc.Span(blocks[1].content, blocks[1].attr)}}
  if topic_only then
    local _, topic = conference_series(div)
    values.heading = {topic}
  end
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
  -- Retain the entry's identifying field after its heading becomes inline.
  -- A group label already supplies this role; descriptive fields stay unmarked.
  if not labelled then
    local identity = values.role or values.heading
    identity[1].classes:insert('entry-label')
  end
  local content, date = {}, nil
  for _, field in ipairs(fields or default_fields) do
    local value = values[field]
    if not value and field ~= 'date' then fail('missing requested field: ' .. div.identifier .. '/' .. field) end
    if not value then
      -- Unknown dates remain absent; a group must never lend another record its date.
    elseif field == 'date' then
      for _, inline in ipairs(value) do
        if inline.t == 'Span' then inline.classes:insert('keep-together') end
      end
      if right_date then date = value[1]
      else
        -- Compact only displayed inline ranges; source dates and aligned headings
        -- retain their own representation.
        value[1].content = {pandoc.Str(pandoc.utils.stringify(value[1]):gsub('%s+—%s+', '–'))}
        if #content > 0 then table.insert(content, pandoc.Space()) end
        table.insert(content, pandoc.Str('('))
        append(content, value)
        table.insert(content, pandoc.Str(')'))
      end
    else
      separator(content, field == 'summary' and ':' or ',')
      append(content, value)
    end
  end
  if right_date and not date then fail('right-aligned date is missing: ' .. div.identifier) end
  return pandoc.Span(content, div.attr), date
end

local function joined_records(rule)
  local chunks, seen = {}, {}
  for _, source in ipairs(rule.sources) do
    local series = rule.group_series and conference_series(source) or nil
    local key = series and pandoc.utils.stringify(series) or nil
    local last = chunks[#chunks]
    if key and last and last.key == key then
      table.insert(last.sources, source)
    else
      if key and seen[key] then fail('conference series must be contiguous in source order') end
      if key then seen[key] = true end
      table.insert(chunks, {key=key, series=series, sources={source}})
    end
  end
  local content, date = {}, nil
  for _, chunk in ipairs(chunks) do
    separator(content, ';')
    if chunk.series then
      table.insert(content, chunk.series)
      table.insert(content, pandoc.Str('—'))
    end
    for index, source in ipairs(chunk.sources) do
      if index > 1 then
        if index == #chunk.sources then
          append(content, {pandoc.Space(), pandoc.Str('and'), pandoc.Space()})
        else separator(content, ',') end
      end
      local record
      record, date = record_span(source, rule.fields,
        rule.label ~= nil or rule.placement ~= 'section', rule.right_date, chunk.series ~= nil)
      table.insert(content, record)
    end
  end
  return content, date
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
    local title = pandoc.Span(blocks[1].content, blocks[1].attr)
    title.classes:insert('entry-label')
    table.insert(items, {pandoc.Plain({pandoc.Span({title}, source.attr)})})
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
      if key ~= 'sources' and key ~= 'target' and key ~= 'placement' and key ~= 'label'
          and key ~= 'fields' and key ~= 'date_position' and key ~= 'group_by' then
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
    local right_date = rule.date_position ~= nil
    if right_date and (pandoc.utils.stringify(rule.date_position) ~= 'right'
        or placement ~= 'section' or #sources ~= 1) then
      fail('right dates require one section record')
    end
    if right_date and fields then
      local found = false
      for _, field in ipairs(fields) do if field == 'date' then found = true end end
      if not found then fail('right date must be included in fields') end
    end
    local group_series = rule.group_by ~= nil
    if group_series and (pandoc.utils.stringify(rule.group_by) ~= 'series'
        or placement ~= 'section' or right_date) then
      fail('series grouping requires an inline section group')
    end
    if group_series and fields then
      local heading = false
      for _, field in ipairs(fields) do if field == 'heading' then heading = true end end
      if not heading then fail('series grouping must retain topic headings') end
    end
    table.insert(parsed, {sources=sources, target=target, placement=placement, label=label,
                         fields=fields, right_date=right_date, group_series=group_series})
  end
  for id, _ in pairs(consumed) do
    if targets[id] then fail('target is also consumed: ' .. id) end
  end
  local groups, replacements = {}, {}
  for _, rule in ipairs(parsed) do
    if rule.placement == 'shared_citation' then
      replacements[rule.sources[1].identifier] = shared_citation(rule.sources)
    else
      local content, date = {}, nil
      if rule.label then
        append(content, {pandoc.Strong({pandoc.Str(rule.label)}), pandoc.Str(':'), pandoc.Space()})
      end
      local records_content
      records_content, date = joined_records(rule)
      append(content, records_content)
      if rule.placement == 'details' then attach(records[rule.target], content)
      else
        groups[rule.target] = groups[rule.target] or {}
        local body = pandoc.Para(content)
        if date then
          body = pandoc.Div({pandoc.Para({
            pandoc.Span(content, pandoc.Attr('', {'entry-identity'})), date})},
            pandoc.Attr('', {'entry-projected-heading'}))
        end
        local group = pandoc.Div({pandoc.BulletList({{body}})},
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
