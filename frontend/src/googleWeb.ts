// Google sign-in for the web app (Google Identity Services). Shows Google's own button in a small sheet and
// resolves with the ID token, which the backend checks exactly like the one from the Android app.
// The web origin (e.g. https://app.be-happyapp.com) must be listed under "Authorized JavaScript origins"
// of the OAuth web client in Google Cloud.
const GIS_SRC = "https://accounts.google.com/gsi/client";
let loading: Promise<void> | null = null;

function loadGis(): Promise<void> {
  if ((window as any).google?.accounts?.id) return Promise.resolve();
  if (!loading) {
    loading = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = GIS_SRC;
      s.async = true;
      s.onload = () => resolve();
      s.onerror = () => {
        loading = null;
        reject(new Error("No se pudo cargar el acceso con Google."));
      };
      document.head.appendChild(s);
    });
  }
  return loading;
}

export async function googleWebIdToken(clientId: string, lang: string, cancelLabel: string): Promise<string | null> {
  await loadGis();
  const google = (window as any).google;
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.style.cssText =
      "position:fixed;inset:0;z-index:99999;background:rgba(14,42,39,.55);display:flex;align-items:center;justify-content:center;padding:24px";
    const card = document.createElement("div");
    card.style.cssText =
      "background:#fff;border-radius:28px;padding:28px 24px;display:flex;flex-direction:column;align-items:center;gap:16px;min-width:280px;box-shadow:0 20px 50px rgba(0,0,0,.25)";
    const slot = document.createElement("div");
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.textContent = cancelLabel;
    cancel.style.cssText =
      "border:0;background:transparent;color:#0B5C55;font:800 15px system-ui,sans-serif;padding:10px 16px;cursor:pointer";
    card.append(slot, cancel);
    overlay.appendChild(card);

    let done = false;
    const finish = (token: string | null) => {
      if (done) return;
      done = true;
      overlay.remove();
      resolve(token);
    };
    cancel.onclick = () => finish(null);
    overlay.onclick = (e) => {
      if (e.target === overlay) finish(null);
    };

    google.accounts.id.initialize({
      client_id: clientId,
      callback: (resp: { credential?: string }) => finish(resp?.credential ?? null),
      ux_mode: "popup",
    });
    document.body.appendChild(overlay);
    google.accounts.id.renderButton(slot, {
      theme: "outline",
      size: "large",
      shape: "pill",
      text: "continue_with",
      locale: lang,
      width: 260,
    });
  });
}
