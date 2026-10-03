let ws = null;
const canvas = document.getElementById('spectrum-canvas');
const ctx = canvas.getContext('2d');

let lastArtworkUrl = '';
let lastTrackTitle = '';

const SPOTIFY_CLIENT_ID = "9a0069b06ee54e049ad75eaf99e986fd";

function generateRandomString(length) {
    let text = '';
    const possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    for (let i = 0; i < length; i++) {
        text += possible.charAt(Math.floor(Math.random() * possible.length));
    }
    return text;
}

async function sha256(plain) {
    const encoder = new TextEncoder();
    const data = encoder.encode(plain);
    return window.crypto.subtle.digest('SHA-256', data);
}

function base64encode(input) {
    return btoa(String.fromCharCode.apply(null, new Uint8Array(input)))
        .replace(/=/g, '')
        .replace(/\+/g, '-')
        .replace(/\//g, '_');
}

function loginWithSpotify() {
    const clientId = document.getElementById('spotify-client-id-input').value.trim() || SPOTIFY_CLIENT_ID;
    fetch('/api/save_spotify_client', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: clientId })
    }).finally(() => {
        window.location.href = `/spotify/login?client_id=${encodeURIComponent(clientId)}`;
    });
}

function checkSpotifyUrlStatus() {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('spotify') === 'connected') {
        window.history.replaceState(null, null, window.location.pathname);
        const providerEl = document.getElementById('track-provider');
        if (providerEl) {
            providerEl.textContent = '🟢 Spotify Web API Conectado';
            providerEl.style.background = '#1db954';
        }
    } else if (urlParams.get('spotify') === 'error') {
        window.history.replaceState(null, null, window.location.pathname);
        alert("❌ Error al autenticar con Spotify. Verifica que el Redirect URI esté registrado en Spotify Developer Dashboard.");
    }
}

function initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/sync`;

    ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        renderDashboard(data);
    };

    ws.onclose = () => {
        setTimeout(initWebSocket, 1000);
    };

    ws.onerror = (err) => {
        console.error('WebSocket Error:', err);
    };
}

function loadAppConfig() {
    const ipInput = document.getElementById('hue-ip');
    const userInput = document.getElementById('hue-username');
    const statusEl = document.getElementById('bridge-status');
    const spotifyCidInput = document.getElementById('spotify-client-id-input');

    fetch('/api/config')
        .then(res => res.json())
        .then(data => {
            if (data.hue_ip) ipInput.value = data.hue_ip;
            if (data.hue_username) userInput.value = data.hue_username;
            if (spotifyCidInput) spotifyCidInput.value = data.spotify_client_id || SPOTIFY_CLIENT_ID;

            if (data.is_connected) {
                statusEl.className = 'status-box success';
                statusEl.innerHTML = `✅ <strong>Hue Bridge guardado y conectado en ${data.hue_ip} (${data.real_lights.length} luces activas).</strong>`;
            } else if (data.hue_ip) {
                statusEl.className = 'status-box warn';
                statusEl.innerHTML = `ℹ️ <strong>IP guardada (${data.hue_ip}). Haz clic en 'Conectar Manualmente' o presiona el botón.</strong>`;
            }

            const savedToken = localStorage.getItem('spotify_access_token');
            if (savedToken || data.spotify_connected) {
                const providerEl = document.getElementById('track-provider');
                if (providerEl) {
                    providerEl.textContent = '🟢 Spotify Vinculado';
                    providerEl.style.background = '#1db954';
                }
                if (savedToken) {
                    fetch('/api/spotify_auth', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ token: savedToken })
                    });
                }
            }
        })
        .catch(err => {
            console.error('Error loading app config:', err);
        });
}

function loadAudioDevices() {
    const deviceSelect = document.getElementById('audio-device');
    fetch('/api/audio_devices')
        .then(res => res.json())
        .then(data => {
            deviceSelect.innerHTML = '';
            const devices = data.devices || [];
            if (devices.length === 0) {
                deviceSelect.innerHTML = '<option value="">No se encontraron micrófonos</option>';
                return;
            }
            devices.forEach(dev => {
                const opt = document.createElement('option');
                opt.value = dev.index;
                opt.textContent = `${dev.name} ${dev.is_default ? '(Predeterminado)' : ''}`;
                if (dev.is_default) opt.selected = true;
                deviceSelect.appendChild(opt);
            });
        })
        .catch(err => {
            console.error('Error loading audio devices:', err);
        });
}

function renderDashboard(data) {
    const metrics = data.audio;
    const lights = data.lights;
    const track = data.track;

    if (track) {
        if (track.title !== lastTrackTitle) {
            lastTrackTitle = track.title;
            document.getElementById('track-title').textContent = track.title || 'Música activa';
            document.getElementById('track-artist').textContent = track.artist || '';
            document.getElementById('track-album').textContent = track.album || '';
        }

        if (track.artwork_url && track.artwork_url !== lastArtworkUrl) {
            lastArtworkUrl = track.artwork_url;
            document.getElementById('track-art').src = track.artwork_url;
        }

        if (track.provider) {
            const providerEl = document.getElementById('track-provider');
            if (track.provider === 'spotify') {
                if (providerEl.textContent !== '🟢 Spotify Web API') {
                    providerEl.textContent = '🟢 Spotify Web API';
                    providerEl.style.background = '#1db954';
                }
            } else if (track.provider === 'apple_music') {
                if (providerEl.textContent !== '🍎 Apple Music / iTunes API') {
                    providerEl.textContent = '🍎 Apple Music / iTunes API';
                    providerEl.style.background = '#fc3c44';
                }
            }
        }
    }

    const beatIndicator = document.getElementById('beat-indicator');
    if (metrics.is_beat) {
        if (!beatIndicator.classList.contains('active')) {
            beatIndicator.classList.add('active');
        }
    } else {
        if (beatIndicator.classList.contains('active')) {
            beatIndicator.classList.remove('active');
        }
    }

    document.getElementById('meter-bass').style.width = `${Math.min(100, metrics.bass * 100)}%`;
    document.getElementById('meter-mids').style.width = `${Math.min(100, metrics.mids * 100)}%`;
    document.getElementById('meter-treble').style.width = `${Math.min(100, metrics.treble * 100)}%`;

    const bulbsContainer = document.getElementById('bulbs-container');
    
    if (bulbsContainer.children.length !== lights.length && lights.length > 0) {
        bulbsContainer.innerHTML = '';
        lights.forEach((light, idx) => {
            const bulbEl = document.createElement('div');
            bulbEl.className = 'bulb-card';
            bulbEl.id = `bulb-${idx + 1}`;
            bulbEl.innerHTML = `
                <div class="glow-effect"></div>
                <div class="bulb-icon">💡</div>
                <div class="bulb-name">${light.name || `Luz #${idx + 1}`}</div>
                <div class="bulb-hex">#000000</div>
            `;
            bulbsContainer.appendChild(bulbEl);
        });
    }

    lights.forEach((light, idx) => {
        const bulbEl = document.getElementById(`bulb-${idx + 1}`);
        if (bulbEl) {
            const glowEl = bulbEl.querySelector('.glow-effect');
            const hexEl = bulbEl.querySelector('.bulb-hex');
            const nameEl = bulbEl.querySelector('.bulb-name');

            if (nameEl.textContent !== light.name) nameEl.textContent = light.name;

            const [r, g, b] = light.rgb;
            const rgbStr = `rgb(${r}, ${g}, ${b})`;
            
            bulbEl.style.borderColor = rgbStr;
            glowEl.style.background = `radial-gradient(circle, rgba(${r},${g},${b}, 0.8) 0%, rgba(0,0,0,0) 70%)`;
            glowEl.style.opacity = (light.brightness / 254).toFixed(2);
            hexEl.textContent = light.hex.toUpperCase();

            if (light.is_flashing) {
                bulbEl.style.transform = 'scale(1.04)';
            } else {
                bulbEl.style.transform = 'scale(1.0)';
            }
        }
    });

    drawSpectrum(metrics.waveform || []);
}

function drawSpectrum(waveform) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (!waveform.length) return;

    ctx.lineWidth = 3;
    ctx.strokeStyle = '#ec4899';

    ctx.beginPath();

    const sliceWidth = canvas.width / waveform.length;
    let x = 0;

    for (let i = 0; i < waveform.length; i++) {
        const v = waveform[i];
        const y = (v * (canvas.height / 3)) + (canvas.height / 2);

        if (i === 0) {
            ctx.moveTo(x, y);
        } else {
            ctx.lineTo(x, y);
        }

        x += sliceWidth;
    }

    ctx.stroke();
}

function searchMediaSong() {
    const query = document.getElementById('media-search-input').value.trim();
    if (!query) return;

    fetch('/api/search_media', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success && data.track) {
            document.getElementById('theme-select').value = 'album_art';
            updateSettings();
        }
    });
}

function saveSpotifyToken() {
    const token = document.getElementById('spotify-token-input').value.trim();
    if (!token) return;

    localStorage.setItem('spotify_access_token', token);
    fetch('/api/spotify_auth', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: token })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            document.getElementById('theme-select').value = 'album_art';
            updateSettings();
        }
    });
}

function updateSettings() {
    const mode = document.getElementById('audio-mode').value;
    const theme = document.getElementById('theme-select').value;
    const deviceVal = document.getElementById('audio-device').value;
    const sensVal = parseFloat(document.getElementById('audio-sensitivity').value);

    document.getElementById('sens-val').textContent = `${sensVal.toFixed(1)}x`;

    const payload = {
        mode: mode,
        theme: theme,
        sensitivity: sensVal
    };

    if (deviceVal !== "") {
        payload.device_index = parseInt(deviceVal);
    }

    fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
}

function pairWithHueButton() {
    const statusEl = document.getElementById('bridge-status');
    const btnPair = document.getElementById('btn-pair');
    const ipInput = document.getElementById('hue-ip');
    const userInput = document.getElementById('hue-username');

    const targetIp = ipInput.value.trim() || null;

    statusEl.className = 'status-box';
    statusEl.textContent = '🔍 Buscando Hue Bridge en la red local... Por favor espera.';
    btnPair.disabled = true;

    fetch('/api/pair_hue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ip: targetIp })
    })
    .then(res => res.json())
    .then(data => {
        btnPair.disabled = false;
        if (data.ip) ipInput.value = data.ip;

        if (data.status === 'button_not_pressed') {
            statusEl.className = 'status-box warn';
            statusEl.innerHTML = `⚠️ <strong>${data.message}</strong>`;
        } else if (data.status === 'success') {
            statusEl.className = 'status-box success';
            statusEl.innerHTML = `✅ <strong>${data.message}</strong>`;
            if (data.username) userInput.value = data.username;
        } else {
            statusEl.className = 'status-box warn';
            statusEl.textContent = `❌ ${data.message}`;
        }
    })
    .catch(err => {
        btnPair.disabled = false;
        statusEl.className = 'status-box warn';
        statusEl.textContent = `❌ Error de red al intentar conectar: ${err}`;
    });
}

function forceTakeover() {
    const statusEl = document.getElementById('bridge-status');
    const btnOverride = document.getElementById('btn-override');

    btnOverride.disabled = true;
    statusEl.className = 'status-box';
    statusEl.textContent = '⚡ Enviando comando de forzado de control a todas las luces...';

    fetch('/api/force_takeover', { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            btnOverride.disabled = false;
            statusEl.className = data.success ? 'status-box success' : 'status-box warn';
            statusEl.innerHTML = data.success ? `✅ <strong>${data.message}</strong>` : `❌ ${data.message}`;
        })
        .catch(err => {
            btnOverride.disabled = false;
            statusEl.className = 'status-box warn';
            statusEl.textContent = `❌ Error al forzar control: ${err}`;
        });
}

function connectBridge() {
    const ip = document.getElementById('hue-ip').value;
    const username = document.getElementById('hue-username').value;
    const statusEl = document.getElementById('bridge-status');

    fetch('/api/connect_bridge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ip: ip, username: username })
    })
    .then(res => res.json())
    .then(data => {
        statusEl.textContent = `Estado: ${data.message}`;
        statusEl.className = data.success ? 'status-box success' : 'status-box warn';
    });
}

// Start WebSocket, check PKCE, load config & Audio Devices on load
window.addEventListener('DOMContentLoaded', () => {
    initWebSocket();
    checkSpotifyUrlStatus();
    loadAppConfig();
    loadAudioDevices();
});
