import colorsys
import math

PALETTES = {
    "cyberpunk": [
        (280/360, 1.0, 1.0), # Neon Magenta
        (180/360, 1.0, 1.0), # Cyan
        (220/360, 0.9, 0.8), # Deep Blue
        (320/360, 1.0, 1.0)  # Electric Pink
    ],
    "sunset": [
        (10/360, 1.0, 1.0),  # Bright Orange-Red
        (40/360, 1.0, 1.0),  # Golden Yellow
        (330/360, 0.9, 0.9), # Deep Rose
        (260/360, 0.8, 0.7)  # Twilight Purple
    ],
    "neon_party": [
        (120/360, 1.0, 1.0), # Electric Lime
        (300/360, 1.0, 1.0), # Fuchsia
        (60/360, 1.0, 1.0),  # Yellow
        (200/360, 1.0, 1.0)  # Neon Blue
    ],
    "chill_vibes": [
        (160/360, 0.8, 0.8), # Mint Teal
        (210/360, 0.7, 0.9), # Soft Blue
        (270/360, 0.6, 0.7), # Lavender
        (140/360, 0.9, 0.8)  # Emerald
    ],
    "album_art": [
        (280/360, 1.0, 1.0),
        (180/360, 1.0, 1.0),
        (220/360, 0.9, 0.8),
        (320/360, 1.0, 1.0)
    ]
}

class ColorMapper:
    """
    Translates Audio Engine metrics into Light Bulb States (RGB, Brightness, Flash).
    Supports color themes and dynamic Album Artwork palette extraction.
    """
    def __init__(self, palette_name="cyberpunk", num_lights=4):
        self.palette_name = palette_name
        self.num_lights = num_lights
        self.hue_shift = 0.0

    def set_palette(self, name):
        if name in PALETTES:
            self.palette_name = name

    def set_custom_hsv_palette(self, hsv_list):
        if hsv_list and len(hsv_list) > 0:
            PALETTES["album_art"] = hsv_list
            self.palette_name = "album_art"

    def compute_light_states(self, metrics, real_lights=None):
        bass = metrics["bass"]
        mids = metrics["mids"]
        treble = metrics["treble"]
        is_beat = metrics["is_beat"]

        palette = PALETTES.get(self.palette_name, PALETTES["cyberpunk"])
        
        # Slowly drift base hue over time based on mids
        self.hue_shift = (self.hue_shift + 0.005 + (mids * 0.01)) % 1.0

        light_states = []

        # Determine light target list
        if real_lights and len(real_lights) > 0:
            target_list = real_lights
        else:
            target_list = [{"id": i + 1, "name": f"Luz Virtual #{i + 1}"} for i in range(self.num_lights)]

        for i, light_info in enumerate(target_list):
            light_id = light_info["id"]
            light_name = light_info.get("name", f"Luz #{light_id}")

            # Base color selection per bulb from palette
            base_h, base_s, base_v = palette[i % len(palette)]
            
            # Dynamic Hue offset per bulb based on music
            final_hue = (base_h + self.hue_shift + (i * 0.15)) % 1.0
            
            # Saturation boosts with mids
            final_sat = float(max(0.4, min(1.0, base_s * (0.7 + mids * 0.5))))

            # Brightness calculation:
            brightness = float(min(1.0, 0.15 + (mids * 0.5) + (bass * 0.35)))
            
            # Beat flash effect
            if is_beat:
                if i % 2 == 0:  # Alternate lights flash on beat
                    brightness = 1.0
                    final_sat = 1.0

            # Convert HSV to RGB (0 - 255)
            r, g, b = colorsys.hsv_to_rgb(final_hue, final_sat, brightness)
            rgb_255 = [int(r * 255), int(g * 255), int(b * 255)]
            
            # CIE xy approximation for Hue API
            xy = self._rgb_to_xy(r, g, b)

            light_states.append({
                "light_id": light_id,
                "name": light_name,
                "rgb": rgb_255,
                "hex": f"#{rgb_255[0]:02x}{rgb_255[1]:02x}{rgb_255[2]:02x}",
                "xy": xy,
                "brightness": int(brightness * 254),
                "is_flashing": is_beat and (i % 2 == 0)
            })

        return light_states

    @staticmethod
    def _rgb_to_xy(r, g, b):
        """Converts normalized RGB (0..1) to approximate CIE xy for Philips Hue API."""
        r = (r / 12.92) if r <= 0.04045 else ((r + 0.055) / 1.055) ** 2.4
        g = (g / 12.92) if g <= 0.04045 else ((g + 0.055) / 1.055) ** 2.4
        b = (b / 12.92) if b <= 0.04045 else ((b + 0.055) / 1.055) ** 2.4

        X = r * 0.664511 + g * 0.154324 + b * 0.162028
        Y = r * 0.283881 + g * 0.639419 + b * 0.076700
        Z = r * 0.000088 + g * 0.085453 + b * 0.897098

        sum_XYZ = X + Y + Z
        if sum_XYZ == 0:
            return [0.0, 0.0]
        
        return [round(X / sum_XYZ, 4), round(Y / sum_XYZ, 4)]
