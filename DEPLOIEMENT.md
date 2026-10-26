# DEPLOIEMENT.md — Séance 3, parties 2, 3 et nettoyage

Auteur : PELLICANO Théo — M2 Industrialisation de l'IA dans le Cloud — YNOV Campus Montpellier — 2026-2027

**Cible utilisée** : **A — App Service for Containers**, plan Linux B1, `germanywestcentral` (voir `FAISABILITE.md`, mesure 2).

**Image de secours** : non utilisée. Mon image S2 a été **republiée** dans le registre recréé (voir 2.1).

## Décisions de la séance (valeurs figées avant exécution)

| Décision | Valeur | Origine |
|---|---|---|
| Port d'écoute applicatif (`PORT`) et port déclaré à la plateforme (`WEBSITES_PORT`) | `8000` | Contrat d'interface de l'image S2 (`EXPOSE 8000`) |
| `MODEL_VERSION` | `1.0.0` | Version du paquet S2 |
| `LOG_LEVEL` | `info` | Assez pour voir les lignes d'accès Gunicorn |
| `ENVIRONMENT` | `recette` | La séance n'est pas une production clinique |
| **`SEUIL` (valeur de S2)** | **`0.1714486704741238`** | Valeur **exacte** du paquet S2, relevée dans la réponse de l'API en local le 26/10 (`"seuil":0.1714486704741238`). `MESURES.md` l'arrondit à 0,171449 : j'utilise la valeur complète pour que `SEUIL` soit bien celui de l'entraînement (le plus haut seuil qui atteint le rappel visé **0,95** sur le test) |
| **`SEUIL_BAS` (valeur abaissée testée en 3.3)** | **`0.017145`** (≈ le dixième) | Voir le choix ci-dessous |
| Chemin de la sonde de santé | `/health` | Contrat d'interface |

**Choix de `SEUIL_BAS`.** Pour que la décision bascule, la probabilité prédite `p` de `charge.json` doit vérifier `SEUIL_BAS < p < SEUIL`. `charge.json` est la ligne **bénigne** (`p = 0,031763`, relevée en 2.4) : 0,017145 < 0,031763 < 0,171449, la condition est vérifiée. La ligne maligne (`charge_maligne.json`, `p ≈ 0,75`) resterait `a_examiner` aux deux seuils et ne démontrerait rien.

---

## Partie 2.1 — Identifier l'image exacte à déployer

### Mesure 3 — identification exacte de l'image

| Relevé | Valeur |
|---|---|
| `loginServer` | `acrdermascantp42.azurecr.io` |
| Nom complet de l'image (`IMAGE_FULL`) | `acrdermascantp42.azurecr.io/dermascan-api:1.0.0` |
| Digest sha256 du tag déployé | `sha256:9269a14bf6e3754ab2dbea447ac95a4278b0db0f50f49191e8a8e01cbceddf97` (relevé dans le registre ; identique au manifeste local construit le 26/10) |
| Architecture déclarée dans le manifeste | `amd64` (système `linux`, manifeste OCI), taille déclarée 147 529 966 octets |
| Date de publication de ce tag | 2026-10-26 à 10:31:30 UTC (11:31 heure locale) |

**Historique à ne pas cacher.** Le digest de la publication S2 d'origine (`sha256:81e8ae36…2334e1`) n'existe plus : j'ai supprimé le registre le 09/10 pour ne rien dépenser pendant deux semaines de pause. Le registre a été recréé, l'image reconstruite depuis le même dossier (`08_docker_final`) et republiée ; le digest ci-dessus est donc **nouveau**, pour un tag `1.0.0` identique. Un rebuild avec le même `Dockerfile` ne reproduit pas le même digest (couches horodatées).

### Question 2.1 — Un camarade repousse une autre image sous le même tag

