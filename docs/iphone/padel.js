// Padel Liège : relève depuis l'iPhone les clubs que GitHub ne peut pas interroger
// (Playtomic, Sport-finder, MATCHi), puis lance la mise à jour de la page.
//
// Script pour l'app Scriptable, à nommer « Padel ».
// La clé GitHub est demandée au premier lancement et rangée dans le trousseau
// de l'iPhone : elle n'est jamais écrite dans ce script.

const DEPOT = "virgilejdb/padel-liege";
const PAGE = "https://virgilejdb.github.io/padel-liege/";
const API = `https://api.github.com/repos/${DEPOT}`;
const NOM_CLE = "padel-liege-github";
const ATTENTE_MAX_MS = 5 * 60 * 1000;

const pause = (ms) => new Promise((fini) => Timer.schedule(ms, false, fini));

async function message(titre, texte, boutons = ["OK"]) {
  const a = new Alert();
  a.title = titre;
  a.message = texte;
  boutons.forEach((b) => a.addAction(b));
  return a.presentAlert();
}

async function lireCle() {
  if (Keychain.contains(NOM_CLE)) return Keychain.get(NOM_CLE);
  const a = new Alert();
  a.title = "Clé GitHub";
  a.message = "Collez la clé « Raccourci Padel » (elle commence par github_pat_). Elle sera gardée dans le trousseau de l'iPhone.";
  a.addSecureTextField("github_pat_…");
  a.addAction("Enregistrer");
  a.addCancelAction("Annuler");
  if ((await a.present()) === -1) throw new Error("Annulé : aucune clé saisie.");
  const cle = a.textFieldValue(0).trim();
  if (!cle.startsWith("github_pat_")) throw new Error("Cette clé ne commence pas par github_pat_.");
  Keychain.set(NOM_CLE, cle);
  return cle;
}

async function github(chemin, methode, corps, cle) {
  const r = new Request(API + chemin);
  r.method = methode;
  r.headers = {
    Authorization: `Bearer ${cle}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "Content-Type": "application/json",
  };
  if (corps) r.body = JSON.stringify(corps);
  const texte = await r.loadString();
  const code = r.response.statusCode;
  if (code === 401) {
    Keychain.remove(NOM_CLE);
    throw new Error("Clé GitHub refusée (expirée ou mal copiée). Relancez le script pour la saisir à nouveau.");
  }
  if (code >= 300) throw new Error(`GitHub a répondu ${code} à ${methode} ${chemin} : ${texte.slice(0, 200)}`);
  return texte ? JSON.parse(texte) : null;
}

async function main() {
  const cle = await lireCle();

  // 1. Liste des adresses à interroger, publiée par la collecte.
  const liste = new Request(`${PAGE}data/telephone-requetes.json?t=${Date.now()}`);
  const envoi = await liste.loadJSON();
  const urls = envoi.requetes || [];
  if (!urls.length) throw new Error("La liste des adresses est vide.");

  // 2. Interrogation depuis l'iPhone, une adresse à la fois.
  const reponses = {};
  const echecs = [];
  for (let i = 0; i < urls.length; i++) {
    const url = urls[i];
    const site = url.split("/")[2];
    try {
      const q = new Request(url);
      q.timeoutInterval = 20;
      const texte = await q.loadString();
      if (q.response.statusCode === 200) reponses[url] = texte.replace(/\s+/g, " ");
      else echecs.push(`${site} : HTTP ${q.response.statusCode}`);
    } catch (e) {
      echecs.push(`${site} : ${e.message}`);
    }
    console.log(`${i + 1}/${urls.length} ${site}`);
    await pause(250);
  }
  if (!Object.keys(reponses).length) throw new Error(`Aucune réponse obtenue. ${echecs.slice(0, 3).join(" ; ")}`);
  envoi.reponses = reponses;

  // 3. Dépôt sur la branche « telephone » : son contenu est remplacé à chaque envoi (pas d'historique).
  const contenu = Data.fromString(JSON.stringify(envoi)).toBase64String();
  const blob = await github("/git/blobs", "POST", { content: contenu, encoding: "base64" }, cle);
  const arbre = await github("/git/trees", "POST",
    { tree: [{ path: "envoi.json", mode: "100644", type: "blob", sha: blob.sha }] }, cle);
  const commit = await github("/git/commits", "POST", { message: "Envoi iPhone", tree: arbre.sha, parents: [] }, cle);
  await github("/git/refs/heads/telephone", "PATCH", { sha: commit.sha, force: true }, cle);

  // 4. Lancement de la mise à jour de la page, puis attente de sa fin.
  // Sans la permission « Actions » de la clé, l'envoi sera repris par la prochaine collecte automatique.
  const depart = Date.now();
  let lancee = true;
  try {
    await github("/actions/workflows/collecte.yml/dispatches", "POST", { ref: "main", inputs: { iphone: "true" } }, cle);
  } catch (e) {
    console.error(e);
    lancee = false;
  }
  let conclusion = null;
  while (lancee && Date.now() - depart < ATTENTE_MAX_MS) {
    await pause(10000);
    const runs = await github("/actions/workflows/collecte.yml/runs?event=workflow_dispatch&per_page=1", "GET", null, cle);
    const run = runs.workflow_runs[0];
    if (run && Date.parse(run.created_at) >= depart - 60000 && run.status === "completed") {
      conclusion = run.conclusion;
      break;
    }
    console.log("Mise à jour de la page en cours…");
  }

  const bilan = `${Object.keys(reponses).length} réponses sur ${urls.length} envoyées.` +
    (echecs.length ? `\n${echecs.length} échecs : ${[...new Set(echecs)].slice(0, 3).join(" ; ")}` : "");
  const titre = !lancee ? "Envoi réussi"
    : conclusion === "success" ? "Page à jour"
    : conclusion ? "Échec de la mise à jour" : "Mise à jour encore en cours";
  const suite = !lancee
    ? "\nMise à jour immédiate refusée (permission « Actions » de la clé) : la page sera à jour à la prochaine collecte automatique, sous 30 minutes."
    : conclusion === "success" ? "" : conclusion
    ? "\nDétail dans l'onglet Actions du dépôt." : "\nLa page sera à jour dans quelques minutes.";
  if ((await message(titre, bilan + suite, ["Ouvrir la page", "Fermer"])) === 0) Safari.open(`${PAGE}?maj=${Date.now()}`);
}

try {
  await main();
} catch (e) {
  console.error(e);
  await message("Padel : erreur", e.message);
}
Script.complete();
