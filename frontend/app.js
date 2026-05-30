const button = document.querySelector('#scanButton');
const statusEl = document.querySelector('#status');
const body = document.querySelector('#resultsBody');
const tickerSummary = document.querySelector('#tickerSummary');
const tickersInput = document.querySelector('#tickers');

button.addEventListener('click', async () => {
  const tickers = parseTickerCsv(tickersInput.value);
  const payload = {
    max_filing_delay_days: Number(document.querySelector('#maxFilingDelay').value),
    lookback_days: Number(document.querySelector('#lookbackDays').value),
  };
  if (tickers.length) payload.tickers = tickers;

  updateTickerSummary(tickers);
  setLoading(true);
  try {
    const response = await fetch('/scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error(await response.text());
    const results = await response.json();
    renderResults(results);
    const universeLabel = tickers.length ? `${tickers.length} supplied ticker${tickers.length === 1 ? '' : 's'}` : 'default ticker list';
    statusEl.textContent = `Scan completed: ${new Date().toISOString().slice(0, 10)} (${results.length} cluster${results.length === 1 ? '' : 's'} from ${universeLabel})`;
  } catch (error) {
    statusEl.textContent = `Scan failed: ${error.message}`;
    statusEl.classList.add('error');
  } finally {
    setLoading(false);
  }
});

tickersInput.addEventListener('input', () => {
  updateTickerSummary(parseTickerCsv(tickersInput.value));
});

function parseTickerCsv(value) {
  return value
    .split(',')
    .map(normalizeTicker)
    .filter(Boolean);
}

function normalizeTicker(value) {
  let ticker = String(value).trim().toUpperCase();
  if (ticker.includes(':')) ticker = ticker.split(':').pop();
  return ticker.replace('.', '-');
}

function updateTickerSummary(tickers) {
  tickerSummary.textContent = tickers.length
    ? `${tickers.length} ticker${tickers.length === 1 ? '' : 's'} ready to scan.`
    : 'Enter comma-separated tickers, including formats like NASDAQ:ALRM,NASDAQ:CBNK.';
}

function setLoading(isLoading) {
  button.disabled = isLoading;
  button.textContent = isLoading ? 'Scanning...' : 'Scan Now';
  statusEl.classList.remove('error');
  statusEl.textContent = isLoading ? 'Fetching SEC Form 4 history and applying tiered cluster rules...' : statusEl.textContent;
}

function renderResults(results) {
  if (!results.length) {
    body.innerHTML = '<tr><td colspan="10" class="empty">No qualifying insider clusters found for the supplied tickers.</td></tr>';
    return;
  }
  body.innerHTML = results.map((result) => `
    <tr>
      <td><strong>${escapeHtml(result.ticker)}</strong><br>${escapeHtml(result.company_name || '')}</td>
      <td><span class="signal ${signalClass(result.signal)}">${escapeHtml(result.signal)}</span></td>
      <td>${result.cluster_size}</td>
      <td>${result.cluster_window_days} days</td>
      <td>${formatMoney(result.average_purchase_value)}</td>
      <td>${formatMoney(result.total_cluster_value)}</td>
      <td>${result.has_csuite_buyer ? 'Yes' : 'No'}</td>
      <td>${result.has_senior_officer ? 'Yes' : 'No'}</td>
      <td>${formatInactivity(result)}</td>
      <td>
        ${escapeHtml(result.rationale.join('; '))}
        <details>
          <summary>Insiders</summary>
          <ul class="mini">${result.insiders.map(formatInsider).join('')}</ul>
        </details>
      </td>
    </tr>`).join('');
}

function formatInactivity(result) {
  if (!result.inactivity_flag) return 'No';
  if (result.inactivity_months === null || result.inactivity_months === undefined) return 'Yes, no prior buy found';
  return `Yes, ~${result.inactivity_months} months`;
}

function formatInsider(insider) {
  return `<li>${escapeHtml(insider.insider_name)} (${escapeHtml(insider.insider_title || 'title N/A')}): ${formatMoney(insider.value)} on ${escapeHtml(insider.transaction_date)}</li>`;
}

function signalClass(signal) {
  return signal.toLowerCase().replace(/\s+/g, '-');
}

function formatMoney(value) {
  if (value === null || value === undefined) return 'N/A';
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: value > 1000 ? 0 : 2 }).format(value);
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
}
