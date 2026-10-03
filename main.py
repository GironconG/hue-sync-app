import os
import asyncio
import json
import time
import urllib.parse
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from pydantic import BaseModel
from typing import Optional

from modules.audio_engine import AudioEngine
from modules.color_mapper import ColorMapper
from modules.hue_engine import HueBridgeEngine
from modules.media_engine import MediaEngine

app = FastAPI(title="HueSync Base App")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "web", "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "web", "templates"))

# Helper for persistent configuration
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_config(updates: dict):
    config = load_config()
    config.update(updates)
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"[Config] Error saving config.json: {e}")

# Initialize Core Engines
config = load_config()

audio_engine = AudioEngine(
    mode=config.get("audio_mode", "simulator"),
    device_index=config.get("device_index"),
    sensitivity=config.get("sensitivity", 3.0)
)
color_mapper = ColorMapper(palette_name=config.get("theme", "cyberpunk"), num_lights=4)
hue_engine = HueBridgeEngine(
    bridge_ip=config.get("hue_ip"),
    username=config.get("hue_username")
)
media_engine = MediaEngine()

if config.get("spotify_client_id"):
    media_engine.set_spotify_credentials(
        client_id=config.get("spotify_client_id"),
        client_secret=config.get("spotify_client_secret"),
        access_token=config.get("spotify_access_token"),
        refresh_token=config.get("spotify_refresh_token")
    )

@app.on_event("startup")
def startup_event():
    audio_engine.start()
    # Attempt connecting to Hue Bridge using saved credentials
    if hue_engine.bridge_ip and hue_engine.username:
        print(f"[Startup] Connecting to saved Hue Bridge at {hue_engine.bridge_ip}...")
        hue_engine.connect()
        if not hue_engine.is_simulated:
            color_mapper.num_lights = max(4, hue_engine.num_lights)

@app.on_event("shutdown")
def shutdown_event():
    audio_engine.stop()

class SettingsPayload(BaseModel):
    mode: str
    theme: str
    device_index: Optional[int] = None
    sensitivity: Optional[float] = 3.0

class BridgePayload(BaseModel):
    ip: Optional[str] = None
    username: Optional[str] = None

class SpotifyClientPayload(BaseModel):
    client_id: str
    client_secret: Optional[str] = ""

class SearchMediaPayload(BaseModel):
    query: str

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/api/config")
async def get_app_config():
    """Returns persistent app configuration for UI initial state."""
    cfg = load_config()
    return {
        "hue_ip": hue_engine.bridge_ip or cfg.get("hue_ip", ""),
        "hue_username": hue_engine.username or cfg.get("hue_username", ""),
        "is_connected": hue_engine.is_connected and not hue_engine.is_simulated,
        "spotify_connected": bool(media_engine.spotify_access_token or media_engine.spotify_refresh_token),
        "spotify_client_id": cfg.get("spotify_client_id", ""),
        "real_lights": hue_engine.real_lights_list
    }

@app.get("/api/audio_devices")
async def get_audio_devices():
    return {"devices": AudioEngine.get_available_devices()}

@app.post("/api/settings")
async def update_settings(payload: SettingsPayload):
    audio_engine.set_mode(payload.mode)
    color_mapper.set_palette(payload.theme)
    if payload.device_index is not None:
        audio_engine.set_device(payload.device_index)
    if payload.sensitivity is not None:
        audio_engine.set_sensitivity(payload.sensitivity)
    
    save_config({
        "audio_mode": payload.mode,
        "theme": payload.theme,
        "device_index": payload.device_index,
        "sensitivity": payload.sensitivity
    })
    return {"status": "ok", "mode": payload.mode, "theme": payload.theme}

@app.post("/api/pair_hue")
async def pair_hue(payload: BridgePayload):
    result = hue_engine.pair_with_button(target_ip=payload.ip)
    if result["success"]:
        color_mapper.num_lights = max(4, hue_engine.num_lights)
        save_config({
            "hue_ip": result["ip"],
            "hue_username": result["username"]
        })
    return result

@app.post("/api/force_takeover")
async def force_takeover():
    return hue_engine.force_takeover()

@app.post("/api/connect_bridge")
async def connect_bridge(payload: BridgePayload):
    hue_engine.bridge_ip = payload.ip
    hue_engine.username = payload.username
    success = hue_engine.connect()
    if success and not hue_engine.is_simulated:
        save_config({
            "hue_ip": payload.ip,
            "hue_username": payload.username
        })
        return {"success": True, "message": f"Conectado y guardado Hue Bridge en {payload.ip}. {len(hue_engine.real_lights_list)} luces encontradas."}
    else:
        return {"success": True, "message": "Corriendo en Modo Simulación Virtual."}