Un tag est un **pointeur mutable** : si quelqu'un repousse une autre image sous `1.0.0` puis que mon service redémarre, la plateforme retire de nouveau le tag et lance **l'autre image**, sans que rien dans ma configuration n'ait changé et sans erreur visible. Le digest relevé aujourd'hui me sert précisément à ça : (1) il identifie sans ambiguïté ce que j'ai audité et mesuré, donc je peux **détecter** que le tag a bougé en le comparant au digest courant du tag ; (2) je peux **redéployer exactement la même image** en la référençant par `dépôt@sha256:…`, qui désigne un contenu et pas un pointeur ; (3) c'est la valeur à inscrire dans `image_digest` des journaux (partie 6). Il reste utilisable tant que le manifeste existe dans le registre : l'ancienne image, devenue sans tag, y reste jusqu'à une purge. Mon déploiement actuel (par tag) n'est donc **pas** protégé ; le déployer par digest ou verrouiller le tag (`az acr repository update --write-enabled false`) le serait.

---

## Partie 2.2 — Création de l'application web

| Élément | Valeur |
|---|---|
| Nom de l'application (`APP_NAME`) | `dermascan-tp42` (accepté du premier coup : le nom était libre) |
| URL | `https://dermascan-tp42.azurewebsites.net` |
| `WEBSITES_PORT` posé à la création | `8000` |

### Mesure 4 — comportement du service **avant** tout octroi de droit sur le registre

| Relevé avant octroi des droits | Valeur |
|---|---|
| Code HTTP retourné | **`000`** : `curl` n'a reçu **aucune réponse HTTP**. Ce n'est pas un code du serveur |
| Durée de la réponse | 0,045 s : trop court pour un aller-retour TCP + TLS jusqu'en Allemagne, donc un échec local immédiat (résolution de nom ou connexion refusée), pas une attente du serveur |
| Contenu de la page renvoyée (une ligne de résumé) | Aucune (corps vide). **Mesure non exploitable** : je n'ai pas observé le comportement « avant octroi des droits ». Je ne le reconstitue pas de mémoire ; le cas a été rejoué (retrait du rôle puis redémarrage) : `503` après ≈ 1 minute, erreur `ACRTokenRetrievalFailure … Status Code:Unauthorized`, conteneur jamais démarré (voir `JOURNAL_INCIDENT.md`, Question 4.1). Mon poste a déjà eu un défaut de résolution DNS le même jour (registre, `ipconfig /flushdns`), ce qui est cohérent avec un `000` immédiat sans l'établir |

---

## Partie 2.3 — Identité d'accès au registre

