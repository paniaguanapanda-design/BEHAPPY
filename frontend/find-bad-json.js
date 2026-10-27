const fs = require("fs");
const path = require("path");
function walk(dir) {
  for (const name of fs.readdirSync(dir)) {
    if (name === "node_modules" || name === ".git" || name === "android" || name === "ios") continue;
    const p = path.join(dir, name);
    if (fs.statSync(p).isDirectory()) walk(p);
    else if (name.endsWith(".json")) {
      const t = fs.readFileSync(p, "utf8");
      try { JSON.parse(t); }
      catch (e) {
        console.log("ROTO " + p);
        console.log(e.message);
        const lines = t.split(/\r?\n/);
        const m = String(e.message).match(/line (\d+)/);
        if (m) {
          const n = Number(m[1]);
          for (let i = Math.max(1, n - 2); i <= Math.min(lines.length, n + 2); i++) {
            console.log(String(i).padStart(3) + " | " + lines[i - 1]);
          }
        }
      }
    }
  }
}
walk(".");
console.log("fin");
