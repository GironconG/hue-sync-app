import io
import time
import json
import base64
import urllib.request
import urllib.parse
import urllib.error
import colorsys
import numpy as np
try:
    from PIL import Image
    HAS_PIL = True
except Exception:
    HAS_PIL = False

class MediaEngine:
    """
    Integrates Spotify Web API (OAuth PKCE & Refresh Tokens), Apple Music / iTunes API.
    Extracts song metadata (Title, Artist, Album, Cover Art) and generates dynamic HSV color palettes.
    """
    def __init__(self):
        self.current_track = {
            "title": "Esperando reproducción...",
            "artist": "Conecta Spotify o Apple Music",
            "album": "",
            "artwork_url": "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=300&q=80",
            "provider": "none",
            "progress_ms": 0,
            "duration_ms": 1000,
            "palette_hsv": []
        }
        self.spotify_client_id = None
        self.spotify_client_secret = None
        self.spotify_access_token = None
        self.spotify_refresh_token = None
        self.spotify_token_expires_at = 0
        self.last_fetch_time = 0

    def set_spotify_credentials(self, client_id=None, client_secret=None, access_token=None, refresh_token=None):
        if client_id: self.spotify_client_id = client_id.strip()
        if client_secret: self.spotify_client_secret = client_secret.strip()
        if access_token: self.spotify_access_token = access_token.strip()
        if refresh_token: self.spotify_refresh_token = refresh_token.strip()

    def exchange_spotify_code(self, code, redirect_uri, client_id, client_secret=None):
        """Exchanges Spotify OAuth authorization code for Access Token & Refresh Token."""
        try:
            url = "https://accounts.spotify.com/api/token"
            payload_dict = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            }
            headers = {
                "Content-Type": "application/x-www-form-urlencoded"
            }
            if client_id and client_secret:
                auth_str = f"{client_id}:{client_secret}"
                b64_auth = base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')
                headers["Authorization"] = f"Basic {b64_auth}"
            else:
                payload_dict["client_id"] = client_id

            payload = urllib.parse.urlencode(payload_dict)
            req = urllib.request.Request(url, data=payload.encode('utf-8'), headers=headers)
            res = urllib.request.urlopen(req, timeout=5)
            if res.status == 200:
                data = json.loads(res.read().decode('utf-8'))
                self.spotify_access_token = data.get("access_token")
                self.spotify_refresh_token = data.get("refresh_token")
                expires_in = data.get("expires_in", 3600)
                self.spotify_token_expires_at = time.time() + expires_in - 60
                print(f"[MediaEngine] Spotify Token Exchange Success!")
                return data
        except urllib.error.HTTPError as e:
            err_body = e.read().decode('utf-8')
            print(f"[MediaEngine] Spotify Token Exchange HTTP Error {e.code}: {err_body}")
        except Exception as e:
            print(f"[MediaEngine] Spotify Token Exchange Error: {e}")
        return None

    def refresh_spotify_token(self):
        """Refreshes Spotify Access Token using saved Refresh Token."""
        if not self.spotify_refresh_token or not self.spotify_client_id:
            return False

        try:
            url = "https://accounts.spotify.com/api/token"
            payload_dict = {
                "grant_type": "refresh_token",
                "refresh_token": self.spotify_refresh_token,
            }
            headers = {
                "Content-Type": "application/x-www-form-urlencoded"
            }
            if self.spotify_client_id and self.spotify_client_secret:
                auth_str = f"{self.spotify_client_id}:{self.spotify_client_secret}"
                b64_auth = base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')
                headers["Authorization"] = f"Basic {b64_auth}"
            else:
                payload_dict["client_id"] = self.spotify_client_id

            payload = urllib.parse.urlencode(payload_dict)
            req = urllib.request.Request(url, data=payload.encode('utf-8'), headers=headers)
            res = urllib.request.urlopen(req, timeout=5)
            if res.status == 200:
                data = json.loads(res.read().decode('utf-8'))
                self.spotify_access_token = data.get("access_token")
                if data.get("refresh_token"):
                    self.spotify_refresh_token = data.get("refresh_token")
                expires_in = data.get("expires_in", 3600)
                self.spotify_token_expires_at = time.time() + expires_in - 60
                print("[MediaEngine] Spotify Access Token refreshed successfully!")
                return True
        except urllib.error.HTTPError as e:
            print(f"[MediaEngine] Spotify Token Refresh HTTP Error {e.code}: {e.read().decode('utf-8')}")
        except Exception as e:
            print(f"[MediaEngine] Spotify Token Refresh Error: {e}")
        return False

    def fetch_spotify_currently_playing(self):
        """Queries Spotify Web API GET /v1/me/player/currently-playing."""
        if time.time() > self.spotify_token_expires_at and self.spotify_refresh_token:
            self.refresh_spotify_token()

        if not self.spotify_access_token:
            return None

        try:
            url = "https://api.spotify.com/v1/me/player/currently-playing"
            req = urllib.request.Request(url, headers={
                "Authorization": f"Bearer {self.spotify_access_token}",
                "User-Agent": "HueSync/1.0"
            })
            res = urllib.request.urlopen(req, timeout=3)
            if res.status == 200:
                data = json.loads(res.read().decode('utf-8'))
                if data and "item" in data and data["item"]:
                    item = data["item"]
                    title = item.get("name", "Desconocido")
                    artists = ", ".join([a["name"] for a in item.get("artists", [])])
                    album_name = item.get("album", {}).get("name", "")
                    images = item.get("album", {}).get("images", [])
                    artwork_url = images[0]["url"] if images else None

                    track_id = item.get("id")
                    progress_ms = data.get("progress_ms", 0)
                    duration_ms = item.get("duration_ms", 1000)
                    is_playing = data.get("is_playing", True)

                    if title != self.current_track["title"]:
                        if artwork_url:
                            palette = self.extract_palette_from_url(artwork_url)
                            self.current_track["palette_hsv"] = palette
                        
                        if track_id:
                            self.spotify_features = self.fetch_spotify_audio_features(track_id)
                            self.spotify_analysis = self.fetch_spotify_audio_analysis(track_id)
                            if self.spotify_features:
                                print(f"[MediaEngine] Spotify Audio Features for '{title}': Energy={self.spotify_features.get('energy')}, Tempo={self.spotify_features.get('tempo')} BPM")

                    self.current_track.update({
                        "id": track_id,
                        "title": title,
                        "artist": artists,
                        "album": album_name,
                        "artwork_url": artwork_url or self.current_track["artwork_url"],
                        "provider": "spotify",
                        "is_playing": is_playing,
                        "progress_ms": progress_ms,
                        "duration_ms": duration_ms
                    })
                    return self.current_track
        except Exception as e:
            print(f"[MediaEngine] Spotify API Error: {e}")
        return None

    def fetch_spotify_audio_features(self, track_id):
        if not track_id or not self.spotify_access_token:
            return None
        try:
            url = f"https://api.spotify.com/v1/audio-features/{track_id}"
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.spotify_access_token}"})
            res = urllib.request.urlopen(req, timeout=3)
            if res.status == 200:
                return json.loads(res.read().decode('utf-8'))
        except Exception as e:
            print(f"[MediaEngine] Audio features error: {e}")
        return None

    def fetch_spotify_audio_analysis(self, track_id):
        if not track_id or not self.spotify_access_token:
            return None
        try:
            url = f"https://api.spotify.com/v1/audio-analysis/{track_id}"
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.spotify_access_token}"})
            res = urllib.request.urlopen(req, timeout=4)
            if res.status == 200:
                return json.loads(res.read().decode('utf-8'))
        except Exception as e:
            print(f"[MediaEngine] Audio analysis error: {e}")
        return None

    def get_spotify_live_analysis_metrics(self):
        """Calculates exact millisecond beat pulse, energy, and section loudness from Spotify Audio Analysis."""
        if not self.current_track.get("is_playing", True):
            return {
                "is_spotify_beat": False,
                "energy": 0.0,
                "tempo": 0.0,
                "danceability": 0.0,
                "is_playing": False,
                "current_pos_sec": 0.0
            }

        if not hasattr(self, 'spotify_analysis') or not self.spotify_analysis or not self.current_track.get("progress_ms"):
            return None

        elapsed_since_fetch = time.time() - self.last_fetch_time
        current_pos_sec = (self.current_track.get("progress_ms", 0) / 1000.0) + elapsed_since_fetch

        beats = self.spotify_analysis.get("beats", [])
        is_beat = False
        for b in beats:
            start = b.get("start", 0)
            if abs(current_pos_sec - start) < 0.09:
                is_beat = True
                break

        features = getattr(self, 'spotify_features', None) or {}
        energy = features.get("energy", 0.5)
        tempo = features.get("tempo", 120.0)
        danceability = features.get("danceability", 0.5)

        return {
            "is_spotify_beat": is_beat,
            "energy": energy,
            "tempo": tempo,
            "danceability": danceability,
            "current_pos_sec": round(current_pos_sec, 2)
        }

    def fetch_apple_music_itunes_search(self, song_query):
        """Queries iTunes / Apple Music API for song metadata and high-res cover artwork."""
        if not song_query:
            return None
        try:
            encoded = urllib.parse.quote(song_query)
            url = f"https://itunes.apple.com/search?term={encoded}&entity=song&limit=1"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            res = urllib.request.urlopen(req, timeout=4)
            data = json.loads(res.read().decode('utf-8'))
            if data and data.get("results"):
                item = data["results"][0]
                title = item.get("trackName", song_query)
                artist = item.get("artistName", "Artista Apple Music")
                album = item.get("collectionName", "")
                art_url = item.get("artworkUrl100", "").replace("100x100bb", "600x600bb")

                palette = self.extract_palette_from_url(art_url) if art_url else []

                self.current_track.update({
                    "title": title,
                    "artist": artist,
                    "album": album,
                    "artwork_url": art_url,
                    "provider": "apple_music",
                    "palette_hsv": palette
                })
                return self.current_track
        except Exception as e:
            print(f"[MediaEngine] Apple Music search error: {e}")
        return None

    def extract_palette_from_url(self, image_url):
        """Downloads cover artwork and extracts top 4 vibrant HSV color tuples."""
        if not HAS_PIL or not image_url or image_url.startswith("/static"):
            return []
        try:
            req = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0"})
            img_bytes = urllib.request.urlopen(req, timeout=3).read()
            img = Image.open(io.BytesIO(img_bytes)).convert("RGB").resize((60, 60))
            
            colors = img.getcolors(maxcolors=3600)
            if not colors:
                return []
            
            sorted_colors = sorted(colors, key=lambda x: x[0], reverse=True)
            hsv_palette = []

            for count, (r, g, b) in sorted_colors:
                h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
                if s > 0.15 and v > 0.2:
                    hsv_palette.append((round(h, 3), round(s, 3), round(v, 3)))
                    if len(hsv_palette) >= 4:
                        break

            if not hsv_palette and sorted_colors:
                for count, (r, g, b) in sorted_colors[:4]:
                    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
                    hsv_palette.append((round(h, 3), round(s, 3), round(v, 3)))

            print(f"[MediaEngine] Extracted Cover Art HSV Palette: {hsv_palette}")
            return hsv_palette
        except Exception as e:
            print(f"[MediaEngine] Failed to extract palette from image: {e}")
            return []

    def get_track_info(self):
        now = time.time()
        if (self.spotify_access_token or self.spotify_refresh_token) and (now - self.last_fetch_time > 3.0):
            self.last_fetch_time = now
            self.fetch_spotify_currently_playing()
        return self.current_track
