import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { storage } from "@/src/utils/storage";

export type Lang = "es" | "it";

const es = {
  app_tagline: "Diagnostica tu hogar con IA",
  tab_scan: "Escanear", tab_specialists: "Expertos", tab_messages: "Mensajes", tab_profile: "Perfil",
  login_title: "Arregla tu casa con una foto",
  login_sub: "Fotografía el problema, la IA te dice cómo resolverlo o te conecta con un especialista verificado.",
  email: "Correo electrónico", password: "Contraseña", name: "Nombre completo",
  sign_in: "Iniciar sesión", sign_up: "Crear cuenta", continue_google: "Continuar con Google",
  no_account: "¿No tienes cuenta? Regístrate", have_account: "¿Ya tienes cuenta? Inicia sesión", or: "o",
  hello: "Hola", home_title: "¿Qué hay que arreglar hoy?",
  scan_cta: "Escanear problema", scan_cta_sub: "Apunta la cámara a la avería",
  gallery_cta: "Subir desde galería", recent: "Diagnósticos recientes", no_recent: "Aún no has escaneado nada. ¡Prueba con una fuga, un enchufe o una grieta!",
  analyzing: "Analizando con IA…", analyzing_sub: "Identificando el problema, materiales y pasos",
  camera_perm_title: "Usa la cámara para diagnosticar", camera_perm_text: "Necesitamos la cámara para fotografiar el problema y que la IA lo analice.",
  allow_camera: "Permitir cámara", open_settings: "Abrir ajustes", use_gallery: "Usar galería",
  frame_hint: "Encuadra el problema dentro del marco",
  difficulty: "Dificultad", diff_easy: "Fácil", diff_medium: "Media", diff_hard: "Difícil", diff_expert: "Experto",
  safety: "Seguridad", materials: "Materiales", tools: "Herramientas", steps: "Pasos a seguir",
  time: "Tiempo", cost: "Coste aprox.", when_pro: "Cuándo llamar a un profesional",
  how_solve: "¿Cómo quieres resolverlo?", diy: "Lo hago yo", diy_sub: "Sigue la guía paso a paso",
  hire: "Contratar especialista", hire_sub: "Profesionales verificados cerca de ti", recommended: "Recomendado",
  not_home: "No parece un problema del hogar. Intenta otra foto.", retry: "Reintentar", scan_again: "Escanear de nuevo",
  diy_mode_on: "Modo hazlo tú: marca cada paso al completarlo", done_steps: "pasos completados",
  specialists_title: "Especialistas", search_ph: "Buscar por nombre o ciudad", all: "Todos",
  for_problem: "Para tu problema", no_specialists: "No hay especialistas en esta categoría todavía.",
  verified: "Verificado", reviews: "reseñas", recommend: "recomiendan", jobs: "trabajos", years: "años exp.",
  about: "Sobre mí", portfolio: "Trabajos realizados", no_portfolio: "Aún no hay fotos de trabajos.",
  reviews_title: "Reseñas y recomendaciones", no_reviews: "Sé el primero en dejar una reseña.",
  write_review: "Escribir reseña", rating: "Valoración", comment: "Comentario", recommend_q: "¿Lo recomiendas?",
  submit: "Enviar", cancel: "Cancelar", save: "Guardar", chat: "Chat", call: "Llamar", whatsapp: "WhatsApp", request: "Solicitar",
  request_title: "Solicitar servicio", description: "Describe el trabajo", address: "Dirección", preferred_date: "Fecha preferida (ej. lunes por la tarde)",
  request_sent: "Solicitud enviada", review_sent: "¡Gracias por tu reseña!", satisfaction: "Satisfacción",
  messages_title: "Mensajes", no_messages: "Sin mensajes todavía. Contacta a un especialista para empezar.",
  type_message: "Escribe un mensaje…", service_request: "Solicitud de servicio",
  profile_title: "Perfil", language: "Idioma", become_specialist: "Registrarme como especialista", become_specialist_sub: "Crea tu perfil profesional y recibe clientes",
  my_specialist_profile: "Mi perfil profesional", edit_specialist: "Editar perfil profesional", my_requests: "Solicitudes de servicio", logout: "Cerrar sesión",
  role_client: "Cliente", role_specialist: "Especialista",
  form_title: "Perfil de especialista", category: "Especialidad", bio: "Presentación", phone: "Teléfono", city: "Ciudad",
  years_exp: "Años de experiencia", rate: "Tarifa (ej. 30 EUR/h)", change_photo: "Cambiar foto", add_photo: "Añadir foto",
  saved: "Guardado", caption: "Descripción del trabajo (opcional)", add_work: "Añadir trabajo",
  verification: "Verificación de perfil", verify_text: "Sube una foto de tu documento de identidad para obtener la insignia de verificado.",
  doc_number: "Número de documento", doc_photo: "Foto del documento", verify_btn: "Verificar perfil", verified_ok: "Perfil verificado",
  save_first: "Guarda tu perfil para añadir trabajos y verificarte.",
  requests_title: "Solicitudes", no_requests: "No tienes solicitudes.", from: "De", to: "Para",
  accept: "Aceptar", reject: "Rechazar", complete: "Marcar completado", open_chat: "Abrir chat", rate_now: "Valorar",
  st_pending: "Pendiente", st_accepted: "Aceptada", st_rejected: "Rechazada", st_completed: "Completada", st_cancelled: "Cancelada",
  cat_plumbing: "Fontanería", cat_electrical: "Electricidad", cat_carpentry: "Carpintería", cat_painting: "Pintura",
  cat_masonry: "Albañilería", cat_appliances: "Electrodomésticos", cat_hvac: "Climatización", cat_roofing: "Tejados", cat_general: "General",
  error_generic: "Algo salió mal", required: "Completa los campos obligatorios", edit_profile: "Editar perfil", back: "Atrás",
  membership: "Membresía", membership_title: "Membresía Profesional", membership_sub: "Activa tu perfil y empieza a recibir clientes",
  mb_benefit_1: "Aparece en el directorio y en los resultados de cada diagnóstico", mb_benefit_2: "Recibe solicitudes de servicio y mensajes de clientes",
  mb_benefit_3: "Envía presupuestos y cierra contratos", mb_benefit_4: "Insignia de verificado y reseñas visibles",
  monthly: "Mensual", yearly: "Anual", per_month: "/mes", per_year: "/año", two_months_free: "2 meses gratis",
  pay_card: "Pagar con tarjeta", pay_card_sub: "Pago seguro con Stripe. Renovación manual al final del periodo.",
  pay_inapp: "Suscribirme en la app", pay_inapp_sub: "App Store / Google Play. Renovación automática.",
  restore: "Restaurar compras", simulated: "Modo prueba (simulado)", active_until: "Activa hasta", mb_active: "Membresía activa",
  mb_inactive: "Sin membresía activa", mb_checking: "Verificando pago…", mb_paid: "¡Pago confirmado! Tu membresía está activa.",
  mb_pending_pay: "Completa el pago en la ventana de Stripe y vuelve aquí.", check_payment: "Ya he pagado, verificar",
  mb_unavailable: "Las opciones de suscripción no están disponibles ahora. Inténtalo más tarde.",
  confirm_purchase: "Confirmar compra", confirm_purchase_text: "Compra de prueba (simulada) en la Test Store de RevenueCat. No se cobrará dinero real.",
  confirm: "Confirmar", hidden_profile: "Tu perfil no es visible para clientes. Activa tu membresía para aparecer y recibir solicitudes.",
  activate_membership: "Activar membresía", not_available: "Este especialista no está disponible ahora.", need_profile_first: "Primero crea tu perfil de especialista.",
  send_quote: "Enviar presupuesto", quote: "Presupuesto", quote_price: "Precio (EUR)", quote_desc: "Qué incluye el trabajo", quote_time: "Tiempo estimado (ej. 2 días)",
  quote_sent: "Presupuesto enviado", quote_accepted: "Presupuesto aceptado", quote_rejected: "Presupuesto rechazado",
  qs_pending: "Pendiente", qs_accepted: "Aceptado", qs_rejected: "Rechazado", agreed_price: "Precio acordado", quotes: "Presupuestos",
};

