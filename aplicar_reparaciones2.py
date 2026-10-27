# Ejecutar desde la carpeta BEHAPPY:  python aplicar_reparaciones2.py
import os, sys, json

def rd(p):
    with open(p, "rb") as f:
        raw = f.read().decode("utf-8")
    crlf = "\r\n" in raw
    return raw.replace("\r\n", "\n"), crlf

def wr(p, txt, crlf):
    if crlf:
        txt = txt.replace("\n", "\r\n")
    with open(p, "wb") as f:
        f.write(txt.encode("utf-8"))

def rep(txt, old, new, name, count=1):
    if old not in txt:
        print("NO ENCONTRADO:", name); sys.exit(1)
    return txt.replace(old, new, count)

# ---------- 1) backend/server.py ----------
p = "backend/server.py"
s, crlf = rd(p)
if "/admin/verifications" in s:
    print("server.py ya tiene el parche"); 
else:
    s = rep(s, "from fastapi import FastAPI, APIRouter, HTTPException, Request, UploadFile, File, Form, Query",
               "from fastapi import FastAPI, APIRouter, HTTPException, Request, UploadFile, File, Form, Query, Header", "import Header")
    # quitar indices duplicados
    dup = ('    await db.reviews.create_index([("specialist_id", 1), ("user_id", 1)], unique=True)\n'
           '    await db.conversations.create_index([("client_id", 1), ("specialist_id", 1)], unique=True)\n')
    first = s.find(dup)
    if first != -1:
        after = first + len(dup)
        while s.startswith(dup, after):
            s = s[:after] + s[after + len(dup):]
    admin = '''

# ---------------- Admin (moderacion manual) ----------------
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")


def require_admin(token: Optional[str]):
    import hmac
    if not ADMIN_TOKEN or not token or not hmac.compare_digest(token, ADMIN_TOKEN):
        raise HTTPException(403, "Forbidden")


@api.get("/admin/verifications")
async def admin_verifications(x_admin_token: Optional[str] = Header(None)):
    require_admin(x_admin_token)
    items = await db.specialists.find({"verification_status": "in_review"},
                                      {"_id": 0, "specialist_id": 1, "name": 1, "user_id": 1, "document_number": 1,
                                       "verification_document": 1, "submitted_at": 1}).to_list(100)
    for it in items:
        doc = it.get("verification_document") or ""
        it["verification_document"] = (doc[:80] + "...") if len(doc) > 80 else doc
    return items


@api.get("/admin/verifications/{sid}/document")
async def admin_verification_document(sid: str, x_admin_token: Optional[str] = Header(None)):
    require_admin(x_admin_token)
    s = await db.specialists.find_one({"specialist_id": sid}, {"_id": 0, "verification_document": 1})
    if not s or not s.get("verification_document"):
        raise HTTPException(404, "No document")
    doc = s["verification_document"]
    if doc.startswith("data:"):
        head, _, b64 = doc.partition(",")
        ct = head[5:].split(";")[0] or "image/jpeg"
        return Response(content=base64.b64decode(b64), media_type=ct)
    data, ct = await run_in_threadpool(get_object, doc)
    return Response(content=data, media_type=ct)


@api.post("/admin/verifications/{sid}/{decision}")
async def admin_decide_verification(sid: str, decision: str, x_admin_token: Optional[str] = Header(None)):
    require_admin(x_admin_token)
    if decision not in ("approve", "reject"):
        raise HTTPException(400, "decision must be approve or reject")
    if decision == "approve":
        upd = {"verified": True, "verification_status": "verified", "verified_by": "admin", "verified_at": iso(now())}
    else:
        upd = {"verified": False, "verification_status": "rejected"}
    r = await db.specialists.update_one({"specialist_id": sid}, {"$set": upd})
    if not r.matched_count:
        raise HTTPException(404, "Specialist not found")
    return {"ok": True, "status": upd["verification_status"]}


@api.get("/admin/reports")
async def admin_reports(x_admin_token: Optional[str] = Header(None)):
    require_admin(x_admin_token)
    return await db.reports.find({"status": "open"}, {"_id": 0}).sort("created_at", -1).to_list(200)


@api.post("/admin/reports/{rid}/resolve")
async def admin_resolve_report(rid: str, x_admin_token: Optional[str] = Header(None)):
    require_admin(x_admin_token)
    r = await db.reports.update_one({"report_id": rid}, {"$set": {"status": "resolved", "resolved_at": iso(now())}})
    if not r.matched_count:
        raise HTTPException(404, "Report not found")
    return {"ok": True}

'''
    s = rep(s, "\n\n@api.post(\"/blocks\")", admin + "\n@api.post(\"/blocks\")", "anchor blocks")
    s = rep(s, 'app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])',
               '_cors = [o.strip() for o in os.environ.get("CORS_ORIGINS", "https://www.be-happyapp.com").split(",") if o.strip()]\n'
               'app.add_middleware(CORSMiddleware, allow_credentials=False, allow_origins=_cors, allow_methods=["*"], allow_headers=["*"])',
               "CORS")
    wr(p, s, crlf)
    print("server.py OK")

# ---------- 2) backend/.env.example ----------
p = "backend/.env.example"
s, crlf = rd(p)
if "ADMIN_TOKEN" not in s:
    s = s.rstrip("\n") + "\nADMIN_TOKEN=\nCORS_ORIGINS=https://www.be-happyapp.com\n"
    wr(p, s, crlf)
    print(".env.example OK")

# ---------- 3) frontend/app/login.tsx (enlaces privacidad / terminos) ----------
p = "frontend/app/login.tsx"
s, crlf = rd(p)
if "be-happyapp.com/privacy" in s:
    print("login.tsx ya tiene el parche")
else:
    s = rep(s, 'import { Pressable, Text, TextInput, View } from "react-native";',
               'import { Linking, Pressable, Text, TextInput, View } from "react-native";', "import Linking")
    s = rep(s, "  const { t } = useI18n();\n", "  const { t, lang } = useI18n();\n", "lang")
    block = '''          <View style={styles.legalRow}>
            <Text style={styles.legalText} onPress={() => Linking.openURL("https://www.be-happyapp.com/privacy")}>
              {lang === "it" ? "Privacy" : "Privacidad"}
            </Text>
            <Text style={styles.legalText}> · </Text>
            <Text style={styles.legalText} onPress={() => Linking.openURL("https://www.be-happyapp.com/termini")}>
              {lang === "it" ? "Termini" : "Términos"}
            </Text>
          </View>
'''
    s = rep(s, '          <View style={styles.langBottom}>', block + '          <View style={styles.langBottom}>', "legal block")
    s = rep(s, "  switch: {", '  legalRow: { flexDirection: "row", justifyContent: "center", marginTop: 4 },\n'
                              '  legalText: { color: c.muted, fontSize: 13, textDecorationLine: "underline" },\n  switch: {', "styles")
    wr(p, s, crlf)
    print("login.tsx OK")

# ---------- 4) frontend/eas.json (perfil production = AAB para Google Play) ----------
p = "frontend/eas.json"
s, crlf = rd(p)
d = json.loads(s)
if "production" not in d["build"]:
    d["build"]["production"] = {
        "autoIncrement": True,
        "android": {"buildType": "app-bundle"},
        "env": dict(d["build"]["preview"]["env"]),
    }
    wr(p, json.dumps(d, indent=2, ensure_ascii=False) + "\n", crlf)
    print("eas.json OK")

# ---------- 5) borrar archivo suelto ----------
if os.path.exists("frontend/find-bad-json.js"):
    os.remove("frontend/find-bad-json.js")
    print("find-bad-json.js borrado")
print("LISTO")
