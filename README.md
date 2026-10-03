# 💡⚡ HueSync Base App (Réplica iLightShow)

Sincronizador en tiempo real de luces inteligentes **Philips Hue** con reproducción de música (Spotify Web API / Apple Music / iTunes API) y captura de espectro de audio FFT de 60 FPS (micrófono o mezclador estéreo).

## ✨ Características Principales

- 🎵 **Sincronización en Tiempo Real:** Análisis FFT (Bajos, Medios, Agudos) y Detección de Ritmo / Beats a 30-60 FPS.
- 🎨 **Color Matching de Portadas:** Extracción automática de paletas cuadráticas HSV desde portadas de álbumes de Spotify / Apple Music.
- 🟢 **Spotify OAuth Completo:** Autenticación oficial Backend con actualización automática de Access/Refresh Tokens.
- 💡 **Auto-Discovery & Pairing Hue:** Detección automática en red local por SSDP / mDNS y emparejamiento con el botón físico del Hue Bridge.
- ⚡ **Forzado de Control Override:** Reclamación prioritaria de comandos de luces frente a otras apps o escenas activas.
- 🌐 **Web Dashboard 60 FPS:** Interfaz web fluida con visualizador de onda y simulación 3D virtual de bombillas.

## 🚀 Instalación y Uso Local

```bash
# 1. Clonar repositorio
git clone <tu-repo-url>
cd hue_sync_app

# 2. Instalar dependencias Python
pip install -r requirements.txt

# 3. Ejecutar aplicación servidor
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Abre tu navegador en `http://127.0.0.1:8000`.

## ⚙️ Despliegue en Vercel

1. Instala Vercel CLI o conecta tu repositorio de GitHub directamente en [Vercel Dashboard](https://vercel.com).
2. El archivo `vercel.json` incluido desplegará el backend de FastAPI como funciones Serverless en la nube.

> ℹ️ **Nota sobre el entorno Serverless en la Nube:**  
> Las luces Philips Hue y los micrófonos de audio son dispositivos de tu **red local / hardware físico**. Para controlar las luces reales de tu casa con el micrófono o mezclador estéreo de tu PC, ejecuta la app en modo local. La versión en Vercel te permite utilizar el Dashboard Web, probar la búsqueda de canciones de Apple Music / Spotify y visualizar la simulación virtual.

## 📄 Licencia

MIT