const it: typeof es = {
  app_tagline: "Diagnostica la tua casa con l'IA",
  tab_scan: "Scansiona", tab_specialists: "Esperti", tab_messages: "Messaggi", tab_profile: "Profilo",
  login_title: "Ripara casa con una foto",
  login_sub: "Fotografa il problema: l'IA ti spiega come risolverlo o ti mette in contatto con un esperto verificato.",
  email: "Email", password: "Password", name: "Nome completo",
  sign_in: "Accedi", sign_up: "Crea account", continue_google: "Continua con Google",
  no_account: "Non hai un account? Registrati", have_account: "Hai già un account? Accedi", or: "oppure",
  hello: "Ciao", home_title: "Cosa c'è da riparare oggi?",
  scan_cta: "Scansiona problema", scan_cta_sub: "Inquadra il guasto con la fotocamera",
  gallery_cta: "Carica dalla galleria", recent: "Diagnosi recenti", no_recent: "Non hai ancora scansionato nulla. Prova con una perdita, una presa o una crepa!",
  analyzing: "Analisi IA in corso…", analyzing_sub: "Identifico problema, materiali e passaggi",
  camera_perm_title: "Usa la fotocamera per la diagnosi", camera_perm_text: "Serve la fotocamera per fotografare il problema e farlo analizzare all'IA.",
  allow_camera: "Consenti fotocamera", open_settings: "Apri impostazioni", use_gallery: "Usa galleria",
  frame_hint: "Inquadra il problema nel riquadro",
  difficulty: "Difficoltà", diff_easy: "Facile", diff_medium: "Media", diff_hard: "Difficile", diff_expert: "Esperto",
  safety: "Sicurezza", materials: "Materiali", tools: "Attrezzi", steps: "Passaggi da seguire",
  time: "Tempo", cost: "Costo stimato", when_pro: "Quando chiamare un professionista",
  how_solve: "Come vuoi risolverlo?", diy: "Lo faccio io", diy_sub: "Segui la guida passo dopo passo",
  hire: "Chiama un esperto", hire_sub: "Professionisti verificati vicino a te", recommended: "Consigliato",
  not_home: "Non sembra un problema domestico. Prova un'altra foto.", retry: "Riprova", scan_again: "Scansiona di nuovo",
  diy_mode_on: "Modalità fai da te: spunta ogni passaggio completato", done_steps: "passaggi completati",
  specialists_title: "Specialisti", search_ph: "Cerca per nome o città", all: "Tutti",
  for_problem: "Per il tuo problema", no_specialists: "Ancora nessuno specialista in questa categoria.",
  verified: "Verificato", reviews: "recensioni", recommend: "consigliano", jobs: "lavori", years: "anni esp.",
  about: "Chi sono", portfolio: "Lavori realizzati", no_portfolio: "Ancora nessuna foto dei lavori.",
  reviews_title: "Recensioni e consigli", no_reviews: "Lascia tu la prima recensione.",
  write_review: "Scrivi recensione", rating: "Valutazione", comment: "Commento", recommend_q: "Lo consigli?",
  submit: "Invia", cancel: "Annulla", save: "Salva", chat: "Chat", call: "Chiama", whatsapp: "WhatsApp", request: "Richiedi",
  request_title: "Richiedi intervento", description: "Descrivi il lavoro", address: "Indirizzo", preferred_date: "Data preferita (es. lunedì pomeriggio)",
  request_sent: "Richiesta inviata", review_sent: "Grazie per la recensione!", satisfaction: "Soddisfazione",
  messages_title: "Messaggi", no_messages: "Nessun messaggio. Contatta uno specialista per iniziare.",
  type_message: "Scrivi un messaggio…", service_request: "Richiesta di intervento",
  profile_title: "Profilo", language: "Lingua", become_specialist: "Registrati come specialista", become_specialist_sub: "Crea il tuo profilo professionale e ricevi clienti",
  my_specialist_profile: "Il mio profilo professionale", edit_specialist: "Modifica profilo professionale", my_requests: "Richieste di intervento", logout: "Esci",
  role_client: "Cliente", role_specialist: "Specialista",
  form_title: "Profilo specialista", category: "Specialità", bio: "Presentazione", phone: "Telefono", city: "Città",
  years_exp: "Anni di esperienza", rate: "Tariffa (es. 30 EUR/h)", change_photo: "Cambia foto", add_photo: "Aggiungi foto",
  saved: "Salvato", caption: "Descrizione del lavoro (opzionale)", add_work: "Aggiungi lavoro",
  verification: "Verifica profilo", verify_text: "Carica una foto del documento d'identità per ottenere il badge verificato.",
  doc_number: "Numero documento", doc_photo: "Foto documento", verify_btn: "Verifica profilo", verified_ok: "Profilo verificato",
  save_first: "Salva il profilo per aggiungere lavori e verificarti.",
  requests_title: "Richieste", no_requests: "Non hai richieste.", from: "Da", to: "A",
  accept: "Accetta", reject: "Rifiuta", complete: "Segna completato", open_chat: "Apri chat", rate_now: "Valuta",
  st_pending: "In attesa", st_accepted: "Accettata", st_rejected: "Rifiutata", st_completed: "Completata", st_cancelled: "Annullata",
  cat_plumbing: "Idraulica", cat_electrical: "Elettricità", cat_carpentry: "Falegnameria", cat_painting: "Pittura",
  cat_masonry: "Muratura", cat_appliances: "Elettrodomestici", cat_hvac: "Climatizzazione", cat_roofing: "Tetti", cat_general: "Generale",
  error_generic: "Qualcosa è andato storto", required: "Compila i campi obbligatori", edit_profile: "Modifica profilo", back: "Indietro",
  membership: "Abbonamento", membership_title: "Abbonamento Professionale", membership_sub: "Attiva il tuo profilo e inizia a ricevere clienti",
  mb_benefit_1: "Compari nell'elenco e nei risultati di ogni diagnosi", mb_benefit_2: "Ricevi richieste di intervento e messaggi dai clienti",
  mb_benefit_3: "Invia preventivi e chiudi contratti", mb_benefit_4: "Badge verificato e recensioni visibili",
  monthly: "Mensile", yearly: "Annuale", per_month: "/mese", per_year: "/anno", two_months_free: "2 mesi gratis",
  pay_card: "Paga con carta", pay_card_sub: "Pagamento sicuro con Stripe. Rinnovo manuale a fine periodo.",
  pay_inapp: "Abbonati nell'app", pay_inapp_sub: "App Store / Google Play. Rinnovo automatico.",
  restore: "Ripristina acquisti", simulated: "Modalità test (simulata)", active_until: "Attivo fino al", mb_active: "Abbonamento attivo",
  mb_inactive: "Nessun abbonamento attivo", mb_checking: "Verifica del pagamento…", mb_paid: "Pagamento confermato! Il tuo abbonamento è attivo.",
  mb_pending_pay: "Completa il pagamento nella finestra di Stripe e torna qui.", check_payment: "Ho pagato, verifica",
  mb_unavailable: "Le opzioni di abbonamento non sono disponibili ora. Riprova più tardi.",
  confirm_purchase: "Conferma acquisto", confirm_purchase_text: "Acquisto di prova (simulato) nel Test Store di RevenueCat. Nessun addebito reale.",
  confirm: "Conferma", hidden_profile: "Il tuo profilo non è visibile ai clienti. Attiva l'abbonamento per comparire e ricevere richieste.",
  activate_membership: "Attiva abbonamento", not_available: "Questo specialista non è disponibile ora.", need_profile_first: "Prima crea il tuo profilo da specialista.",
  send_quote: "Invia preventivo", quote: "Preventivo", quote_price: "Prezzo (EUR)", quote_desc: "Cosa include il lavoro", quote_time: "Tempo stimato (es. 2 giorni)",
  quote_sent: "Preventivo inviato", quote_accepted: "Preventivo accettato", quote_rejected: "Preventivo rifiutato",
  qs_pending: "In attesa", qs_accepted: "Accettato", qs_rejected: "Rifiutato", agreed_price: "Prezzo concordato", quotes: "Preventivi",
};

export type TKey = keyof typeof es;
const dict = { es, it };
export const CATEGORIES = ["plumbing", "electrical", "carpentry", "painting", "masonry", "appliances", "hvac", "roofing", "general"] as const;

type Ctx = { lang: Lang; setLang: (l: Lang) => void; t: (k: TKey | string) => string };
const I18nContext = createContext<Ctx>({ lang: "es", setLang: () => {}, t: (k) => String(k) });

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>("es");
  useEffect(() => {
    storage.getItem<string>("app_lang", "es").then((v) => setLangState(v === "it" ? "it" : "es"));
  }, []);
  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    storage.setItem("app_lang", l);
  }, []);
  const t = useCallback((k: string) => (dict[lang] as Record<string, string>)[k] ?? k, [lang]);
  return <I18nContext.Provider value={{ lang, setLang, t }}>{children}</I18nContext.Provider>;
}

export const useI18n = () => useContext(I18nContext);
