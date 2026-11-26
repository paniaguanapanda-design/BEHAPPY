// @ts-nocheck
import { ScrollViewStyleReset } from "expo-router/html";
import type { PropsWithChildren } from "react";

export default function Root({ children }: PropsWithChildren) {
  return (
    <html lang="es" translate="no" style={{ height: "100%" }}>
      <head>
        <meta charSet="utf-8" />
        {/* Sin esto, Chrome traduce la app a su idioma y pisa el idioma elegido dentro de la app (p. ej. "IT" aparece como "ÉL") */}
        <meta name="google" content="notranslate" />
        <meta httpEquiv="X-UA-Compatible" content="IE=edge" />
        <meta
          name="viewport"
          content="width=device-width, initial-scale=1, shrink-to-fit=no, viewport-fit=cover"
        />
        <title>BE HAPPY: diagnostica problemas del hogar con una foto</title>
        <meta name="description" content="Fotografía un problema de casa y la IA te dice qué pasa y cómo arreglarlo. Conecta con especialistas cerca de ti." />
        <meta name="robots" content="index, follow" />
        <link rel="canonical" href="https://app.be-happyapp.com/" />
        {/* Redes sociales y vista previa de enlaces (WhatsApp, Facebook, LinkedIn...) */}
        <meta property="og:type" content="website" />
        <meta property="og:site_name" content="BE HAPPY" />
        <meta property="og:locale" content="es_ES" />
        <meta property="og:title" content="BE HAPPY: diagnostica problemas del hogar con una foto" />
        <meta property="og:description" content="Fotografía un problema de casa y la IA te dice qué pasa y cómo arreglarlo." />
        <meta property="og:url" content="https://app.be-happyapp.com/" />
        <meta property="og:image" content="https://app.be-happyapp.com/icons/icon-512.png" />
        <meta name="twitter:card" content="summary" />
        <meta name="twitter:title" content="BE HAPPY: diagnostica problemas del hogar con una foto" />
        <meta name="twitter:description" content="Fotografía un problema de casa y la IA te dice qué pasa y cómo arreglarlo." />
        <meta name="twitter:image" content="https://app.be-happyapp.com/icons/icon-512.png" />
        {/* Datos estructurados para buscadores */}
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              "@context": "https://schema.org",
              "@type": "MobileApplication",
              name: "BE HAPPY",
              description: "Fotografía un problema de casa y la IA te dice qué pasa y cómo arreglarlo.",
              applicationCategory: "LifestyleApplication",
              operatingSystem: "Android, Web",
              inLanguage: "es",
              url: "https://app.be-happyapp.com/",
              offers: { "@type": "Offer", price: "0", priceCurrency: "EUR" },
            }),
          }}
        />
        {/* Installable web app (PWA) */}
        <link rel="manifest" href="/manifest.webmanifest" />
        <meta name="theme-color" content="#0B5C55" />
        <link rel="icon" type="image/png" sizes="48x48" href="/icons/favicon-48.png" />
        <link rel="apple-touch-icon" href="/icons/apple-touch-icon.png" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
        <meta name="apple-mobile-web-app-title" content="BE HAPPY" />
        <script
          dangerouslySetInnerHTML={{
            __html: `if ("serviceWorker" in navigator && location.hostname !== "localhost") { window.addEventListener("load", function () { navigator.serviceWorker.register("/sw.js").catch(function () {}); }); }`,
          }}
        />
        {/*
          Disable body scrolling on web to make ScrollView components work correctly.
          If you want to enable scrolling, remove `ScrollViewStyleReset` and
          set `overflow: auto` on the body style below.
        */}
        <ScrollViewStyleReset />
        <style
          dangerouslySetInnerHTML={{
            __html: `
              body > div:first-child { position: fixed !important; top: 0; left: 0; right: 0; bottom: 0; }
              [role="tablist"] [role="tab"] * { overflow: visible !important; }
              [role="heading"], [role="heading"] * { overflow: visible !important; }
            `,
          }}
        />
      </head>
      <body
        style={{
          margin: 0,
          height: "100%",
          backgroundColor: "#F2FBF7",
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {children}
      </body>
    </html>
  );
}
