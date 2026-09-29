const routes = [
  { path: '/' },
  { path: '/new' },
  { path: '/w/:id' },
];

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[ch]));
}

function cellsInRange(start, end) {
  const parse = (value) => {
    const match = /^([A-Z]+)(\d+)$/.exec(String(value || '').toUpperCase());
    if (!match) return null;
    const col = [...match[1]].reduce((total, ch) => total * 26 + ch.charCodeAt(0) - 64, 0) - 1;
    return { col, row: Number(match[2]) };
  };
  const a = parse(start);
  const b = parse(end || start);
  if (!a || !b) return [];
  const out = [];
  for (let row = Math.min(a.row, b.row); row <= Math.max(a.row, b.row); row += 1) {
    for (let col = Math.min(a.col, b.col); col <= Math.max(a.col, b.col); col += 1) {
      let name = '';
      let index = col + 1;
      while (index > 0) {
        const rem = (index - 1) % 26;
        name = String.fromCharCode(65 + rem) + name;
        index = Math.floor((index - 1) / 26);
      }
      out.push(`${name}${row}`);
    }
  }
  return out;
}

async function api(method, path, body) {
  const response = await fetch(path, {
    method,
    credentials: 'same-origin',
    headers: body ? { 'content-type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || 'Request failed');
    error.data = data;
    throw error;
  }
  return data;
}

function routeOf(pathname) {
  const parts = pathname.split('/').filter(Boolean).map(decodeURIComponent);
  if (!parts.length) return { page: 'home' };
  if (parts[0] === 'new') return { page: 'new' };
  if (parts[0] === 'w' && parts[1]) return { page: 'editor', id: parts[1] };
  return { page: 'missing' };
}

function shell() {
  return `<header class="app-header"><a href="/">Workbooks</a></header><div id="page">`;
}

function homeHtml(payload, message) {
  const items = (payload.workbooks || []).map((book) => {
    const href = '/w/' + encodeURIComponent(book.id);
    return `<li><a href="${href}">${esc(book.name)}</a><p>Last updated: ${esc(book.updated)}</p></li>`;
  }).join('');
  const error = message ? `<p class="error">${esc(message)}</p>` : '';
  return `<h1>Workbooks</h1>${error}<p><button type="button" id="new-blank">New blank workbook</button></p><button type="button" id="open-import">Import CSV</button><div class="dialog-layer" id="import-layer" hidden><div role="dialog" aria-label="Import CSV"><label>CSV file <input id="csv-file" type="file" accept=".csv,text/csv"></label><button type="button" id="confirm-import">Confirm import</button><button type="button" id="cancel-import">Cancel</button></div></div><ul>${items}</ul>`;
}

function createHtml() {
  return `<h1>New blank workbook</h1><form id="create-form"><button type="submit">Create</button></form>`;
}

function editorHtml(book, message) {
  const selected = book.selection || 'A1';
  const anchor = book.selectionAnchor || selected;
  const focus = book.selectionFocus || selected;
  const selectedSet = new Set(cellsInRange(anchor, focus));
  const selectedCell = book.grid.flatMap((row) => row.cells).find((cell) => cell.addr === selected) || { raw: '', value: '' };
  const tabs = book.sheets.map((name) => `<button type="button" role="tab" data-sheet="${esc(name)}" aria-selected="${name === book.active ? 'true' : 'false'}">${esc(name)}</button><button type="button" class="sheet-options" data-options="${esc(name)}" aria-expanded="false">Worksheet options for ${esc(name)}</button>`).join('');
  const headers = book.columns.map((name) => `<div role="columnheader" aria-label="${esc(name)}">${esc(name)}<button type="button" data-col="${esc(name)}">Column ${esc(name)}</button></div>`).join('');
  const headerCells = ((book.grid[0] && book.grid[0].cells) || []).filter((cell) => cell.value);
  const headerValues = headerCells.map((cell) => cell.value);
  const sortOptions = headerCells.map((cell) => `<option data-col="${esc(cell.addr.replace(/\d+$/, ''))}">${esc(cell.value)}</option>`).join('') || '<option data-col="A">A</option>';
  const rule = book.validation || null;
  const dropdownCells = rule && rule.type === 'Dropdown' ? cellsInRange(rule.start || rule.cell || selected, rule.end || rule.start || rule.cell || selected) : [];
  const dropdownButton = dropdownCells.map((addr) => `<button type="button" class="open-dropdown" data-cell="${esc(addr)}">Open dropdown for ${esc(addr)}</button>`).join('');
  const dropdownList = dropdownCells.length
    ? `<div id="dropdown-list" role="listbox" hidden>${String(rule.values || '').split(',').map((item) => item.trim()).filter(Boolean).map((item) => `<button type="button" role="option">${esc(item)}</button>`).join('')}</div>`
    : '';
  const pivotNames = book.pivotHeaders || [];
  const pivotOption = (selectedName, allowBlank) => `${allowBlank ? '<option value=""></option>' : ''}${pivotNames.map((name) => `<option${name === selectedName ? ' selected' : ''}>${esc(name)}</option>`).join('')}`;
  const pivotEditor = book.pivot
    ? `<div id="pivot-editor" role="region" aria-label="Pivot table editor"><label>Rows <select id="pivot-rows">${pivotOption(book.pivot.rows, false)}</select></label><label>Columns <select id="pivot-columns">${pivotOption(book.pivot.columns, true)}</select></label><label>Values <select id="pivot-values">${pivotOption(book.pivot.values, false)}</select></label><label>Summarize by <select id="pivot-summarize"><option${book.pivot.summarize === 'SUM' ? ' selected' : ''}>SUM</option><option${book.pivot.summarize === 'COUNT' ? ' selected' : ''}>COUNT</option><option${book.pivot.summarize === 'AVERAGE' ? ' selected' : ''}>AVERAGE</option></select></label><button type="button" id="apply-pivot">Apply</button></div>`
    : '';
  const filterButtons = headerValues.map((name) => `<button type="button" class="filter-header" data-header="${esc(name)}">Filter ${esc(name)}</button>`).join('');
  const rows = book.grid.map((row) => {
      const cells = row.cells.map((cell) => `<div role="gridcell" data-cell="${esc(cell.addr)}" data-raw="${esc(cell.raw)}" aria-label="${esc(cell.addr)}" aria-selected="${selectedSet.has(cell.addr) ? 'true' : 'false'}" data-active="${cell.addr === focus ? 'true' : 'false'}" tabindex="0">${esc(cell.value)}</div>`).join('');
    return `<div role="row"${row.hidden ? ' hidden' : ''}><div role="rowheader" aria-label="${row.row}">${row.row}<button type="button" data-row="${row.row}">Row ${row.row}</button></div>${cells}</div>`;
  }).join('');
  const error = message ? `<p class="error">${esc(message)}</p>` : '';
  return `<h1>${esc(book.name)}</h1><p>Last updated: ${esc(book.updated)}</p>${error}<button type="button" id="rename-open">Rename workbook</button><form id="rename-form" hidden><label>Workbook name <input name="name" type="text" value="${esc(book.name)}"></label><button type="submit">Save</button></form><button type="button" id="export-csv">Export CSV</button><button type="button" id="undo"${book.canUndo ? '' : ' disabled'}>Undo</button><button type="button" id="redo"${book.canRedo ? '' : ' disabled'}>Redo</button><button type="button" id="add-sheet">Add worksheet</button><div class="menu" id="sheet-options-menu" role="menu" hidden><button type="button" role="menuitem" id="rename-sheet-open">Rename</button><button type="button" role="menuitem" id="delete-sheet-open">Delete</button></div><div role="tablist">${tabs}</div><label>Formula bar <input id="formula-bar" type="text" value="${esc(selectedCell.raw)}"></label>${dropdownButton}<label>Edit ${esc(selected)} <input id="cell-editor" type="text" value="${esc(selectedCell.raw)}"></label><button type="button" id="insert-above">Insert 1 row above</button><button type="button" id="insert-below">Insert 1 row below</button><button type="button" id="delete-row">Delete row</button><button type="button" id="insert-left">Insert 1 column left</button><button type="button" id="insert-right">Insert 1 column right</button><button type="button" id="delete-column">Delete column</button><div class="menu" id="row-menu" role="menu" hidden><button type="button" role="menuitem" id="menu-insert-above">Insert 1 row above</button><button type="button" role="menuitem" id="menu-insert-below">Insert 1 row below</button><button type="button" role="menuitem" id="menu-delete-row">Delete row</button></div><div class="menu" id="column-menu" role="menu" hidden><button type="button" role="menuitem" id="menu-insert-left">Insert 1 column left</button><button type="button" role="menuitem" id="menu-insert-right">Insert 1 column right</button><button type="button" role="menuitem" id="menu-delete-column">Delete column</button></div><div class="menu" id="grid-menu" role="menu" hidden><button type="button" role="menuitem" id="menu-paste">Paste</button></div><button type="button" id="data-menu" aria-expanded="false">Data</button><div class="menu" id="data-menu-list" role="menu" hidden><button type="button" role="menuitem" id="sort-open">Sort range</button><button type="button" role="menuitem" id="filter-open">Create filter</button><button type="button" role="menuitem" id="validation-open">Data validation</button><button type="button" role="menuitem" id="pivot-open">Create pivot table</button></div>${filterButtons}<button type="button" id="refresh-pivot">Refresh pivot table</button><button type="button" id="copy-range">Copy</button><button type="button" id="cut-range">Cut</button><button type="button" id="paste-range">Paste</button><div class="grid" role="grid" aria-multiselectable="true" aria-label="Worksheet grid"><div role="row">${headers}</div>${rows}</div><div class="dialog-layer" id="rename-sheet-layer" hidden><div role="dialog" aria-label="Rename worksheet"><label>Worksheet name <input id="sheet-name" type="text" value="${esc(book.active)}"></label><button type="button" id="save-sheet-name">Save</button></div></div><div class="dialog-layer" id="delete-sheet-layer" hidden><div role="dialog" aria-label="Delete worksheet"><p>${esc(book.active)}</p><button type="button" id="confirm-delete-sheet">Delete worksheet</button></div></div><div class="dialog-layer" id="sort-layer" hidden><div role="dialog" aria-label="Sort range"><label>Sort by <select id="sort-by">${sortOptions}</select></label><label>Order <select id="sort-order"><option>Ascending</option><option>Descending</option></select></label><label><input id="sort-header" type="checkbox"> Data has header row</label><button type="button" id="apply-sort">Sort</button></div></div><div class="dialog-layer" id="filter-layer" hidden><div role="dialog" aria-label="Filter"><button type="button" id="clear-filter">Clear filter</button><button type="button" id="clear-selection">Clear selection</button><div id="filter-values"></div><label>Condition <select id="filter-condition"><option>Text contains</option><option>Greater than</option><option>Before</option><option>Is empty</option><option>Is not empty</option></select></label><label>Value <input id="filter-value" type="text" value=""></label><button type="button" id="apply-filter">Apply</button></div></div><div class="dialog-layer" id="validation-layer" hidden><div role="dialog" aria-label="Data validation"><label>Rule type <select id="rule-type"><option${rule && rule.type === 'Dropdown' ? ' selected' : ''}>Dropdown</option><option${rule && rule.type === 'Number range' ? ' selected' : ''}>Number range</option></select></label><label>Allowed values <input id="allowed-values" type="text" value="${esc(rule && rule.values || '')}"></label><label>Minimum <input id="minimum" type="text" value="${esc(rule && rule.minimum != null ? rule.minimum : '0')}"></label><label>Maximum <input id="maximum" type="text" value="${esc(rule && rule.maximum != null ? rule.maximum : '100')}"></label><button type="button" id="save-validation">Save</button><button type="button" id="delete-rule">Delete rule</button></div></div><div class="dialog-layer" id="pivot-layer" hidden><div role="dialog" aria-label="Create pivot table"><p>Source range: ${esc(book.sourceRange || "A1")}</p><label><input type="radio" name="pivot-place" checked> New worksheet</label><button type="button" id="create-pivot">Create</button></div></div>${pivotEditor}${dropdownList}`;
}

async function pageHtml(route) {
  if (route.page === 'new') return createHtml();
  if (route.page === 'editor') {
    try {
      return editorHtml(await api('GET', '/api/workbooks/' + encodeURIComponent(route.id)));
    } catch (error) {
      return `<h1>Not found</h1><p class="error">${esc(error.message)}</p>`;
    }
  }
  return homeHtml(await api('GET', '/api/workbooks'));
}

function bind(route) {
  const show = (id) => {
    const layer = document.querySelector(id);
    if (layer) layer.hidden = false;
  };
  const importOpen = document.querySelector('#open-import');
  if (importOpen) importOpen.addEventListener('click', () => show('#import-layer'));
  const newBlank = document.querySelector('#new-blank');
  if (newBlank) newBlank.addEventListener('click', () => { location.assign('/new'); });
  const cancelImport = document.querySelector('#cancel-import');
  if (cancelImport) cancelImport.addEventListener('click', () => { document.querySelector('#import-layer').hidden = true; });
  const confirmImport = document.querySelector('#confirm-import');
  if (confirmImport) {
    confirmImport.addEventListener('click', async () => {
      const file = document.querySelector('#csv-file').files[0];
      const csv = file ? await file.text() : '';
      try {
        const result = await api('POST', '/api/workbooks/import', { csv, name: file ? file.name.replace(/\.csv$/i, '') : 'Imported workbook' });
        location.assign('/w/' + encodeURIComponent(result.id));
      } catch (error) {
        document.querySelector('#page').insertAdjacentHTML('afterbegin', `<p class="error">${esc(error.message)}</p>`);
      }
    });
  }
  const create = document.querySelector('#create-form');
  if (create) {
    create.addEventListener('submit', async (event) => {
      event.preventDefault();
      const result = await api('POST', '/api/workbooks', {});
      location.assign('/w/' + encodeURIComponent(result.id));
    });
  }
  if (route.page !== 'editor') return;
  const base = '/api/workbooks/' + encodeURIComponent(route.id);
  const post = async (action, body) => {
    await api('POST', base + '/' + action, body || {});
    render();
  };
  const renameOpen = document.querySelector('#rename-open');
  if (renameOpen) renameOpen.addEventListener('click', () => { document.querySelector('#rename-form').hidden = false; });
  const rename = document.querySelector('#rename-form');
  if (rename) {
    rename.addEventListener('submit', async (event) => {
      event.preventDefault();
      const data = Object.fromEntries(new FormData(rename));
      try { await post('rename', { name: data.name || '' }); }
      catch (error) { document.querySelector('#page').insertAdjacentHTML('afterbegin', `<p class="error">${esc(error.message)}</p>`); }
    });
  }
  document.querySelectorAll('[data-sheet]').forEach((tab) => {
    tab.addEventListener('click', () => post('activate-sheet', { name: tab.getAttribute('data-sheet') }));
  });
  const selectedAddr = () => {
    const current = document.querySelector('[data-active="true"]') || document.querySelector('[data-cell][aria-selected="true"]');
    return current ? current.getAttribute('data-cell') : 'A1';
  };
  const selectedRaw = () => {
    const current = document.querySelector('[data-active="true"]') || document.querySelector('[data-cell][aria-selected="true"]');
    return current ? (current.getAttribute('data-raw') || '') : '';
  };
  let pending = null;
  const markPending = (source) => { pending = source; };
  const commitPending = async () => {
    if (!pending) return;
    const source = pending;
    pending = null;
    const field = document.querySelector(source);
    if (!field) return;
    await api('POST', base + '/cell', { value: field.value, cell: selectedAddr() });
  };
  const focusCell = async (cell) => {
    const next = cell.getAttribute('data-cell');
    if (pending && next !== selectedAddr()) {
      await commitPending();
      await api('POST', base + '/select', { cell: next, anchor: next, focus: next });
      render();
      return;
    }
    document.querySelectorAll('[data-cell]').forEach((item) => {
      item.setAttribute('aria-selected', item === cell ? 'true' : 'false');
      item.setAttribute('data-active', item === cell ? 'true' : 'false');
    });
    const raw = cell.getAttribute('data-raw') || '';
    const formulaBar = document.querySelector('#formula-bar');
    const inline = document.querySelector('#cell-editor');
    if (formulaBar) formulaBar.value = raw;
    if (inline) {
      inline.value = raw;
      inline.setAttribute('aria-label', 'Edit ' + next);
      const inlineLabel = inline.closest('label');
      if (inlineLabel) inlineLabel.firstChild.textContent = 'Edit ' + next + ' ';
    }
    api('POST', base + '/select', { cell: next, anchor: next, focus: next }).catch(() => {});
  };
  let rangeAnchor = 'A1';
  const splitAddr = (value) => {
    const match = /^([A-Z]+)(\d+)$/.exec(value || '');
    return match ? { col: match[1], row: Number(match[2]) } : { col: 'A', row: 1 };
  };
  const colNumber = (name) => [...name].reduce((total, ch) => total * 26 + ch.charCodeAt(0) - 64, 0);
  const selectRange = (start, end) => {
    const a = splitAddr(start);
    const b = splitAddr(end);
    const c1 = Math.min(colNumber(a.col), colNumber(b.col));
    const c2 = Math.max(colNumber(a.col), colNumber(b.col));
    const r1 = Math.min(a.row, b.row);
    const r2 = Math.max(a.row, b.row);
    document.querySelectorAll('[data-cell]').forEach((item) => {
      const part = splitAddr(item.getAttribute('data-cell'));
      const number = colNumber(part.col);
      const inside = number >= c1 && number <= c2 && part.row >= r1 && part.row <= r2;
      item.setAttribute('aria-selected', inside ? 'true' : 'false');
      item.setAttribute('data-active', item.getAttribute('data-cell') === end ? 'true' : 'false');
    });
  };
  let dragged = false;
  let dragAnchor = '';
  let dragCommitted = false;
  if (window.__sheetPointer) document.removeEventListener('pointerup', window.__sheetPointer);
  window.__sheetPointer = () => {
    if (!dragAnchor || !dragged) return;
    const active = document.querySelector('[data-active="true"]');
    const focusAddr = active ? active.getAttribute('data-cell') : dragAnchor;
    api('POST', base + '/select', { cell: focusAddr, anchor: dragAnchor, focus: focusAddr }).catch(() => {});
    dragAnchor = '';
    dragged = false;
    dragCommitted = true;
  };
  document.addEventListener('pointerup', window.__sheetPointer);
  document.querySelectorAll('[data-cell]').forEach((cell) => {
    cell.addEventListener('pointerdown', (event) => {
      if (event.button !== 0) return;
      dragAnchor = cell.getAttribute('data-cell');
      dragged = false;
      dragCommitted = false;
      rangeAnchor = dragAnchor;
    });
    cell.addEventListener('pointerenter', (event) => {
      if (!dragAnchor || event.buttons !== 1) return;
      const addr = cell.getAttribute('data-cell');
      if (addr === dragAnchor) return;
      dragged = true;
      selectRange(dragAnchor, addr);
    });
    cell.addEventListener('click', (event) => {
      const addr = cell.getAttribute('data-cell');
      if (dragCommitted) {
        dragCommitted = false;
        return;
      }
      dragAnchor = '';
      if (event.shiftKey) {
        selectRange(rangeAnchor, addr);
        api('POST', base + '/select', { cell: addr, anchor: rangeAnchor, focus: addr }).catch(() => {});
        return;
      }
      rangeAnchor = addr;
      focusCell(cell);
    });
    cell.addEventListener('dblclick', () => {
      rangeAnchor = cell.getAttribute('data-cell');
      focusCell(cell);
      const inline = document.querySelector('#cell-editor');
      if (inline) inline.focus();
    });
    cell.addEventListener('contextmenu', (event) => {
      event.preventDefault();
      const menu = document.querySelector('#grid-menu');
      if (!menu) return;
      menu.hidden = false;
      document.querySelector('#row-menu').hidden = true;
      document.querySelector('#column-menu').hidden = true;
    });
  });
  const bindEditor = (selector) => {
    const field = document.querySelector(selector);
    if (!field) return;
    field.addEventListener('input', () => markPending(selector));
    field.addEventListener('keydown', async (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        pending = null;
        await post('cell', { value: field.value, cell: selectedAddr() });
      }
      if (event.key === 'Escape') {
        event.preventDefault();
        pending = null;
        field.value = selectedRaw();
      }
    });
  };
  bindEditor('#formula-bar');
  bindEditor('#cell-editor');
  const exportCsv = document.querySelector('#export-csv');
  if (exportCsv) {
    exportCsv.addEventListener('click', () => {
      const link = document.createElement('a');
      link.href = base + '/export.csv';
      link.download = (document.querySelector('h1') ? document.querySelector('h1').textContent : 'worksheet') + '.csv';
      link.click();
    });
  }
  const dataMenu = document.querySelector('#data-menu');
  if (dataMenu) dataMenu.addEventListener('click', () => {
    const menu = document.querySelector('#data-menu-list');
    menu.hidden = !menu.hidden;
    dataMenu.setAttribute('aria-expanded', menu.hidden ? 'false' : 'true');
  });
  document.querySelectorAll('.sheet-options').forEach((button) => {
    button.addEventListener('click', () => {
      const menu = document.querySelector('#sheet-options-menu');
      menu.hidden = false;
      button.setAttribute('aria-expanded', 'true');
    });
  });
  let filterColumn = 'A';
  const columnValues = (column) => {
    const values = [];
    document.querySelectorAll('[data-cell]').forEach((cell) => {
      const addr = cell.getAttribute('data-cell') || '';
      if (addr.replace(/\d+$/, '') !== column || addr.endsWith('1')) return;
      const shown = cell.textContent || '';
      if (shown && !values.includes(shown)) values.push(shown);
    });
    return values;
  };
  const openFilter = (header) => {
    const match = [...document.querySelectorAll('[data-cell]')].find((cell) => cell.textContent === header && (cell.getAttribute('data-cell') || '').endsWith('1'));
    filterColumn = match ? match.getAttribute('data-cell').replace(/\d+$/, '') : 'A';
    const dialog = document.querySelector('#filter-layer [role=dialog]');
    if (dialog) dialog.setAttribute('aria-label', `Filter ${header}`);
    const box = document.querySelector('#filter-values');
    if (box) {
      box.innerHTML = columnValues(filterColumn).map((value) => `<label><input type="checkbox" data-value="${esc(value)}" checked> ${esc(value)}</label>`).join('');
    }
    show('#filter-layer');
  };
  document.querySelectorAll('.filter-header').forEach((button) => {
    button.addEventListener('click', () => openFilter(button.getAttribute('data-header')));
  });
  const refreshPivot = document.querySelector('#refresh-pivot');
  if (refreshPivot) refreshPivot.addEventListener('click', async () => {
    try { await post('refresh-pivot'); }
    catch (error) { document.querySelector('#page').insertAdjacentHTML('afterbegin', `<p class="error">${esc(error.message)}</p>`); }
  });
  document.querySelector('#undo').addEventListener('click', () => post('undo'));
  document.querySelector('#redo').addEventListener('click', () => post('redo'));
  if (window.__sheetKeys) document.removeEventListener('keydown', window.__sheetKeys);
  window.__sheetKeys = (event) => {
    if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
    const key = event.key.toLowerCase();
    if (key !== 'z' && key !== 'y') return;
    event.preventDefault();
    const button = document.querySelector(key === 'z' ? '#undo' : '#redo');
    if (button && !button.disabled) post(key === 'z' ? 'undo' : 'redo');
  };
  document.addEventListener('keydown', window.__sheetKeys);
  const rowMenu = document.querySelector('#row-menu');
  const columnMenu = document.querySelector('#column-menu');
  document.querySelectorAll('[role="rowheader"]').forEach((header) => {
    header.addEventListener('contextmenu', (event) => {
      event.preventDefault();
      rowMenu.dataset.row = header.getAttribute('aria-label');
      rowMenu.hidden = false;
      columnMenu.hidden = true;
    });
  });
  document.querySelectorAll('[role="columnheader"]').forEach((header) => {
    header.addEventListener('contextmenu', (event) => {
      event.preventDefault();
      columnMenu.dataset.col = header.getAttribute('aria-label');
      columnMenu.hidden = false;
      rowMenu.hidden = true;
    });
  });
  document.querySelector('#menu-insert-above').addEventListener('click', () => post('row', { op: 'above', row: rowMenu.dataset.row }));
  document.querySelector('#menu-insert-below').addEventListener('click', () => post('row', { op: 'below', row: rowMenu.dataset.row }));
  document.querySelector('#menu-delete-row').addEventListener('click', () => post('row', { op: 'delete', row: rowMenu.dataset.row }));
  document.querySelector('#menu-insert-left').addEventListener('click', () => post('column', { op: 'left', col: columnMenu.dataset.col }));
  document.querySelector('#menu-insert-right').addEventListener('click', () => post('column', { op: 'right', col: columnMenu.dataset.col }));
  document.querySelector('#menu-delete-column').addEventListener('click', () => post('column', { op: 'delete', col: columnMenu.dataset.col }));
  document.querySelectorAll('.open-dropdown').forEach((button) => {
    button.addEventListener('click', () => {
      const list = document.querySelector('#dropdown-list');
      if (!list) return;
      list.dataset.cell = button.getAttribute('data-cell');
      list.hidden = false;
    });
  });
  const dropdownList = document.querySelector('#dropdown-list');
  if (dropdownList) dropdownList.querySelectorAll('[role="option"]').forEach((option) => {
    option.addEventListener('click', () => post('cell', { value: option.textContent, cell: dropdownList.dataset.cell }));
  });
  document.querySelector('#add-sheet').addEventListener('click', () => post('add-sheet'));
  document.querySelector('#rename-sheet-open').addEventListener('click', () => show('#rename-sheet-layer'));
  document.querySelector('#save-sheet-name').addEventListener('click', () => post('rename-sheet', { name: document.querySelector('#sheet-name').value }));
  document.querySelector('#delete-sheet-open').addEventListener('click', () => {
    const menu = document.querySelector('#sheet-options-menu');
    if (menu) menu.hidden = true;
    if (document.querySelectorAll('[role="tab"]').length < 2) {
      document.querySelector('#page').insertAdjacentHTML('afterbegin', '<p class="error">A workbook must contain at least one worksheet</p>');
      return;
    }
    show('#delete-sheet-layer');
  });
  document.querySelector('#confirm-delete-sheet').addEventListener('click', async () => {
    const layer = document.querySelector('#delete-sheet-layer');
    if (layer) layer.hidden = true;
    try { await post('delete-sheet'); }
    catch (error) {
      document.querySelector('#page').insertAdjacentHTML('afterbegin', `<p class="error">${esc(error.message)}</p>`);
    }
  });
  document.querySelector('#insert-above').addEventListener('click', () => post('row', { op: 'above' }));
  document.querySelector('#insert-below').addEventListener('click', () => post('row', { op: 'below' }));
  document.querySelector('#delete-row').addEventListener('click', () => post('row', { op: 'delete' }));
  document.querySelector('#insert-left').addEventListener('click', () => post('column', { op: 'left' }));
  document.querySelector('#insert-right').addEventListener('click', () => post('column', { op: 'right' }));
  document.querySelector('#delete-column').addEventListener('click', () => post('column', { op: 'delete' }));
  document.querySelector('#sort-open').addEventListener('click', () => {
    const chosen = [...document.querySelectorAll('[data-cell][aria-selected="true"]')];
    if (chosen.length) {
      const minRow = Math.min(...chosen.map((cell) => splitAddr(cell.getAttribute('data-cell')).row));
      const headersInRange = chosen.filter((cell) => splitAddr(cell.getAttribute('data-cell')).row === minRow);
      const select = document.querySelector('#sort-by');
      if (select && headersInRange.length) {
        select.innerHTML = headersInRange.map((cell) => {
          const addr = cell.getAttribute('data-cell');
          const col = addr.replace(/\d+$/, '');
          const label = (cell.textContent || col).trim() || col;
          return `<option data-col="${esc(col)}">${esc(label)}</option>`;
        }).join('');
      }
    }
    show('#sort-layer');
  });
  document.querySelector('#apply-sort').addEventListener('click', () => {
    const chosen = [...document.querySelectorAll('[data-cell][aria-selected="true"]')].map((cell) => splitAddr(cell.getAttribute('data-cell')));
    chosen.sort((left, right) => left.row - right.row || colNumber(left.col) - colNumber(right.col));
    const start = chosen[0];
    const end = chosen[chosen.length - 1];
    const checked = document.querySelector('#sort-by option:checked');
    post('sort', {
      column: checked && checked.getAttribute('data-col') ? checked.getAttribute('data-col') : 'A',
      order: document.querySelector('#sort-order').value,
      header: document.querySelector('#sort-header').checked,
      anchor: start ? `${start.col}${start.row}` : 'A1',
      focus: end ? `${end.col}${end.row}` : 'A1',
    });
  });
  document.querySelector('#filter-open').addEventListener('click', () => {
    const first = document.querySelector('.filter-header');
    if (first) openFilter(first.getAttribute('data-header'));
    else show('#filter-layer');
  });
  const clearSelection = document.querySelector('#clear-selection');
  if (clearSelection) clearSelection.addEventListener('click', () => {
    document.querySelectorAll('#filter-values input[type=checkbox]').forEach((box) => { box.checked = false; });
  });
  document.querySelector('#clear-filter').addEventListener('click', () => post('filter', { column: filterColumn, clear: true }));
  document.querySelector('#apply-filter').addEventListener('click', () => {
    const boxes = [...document.querySelectorAll('#filter-values input[type=checkbox]')];
    const checked = boxes.filter((item) => item.checked).map((item) => item.getAttribute('data-value'));
    post('filter', {
      column: filterColumn,
      include: boxes.length && checked.length === boxes.length ? null : checked,
      condition: document.querySelector('#filter-condition').value,
      conditionValue: document.querySelector('#filter-value').value,
    });
  });
  document.querySelector('#validation-open').addEventListener('click', () => show('#validation-layer'));
  document.querySelector('#save-validation').addEventListener('click', () => {
    const selected = [...document.querySelectorAll('[data-cell][aria-selected="true"]')].map((cell) => cell.getAttribute('data-cell'));
    const start = selected[0] || selectedAddr();
    const end = selected[selected.length - 1] || start;
    post('validation', {
      type: document.querySelector('#rule-type').value,
      values: document.querySelector('#allowed-values').value,
      minimum: document.querySelector('#minimum').value,
      maximum: document.querySelector('#maximum').value,
      start,
      end,
    });
  });
  const deleteRule = document.querySelector('#delete-rule');
  if (deleteRule) deleteRule.addEventListener('click', () => post('delete-rule'));
  document.querySelector('#pivot-open').addEventListener('click', () => show('#pivot-layer'));
  document.querySelector('#create-pivot').addEventListener('click', () => post('pivot'));
  const applyPivot = document.querySelector('#apply-pivot');
  if (applyPivot) applyPivot.addEventListener('click', async () => {
    try {
      await post('pivot-apply', {
        rows: document.querySelector('#pivot-rows').value,
        columns: document.querySelector('#pivot-columns').value,
        values: document.querySelector('#pivot-values').value,
        summarize: document.querySelector('#pivot-summarize').value,
      });
    } catch (error) {
      document.querySelector('#page').insertAdjacentHTML('afterbegin', `<p class="error">${esc(error.message)}</p>`);
    }
  });
  let clipboard = null;
  const rememberCopy = (cut) => {
    const cells = [...document.querySelectorAll('[data-cell][aria-selected="true"]')].map((cell) => ({
      ...splitAddr(cell.getAttribute('data-cell')),
      raw: cell.getAttribute('data-raw') || '',
      addr: cell.getAttribute('data-cell'),
    }));
    if (!cells.length) return;
    const rows = [...new Set(cells.map((item) => item.row))].sort((a, b) => a - b);
    const cols = [...new Set(cells.map((item) => item.col))].sort((a, b) => colNumber(a) - colNumber(b));
    const text = rows.map((row) => cols.map((col) => {
      const found = cells.find((item) => item.row === row && item.col === col);
      return found ? found.raw : '';
    }).join('\t')).join('\n');
    const origin = cells.slice().sort((a, b) => a.row - b.row || colNumber(a.col) - colNumber(b.col))[0];
    clipboard = { text, from: `${origin.col}${origin.row}`, cut: Boolean(cut), clear: cells.map((item) => item.addr) };
  };
  const pasteNow = () => {
    if (!clipboard) return;
    post('paste', { text: clipboard.text, cell: selectedAddr(), from: clipboard.from, cut: clipboard.cut, clear: clipboard.clear });
    if (clipboard.cut) clipboard = null;
  };
  document.querySelector('#copy-range').addEventListener('click', () => rememberCopy(false));
  const cutButton = document.querySelector('#cut-range');
  if (cutButton) cutButton.addEventListener('click', () => rememberCopy(true));
  document.querySelector('#paste-range').addEventListener('click', pasteNow);
  const menuPaste = document.querySelector('#menu-paste');
  if (menuPaste) menuPaste.addEventListener('click', () => {
    document.querySelector('#grid-menu').hidden = true;
    pasteNow();
  });
  document.addEventListener('paste', (event) => {
    if (route.page !== 'editor') return;
    if (event.target && (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA')) return;
    const text = event.clipboardData && event.clipboardData.getData('text/plain');
    if (!text) return;
    event.preventDefault();
    post('paste', { text, cell: selectedAddr(), from: clipboard ? clipboard.from : selectedAddr() });
  });
  void routes;
}

async function render() {
  const route = routeOf(location.pathname);
  const page = await pageHtml(route);
  document.querySelector('#app').innerHTML = `${shell()}${page}</div>`;
  bind(route);
}

render();
