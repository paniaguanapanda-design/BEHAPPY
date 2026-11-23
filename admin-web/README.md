# BE HAPPY Admin

Panel privado de BE HAPPY: personas activas, diagnósticos, uso de la IA, especialistas, solicitudes y ferreterías.
Es una web aparte de la app pública, instalable en el móvil, sin dependencias ni compilación (HTML, CSS y JS).

- **Dirección:** https://admin.be-happyapp.com (proyecto `behappy-admin` en Vercel, carpeta raíz `admin-web`).
- **Acceso:** la clave `ADMIN_TOKEN` del servidor en Render. Se guarda solo en el dispositivo donde la escribes.
- **Datos:** `GET /api/admin/stats` del servidor; Vercel reenvía `/api/*` a Render (ver `vercel.json`).
- **Instalar:** en Android/Chrome, botón «Instalar» del panel o menú ⋮ → «Instalar aplicación».
  En iPhone/Safari: Compartir → «Añadir a pantalla de inicio».
- No la indexan los buscadores (`robots.txt`, `X-Robots-Tag` y `<meta name="robots">`).
