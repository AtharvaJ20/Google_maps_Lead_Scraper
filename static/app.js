/* app.js — Google Maps Lead Scraper */
(function () {
  'use strict';

  // ── Constants ────────────────────────────────────────────────────────────
  const PAGE_SIZE    = 20;
  const TIMEOUT_MS   = 120000;

  // Progress step timing: ms after search start when each step becomes active
  const STEP_TIMINGS = [0, 2500, 6000, 18000, 48000];
  const STEP_LABELS  = [
    'Opening Google Maps…',
    'Searching for businesses…',
    'Loading results…',
    'Extracting business details…',
    'Preparing your results…',
  ];

  // ── State ────────────────────────────────────────────────────────────────
  let results       = [];
  let currentQuery  = '';
  let currentPage   = 1;
  let stepTimers    = [];
  let timeoutTimer  = null;
  let scrapeAbort   = null;

  // ── DOM refs ─────────────────────────────────────────────────────────────
  const $  = id => document.getElementById(id);
  const stSearch   = $('state-search');
  const stProgress = $('state-progress');
  const stResults  = $('state-results');
  const stError    = $('state-error');

  const form         = $('search-form');
  const fCategory    = $('category');
  const fLocation    = $('location');
  const errCategory  = $('category-error');
  const errLocation  = $('location-error');
  const searchBtn    = $('search-btn');
  const searchBtnIcon= $('search-btn-icon');
  const searchBtnLbl = $('search-btn-label');

  const progressQuery = $('progress-query');
  const statusText    = $('status-text');

  const resultsSummary = $('results-summary');
  const resultsTbody   = $('results-tbody');
  const paginationWrap = $('pagination-wrap');
  const paginationNav  = $('pagination-nav');

  const errorCard    = $('error-card');
  const errorIconEl  = $('error-icon');
  const errorMsg     = $('error-message');

  // ── State toggling ───────────────────────────────────────────────────────
  function showOnly(el) {
    [stSearch, stProgress, stResults, stError].forEach(s => {
      s.hidden = (s !== el);
    });
  }

  // ── Validation ───────────────────────────────────────────────────────────
  function validateField(input, errEl) {
    if (!input.value.trim()) {
      input.classList.add('is-invalid');
      errEl.style.display = 'block';
      return false;
    }
    input.classList.remove('is-invalid');
    errEl.style.display = 'none';
    return true;
  }

  function clearFieldError(input, errEl) {
    if (input.value.trim()) {
      input.classList.remove('is-invalid');
      errEl.style.display = 'none';
    }
  }

  fCategory.addEventListener('blur',  () => validateField(fCategory, errCategory));
  fLocation.addEventListener('blur',  () => validateField(fLocation, errLocation));
  fCategory.addEventListener('input', () => clearFieldError(fCategory, errCategory));
  fLocation.addEventListener('input', () => clearFieldError(fLocation, errLocation));

  // ── Progress stepper ─────────────────────────────────────────────────────
  function setStepIcon(n, state) {
    const container = $('step-icon-' + n);
    if (!container) return;

    let iconName, color, spin = false;
    if (state === 'done') {
      iconName = 'check-circle-2';
      color    = 'var(--color-step-done)';
    } else if (state === 'active') {
      iconName = 'loader-2';
      color    = 'var(--color-step-active)';
      spin     = true;
    } else {
      iconName = 'circle';
      color    = 'var(--color-step-pending)';
    }

    container.style.color = color;
    container.innerHTML   =
      '<i data-lucide="' + iconName + '" aria-hidden="true"'
      + ' style="width:20px;height:20px' + (spin ? ';animation:spin 1s linear infinite' : '') + '">'
      + '</i>';
    lucide.createIcons();
  }

  function advanceToStep(n) {
    for (let i = 1; i < n; i++) {
      setStepIcon(i, 'done');
      const conn = $('conn-' + i);
      if (conn) conn.classList.add('done');
    }
    setStepIcon(n, 'active');
    statusText.textContent = STEP_LABELS[n - 1] || '';
  }

  function markAllDone() {
    for (let i = 1; i <= 5; i++) {
      setStepIcon(i, 'done');
      const conn = $('conn-' + i);
      if (conn) conn.classList.add('done');
    }
    statusText.textContent = 'Done!';
  }

  function resetSteps() {
    for (let i = 1; i <= 5; i++) {
      setStepIcon(i, 'pending');
      const conn = $('conn-' + i);
      if (conn) conn.classList.remove('done');
    }
    statusText.textContent = 'Opening Google Maps…';
  }

  function startProgressSim() {
    clearTimers();
    advanceToStep(1);

    STEP_TIMINGS.slice(1).forEach((delay, idx) => {
      const stepNum = idx + 2;
      stepTimers.push(setTimeout(() => advanceToStep(stepNum), delay));
    });

    timeoutTimer = setTimeout(() => {
      if (scrapeAbort) { scrapeAbort.abort(); scrapeAbort = null; }
      clearTimers();
      resetSearchBtn();
      showError('timeout');
    }, TIMEOUT_MS);
  }

  function clearTimers() {
    stepTimers.forEach(clearTimeout);
    stepTimers = [];
    if (timeoutTimer) { clearTimeout(timeoutTimer); timeoutTimer = null; }
  }

  // ── Search button state ───────────────────────────────────────────────────
  function setSearchBtnLoading(loading) {
    searchBtn.disabled = loading;
    if (loading) {
      searchBtnIcon.innerHTML =
        '<i data-lucide="loader-2" aria-hidden="true"'
        + ' style="width:16px;height:16px;animation:spin 1s linear infinite"></i>';
      searchBtnLbl.textContent = 'Searching…';
    } else {
      searchBtnIcon.innerHTML =
        '<i data-lucide="search" aria-hidden="true" style="width:16px;height:16px"></i>';
      searchBtnLbl.textContent = 'Search Leads';
    }
    lucide.createIcons();
  }

  function resetSearchBtn() { setSearchBtnLoading(false); }

  // ── Form submit ───────────────────────────────────────────────────────────
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    const catOk = validateField(fCategory, errCategory);
    const locOk = validateField(fLocation, errLocation);
    if (!catOk) { fCategory.focus(); return; }
    if (!locOk) { fLocation.focus(); return; }
    doSearch(fCategory.value.trim(), fLocation.value.trim());
  });

  // ── Chips ─────────────────────────────────────────────────────────────────
  document.querySelectorAll('.chip').forEach(chip => {
    chip.addEventListener('click', function () {
      fCategory.value = chip.dataset.category;
      fLocation.value = chip.dataset.location;
      fCategory.classList.remove('is-invalid');
      fLocation.classList.remove('is-invalid');
      errCategory.style.display = 'none';
      errLocation.style.display = 'none';
      form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    });
  });

  // ── Core search ───────────────────────────────────────────────────────────
  function doSearch(category, location) {
    currentQuery = category + ' in ' + location;
    setSearchBtnLoading(true);

    progressQuery.textContent = 'Searching "' + currentQuery + '"';
    resetSteps();
    showOnly(stProgress);
    startProgressSim();

    scrapeAbort = new AbortController();
    fetch('/scrape', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ category, location }),
      signal:  scrapeAbort.signal,
    })
      .then(r => r.json())
      .then(data => {
        scrapeAbort = null;
        clearTimers();
        resetSearchBtn();

        if (data.status === 'success' && Array.isArray(data.results) && data.results.length > 0) {
          markAllDone();
          results      = data.results;
          currentQuery = data.query || currentQuery;
          currentPage  = 1;
          setTimeout(() => {
            renderResults();
            showOnly(stResults);
          }, 400);
        } else {
          showError(data.message || 'no results');
        }
      })
      .catch(err => {
        scrapeAbort = null;
        clearTimers();
        resetSearchBtn();
        if (err.name !== 'AbortError') showError('timeout');
      });
  }

  // ── Error state ───────────────────────────────────────────────────────────
  function showError(raw) {
    const lower = (raw || '').toLowerCase();
    let msg, isWarning = false;

    if (lower.includes('no result') || lower.includes('not found') || lower.includes('0 result')) {
      msg = 'No businesses found for this search. Try a different category or location.';
    } else if (lower.includes('blocking') || lower.includes('captcha') || lower.includes('blocked')) {
      msg = 'Google is temporarily blocking automated requests. Please wait a few minutes and try again.';
      isWarning = true;
    } else if (lower.includes('timeout') || lower.includes('timed out')) {
      msg = 'The search took too long to complete. Google Maps may be slow right now — please try again.';
    } else {
      msg = 'Something went wrong. Please try again or try a different search.';
    }

    errorMsg.textContent       = msg;
    errorCard.style.background = isWarning ? 'var(--color-warning-bg)' : 'var(--color-error-bg)';
    errorIconEl.style.color    = isWarning ? 'var(--color-warning)'    : 'var(--color-error)';
    errorIconEl.innerHTML =
      '<i data-lucide="' + (isWarning ? 'alert-triangle' : 'x-circle') + '"'
      + ' aria-hidden="true" style="width:24px;height:24px"></i>';
    lucide.createIcons();
    showOnly(stError);
  }

  // ── Reset to search ───────────────────────────────────────────────────────
  function resetToSearch() {
    fCategory.value = '';
    fLocation.value = '';
    fCategory.classList.remove('is-invalid');
    fLocation.classList.remove('is-invalid');
    errCategory.style.display = 'none';
    errLocation.style.display = 'none';
    results     = [];
    currentPage = 1;
    showOnly(stSearch);
    fCategory.focus();
  }

  $('btn-new-search').addEventListener('click', resetToSearch);
  $('btn-error-new-search').addEventListener('click', resetToSearch);

  // ── Render table ──────────────────────────────────────────────────────────
  function renderResults() {
    const count = results.length;
    resultsSummary.innerHTML =
      'Found <strong>' + count + '</strong> '
      + (count === 1 ? 'business' : 'businesses')
      + ' for “' + esc(currentQuery) + '”';

    renderPage();
    renderPagination();
  }

  function renderPage() {
    const start = (currentPage - 1) * PAGE_SIZE;
    const rows  = results.slice(start, start + PAGE_SIZE);
    resultsTbody.innerHTML = rows.map(buildRow).join('');
    lucide.createIcons();
  }

  function buildRow(b) {
    const dash = '<span style="color:var(--color-text-muted)" aria-label="not available">—</span>';

    const name = b.name
      ? '<span style="font-weight:600">' + esc(b.name) + '</span>'
      : dash;

    const addr = b.address
      ? '<span title="' + escAttr(b.address) + '"'
        + ' style="display:block;max-width:220px;overflow:hidden;'
        + 'text-overflow:ellipsis;white-space:nowrap">'
        + esc(b.address) + '</span>'
      : dash;

    const phone = b.phone
      ? '<a href="tel:' + escAttr(b.phone) + '" class="link-muted">' + esc(b.phone) + '</a>'
      : dash;

    const site = b.website
      ? '<a href="' + escAttr(b.website) + '" target="_blank" rel="noopener noreferrer"'
        + ' class="link-accent"'
        + ' style="display:inline-flex;align-items:center;gap:4px">'
        + 'Visit <i data-lucide="external-link" aria-hidden="true"'
        + ' style="width:12px;height:12px"></i></a>'
      : dash;

    const star = b.rating
      ? '<span style="display:inline-flex;align-items:center;gap:4px">'
        + '<svg width="13" height="13" viewBox="0 0 24 24" fill="#f59e0b" stroke="none"'
        + ' aria-hidden="true"><polygon points="12,2 15.09,8.26 22,9.27 17,14.14'
        + ' 18.18,21.02 12,17.77 5.82,21.02 7,14.14 2,9.27 8.91,8.26"/></svg>'
        + '<span>' + esc(String(b.rating)) + '</span></span>'
      : dash;

    const reviews = b.reviews
      ? '<span style="font-variant-numeric:tabular-nums">' + esc(String(b.reviews)) + '</span>'
      : dash;

    return '<tr>'
      + '<td class="results-table" style="padding:12px 16px;font-size:14px;border-bottom:1px solid var(--color-border);vertical-align:middle">' + name + '</td>'
      + '<td style="padding:12px 16px;font-size:14px;border-bottom:1px solid var(--color-border);vertical-align:middle">' + addr + '</td>'
      + '<td style="padding:12px 16px;font-size:14px;border-bottom:1px solid var(--color-border);vertical-align:middle">' + phone + '</td>'
      + '<td style="padding:12px 16px;font-size:14px;border-bottom:1px solid var(--color-border);vertical-align:middle">' + site + '</td>'
      + '<td style="padding:12px 16px;font-size:14px;border-bottom:1px solid var(--color-border);vertical-align:middle;text-align:center">' + star + '</td>'
      + '<td style="padding:12px 16px;font-size:14px;border-bottom:1px solid var(--color-border);vertical-align:middle;text-align:right">' + reviews + '</td>'
      + '</tr>';
  }

  // ── Pagination ────────────────────────────────────────────────────────────
  function renderPagination() {
    const total = Math.ceil(results.length / PAGE_SIZE);
    if (total <= 1) { paginationWrap.hidden = true; return; }
    paginationWrap.hidden = false;

    const pages = getPageNumbers(currentPage, total);
    let html = '';

    html += '<button class="page-btn" id="pg-prev"'
      + (currentPage === 1 ? ' disabled' : '')
      + ' aria-label="Previous page">'
      + '<i data-lucide="chevron-left" aria-hidden="true" style="width:16px;height:16px"></i>'
      + '</button>';

    pages.forEach(p => {
      if (p === '…') {
        html += '<span style="padding:0 4px;color:var(--color-text-muted);line-height:36px;font-size:14px">…</span>';
      } else {
        const active = p === currentPage;
        html += '<button class="page-btn' + (active ? ' active' : '') + '"'
          + ' data-page="' + p + '"'
          + (active ? ' aria-current="page"' : '')
          + ' aria-label="Page ' + p + '">'
          + p + '</button>';
      }
    });

    html += '<button class="page-btn" id="pg-next"'
      + (currentPage === total ? ' disabled' : '')
      + ' aria-label="Next page">'
      + '<i data-lucide="chevron-right" aria-hidden="true" style="width:16px;height:16px"></i>'
      + '</button>';

    paginationNav.innerHTML = html;
    lucide.createIcons();

    paginationNav.querySelectorAll('[data-page]').forEach(btn => {
      btn.addEventListener('click', function () {
        currentPage = parseInt(btn.dataset.page, 10);
        renderPage();
        renderPagination();
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    });

    const prev = document.getElementById('pg-prev');
    const next = document.getElementById('pg-next');
    if (prev) prev.addEventListener('click', () => { if (currentPage > 1) { currentPage--; renderPage(); renderPagination(); } });
    if (next) next.addEventListener('click', () => { if (currentPage < total) { currentPage++; renderPage(); renderPagination(); } });
  }

  function getPageNumbers(cur, total) {
    if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
    if (cur <= 3)          return [1, 2, 3, 4, '…', total];
    if (cur >= total - 2)  return [1, '…', total - 3, total - 2, total - 1, total];
    return [1, '…', cur - 1, cur, cur + 1, '…', total];
  }

  // ── Downloads ─────────────────────────────────────────────────────────────
  function setupDownload(btnId, iconId, labelId, format, origIcon, origLabel) {
    $(btnId).addEventListener('click', function () {
      const btn   = $(btnId);
      const icon  = $(iconId);
      const label = $(labelId);
      btn.disabled = true;
      icon.innerHTML  = '<i data-lucide="loader-2" aria-hidden="true"'
        + ' style="width:16px;height:16px;animation:spin 1s linear infinite"></i>';
      label.textContent = 'Generating…';
      lucide.createIcons();

      fetch('/export', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ results, format, query: currentQuery }),
      })
        .then(r => {
          if (!r.ok) throw new Error('export failed');
          const cd = r.headers.get('Content-Disposition') || '';
          const match = cd.match(/filename="([^"]+)"/);
          return r.blob().then(blob => ({ blob, filename: match ? match[1] : null }));
        })
        .then(({ blob, filename }) => {
          const url  = URL.createObjectURL(blob);
          const a    = document.createElement('a');
          const safe = currentQuery.replace(/[^a-z0-9]/gi, '_').toLowerCase();
          a.href     = url;
          a.download = filename || ('leads_' + safe + '.' + format);
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(url);

          icon.innerHTML = '<i data-lucide="check-circle-2" aria-hidden="true"'
            + ' style="width:16px;height:16px;color:#16a34a"></i>';
          label.textContent = 'Downloaded!';
          lucide.createIcons();
          setTimeout(() => {
            icon.innerHTML = '<i data-lucide="' + origIcon + '" aria-hidden="true"'
              + ' style="width:16px;height:16px"></i>';
            label.textContent = origLabel;
            lucide.createIcons();
          }, 2000);
        })
        .catch(err => {
          console.error('Download error:', err);
          icon.innerHTML = '<i data-lucide="alert-circle" aria-hidden="true"'
            + ' style="width:16px;height:16px;color:#dc2626"></i>';
          label.textContent = 'Failed — retry';
          lucide.createIcons();
          setTimeout(() => {
            icon.innerHTML = '<i data-lucide="' + origIcon + '" aria-hidden="true"'
              + ' style="width:16px;height:16px"></i>';
            label.textContent = origLabel;
            lucide.createIcons();
          }, 3000);
        })
        .finally(() => {
          btn.disabled = false;
        });
    });
  }

  setupDownload('btn-xlsx', 'xlsx-icon', 'xlsx-label', 'xlsx', 'file-spreadsheet', 'Download Excel');
  setupDownload('btn-csv',  'csv-icon',  'csv-label',  'csv',  'file-text',         'Download CSV');

  // ── Utilities ─────────────────────────────────────────────────────────────
  function esc(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
  function escAttr(str) {
    return String(str).replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  // ── Init ──────────────────────────────────────────────────────────────────
  lucide.createIcons();
  showOnly(stSearch);
  fCategory.focus();

})();
