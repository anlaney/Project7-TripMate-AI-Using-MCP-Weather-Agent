/* ============================================================
   Weather Agent — script.js
   Pure AI Weather Agent with real-time conditions & 5-step forecast
   ============================================================ */

'use strict';

// ---- Weather Condition Icon Map ----
const CONDITION_MAP = [
  { keys: ['thunderstorm', 'lightning'],              icon: '⛈️' },
  { keys: ['drizzle', 'light rain'],                  icon: '🌦️' },
  { keys: ['rain', 'shower'],                         icon: '🌧️' },
  { keys: ['snow', 'sleet', 'blizzard', 'ice'],       icon: '❄️' },
  { keys: ['mist', 'smoke', 'haze', 'fog', 'dust'],   icon: '🌫️' },
  { keys: ['clear', 'sunny'],                         icon: '☀️' },
  { keys: ['few clouds', 'scattered'],                icon: '🌤️' },
  { keys: ['broken clouds', 'overcast', 'clouds'],    icon: '☁️' },
];

function getConditionIcon(description) {
  const lower = (description || '').toLowerCase();
  for (const entry of CONDITION_MAP) {
    if (entry.keys.some(k => lower.includes(k))) {
      return entry.icon;
    }
  }
  return '🌤️';
}

function formatDatetime(dt) {
  const date = new Date((dt || '').replace(' ', 'T'));
  if (isNaN(date)) return { date: dt, time: '' };
  const day  = date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
  const time = date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true });
  return { date: day, time };
}

// ---- DOM Elements ----
const heroSection          = document.getElementById('hero-section');
const searchForm           = document.getElementById('search-form');
const searchInput          = document.getElementById('search-input');
const searchBtn            = document.getElementById('search-btn');
const btnText              = document.getElementById('btn-text');
const btnLoader            = searchBtn.querySelector('.btn-loader');

const errorBanner          = document.getElementById('error-banner');
const errorMessage         = document.getElementById('error-message');
const errorClose           = document.getElementById('error-close');

const loadingSection       = document.getElementById('loading-section');

// Weather Results Elements
const weatherResultsSec    = document.getElementById('weather-results-section');
const wCity                = document.getElementById('w-city');
const wCondition           = document.getElementById('w-condition');
const wTemp                = document.getElementById('w-temp');
const wIcon                = document.getElementById('w-icon');
const wFeels               = document.getElementById('w-feels');
const wHumidity            = document.getElementById('w-humidity');
const wWind                = document.getElementById('w-wind');
const forecastGrid         = document.getElementById('forecast-grid');
const wNewSearchBtn        = document.getElementById('w-new-search-btn');

// ---- Toast Helpers ----
function showError(msg) {
  errorMessage.textContent = msg;
  errorBanner.classList.remove('hidden');
}

function hideError() {
  errorBanner.classList.add('hidden');
}
errorClose.addEventListener('click', hideError);

// ---- Loading Helpers ----
function setLoading(isLoading) {
  searchBtn.disabled = isLoading;
  if (isLoading) {
    btnText.classList.add('hidden');
    btnLoader.classList.add('visible');
  } else {
    btnText.classList.remove('hidden');
    btnLoader.classList.remove('visible');
  }
}

function showLoading() {
  heroSection.style.opacity = '0.2';
  heroSection.style.pointerEvents = 'none';
  heroSection.style.transition = 'opacity 0.4s';
  weatherResultsSec.classList.add('hidden');
  loadingSection.classList.remove('hidden');
}

function hideLoading() {
  heroSection.style.opacity = '1';
  heroSection.style.pointerEvents = '';
  loadingSection.classList.add('hidden');
}

// ---- Render Weather Agent Results ----
function renderWeatherAgent(weather, forecast) {
  wCity.textContent       = weather.city || '—';
  wCondition.textContent  = weather.condition || '—';
  wTemp.textContent       = Math.round(weather.temperature_c ?? 0);
  wIcon.textContent       = getConditionIcon(weather.condition);
  wFeels.textContent      = `${Math.round(weather.feels_like_c ?? 0)}°C`;
  wHumidity.textContent   = `${weather.humidity ?? '—'}%`;
  wWind.textContent       = `${weather.wind_speed ?? '—'} m/s`;

  forecastGrid.innerHTML  = '';
  if (forecast && forecast.length > 0) {
    forecast.slice(0, 5).forEach((item, idx) => {
      const { date, time } = formatDatetime(item.datetime);
      const icon = getConditionIcon(item.weather);
      const card = document.createElement('div');
      card.className = 'fc-card';
      card.style.animationDelay = `${idx * 0.06}s`;
      card.innerHTML = `
        <p class="fc-date">${date}<br/>${time}</p>
        <span class="fc-emoji" aria-hidden="true">${icon}</span>
        <p class="fc-temp">${Math.round(item.temperature ?? 0)}°C</p>
        <p class="fc-cond">${item.weather || '—'}</p>
      `;
      forecastGrid.appendChild(card);
    });
  } else {
    forecastGrid.innerHTML = '<p style="grid-column:1/-1; color:var(--text-muted); text-align:center;">No forecast data available.</p>';
  }

  weatherResultsSec.classList.remove('hidden');
  weatherResultsSec.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ---- Reset to Search ----
function resetToSearch() {
  weatherResultsSec.classList.add('hidden');
  loadingSection.classList.add('hidden');
  heroSection.style.opacity = '1';
  heroSection.style.pointerEvents = '';
  searchInput.value = '';
  searchInput.focus();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

wNewSearchBtn.addEventListener('click', resetToSearch);

// ---- Suggestion Pills Click ----
document.querySelectorAll('.suggestion-pills .pill').forEach(btn => {
  btn.addEventListener('click', () => {
    const city = btn.getAttribute('data-city');
    if (city) {
      searchInput.value = city;
      searchForm.dispatchEvent(new Event('submit'));
    }
  });
});

// ---- Form Submit Handler ----
searchForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const city = searchInput.value.trim();
  if (!city) return;

  hideError();
  setLoading(true);
  showLoading();

  try {
    const res = await fetch('/api/weather', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ city })
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      throw new Error(data.error || `Could not find weather data for "${city}".`);
    }
    hideLoading();
    renderWeatherAgent(data.weather, data.forecast);
  } catch (err) {
    hideLoading();
    showError(err.message || 'An unexpected error occurred. Please try again.');
  } finally {
    setLoading(false);
  }
});