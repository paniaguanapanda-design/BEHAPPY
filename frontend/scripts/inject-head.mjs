// Expo "output: single" (SPA) genera un index.html con <head> minimo y no usa app/+html.tsx.
// Este paso, despues de "expo export", mete en dist/index.html el titulo, las metaetiquetas para
// buscadores y redes, el manifiesto de la app instalable, el registro del service worker y
// translate="no" (para que Chrome no traduzca la app y pise el idioma elegido dentro de ella).
import { readFileSync, writeFileSync } from "node:fs";

const file = "dist/index.html";
let html = readFileSync(file, "utf8");

const TITLE = "BE HAPPY: diagnostica problemas del hogar con una foto";
const DESC = "Fotografía un problema de casa y la IA te dice qué pasa y cómo arreglarlo. Conecta con especialistas cerca de ti.";
const URL = "https://app.be-happyapp.com/";
const IMG = "https://app.be-happyapp.com/icons/icon-512.png";

const head = `
    <title>${TITLE}</title>
    <meta name="description" content="${DESC}" />
    <meta name="robots" content="index, follow" />
    <meta name="google" content="notranslate" />
    <link rel="canonical" href="${URL}" />
    <meta property="og:type" content="website" />
    <meta property="og:site_name" content="BE HAPPY" />
    <meta property="og:locale" content="es_ES" />
    <meta property="og:title" content="${TITLE}" />
    <meta property="og:description" content="${DESC}" />
    <meta property="og:url" content="${URL}" />
    <meta property="og:image" content="${IMG}" />
    <meta name="twitter:card" content="summary" />
    <meta name="twitter:title" content="${TITLE}" />
    <meta name="twitter:description" content="${DESC}" />
    <meta name="twitter:image" content="${IMG}" />
    <script type="application/ld+json">${JSON.stringify({
      "@context": "https://schema.org",
      "@type": "MobileApplication",
      name: "BE HAPPY",
      description: DESC,
      applicationCategory: "LifestyleApplication",
      operatingSystem: "Android, Web",
      inLanguage: "es",
      url: URL,
      offers: { "@type": "Offer", price: "0", priceCurrency: "EUR" },
    })}</script>
    <link rel="manifest" href="/manifest.webmanifest" />
    <meta name="theme-color" content="#0B5C55" />
    <link rel="icon" type="image/png" sizes="48x48" href="/icons/favicon-48.png" />
    <link rel="apple-touch-icon" href="/icons/apple-touch-icon.png" />
    <meta name="apple-mobile-web-app-capable" content="yes" />
    <meta name="mobile-web-app-capable" content="yes" />
    <meta name="apple-mobile-web-app-title" content="BE HAPPY" />
    <script>if ("serviceWorker" in navigator && location.hostname !== "localhost") { window.addEventListener("load", function () { navigator.serviceWorker.register("/sw.js").catch(function () {}); }); }</script>
`;

// Quita lo que Expo ya puso (titulo viejo) para no duplicar etiquetas
html = html.replace(/<title>[\s\S]*?<\/title>/, "");
html = html.replace(/<html lang="[^"]*"/, '<html lang="es" translate="no"');
if (!html.includes("</head>")) throw new Error("dist/index.html sin </head>");
html = html.replace("</head>", `${head}  </head>`);
writeFileSync(file, html);
console.log("inject-head: OK");
