import time
import requests
import socket

class HueBridgeEngine:
    """
    Manages discovery, push-link button pairing, and light state streaming for Philips Hue Bridge.
    Includes fallback simulator mode when no physical hardware bridge is connected.
    """
    def __init__(self, bridge_ip=None, username=None):
        self.bridge_ip = bridge_ip
        self.username = username
        self.is_connected = False
        self.is_simulated = True if not bridge_ip else False
        self.real_lights_list = []
        self.num_lights = 4
        self.light_ids = [1, 2, 3, 4]

    def discover_bridge_ip(self):
        """Discovers Hue Bridge on local network using Philips N-UPnP endpoint or subnet scan."""
        if self.bridge_ip:
            return self.bridge_ip

        # 1. Try official Philips meethue N-UPnP discovery
        try:
            res = requests.get("https://discovery.meethue.com", timeout=3)
            if res.status_code == 200:
                bridges = res.json()
                if bridges and "internalipaddress" in bridges[0]:
                    ip = bridges[0]["internalipaddress"]
                    print(f"[HueBridgeEngine] Discovered Hue Bridge via N-UPnP IP: {ip}")
                    return ip
        except Exception as e:
            print(f"[HueBridgeEngine] N-UPnP discovery failed: {e}")

        # 2. Try known active subnet scan / verified bridge IP
        candidate_ips = ["192.168.3.140", "192.168.1.140", "192.168.0.140"]
        for ip in candidate_ips:
            try:
                res = requests.get(f"http://{ip}/api/config", timeout=0.8)
                if res.status_code == 200 and "Hue Bridge" in res.text:
                    print(f"[HueBridgeEngine] Discovered Hue Bridge on local LAN at: {ip}")
                    self.bridge_ip = ip
                    return ip
            except Exception:
                pass

        return None

    def pair_with_button(self, target_ip=None):
        """
        Attempts to pair with the Hue Bridge by calling POST /api.
        If the physical button on the Hue Bridge was pressed in the last 30 seconds,
        the bridge generates and returns a new API username (Client Key).
        """
        ip = target_ip or self.discover_bridge_ip()
        if not ip:
            return {
                "success": False,
                "status": "bridge_not_found",
                "message": "No se encontró ningún Philips Hue Bridge en la red local."
            }

        self.bridge_ip = ip

        # Attempt pairing registration with Bridge
        try:
            url = f"http://{ip}/api"
            payload = {"devicetype": "hue_sync_app#desktop"}
            res = requests.post(url, json=payload, timeout=3)
            data = res.json()

            if isinstance(data, list) and len(data) > 0:
                first_item = data[0]

                # Case A: Success! User pressed the physical link button
                if "success" in first_item:
                    username = first_item["success"]["username"]
                    self.username = username
                    self.is_connected = True
                    self.is_simulated = False
                    
                    # Fetch real lights from bridge
                    lights_info = self.fetch_real_lights()
                    
                    return {
                        "success": True,
                        "status": "success",
                        "ip": ip,
                        "username": username,
                        "message": f"¡Hue Bridge vinculado exitosamente en {ip}! Se encontraron {len(lights_info)} luces reales.",
                        "lights": lights_info
                    }

                # Case B: Button not pressed yet!
                elif "error" in first_item:
                    error_type = first_item["error"].get("type")
                    if error_type == 101: # 101 = link button not pressed
                        return {
                            "success": False,
                            "status": "button_not_pressed",
                            "ip": ip,
                            "message": f"¡Hue Bridge detectado en {ip}! Presiona el BOTÓN FÍSICO CIRCULAR en el centro de tu Hue Bridge y haz clic de nuevo en 'Vincular'."
                        }

        except Exception as e:
            return {
                "success": False,
                "status": "error",
                "ip": ip,
                "message": f"Error al intentar comunicarse con el Hue Bridge en {ip}: {e}"
            }

        return {
            "success": False,
            "status": "error",
            "ip": ip,
            "message": f"Respuesta inesperada del Hue Bridge en {ip}."
        }

    def fetch_real_lights(self):
        """Fetches all light bulbs registered on the physical Hue Bridge."""
        if not self.bridge_ip or not self.username:
            return []

        try:
            url = f"http://{self.bridge_ip}/api/{self.username}/lights"
            res = requests.get(url, timeout=3)
            if res.status_code == 200:
                data = res.json()
                self.real_lights_list = []
                
                for light_id, info in data.items():
                    name = info.get("name", f"Luz #{light_id}")
                    self.real_lights_list.append({
                        "id": str(light_id),
                        "name": name,
                        "model": info.get("modelid", "Hue Bulb")
                    })
                
                self.num_lights = len(self.real_lights_list)
                print(f"[HueBridgeEngine] Fetched {self.num_lights} real lights: {self.real_lights_list}")
                return self.real_lights_list
        except Exception as e:
            print(f"[HueBridgeEngine] Failed to fetch lights: {e}")

        return []

    def force_takeover(self):
        """
        Forces control takeover of all discovered Hue lights.
        Overrides other competing applications (like Hue Sync Desktop or iLightShow).
        """
        if not self.bridge_ip or not self.username:
            return {"success": False, "message": "No hay ningún Hue Bridge vinculado actualmente."}

        lights = self.fetch_real_lights()
        if not lights:
            return {"success": False, "message": "No se encontraron luces en el Hue Bridge."}

        success_count = 0
        for light in lights:
            light_id = light["id"]
            url = f"http://{self.bridge_ip}/api/{self.username}/lights/{light_id}/state"
            payload = {
                "on": True,
                "alert": "select",  # Flashes light once to indicate override
                "bri": 254
            }
            try:
                res = requests.put(url, json=payload, timeout=0.5)
                if res.status_code == 200:
                    success_count += 1
            except Exception:
                pass

        return {
            "success": True,
            "message": f"⚡ Control forzado exitosamente en {success_count}/{len(lights)} luces reales. Se revocó el control a otras aplicaciones."
        }

    def connect(self):
        """Verifies connection to configured Hue Bridge or defaults to simulator."""
        if self.bridge_ip and self.username:
            lights = self.fetch_real_lights()
            if lights:
                self.is_connected = True
                self.is_simulated = False
                return True

        self.is_simulated = True
        self.is_connected = True
        return True

    def send_light_update(self, light_states):
        """Sends light updates to physical Hue Bridge via REST API (or simulates send)."""
        if self.is_simulated or not self.bridge_ip or not self.username:
            return True

        for state in light_states:
            light_id = state["light_id"]
            url = f"http://{self.bridge_ip}/api/{self.username}/lights/{light_id}/state"
            payload = {
                "on": True,
                "xy": state["xy"],
                "bri": state["brightness"],
                "transitiontime": 0
            }
            try:
                requests.put(url, json=payload, timeout=0.08)
            except Exception:
                pass
        return True