Méthode retenue : **identité managée affectée par le système**, rôle **AcrPull** sur le **registre** (pas l'abonnement), `acrUseManagedIdentityCreds=true`. Aucun mot de passe n'existe. Méthode écartée mais connue : activer l'utilisateur administrateur du registre et coller son mot de passe dans la configuration, c'est-à-dire un secret partagé, long à révoquer, qui fuit dans l'historique des commandes et dans le portail.

### Mesure 5 — identité managée, rôle, portée, propagation

| Relevé | Valeur |
|---|---|
| `principalId` de l'identité managée | `7d4fa374-f956-4411-aaac-df7d1432f7a1` |
| Rôle accordé | `AcrPull` |
| Portée exacte du rôle (chemin complet) | `/subscriptions/fa6f278b-c975-4514-a7d5-ae2c3eb4310b/resourceGroups/rg-dermascan-registre-tp42/providers/Microsoft.ContainerRegistry/registries/acrdermascantp42` (le **registre**, pas l'abonnement ni le groupe) |
| Délai entre l'attribution du rôle et le premier pull réussi | **≤ 30 s** pour que le droit soit effectif : rôle créé à 10:39:46 UTC (champ `createdOn`), premier tirage de l'image lancé à 10:40:16 UTC et **réussi** à 10:40:41 UTC (25 s de téléchargement), d'après le journal de la plateforme. Je n'ai fait qu'un essai : c'est une borne haute, pas une mesure du délai réel de propagation. Jusqu'au premier `200` : 68 s (11:39:51 → ≈ 11:40:59), pull et démarrage compris |

### Question 2.2 — Les rôles plus larges

- **`AcrPush`** (qui inclut le pull) aurait aussi fonctionné : l'application pourrait en plus **pousser** des images, donc écraser le tag `1.0.0` que toutes les instances tirent. Une application compromise pourrait y substituer son propre code, c'est une attaque de chaîne d'approvisionnement.
- **`Contributor`** sur le registre (recommandé par certains tutoriels « pour que ça marche ») : l'application pourrait en plus **supprimer le registre**, **activer le compte administrateur** et lire ses identifiants, modifier le SKU ou les règles réseau.
- `AcrPull` ne permet que de **lire les images** : c'est le seul droit dont l'application a besoin pour démarrer.

### Question 2.3 — Propagation du rôle

Délai que j'ai dû attendre avant un pull réussi : **aucune nouvelle tentative n'a été nécessaire** ; le premier tirage de l'image, lancé 30 s après la création du rôle, a réussi (journal de la plateforme : `Pulling image` à 10:40:16 UTC, `is pulled from registry` à 10:40:41 UTC ; 68 s jusqu'au premier `200`). Une seule observation ne fixe pas un délai de propagation : Azure documente des délais pouvant aller jusqu'à plusieurs minutes. À reprendre dans un script de déploiement automatisé : une boucle de nouvelle tentative avec un plafond de **plusieurs minutes** après `az role assignment create`, plutôt qu'un `restart` unique, sous peine de conclure à tort à une erreur de configuration.

---

## Partie 2.4 — Premier démarrage et démarrage à froid

### Mesure 6 — premier démarrage réussi

| Mesure du premier démarrage | Valeur |
|---|---|
| Durée entre le `restart` et le premier 200 sur `/health` | **55,6 s** (restart à 11:40:01, premier 200 à 11:40:43 puis fin de la mesure ; tour 1, pas de nouvelle tentative). Journal de la plateforme (UTC) : début 10:40:00, image tirée en 25 s (10:40:16 → 10:40:41), sonde de démarrage réussie après 9,8 s, `Site started` à 10:40:52, soit 51 s au total. Résolution de ma mesure limitée : 2 sondes seulement, la première ayant attendu les 30 s du délai client |
| Codes HTTP observés pendant l'attente, dans l'ordre (`000` : délai client de 30 s dépassé) | `000` (11:40:03), puis `200` (11:40:43) |
| Champ `model_loaded` de la réponse `/health` | `true` (corps complet : `{"model_loaded":true,"status":"ok","version_modele":"1.0.0"}`) |
| Version de modèle retournée par `/model/info` | `1.0.0` (entraîné le 2026-10-09T09:48:24+00:00, 40 colonnes attendues, rappel cible 0,95) |
| `probabilite_maligne` et `decision` retournés par `/predict` | `0.031763` et `non_signale` |
| Le seuil appliqué par le service est-il celui de mon paquet S2 (0,1714486704741238, affiché 0,171449 en 6 décimales) ? | **Oui**, `"seuil":0.1714486704741238` dans `/model/info` et `/predict`, à ce moment aucun réglage `SEUIL` n'existait encore (valeur lue dans le paquet) |
| Durée de la première requête `/predict` | 0,170736 s (la première des cinq requêtes chronométrées) |
| Durée de la cinquième requête `/predict` identique | 0,173924 s (série : 0,1707 ; 0,1880 ; 0,1710 ; 0,1707 ; 0,1739) |

### Question 2.4 — Écart entre la première et la cinquième requête

Écart observé : **nul** — 0,003 s (≈ 2 %) entre la première et la cinquième requête, dans le bruit de la série (0,1707 à 0,1880 s).

**Limite de ma mesure.** Ces cinq requêtes ne sont pas les premières du processus : `/health`, `/model/info` et un `/predict` (celui de l'affichage) les ont précédées. Une initialisation paresseuse aurait été consommée par ce premier `/predict` non chronométré ; ma série ne peut donc ni confirmer ni exclure la cause 1. Par ailleurs chaque `curl.exe` ouvre une connexion neuve : le coût DNS/TLS est dans les cinq valeurs et ne peut pas créer d'écart entre elles. Il n'y a donc pas d'écart à expliquer ici ; il aurait fallu chronométrer le tout premier `/predict` après un redémarrage.

Deux causes possibles, chacune avec son test :

1. **Initialisation paresseuse dans le processus Python** (premier appel : importation tardive, premier passage dans le préprocesseur scikit-learn, premier appel de la bibliothèque numérique). *Confirmation ou exclusion* : lancer l'image **en local** (`docker run`, même `charge.json`) et mesurer sa première et sa cinquième requête avec `curl.exe` ; si l'écart local est du même ordre, la cause est dans le code, pas dans le réseau.
2. **Coût réseau et plateforme sur la première connexion** (résolution DNS, poignée de main TLS, chemin froid du répartiteur d'App Service). *Confirmation ou exclusion* : décomposer le temps avec `curl.exe -w "dns=%{time_namelookup} connect=%{time_connect} tls=%{time_appconnect} premier_octet=%{time_starttransfer} total=%{time_total}"` ; si l'écart est dans `dns`, `connect` ou `tls`, c'est le réseau ; s'il est dans `premier_octet` moins `tls`, c'est le serveur.

---

## Partie 3.1 — Variables d'environnement

Réglages posés (sans reconstruire l'image) : `PORT=8000`, `MODEL_VERSION=1.0.0`, `LOG_LEVEL=info`, `ENVIRONMENT=recette`, `SEUIL=0.1714486704741238` — valeur de S2, relevée dans `MESURES.md` de S2 : **rappel visé 0,95, seuil 0,171449**.

Nombre total de réglages d'application après 3.1 et 3.2 : **8** — les sept noms listés à la fin de 3.1 (`WEBSITES_ENABLE_APP_SERVICE_STORAGE`, `WEBSITES_PORT`, `PORT`, `MODEL_VERSION`, `LOG_LEVEL`, `ENVIRONMENT`, `SEUIL`) plus `INFERENCE_LOG_SALT` posé en 3.2. Le décompte automatique de mon script a échoué (guillemets de la requête `length(@)` mal transmis par PowerShell) ; le total de 8 est donc déduit de la liste, non recompté. `WEBSITES_ENABLE_APP_SERVICE_STORAGE` n'est pas de moi : la plateforme l'ajoute pour les conteneurs.

### Question 3.1 — `WEBSITES_PORT` et `PORT`

Réponse écrite **avant** la mesure de la partie 4 :

- Ils doivent porter **la même valeur** (8000).
- `WEBSITES_PORT` est lu **par la plateforme** : il lui dit sur quel port du conteneur router le trafic et envoyer sa sonde de démarrage. `PORT` est lu **par mon code** : `gunicorn -b 0.0.0.0:${PORT}`.
- S'ils diffèrent : l'application est saine (elle écoute bien sur `PORT`) mais la plateforme frappe un port vide, juge le conteneur défaillant et renvoie une erreur 503 : *l'application est saine, le service est mort*. Je prédis aussi que, comme j'ai posé `PORT` explicitement en réglage, la plateforme ne l'écrasera pas avec `WEBSITES_PORT` ; c'est ce que la partie 4.2 devait trancher. **Résultat (voir `JOURNAL_INCIDENT.md`) : prédiction confirmée.** Avec `WEBSITES_PORT=9999`, Gunicorn a quand même écouté sur `0.0.0.0:8000` à chacun des quatre essais : la plateforme n'écrase pas `PORT`.

---

## Partie 3.2 — Secrets

Sel engendré localement (`openssl rand -hex 16` ou équivalent PowerShell) et poussé comme réglage `INFERENCE_LOG_SALT`. **Il ne figure dans aucun fichier du rendu, dans aucune capture, et n'est pas répété dans ce document.**

### Mesure 7 — visibilité réelle du secret à ses trois points d'exposition

| Contrôle | Observation |
|---|---|
| La valeur du sel est-elle masquée dans la sortie du CLI ? | **Non.** `az webapp config appsettings list` a renvoyé une valeur de 32 caractères **identique au sel engendré** (comparaison faite dans le script, sans l'afficher). Quiconque peut lister les réglages (rôle Contributeur sur l'application) lit le secret en clair |
| Est-elle visible dans le portail Azure, onglet Variables d'environnement ? | **Non observé** : l'application a été supprimée à 16:42 avant que j'aie ouvert cette page. Constat sans portail : le CLI renvoie déjà la valeur en clair (ligne précédente), donc le niveau d'exposition est celui du droit de lecture des réglages, quelle que soit l'interface |
| Est-elle lisible par un processus qui s'exécuterait dans le conteneur ? | **Oui par principe** (`os.environ["INFERENCE_LOG_SALT"]` est le mécanisme prévu). Non vérifié par SSH ou console |

### Question 3.2 — Le coffre-fort

Le service est **Azure Key Vault**. Associé à l'**identité managée** créée en 2.3 (avec le rôle `Key Vault Secrets User` sur le coffre), il permettrait de **supprimer complètement la valeur du sel de la configuration** : le réglage d'application n'y contiendrait plus qu'une *référence* au secret, que la plateforme résout à l'exécution avec l'identité de l'application. Il n'y a alors plus de copie du secret dans le portail ni dans l'historique du CLI, sa rotation ne demande pas de redéploiement, et chaque lecture est auditée.

---

## Partie 3.3 — Sonde de santé et épreuve du seuil

### Mesure 8 — effet de la configuration complète après redémarrage

| Relevé après redémarrage | Valeur |
|---|---|
| Chemin de sonde enregistré | `/health` |
| Durée du redémarrage jusqu'au premier 200 | Relevé brut : **0,2 s** (redémarrage à 11:41:53, `200` à 11:41:55). **Ce n'est pas une durée de redémarrage** : un conteneur ne repart pas en 2 s (le premier démarrage en a pris 55,6). Les changements de réglages faits juste avant (3.1, 3.2, sonde) recyclaient déjà le conteneur ; c'est l'**ancien** conteneur qui a répondu, la preuve étant que `/predict` rendait encore le seuil du paquet alors que `SEUIL` était déjà posé. Le journal de la plateforme montre ce qui s'est passé à 10:41:53 UTC : mon redémarrage explicite est tombé pendant un recyclage en cours, le démarrage a été annulé (`Site startup probe failed after 0.5886452 seconds`, `LastError: ContainerStartupFailure`, `Failed to start site. Revert by stopping site`), le site est resté **arrêté de 10:42:00 à 10:43:48 UTC**, puis a redémarré (sonde réussie après 19,9 s, 10:44:08). Durées de recyclage vues du poste : **136 s** (collision comprise), **49 s**, puis **44 s** ; vues de la plateforme, sans collision : **≈ 26 s** (10:44:27 → 10:44:53 UTC) ; démarrage à froid : **55,6 s** (Mesure 6). La différence poste/plateforme (≈ 20 s) est la durée de la commande `az` elle-même |
| Délai entre le `appsettings set` du seuil abaissé et l'apparition du nouveau seuil dans la réponse | **136 s**. Pendant ce délai : deux réponses de l'ancien conteneur (11:42:01, 11:42:06), puis une requête restée sans réponse jusqu'au délai client de 60 s (11:43:12), puis la réponse du nouveau conteneur ; soit **environ 2 minutes** sans réponse utile (site arrêté de 11:42:00 à 11:43:48 heure locale d'après la plateforme, voir ci-dessus : l'allongement vient de la collision avec mon redémarrage explicite). Remise du seuil : **49 s**. Un `appsettings set` n'est donc pas un changement « à chaud » : il recycle le conteneur, et avec une seule instance le service est coupé (≈ 26 s côté plateforme sans collision). Le recyclage vu du poste varie de 44 à 136 s (trois mesures) |
| Nombre total de réglages d'application | 8 (déduit de la liste, voir 3.1) |
| La valeur de `MODEL_VERSION` apparaît-elle dans la réponse de `/model/info` ? | **Non : aucun champ ne porte ce nom**, et `version_modele` (`1.0.0`) vient du paquet ; comme `MODEL_VERSION` vaut aussi `1.0.0`, la réponse seule ne prouve rien dans un sens ou dans l'autre. La lecture de `app.py` tranche : l'API ne lit pas `MODEL_VERSION`, `version_modele` vient de `PAQUET["version"]`. Seules `PORT`, `MODEL_PATH` et `SEUIL` sont lues dans l'environnement. Le réglage `MODEL_VERSION` est donc inerte |
| `probabilite_maligne`, avec mon seuil de S2 | `0.031763` |
| `seuil` et `decision` retournés, avec mon seuil de S2 (0,1714487) | `0.1714486704741238` et `non_signale` |
| `probabilite_maligne`, avec le seuil abaissé (0,017145) | `0.031763` — **identique** |
| `seuil` et `decision` retournés, avec le seuil abaissé (0,017145) | `0.017145` et `a_examiner` |

Contrôle de cohérence : même entrée, même modèle, la **probabilité est identique** aux deux seuils (0,031763) ; seuls `seuil` et `decision` changent (`non_signale` → `a_examiner`).

Seuil remis à la fin de l'épreuve : **49 s** après la commande, mais à `0.171449` et non à `0.1714486704741238` : la copie de mon fichier de variables présente sur mon poste portait encore la valeur arrondie (mon correctif n'y avait pas été déposé). Écart de 3,3·10⁻⁷, sans effet sur la décision de `charge.json` (`p = 0,031763`), mais le service ne tournait plus avec le seuil exact du paquet et `seuil_source` aurait valu `env`. **Corrigé** par une nouvelle commande `appsettings set` (11:49:48) : l'ancienne valeur a été servie pendant 8 sondes consécutives sans aucune interruption, puis `0.1714486704741238` est apparu après **44 s** (`/predict` et `/model/info` concordent). Troisième mesure d'un recyclage par `appsettings set` : 136 s, 49 s, 44 s ; ici l'ancien conteneur a répondu jusqu'à la bascule, sans coupure visible, alors que la première série avait montré une requête sans réponse.

### Question 3.3 — Deux versions de la sonde

Je déploierais la **version 2** (modèle chargé **et** inférence de test sur une entrée figée), mais en la gardant légère : l'inférence de test est calculée **une fois au chargement** et le résultat mémorisé, la sonde ne fait que relire cet état.

Le risque de la version 1 (200 dès que le processus répond) : une instance dont **le modèle n'a pas pu être chargé** répond « santé OK » ; la plateforme continue de lui envoyer du trafic et chaque `/predict` échoue en 503, sans que rien ne la retire du routage. Pour un outil clinique, c'est un échec silencieux. Le risque de la version 2 : une sonde trop exigeante (inférence réelle à chaque passage, ou dépendance externe) peut retirer **toutes** les instances en même temps pour un défaut de la sonde elle-même, et provoquer un redémarrage en boucle. Remarque : mon `/health` de S2 renvoie déjà 503 quand le modèle est absent, il est donc plus proche de la version 2 allégée que de la version 1.

### Question 3.4 — La probabilité n'a pas bougé d'un millième, la décision a changé

1. **C'est le service qui a changé de comportement, pas le modèle** : l'estimation (la probabilité) est identique, c'est le **seuil**, une variable de configuration du service, qui a bougé.
2. **Non, le service ne rend pas « les mêmes décisions »**, et un rapport qui dit « le modèle a changé d'avis » décrit mal ce qui s'est passé : le modèle n'a pas d'avis, il estime ; c'est la **politique de décision** (le seuil) qui a été modifiée. Un audit doit dire « le seuil appliqué est passé de 0,171449 à 0,017145 le … à … ».
3. **La trace qui permettrait de le découvrir après coup** : les champs `seuil_applique` et `seuil_source` (`paquet` ou `env`) de **chaque ligne de journal** (grille de la partie 6) ; un simple regroupement par `seuil_applique` dans le temps révèle le changement, et `seuil_source = "env"` signale qu'il vient d'un remplacement opérationnel. Complément côté plateforme : le journal d'activité d'Azure enregistre qui a modifié les réglages d'application.
4. **Position** : c'est **un progrès à condition d'être encadré**. Progrès : régler le compromis rappel/charge d'alertes sans reconstruire ni redéployer, c'est la séparation entre artefact immuable et configuration. Risque : un paramètre qui porte la promesse clinique (rappel visé 0,95) se change par une commande, sans relecture. Argument adverse : le seuil fait partie de la validation du modèle, le changer revient à livrer une **nouvelle version** qui doit repasser par la chaîne de validation ; « facile à changer » veut aussi dire « facile à changer à tort ». Mon encadrement : droit d'écriture sur les réglages restreint, `seuil_source` journalisé, alerte si `env` apparaît, model card mise à jour.

---

## Nettoyage et extinction

### Mesure 16 — inventaire avant destruction

| Relevé avant destruction | Valeur |
|---|---|
| Nombre de ressources dans le groupe | **2** (`az resource list`, 16:40) |
| Types de ressources listés | `plan-dermascan-tp42` (`Microsoft.Web/serverFarms`) et `dermascan-tp42` (`Microsoft.Web/sites`), tous deux `Succeeded`. L'identité managée affectée par le système n'apparaît pas comme ressource séparée : elle disparaît avec l'application |
| Le registre ACR est-il dans ce groupe ou dans le groupe du registre ? | Dans le **groupe du registre** `rg-dermascan-registre-tp42` : `acrdermascantp42` (`Microsoft.ContainerRegistry/registries`, `Succeeded`). Une seule attribution de rôle sur le registre avant la destruction : `AcrPull` (portée : le registre) |

### Mesure 17 — contrôles de destruction

| Contrôle de fin de séance | Observation |
|---|---|
| Le groupe `rg-dermascan-s3-tp42` apparaît-il encore ? | **Non.** `az group list` ne renvoie plus que `rg-dermascan-registre-tp42` (`Succeeded`) |
| Reste-t-il une attribution de rôle sur le registre ? | **Non.** L'attribution `AcrPull` a été supprimée **avant** le groupe ; `az role assignment list` sur le registre renvoie une liste vide, donc aucune ligne « identité inconnue » orpheline |
| Le groupe du registre est-il, lui, toujours debout ? | **Oui** : `az group exists` renvoie `true` |
| `az group exists` renvoie | `true` à six interrogations consécutives (16:42:19 → 16:43:18), puis **`false` à 16:43:30**, soit environ 70 s après la première interrogation |
| Crédit restant, relevé dans Cost Management | Voir la section suivante |

### Contrôle d'extinction

| Contrôle d'extinction | Fait |
|---|---|
| `az group exists` sur le groupe de la séance renvoie `false` | Oui, à 16:43:30 |
| Aucun conteneur de la séance dans `docker ps -a` | Oui : la liste est vide |
| Environnement Locust du poste | Supprimé |

### Question 7.1 — Conserver le registre, détruire le reste

Le registre vit dans **son propre groupe de ressources** (`rg-dermascan-registre-tp42`), distinct du groupe de la séance (`rg-dermascan-s3-tp42`). Un groupe de ressources est l'**unité de cycle de vie** : `az group delete` du groupe de la séance emporte tout ce qu'il contient et ne peut pas toucher le registre, qui est ailleurs. L'opération est sûre en une commande parce que la frontière de suppression suit déjà la frontière de ce qu'on veut garder.

Si le registre avait été dans le même groupe que l'application, il aurait fallu : soit **déplacer** le registre dans un autre groupe avant la suppression (`az resource move`), soit **supprimer ressource par ressource** (application, plan, etc.) en listant précisément ce qu'on garde, avec le risque d'en oublier une et de continuer à la payer. Dans les deux cas, l'attribution de rôle `AcrPull` orpheline sur le registre reste à supprimer à part, avant le groupe.
