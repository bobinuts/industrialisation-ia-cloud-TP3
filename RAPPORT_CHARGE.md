# RAPPORT_CHARGE.md — Séance 3, partie 5

Auteur : PELLICANO Théo — M2 Industrialisation de l'IA dans le Cloud — YNOV Campus Montpellier — 2026-2027

Pièces jointes, non retouchées : `palier1_stats.csv` … `palier4_stats.csv` et `palier1.html` … `palier4.html`. Captures (dossier `captures/`) : `01_health_200.png`, `02_predict_reponse.png`, `03_log_port_mismatch.png`, `locust_palier3/` et `locust_palier4/` (rapports Locust). Les rapports HTML comptent quelques requêtes de plus que les CSV (par exemple 3 142 contre 3 129 au palier 3, soit 0,4 %) : le HTML est écrit à l'arrêt, une fois les requêtes en vol terminées. Les tableaux ci-dessous utilisent les CSV.

---

## 0. Cible testée et conditions de mesure

| Élément | Valeur |
|---|---|
| Cible retenue (A / B / C) | **A** — App Service for Containers (voir `FAISABILITE.md`, mesure 2) |
| URL testée | `https://dermascan-tp42.azurewebsites.net` |
| Plan / taille | `plan-dermascan-tp42`, SKU **B1** (tier Basic, Linux), **1 instance** ; 1 vCPU et 1,75 Go de RAM d'après la fiche du SKU (valeurs de catalogue, non mesurées) |
| Workers Gunicorn de l'image | **1 *worker* synchrone** : le `CMD` de mon Dockerfile S2 est `exec gunicorn -b 0.0.0.0:${PORT} app:app`, sans `--workers` ni `--threads`, donc valeur par défaut de Gunicorn. Une requête à la fois par instance. Confirmé par le journal de démarrage du conteneur en local (26/10) : `Using worker: sync`, un seul `Booting worker`. |
| Poste de test | Un seul poste Windows, en **Wi-Fi** pendant toute la séance (pas de liaison filaire) : la variabilité du réseau (aller-retour de 30 à 119 ms, Mesure 14) est donc comprise dans mes latences |
| Version de Locust | 2.47.0 (Python 3.12.7, environnement virtuel dédié) |

**Règle d'honnêteté de la mesure.** Locust tourne sur mon poste et traverse le réseau de la salle puis Internet jusqu'à l'Allemagne : une partie de la latence mesurée n'appartient pas au service. Je la quantifie en Mesure 14 et la soustrais à ma lecture ; mes percentiles sont des latences **vues du poste**, pas des latences du serveur.

---

## 1. Scénario (rappel, détails dans `locustfile.py`)

- Un utilisateur = un dermatologue ; temps de réflexion `between(1, 5)` s ; charge utile perturbée à chaque appel sur `clin_size_long_diam_mm`, `tbp_lv_areaMM2`, `tbp_lv_perimeterMM` et `age_approx` ; verdict explicite sur `/predict` (tout code ≠ 200 est un échec) ; noms de tâches fixes.
- Contrôle préalable d'un appel unique : `python locustfile.py --check "$APP_URL"` → **dix `200`** (26/10, 14:34).

### Question 5.1 — Justification des trois poids (10 / 1 / 1)

- **`POST /predict` : 10.** C'est l'acte métier : chaque lésion examinée donne lieu à une soumission. C'est aussi la seule route qui consomme du calcul ; elle doit donc dominer la mesure.
- **`GET /health` : 1.** Un praticien n'appelle pas la sonde de santé ; elle est interrogée par la plateforme et par la supervision. Un poids faible représente la vérification occasionnelle du poste (la page vérifie que le service répond) sans fausser le profil de charge.
- **`GET /model/info` : 1.** Le poste l'interroge au début d'une session pour afficher la version du modèle (traçabilité), pas à chaque lésion : une fois par séquence de consultation, soit environ une requête pour dix soumissions.

Soit ≈ 83 % de prédictions, 8 % de santé, 8 % d'information modèle.

---

## 2. Critère de rupture — posé AVANT toute mesure

| Élément du critère | Choix | Justification en une ligne |
|---|---|---|
| Seuil de taux d'échec jugé inacceptable | **1 %** | Pour un outil d'aide à la décision clinique, une requête sur cent sans réponse oblige le praticien à re-soumettre, ce qui n'est pas tolérable en consultation |
| Seuil de p95 jugé inacceptable | **3 ×** le p95 du palier 1 | Le palier 1 est la référence « service au repos » ; triple signifie que la file d'attente domine le temps de service (valeur de référence du cours) |
| Le point de rupture est atteint quand | **l'un des deux** critères est franchi | Un service lent mais sans erreur est déjà dégradé pour l'utilisateur ; je ne veux pas attendre les erreurs |

