"""locustfile.py — Séance 3 : test de charge de l'API d'inférence DermaScan.

Un utilisateur type = un dermatologue à son poste de consultation. Locust en lance
autant d'exemplaires que demandé par --users.

Usage (palier 1, par exemple) :
    locust -f locustfile.py --host "$APP_URL" --users 10 --spawn-rate 2 \
           --run-time 3m --headless --csv palier1 --html palier1.html

Contrôle d'un appel unique AVANT le premier palier (doit afficher 10 x 200) :
    python locustfile.py --check "$APP_URL"
"""
import copy
import json
import os
import random
import sys
import uuid

from locust import HttpUser, between, task

# --------------------------------------------------------------------------
# Charge utile : chargée UNE fois au démarrage du module, jamais recopiée ici.
# charge.json = ligne de lésion réelle de la séance 2, 40 variables attendues.
# --------------------------------------------------------------------------
CHEMIN_CHARGE = os.environ.get(
    "CHARGE_JSON", os.path.join(os.path.dirname(os.path.abspath(__file__)), "charge.json")
)
with open(CHEMIN_CHARGE, encoding="utf-8") as f:
    CHARGE_BASE = json.load(f)

# Variables perturbées à chaque appel : (amplitude relative, borne basse, borne haute).
# Amplitude = ±10 % de la valeur de base, puis bornage dans le domaine.
# Les bornes ci-dessous sont des bornes de sécurité : à resserrer sur les plages
# relevées en séance 2 (EXPLORATION.md) si elles sont plus étroites.
PERTURBATIONS = {
    "clin_size_long_diam_mm": (0.10, 1.0, 40.0),
    "tbp_lv_areaMM2": (0.10, 0.5, 400.0),
    "tbp_lv_perimeterMM": (0.10, 2.0, 120.0),
}
AGE_PAS = 5          # age_approx est un multiple de 5 dans le jeu ISIC
AGE_BORNES = (5, 85)

# On ne perturbe que ce qui existe et est numérique dans la charge : la fonction
# ne doit jamais fabriquer une variable absente (ce serait un 400, pas une mesure).
VARIABLES_PERTURBEES = [
    k for k in PERTURBATIONS
    if isinstance(CHARGE_BASE.get(k), (int, float)) and not isinstance(CHARGE_BASE.get(k), bool)
]
if isinstance(CHARGE_BASE.get("age_approx"), (int, float)):
    VARIABLES_PERTURBEES.append("age_approx")
if len(VARIABLES_PERTURBEES) < 2:
    raise SystemExit(
        "Moins de deux variables numériques perturbables dans charge.json : "
        "ajuster PERTURBATIONS avec des colonnes présentes dans votre /model/info."
    )


def charge_utile_perturbee():
    """Copie de charge.json avec quelques variables numériques perturbées.

    Sans perturbation, un cache éventuel côté serveur servirait toujours la même
    réponse et la mesure ne représenterait aucun usage réel.
    """
    charge = copy.deepcopy(CHARGE_BASE)
    for nom in VARIABLES_PERTURBEES:
        base = CHARGE_BASE[nom]
        if nom == "age_approx":
            valeur = base + random.choice((-2, -1, 0, 1, 2)) * AGE_PAS
            valeur = max(AGE_BORNES[0], min(AGE_BORNES[1], valeur))
            # On garde le type de la charge de base : age_approx vaut 60.0 (float) dans charge.json.
            charge[nom] = float(valeur) if isinstance(base, float) else int(valeur)
            continue
        amplitude, bas, haut = PERTURBATIONS[nom]
        valeur = base * (1.0 + random.uniform(-amplitude, amplitude))
        valeur = max(bas, min(haut, valeur))
        charge[nom] = round(valeur, 4) if isinstance(base, float) else int(round(valeur))
    return charge


class Dermatologue(HttpUser):
    """Un praticien qui soumet des lésions depuis son poste de consultation."""

    # Temps de réflexion : 1 à 5 s. Un temps nul simulerait un robot ; un
    # dermatologue regarde la lésion, saisit, soumet, lit, passe à la suivante.
    wait_time = between(1, 5)

    # Poids 10 / 1 / 1 — justification dans RAPPORT_CHARGE.md (Q5.1).
    @task(10)
    def predire(self):
        with self.client.post(
            "/predict",
            json=charge_utile_perturbee(),
            headers={"X-Request-ID": str(uuid.uuid4())},
            name="POST /predict",
            catch_response=True,
        ) as reponse:
            if reponse.status_code == 200:
                reponse.success()
            else:
                # Sans ce verdict explicite, une réponse 400 serait comptée comme un succès.
                reponse.failure(f"statut {reponse.status_code}")

    @task(1)
    def sante(self):
        self.client.get("/health", name="GET /health")

    @task(1)
    def info_modele(self):
        self.client.get("/model/info", name="GET /model/info")


# --------------------------------------------------------------------------
# Contrôle hors Locust : python locustfile.py --check https://<app>.azurewebsites.net
# Un 400 ici signifie que la perturbation sort une variable de son domaine :
# la corriger AVANT de lancer un palier, sinon le taux d'échec ne mesure rien.
# --------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--check":
        raise SystemExit("usage : python locustfile.py --check <APP_URL>")
    import requests

    url = sys.argv[2].rstrip("/")
    codes = []
    for _ in range(10):
        r = requests.post(f"{url}/predict", json=charge_utile_perturbee(), timeout=60)
        codes.append(r.status_code)
    print("variables perturbées :", VARIABLES_PERTURBEES)
    print("codes /predict       :", codes)
    sys.exit(0 if all(c == 200 for c in codes) else 1)
