# BE HAPPY

App movil (Android) que diagnostica problemas del hogar con una foto usando IA.

## Tecnologia
- App: Expo / React Native (carpeta frontend)
- Servidor: FastAPI + MongoDB (carpeta backend)
- IA: Google Gemini
- Fotos: Cloudflare R2
- Membresia: RevenueCat
- Hosting: Render

## Seguridad
Los archivos .env nunca se suben a Git.

## Pruebas del backend
Desde `backend`, instala las dependencias de desarrollo y ejecuta la suite:

```bash
python -m pip install -r requirements-test.txt
python -m pytest
```

Las pruebas usan una base MongoDB separada (`MONGO_URL` y `DB_NAME`).

La promocion de registro web requiere que `WEB_PROXY_KEY` este configurada de forma privada tanto en el backend como en el proxy web.