Critère écrit le : **2026-10-26 à 12:34 (heure locale)**, avant le lancement du premier palier et avant toute lecture d'un fichier de mesure de charge.

---

## 3. Paliers exécutés

Chaque palier dure 3 minutes, dont la première sert à la stabilisation. Les valeurs de `--users` couvrent **un facteur 20** (plus d'un ordre de grandeur) ; `--spawn-rate` fait monter la population en ≈ 5 secondes.

| Palier | `--users` | `--spawn-rate` | Fichiers produits |
|---|---|---|---|
| 1 | 10 | 2 | `palier1_stats.csv`, `palier1.html` |
| 2 | 40 | 8 | `palier2_stats.csv`, `palier2.html` |
| 3 | 100 | 20 | `palier3_stats.csv`, `palier3.html` |
| 4 | 200 | 40 | `palier4_stats.csv`, `palier4.html` |

### Mesure 13 — débit, percentiles et taux d'échec (ligne `Aggregated` de chaque CSV)

| Palier | Utilisateurs | Débit (req/s) | p50 (ms) | p95 (ms) | p99 (ms) | Taux d'échec (%) | Échecs les plus fréquents |
|---|---|---|---|---|---|---|---|
| 1 | 10 | 3,19 | 90 | 400 | 860 | 0 (0 / 571) | aucun |
| 2 | 40 | 11,46 | 180 | 1 800 | 6 300 | 0 (0 / 2 047) | aucun |
| 3 | 100 | 17,53 | 2 600 | 4 100 | 4 300 | 0 (0 / 3 129) | aucun |
| 4 | 200 | 17,80 | 7 900 | 10 000 | 11 000 | 0 (0 / 3 177) | aucun |

Source : ligne `Aggregated` de chaque `*_stats.csv` (colonnes `Requests/s`, `50%`, `95%`, `99%`, `Failure Count` ÷ `Request Count`) ; les quatre `*_failures.csv` sont vides. Les percentiles de Locust sont arrondis à deux chiffres significatifs et **incluent la première minute** (montée en charge) : c'est le CSV brut, non retouché, qui fait foi.

Par route, `POST /predict` seul : palier 1, p50 96 ms, p95 450 ms, p99 900 ms (458 requêtes) ; palier 2, p50 200 ms, p95 1 800 ms ; palier 3, p50 2 600 ms, p95 4 100 ms ; palier 4, p50 7 900 ms, p95 10 000 ms.

Régime établi (`*_stats_history.csv`, du 60ᵉ au 180ᵉ seconde) : débit de 3,2 / 11,1 / 17,6 / 18,2 req/s aux quatre paliers. **Le débit plafonne autour de 18 req/s à partir de 100 utilisateurs** : un seul *worker* synchrone sert environ une requête toutes les 55 ms, et tout le reste s'accumule en file. Contrôle de cohérence (loi de Little en boucle fermée, `N ≈ X × (R + temps de réflexion moyen 3 s)`) : palier 3, 17,5 × (2,64 + 3) ≈ 99 pour 100 utilisateurs ; palier 4, 17,8 × (7,88 + 3) ≈ 194 pour 200. Les chiffres sont cohérents entre eux.

### Mesure 14 — ligne de base réseau

| Ligne de base | Valeur |
|---|---|
| Temps d'établissement de connexion, médiane sur 20 mesures (`time_connect`) | **49,0 ms** (min 30,3 ms, max 119,0 ms) |
| Part que cela représente dans mon p50 du palier 1 | 49,0 / 90 ≈ **54 %** du p50 agrégé (49 / 96 ≈ 51 % de celui de `/predict`). Le minimum, 30,3 ms, est la meilleure estimation d'un aller-retour pur : `time_connect` de `curl` inclut la résolution DNS, que Locust ne paie pas (connexions réutilisées). Cohérent avec `GET /health` : p50 31 ms, c'est-à-dire **un aller-retour réseau et presque aucun temps serveur**. Il reste donc ≈ 65 ms du p50 de `/predict` (96 − 31) pour le calcul, de l'ordre des 55 ms de service déduites du débit maximal |

Limite de la mesure : `time_connect` ne couvre que l'établissement TCP, pas la négociation TLS ni l'aller-retour de la requête. La part réseau réelle de mon p50 est donc **plus grande** que ce que ce relevé suggère ; je le dis plutôt que de l'attribuer au serveur.

### Mesure 15 — point de rupture constaté (au regard du critère de la section 2)

| Conclusion | Réponse |
|---|---|
| Palier où le critère est franchi pour la première fois | **Palier 2** (40 utilisateurs) : p95 = 1 800 ms > 3 × 400 = 1 200 ms (rapport 4,5). Taux d'échec : 0 %, donc seul le critère de latence est franchi |
| Nombre d'utilisateurs simultanés supporté, borné entre deux paliers | **Entre 10 et 40** utilisateurs. Réserve : au palier 2, le p95 glissant du régime établi oscille entre 770 et 2 600 ms (`stats_history`), autour du seuil de 1 200 ms : le palier 2 est *sur* le coude ; le palier 3 (p95 = 10 × celui du palier 1) est sans ambiguïté. Un palier à 20 ou 25 utilisateurs situerait le point précisément ; je ne l'ai pas exécuté |
| Débit maximal observé avant dégradation (req/s) | **3,19 req/s** (palier 1, dernier palier respectant le critère). La capacité maximale du service, atteinte et non dépassée, est de **≈ 18 req/s** (plateau des paliers 3 et 4) |
| Ressource qui sature en premier, d'après les métriques de la partie 4.3 | **La CPU du plan.** Moyenne par minute, heures UTC. Palier 1 (13:36 à 13:39) : 7, 14, 36, 25 % (max **36**) ; palier 2 (13:40 à 13:43) : 15, 23, 77, 73 % (max **77**) ; palier 3 (13:44 à 13:47) : 56, 52, **99, 100** % ; palier 4 (13:48 à 13:51) : **96**, 29, **99, 99** % ; retour à 6-7 % cinq minutes après. La CPU monte avec la charge (36 → 77 → 100 → 99 %) et touche le plafond au palier 3, exactement là où le débit cesse de croître. La mémoire reste à 75-80 % de 13:36 à 13:52, sans lien avec la charge : elle ne sature pas. Réserve : la CPU n'est pas à 100 % sur chaque minute (52-56 % au début du palier 3, 29 % à 13:49) ; je ne l'explique pas |
| Valeur de `Http5xx` au palier le plus chargé | **0** (plateforme, `Http Server Errors`, 7 500 requêtes comptées sur la fenêtre d'une heure) ; côté Locust : 0 échec sur 8 924 requêtes |

Diagnostic, d'après ma grille écrite avant la mesure : *si la CPU du plan reste loin de 100 % alors que le p95 explose, la saturation est la file d'attente devant le worker ; si la CPU est à 100 %, c'est le calcul.* La CPU atteint 99-100 % pendant les paliers 3 et 4 : **c'est le calcul**. Les deux observations se tiennent : un seul *worker* synchrone occupe l'unique cœur de B1 (≈ 55 ms de calcul par requête, soit ≈ 18 req/s au plus), le reste attend en file ; la saturation de la CPU et la file sont deux faces du même plafond.

---

## 4. Questions

### Question 5.2 — p50 contre p99 sur le palier le plus chargé

Un écart faible entre p99 et p50 indique un problème de **capacité** (tout le monde attend pareil) ; un écart important indique un problème de **queue de distribution** (file derrière un *worker* unique, démarrage à froid, ramasse-miettes).

- Au palier 4 : p50 = 7 900 ms ; p99 = 11 000 ms ; rapport = **1,4**. **Écart faible** : tout le monde attend pareil, c'est un problème de **capacité** et non de queue de distribution. À titre de contraste, au palier 2 : p50 = 180 ms, p99 = 6 300 ms, rapport **35** : là, la majorité des requêtes est bonne et une minorité attend longtemps (rafale de 40 utilisateurs lancés en 4 s derrière un seul *worker* ; maximum de 7,6 s).
- Proportion de praticiens touchés : le p99 est la valeur dépassée par **1 requête sur 100**. Un praticien qui soumet *N* lésions par jour subit au moins une requête au-delà du p99 avec la probabilité `1 − 0,99^N` : environ **10 % pour N = 10**, **26 % pour N = 30**, **63 % pour N = 100**. Le p99 n'est donc pas un cas rare vu de l'utilisateur : il est sa journée.

### Question 5.3 — Engagement de service en une phrase

> « Jusqu'à **10** utilisateurs simultanés, 95 % des prédictions sont rendues en moins de **450** ms, avec moins de **1** % d'échecs, mesuré depuis un poste de consultation. »

Les trois valeurs sont lues sur le **dernier palier qui respecte le critère de la section 2** (palier 1), pas sur le palier de rupture : 450 ms est le p95 de `POST /predict` seul (le p95 agrégé, 400 ms, est tiré vers le bas par deux routes très rapides) ; il est vu du poste, réseau compris (≈ 30 ms d'aller-retour). Le taux d'échec observé est de 0 sur 458 prédictions ; je m'engage sur « moins de 1 % », qui est mon propre critère, car 458 observations sans échec ne bornent le vrai taux qu'à ≈ 0,7 % (règle des trois, 3 / 458).

### Question 5.4 — Deux options pour tenir l'engagement avec une charge doublée

1. **Mise à l'échelle verticale (*scale up*)** : passer à un SKU plus gros (plus de vCPU et de RAM sur la même instance, par exemple de B1 à B2 ou P1v3).
2. **Mise à l'échelle horizontale (*scale out*)** : ajouter des instances du même plan derrière le répartiteur de la plateforme (`az appservice plan update --number-of-workers N`, ou des règles d'*autoscale*).

**Je testerais en premier le *scale out*.** Mon API est sans état : le modèle est chargé en mémoire au démarrage et aucune session n'est conservée, donc deux instances font exactement le travail d'une, deux fois plus de capacité, et la mise à l'échelle est (presque) linéaire. Elle apporte en plus une redondance : un redémarrage ne coupe plus le service. Le *scale up* n'aide que si l'application sait utiliser les cœurs supplémentaires, ce qui n'est pas acquis avec un seul *worker* Gunicorn synchrone : un SKU à 2 vCPU resterait à moitié inutilisé tant que `--workers` n'est pas relevé dans l'image. **Ce que la mesure change.** Ma vérification du gain gratuit (`--workers`/`--threads`) est tranchée par la Mesure 15 : la CPU du plan atteint 99-100 % sur **un seul vCPU**, donc ajouter des *workers* ou des *threads* sur B1 n'ajouterait aucun calcul disponible, et ne ferait que répartir la même CPU. Le gain est à chercher dans plus de cœurs (*scale up* vers un SKU à 2 vCPU, avec `--workers 2`) ou dans plus d'instances (*scale out*). Pour tenir une charge doublée au même p95, la capacité mesurée de ≈ 18 req/s devrait être doublée : deux instances B1 en donneraient ≈ 36 req/s si la répartition est homogène, hypothèse que je n'ai pas testée.

### Question 5.5 — Si l'API rechargeait le modèle à chaque requête

- **Colonne la plus visible : les percentiles de latence**, p50 d'abord. Le coût du chargement s'ajouterait à *chaque* requête ; toute la distribution se décalerait vers le haut du temps de chargement, p95 et p99 compris.
- **Pourquoi pas le débit aux paliers non saturés.** Mon test est en **boucle fermée** : chaque utilisateur attend la réponse, puis réfléchit 1 à 5 s (3 s en moyenne). Le débit est ≈ `utilisateurs / (temps de réflexion + latence)`. À 100 utilisateurs, passer de 50 ms à 200 ms de latence ne ferait baisser le débit que de 32,8 à 31,3 req/s (−5 %), parce que le temps de réflexion écrase la latence. Le débit ne s'effondre qu'**à saturation**, quand les requêtes s'accumulent devant le *worker*.
- **Ordre de grandeur sur mon modèle.** Mon paquet fait 9,6 Ko et son rechargement a été mesuré à ≈ 1,5 ms en S2 : l'effet aurait été **faible** aujourd'hui. Il deviendra massif avec le réseau de neurones de la séance 4 (dizaines de Mo), et c'est alors que cette décision de conception de S2 se mesurera.

---

## 5. Limites de la mesure

- Latences vues d'un poste unique, sur un réseau partagé (voir Mesure 14) ; un second poste ne donnerait pas les mêmes chiffres.
- Un test de 3 minutes par palier dont la première est exclue ne laisse que 2 minutes de régime : le p99 d'un palier léger repose sur peu de requêtes.
- Le plan de service repose sur du matériel mutualisé : un même palier rejoué peut varier. Je n'ai exécuté chaque palier qu'une fois.
- La charge est une seule lésion perturbée : elle ne représente pas la diversité d'un vrai trafic.