# Spotify OAuth Flow
DEFAULT_SPOTIFY_CLIENT_ID = "9a0069b06ee54e049ad75eaf99e986fd"
DEFAULT_SPOTIFY_CLIENT_SECRET = "fc9bd1da860d430fae4cdf4039d956ab"

def get_redirect_uri(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host", request.url.netloc)
    return f"{proto}://{host}/spotify/callback"

class DirectTokenPayload(BaseModel):
    token: str

@app.get("/spotify/login")
async def spotify_login(request: Request, client_id: Optional[str] = None):
    cfg = load_config()
    cid = client_id or cfg.get("spotify_client_id") or DEFAULT_SPOTIFY_CLIENT_ID
    save_config({"spotify_client_id": cid})
    
    redirect_uri = get_redirect_uri(request)
    scope = "user-read-currently-playing user-read-playback-state user-read-playback-position"
    
    params = {
        "response_type": "code",
        "client_id": cid,
        "scope": scope,
        "redirect_uri": redirect_uri,
        "show_dialog": "true"
    }
    spotify_url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(params)
    return RedirectResponse(spotify_url)

@app.get("/spotify/callback")
async def spotify_callback(request: Request, code: str):
    cfg = load_config()
    cid = cfg.get("spotify_client_id", DEFAULT_SPOTIFY_CLIENT_ID)
    csecret = cfg.get("spotify_client_secret", DEFAULT_SPOTIFY_CLIENT_SECRET)
    redirect_uri = get_redirect_uri(request)

    result = media_engine.exchange_spotify_code(code, redirect_uri, cid, csecret)
    if result:
        save_config({
            "spotify_client_id": cid,
            "spotify_client_secret": csecret,
            "spotify_access_token": media_engine.spotify_access_token,
            "spotify_refresh_token": media_engine.spotify_refresh_token
        })
        return RedirectResponse("/?spotify=connected")
    return RedirectResponse("/?spotify=error")

@app.post("/api/spotify_auth")
async def spotify_auth_direct(payload: DirectTokenPayload):
    media_engine.spotify_access_token = payload.token
    save_config({"spotify_access_token": payload.token})
    return {"success": True, "message": "Token de Spotify guardado."}

@app.post("/api/save_spotify_client")
async def save_spotify_client(payload: SpotifyClientPayload):
    save_config({
        "spotify_client_id": payload.client_id,
        "spotify_client_secret": payload.client_secret
    })
    media_engine.set_spotify_credentials(client_id=payload.client_id, client_secret=payload.client_secret)
    return {"success": True, "message": "Credenciales de Spotify guardadas."}

@app.post("/api/search_media")
async def search_media(payload: SearchMediaPayload):
    track_info = media_engine.fetch_apple_music_itunes_search(payload.query)
    if track_info and track_info.get("palette_hsv"):
        color_mapper.set_custom_hsv_palette(track_info["palette_hsv"])
        return {"success": True, "track": track_info}
    return {"success": False, "message": "No se encontraron resultados para la consulta."}

@app.websocket("/ws/sync")
async def websocket_sync(websocket: WebSocket):
    await websocket.accept()
    last_hue_update = 0.0
    try:
        while True:
            # 1. Fetch live metrics from Audio Engine
            audio_metrics = audio_engine.get_metrics()

            # 2. Fetch live track info from Media Engine
            track_info = media_engine.get_track_info()

            # Apply artwork palette if selected
            if color_mapper.palette_name == "album_art" and track_info.get("palette_hsv"):
                color_mapper.set_custom_hsv_palette(track_info["palette_hsv"])

            # 3. Map metrics to Light States (using real lights if paired)
            real_lights = hue_engine.real_lights_list if not hue_engine.is_simulated else None
            light_states = color_mapper.compute_light_states(audio_metrics, real_lights=real_lights)

            # 4. Non-blocking async dispatch of light updates to physical Hue Bridge (~10 Hz)
            now = time.time()
            if not hue_engine.is_simulated and (now - last_hue_update) >= 0.1:
                last_hue_update = now
                asyncio.create_task(asyncio.to_thread(hue_engine.send_light_update, light_states))

            # 5. Stream payload to Web Dashboard via WebSocket (~30 FPS)
            payload = {
                "audio": audio_metrics,
                "track": track_info,
                "lights": light_states
            }
            await websocket.send_text(json.dumps(payload))

            # ~30 FPS loop (33ms sleep)
            await asyncio.sleep(0.033)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[WebSocket] Disconnected: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
