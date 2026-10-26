# JOURNAL_INCIDENT.md — Séance 3, partie 4

Auteur : PELLICANO Théo — M2 Industrialisation de l'IA dans le Cloud — YNOV Campus Montpellier — 2026-2027

---

## 4.1 — Ce que le flux de logs laisse voir

Journalisation activée avant lecture (`az webapp log config … --docker-container-logging filesystem --application-logging filesystem`), niveau : `Information` (système de fichiers, 3 jours / 100 Mo pour les journaux HTTP) ; flux ouvert avec `az webapp log tail`. Trafic généré : un `GET /health`, un `GET /model/info`, un `POST /predict` incomplet (`{"age_approx": 55}`, une variable sur quarante).

### Mesure 9 — flux de logs de la plateforme

| Observation dans le flux de logs | Relevé |
|---|---|
| Le nom du conteneur apparaît-il en préfixe de chaque ligne ? | **Non.** Les lignes de mon application (Gunicorn) n'ont qu'un horodatage UTC. Le nom du conteneur (`7797c9acce10_dermascan-tp42`) n'apparaît que dans les lignes de **statut de la plateforme** (`Stopping container: …`). Dans les fichiers de démarrage, les lignes du conteneur portent l'étiquette `ContainerStream:` et celles d'un ancien conteneur `[Previous Container]` |
| Retrouve-t-on la ligne d'accès de Gunicorn pour chaque requête ? | **Non**, aucune ligne par requête : 0 correspondance pour `GET`, `POST`, `/predict` dans l'archive des journaux de la plateforme (`az webapp log download`), ni pour le `GET /health` du 26/10 à 10:59:59 UTC (envoyé à un conteneur déjà journalisé) dans l'archive de l'incident. **Réserve levée par un second essai** : le premier trafic de test (10:57:43 UTC) est parti sur l'ancien conteneur, recyclé par `az webapp log config` (nouveau démarrage à 10:58:05). Second essai sur un conteneur stable (26/10, 12:36 ; trois `GET /health`, un `GET /model/info`, un `POST /predict` incomplet → `400`, un `POST /predict` complet → `200`) : **0 ligne** mentionnant une requête ou la charge utile dans `*_default_docker.log` ; le journal ne contient que les lignes de démarrage et d'arrêt de Gunicorn. Cohérent avec le **local (26/10, `docker logs`)** : le `CMD` de mon image n'active pas `--access-logfile`, et les 30 dernières lignes du conteneur ne contenaient que le démarrage (`Starting gunicorn 26.2.0`, `Listening at: http://0.0.0.0:8000`, `Using worker: sync`, `Booting worker`, `Control socket listening`) |
| Que journalise mon API sur un `/predict` incomplet ? | **Rien** (confirmé par le second essai). Le client reçoit un `400` : `{"error":"colonnes manquantes","nombre_manquantes":39,…}`. Cohérent avec le code : `app.py` ne contient aucun appel de journalisation |
| La liste des variables manquantes apparaît-elle dans les logs ? | **Non** : elle n'existe que dans le corps de la réponse HTTP (10 noms sur 39, tronquée par l'API) |
| Délai approximatif entre la requête et l'apparition de sa ligne | Sans objet : aucune ligne de requête. Les lignes de démarrage de Gunicorn (10:58:05) étaient déjà dans le flux à sa connexion (10:58:09) : `log tail` rejoue les dernières lignes existantes |
| **La charge utile complète du POST apparaît-elle dans les logs ?** | **Non** : aucune trace de `age_approx` ni des noms de colonnes dans les fichiers téléchargés. Conforme à la décision de S2 (l'API ne journalise jamais la charge). Le revers est la partie 6 : sans journal applicatif, je ne peux pas non plus reconstituer les décisions |

Constat pratique : `az webapp log tail` écrit sur la **sortie d'erreur** (fichier `log_tail.txt` vide, contenu dans `log_tail_err.txt`) ; il s'arrête avec « Log stream interrupted » quand le site est arrêté. Et `az webapp log config` **recycle le conteneur**.

Archive complète des journaux (`az webapp log download`) : **non jointe au dépôt**. Elle contient mon adresse IP publique dans une trace du service de gestion de la plateforme (Kudu) ; les lignes utiles sont citées dans ce document.

---

## 4.2 — Compte rendu d'incident : panne de port provoquée

### Résumé

| Élément | Contenu |
|---|---|
| Nature | Exercice : panne **provoquée**, pas un accident |
| Service touché | `dermascan-tp42` (cible A, App Service for Containers) |
| Début / fin | 11:59:53 (réglage posé) / 12:28:00 (premier 200 après correction), heure locale (UTC+1) |
| Durée d'indisponibilité | **≈ 28 min** (de 12:00 à 12:28). La panne a duré aussi longtemps parce que l'observation, prévue pour 10 min, en a duré 22 (21 sondes dont beaucoup de délais de 60 s) avant la correction ; la reprise elle-même a pris ≈ 5 min |
| Impact | Service injoignable depuis l'extérieur ; aucun patient concerné (environnement de recette) |

### Chronologie

| Heure | Événement |
|---|---|
| 11:59:53 | `WEBSITES_PORT` passé de 8000 à `9999` (port volontairement faux) |
| 11:59:59 | `az webapp restart` (la sonde de ce même instant répond encore `200` : c'est l'ancien conteneur) |
| 12:00:29 | Première défaillance vue du poste : `code=000` après 60 s (requête retenue puis abandonnée par `curl`). Le conteneur précédent a été arrêté à 12:00:24 |
| 12:04:54 | Ligne fautive (voir Mesure 10), quatre minutes cinquante-cinq après le redémarrage. Premier `503` vu du poste à 12:04:59 |
| 12:20:37 | **La plateforme n'abandonne pas** : quatrième échec de sonde (précédents : 12:04:54, 12:09:31, 12:15:04) ; un cinquième essai est en cours à la correction (12:23). Entre les essais : 1 min de blocage (« will be blocked for 1 minutes ») après les 2ᵉ et 3ᵉ échecs |
| 12:23:04 | Correction : `WEBSITES_PORT` remis à 8000, **sans** redémarrage explicite |
| 12:28:00 | Premier `200` sur `/health` (295,9 s après la correction) |

### Symptôme (vu de l'extérieur)

`curl -s -m 60 -o /dev/null -w "code=%{http_code} duree=%{time_total}s" "$APP_URL/health"` toutes les 30 s (prévu : 10 min ; réalisé : 22 min, car chaque sonde bloquée dure jusqu'à 60 s). Sur 21 sondes : **1** `200` (la première), **12** `000` (60 s sans réponse), **8** `503`. Les `503` arrivent **juste après** chaque échec de sonde de la plateforme (12:04:59 ; 12:10:05 et 12:10:35 pendant le blocage ; 12:15:37 et 12:16:07 ; 12:21:08 à 12:22:09), les `000` pendant la fenêtre de sonde de 230 s où la requête est retenue.

### Mesure 10 — diagnostic de la panne provoquée

| Élément du diagnostic | Relevé |
|---|---|
| Code HTTP vu par le client | `000` (aucune réponse en 60 s) pendant l'attente de la plateforme, `503` quand elle a déclaré l'échec et quand le site est bloqué ; aucun autre code |
| Délai avant la réponse d'erreur | Premier `503` : **300 s** après le redémarrage (12:04:59, réponse en 5,2 s). Avant, rien : les requêtes sont retenues puis abandonnées après 60 s par le client. Ensuite, `503` en 0,6 à 0,8 s |
| **Ligne de log exacte qui nomme la cause**, recopiée intégralement | Fichier `2026_10_26_lw0sdlwk00035Q_docker.log` : `2026-10-26T11:04:54.4204069Z State: Starting, Action: WaitingForSiteWarmUpProbeSuccess, LastError: ContainerTimeout, LastErrorTimestamp: 10/26/2026 11:04:54, LastErrorDetails: Container did not respond to startup probe on port 9999 within the expected time limit of 230s. Port mismatch detected: the container is listening on port 8000 but the platform is probing port 9999. Set the WEBSITES_PORT app setting to match the port your application listens on. If your application needs more time to start, increase WEBSITES_CONTAINER_START_TIME_LIMIT. Please inspect your container logs for more details as this could indicate an issue with your application., Details: Pinging warmup path to ensure container is ready to receive requests., DetailsLevel: ERR`. Précédée de : `2026-10-26T11:04:54.2916903Z Site startup probe failed after 230.016822 seconds.` |
| Combien de fois la plateforme a-t-elle retenté avant d'abandonner ? | Elle n'a **pas abandonné** : **4 échecs** de 230 s consécutifs (12:04:54, 12:09:31, 12:15:04, 12:20:37), soit 3 relances après le premier essai, et un 5ᵉ essai en cours à ma correction (23 min après le début) |
| Le processus applicatif a-t-il démarré, oui ou non ? | **Oui, à chaque essai** : `Starting gunicorn 26.2.0`, `Listening at: http://0.0.0.0:8000`, `Using worker: sync`, `Booting worker` (12:01:06, 12:05:43, 12:11:16, 12:16:49). L'application est saine ; la plateforme sonde le mauvais port |
| Temps écoulé entre le redémarrage et la ligne fautive | **4 min 55 s** (11:59:59 → 12:04:54) : arrêt de l'ancien conteneur et démarrage du nouveau (≈ 65 s) puis 230 s de sonde |

La ligne fautive est suivie de `Port mismatch detected`, avec en plus la mention explicite « the container is listening on port 8000 but the platform is probing port 9999 » : la plateforme diagnostique elle-même le désaccord.

### Cause

Désaccord entre deux réglages qui devaient porter la même valeur : `WEBSITES_PORT` (lu par la plateforme, port sondé) et `PORT` (lu par mon code, port d'écoute réel). Gunicorn écoutait sur 8000, la plateforme sondait `9999` : **l'application est saine, le service est mort**.

Vérification expérimentale de la Question 3.1 (la plateforme écrase-t-elle `PORT` avec `WEBSITES_PORT` ?) : **non**. Avec `WEBSITES_PORT=9999`, Gunicorn a démarré sur `0.0.0.0:8000` à chacun des quatre essais : `PORT`, posé explicitement en 3.1, n'est pas réécrit par la plateforme.

### Correction

`az webapp config appsettings set … WEBSITES_PORT=8000`, **sans** `restart`.

### Mesure 11 — délai de retour au service après correction

| Élément | Relevé |
|---|---|
| Durée entre la correction et le premier 200 | **295,9 s** (12:23:04 → 12:28:00), résolution ±30 s. Séquence vue du poste : six `000`, un `503` (12:27:04), un `000`, puis `200` |
| A-t-il fallu un redémarrage explicite, ou la plateforme a-t-elle repris seule ? | **Aucun redémarrage explicite** : la plateforme a repris seule. Le délai de ≈ 5 min est cohérent avec la fenêtre de sonde de 230 s en cours au moment de la correction (cinquième essai commencé vers 12:22) : corriger la configuration n'a pas écourté l'attente, la reprise a suivi la fin de cet essai (`503` à 12:27:04 puis `200`). *Hypothèse tirée des horaires ; les journaux de cette période n'ont pas été téléchargés* |

### Leçons

- Le code HTTP seul ne diagnostique rien (voir Q4.1) : la cause est dans le journal de la plateforme, pas dans le corps de la réponse.
- Une panne de configuration se répare par la configuration : retour à l'état sain sans reconstruire l'image, chiffré ci-dessus.
- À automatiser : une assertion « `WEBSITES_PORT` = `PORT` = `EXPOSE` » dans le script de déploiement.

---

## Questions

### Question 4.1 — Même code HTTP, deux causes sans rapport

Les deux cas sont relevés. Ma Mesure 4 (`DEPLOIEMENT.md`) avait donné `code=000` en 45 ms, c'est-à-dire aucune réponse HTTP, et ne documentait pas le cas du rôle absent ; je l'ai donc rejoué (rôle retiré à 14:23:41, redémarrage à 14:24:13, rôle rétabli à 14:31:33).

**Chronologie du cas « rôle absent »** (heure locale ; journaux en UTC, +1 h) : 14:24:39 premier échec de tirage de l'image, 26 s après le redémarrage ; **5 tentatives** de tirage (14:24:37, 14:25:22, 14:26:36, 14:27:51, 14:30:13), chacune échouant en moins de 2 s, séparées par des blocages de la plateforme de 1, 1 puis 2 minutes (« Site … will be blocked for 2 minutes ») : une temporisation croissante, qui n'existait pas pour le port faux. Vu du poste, 12 sondes : `200` (14:24:13), `200` (14:24:43, ancien conteneur), puis **dix `503`**, alternativement rapides (0,25 à 0,36 s) et lents (12,8 à 19,2 s). Retour au service **72 s** après le rétablissement du rôle (un seul redémarrage).

1. **Du point de vue du client**, qu'est-ce qui distingue les deux cas ? Dans les deux cas, le conteneur n'est pas en état de répondre et la plateforme renvoie un `503`. **Ce qui change est le profil de délai** : pour le port faux, 12 sondes sur 21 sont restées sans réponse pendant 60 s (`000`) tant que la plateforme attendait sa sonde de 230 s, et les `503` n'apparaissaient qu'après un échec de sonde ; pour le rôle absent, **aucun `000`** : la plateforme sait en 2 s qu'elle ne peut pas tirer l'image et répond `503` d'emblée. Cette différence statistique n'est visible qu'avec des dizaines de sondes, elle ne nomme pas la cause, et rien dans le code HTTP ne les sépare.
2. **Dans les logs**, ce qui les distingue :
   - cas du rôle absent (2.2) — ligne discriminante **relevée** : `LastError: ACRTokenRetrievalFailure, LastErrorDetails: Could not resolve the ACR token with the specified managed identity due to the following: Fetching Acr token failed -- response status indicates failure. Status Code:Unauthorized`, avec `Container pull image failed with reason: ImagePullFailure. Revert by terminate.` Le conteneur **n'a jamais démarré** : aucune ligne de Gunicorn après l'arrêt de l'ancien conteneur. Le libellé observé est `ACRTokenRetrievalFailure` / `ImagePullFailure` (et non `ImagePullUnauthorizedFailure`) ; le sens est le même (accès refusé au registre).
   - cas du port faux (4.2) — ligne discriminante **relevée** : `LastErrorDetails: Container did not respond to startup probe on port 9999 within the expected time limit of 230s. Port mismatch detected: the container is listening on port 8000 but the platform is probing port 9999.` ; le conteneur **a démarré** (lignes de Gunicorn présentes à chaque essai).
3. **Conclusion sur la valeur d'un code HTTP comme élément de diagnostic** : un code HTTP est un **symptôme agrégé**, pas une cause : le même 503 recouvre des défaillances situées à des couches différentes (le pull de l'image, le démarrage du processus, le routage), et un tableau de bord qui ne montre que des 5xx est insuffisant. Il faut croiser avec les journaux de la plateforme. Une alerte sur un taux de 5xx doit donc pointer vers la procédure de lecture de ces journaux.

### Question 4.2 — Les métriques de plateforme suffisent-elles à répondre à « mon service est-il lent pour mes utilisateurs ? »

**Non : il y manque les percentiles.** `HttpResponseTime` est une moyenne ; une moyenne stable peut cacher une queue qui s'allonge, et c'est cette queue (p95, p99) que la partie 5 mesure et que l'utilisateur subit.

---

## 4.3 — Métriques de plateforme

### Mesure 12 — métriques agrégées de la plateforme sur l'heure écoulée

Relevées avec `--interval PT1H` (un point par métrique : *Total* pour les compteurs, *Average* pondérée pour le temps de réponse) ; **aucune moyenne faite à la main** sur les lignes par minute.

| Métrique | Relevé sur l'heure écoulée |
|---|---|
| Nombre total de requêtes (`Requests`) | **7 500** (fenêtre d'une heure du 26/10 de 13:43 à 14:43 UTC, soit 14:43 à 15:43 en heure locale, relevée à 15:43) |
| Nombre de réponses 5xx (`Http5xx`) | **0** (`Http Server Errors`) : cohérent avec les 0 échec de Locust |
| Temps de réponse moyen (`HttpResponseTime`) | **4,606** (moyenne pondérée de la plateforme ; unité : secondes) |

**Lecture.** La fenêtre d'une heure ne couvre ni le palier 1 ni presque tout le palier 2 : le total de 7 500 est donc inférieur aux 8 924 requêtes émises par Locust, ce qui est cohérent, mais je n'ai pas rapproché les deux chiffres à l'unité (la plateforme compte aussi ses propres sondes de santé). Le temps moyen de 4,6 s est dominé par les paliers 3 et 4 (p50 de 2,6 s et 7,9 s) : il confirme la réponse à la Question 4.2, une moyenne dit que le service est lent sans dire à qui, ni la queue de distribution (p95 de 4,1 s et 10 s).

Les métriques du **plan** (`CpuPercentage`, `MemoryPercentage`) sont relevées après les paliers de charge et reportées dans la Mesure 15 de `RAPPORT_CHARGE.md`.
