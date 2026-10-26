# FAISABILITE.md — Séance 3, parties 0 et 1

Auteur : PELLICANO Théo — M2 Industrialisation de l'IA dans le Cloud — YNOV Campus Montpellier — 2026-2027

---

## Tableau de décisions (valeurs fixées avant la partie 1)

| Décision | Contrainte | Valeur |
|---|---|---|
| Suffixe personnel identique à S1 | repris de S1 | `tp42` |
| Région Azure | une seule, la même partout | `germanywestcentral` — la politique d'abonnement « Allowed resource deployment regions » relevée en S1 n'autorise que `germanywestcentral`, `austriaeast`, `italynorth`, `denmarkeast`, `belgiumcentral` ; la sonde 1 l'a revérifiée le 26/10 à 11:32 : mêmes cinq régions |
| Groupe de ressources de la séance | préfixé `rg-dermascan-s3-` | `rg-dermascan-s3-tp42` |
| Registre ACR existant | celui de S1 | `acrdermascantp42` (groupe `rg-dermascan-registre-tp42`), **recréé pour cette séance** : il avait été supprimé le 09/10 pour ne rien consommer pendant la pause, ce qui a aussi fait disparaître le digest de l'image S2 publiée (voir `DEPLOIEMENT.md`, 2.1) |
| Dépôt et tag de l'image S2 | ce qui est réellement dans le registre | `dermascan-api:1.0.0` — contrôlé avec `az acr repository show-tags` en 2.1 |
| Plan de service | préfixé `plan-dermascan-` | `plan-dermascan-tp42` |
| Application web | unique sur Azure | `dermascan-tp42` (nom libre à la création) |

### Question 0.1 — Conséquence supplémentaire de l'unicité du nom de l'application web

Le nom devient un **sous-domaine public** `<nom>.azurewebsites.net`, résolu dans le DNS mondial : il est donc énumérable. Un attaquant qui cherche des services mal protégés n'a pas besoin d'accéder à mon abonnement, il lui suffit de deviner ou de balayer des noms prévisibles (`<projet>-<suffixe>`, `dermascan-…`) pour trouver une API de santé exposée sans authentification, alors qu'un registre ACR n'expose rien tant qu'on ne s'y authentifie pas. S'y ajoute un risque de reprise de sous-domaine : un nom libéré et redéposé par un tiers hérite des enregistrements DNS laissés pendants.

---

## Partie 1.2 — Sondes de faisabilité de l'abonnement

### Mesure 1 — sondes de faisabilité

| Sonde | Commande source | Relevé |
|---|---|---|
| Régions autorisées par la politique | `az policy assignment list` | `germanywestcentral`, `austriaeast`, `italynorth`, `denmarkeast`, `belgiumcentral` (sonde 1 de 11:32 ; ma région en fait partie) |
| `Microsoft.Web` | `az provider show` | `NotRegistered` au départ (déjà vu dans `01_prealables`, 11:16) ; enregistré par la sonde → `Registered` |
| `Microsoft.ContainerInstance` | `az provider show` | `NotRegistered` au départ ; enregistré par la sonde → `Registered` (utile si la cible B devenait nécessaire) |
| `Microsoft.ContainerRegistry` | `az provider show` | `Registered` (inchangé) |
| Création du plan App Service Linux | `az appservice plan create` | **Succès** : code retour 0, `provisioningState` `Succeeded`, état `Ready`, SKU `B1` (tier Basic, capacité 1), `germanywestcentral`, créé en 15 s |
| Code d'erreur exact, le cas échéant | sortie de la commande | Aucun. Le seul avertissement affiché est l'information `Creating App Service Plan … (Linux, SKU: B1)` |
| Durée totale de la sonde | chronomètre | 6,5 min (11:31:59 → 11:38:26) ; la création du plan n'en représente que 15 s, le reste est l'enregistrement des deux fournisseurs manquants. Limite de 20 min : respectée |

Rappel de S1 : `Microsoft.ContainerRegistry` était `Registered` et `Microsoft.ContainerInstance` `NotRegistered` ; `Microsoft.Web` n'avait jamais été sondé. Un fournisseur non enregistré se rattrape avec `az provider register --namespace <nom> --wait` (une à trois minutes), et l'erreur correspondante, `MissingSubscriptionRegistration`, n'a rien à voir avec les droits.

Étiquettes du groupe de la séance : `projet=dermascan`, `seance=s3`, `proprietaire=theo.pellicano`, `a_detruire=2026-10-26` (relevé sur le groupe créé, sortie de `02_faisabilite`).

---

## Partie 1.3 — Choix de la cible et engagement

### Mesure 2 — cible retenue, fait déclencheur et heure de la décision

| Élément de la décision | Réponse |
|---|---|
| Cible retenue | **A — Azure App Service for Containers** (plan Linux B1) |
| Fait déclencheur, cité avec le message d'erreur s'il y en a un | La **création réelle** du plan B1 a réussi (code 0, état `Ready`) une fois `Microsoft.Web` enregistré, et la politique de régions autorise `germanywestcentral`. Aucune erreur à citer : la seule cause de blocage possible, `MissingSubscriptionRegistration`, se rattrapait par l'enregistrement |
| Heure de la décision | 11:38 (fin de la sonde), soit 6,5 min après le début de la partie 1 (11:31:59), pour une limite de 11:51:59 |
| Ce que cette cible ne permettra pas de montrer aujourd'hui | Rien de ce que la séance mesure n'est perdu (identité managée pour le pull, répartiteur et TLS gérés, paramètres, sondes). Je ne montrerai **pas** par choix : la mise à l'échelle automatique, les emplacements de déploiement et l'isolation réseau privée. La capacité testée en partie 5 est celle d'**une** instance B1 |

---

## Questions

### Question 1.1 — Niveau d'abstraction des trois cibles (grille IaaS / PaaS / SaaS de S1)

| Cible | Modèle de service | Ce que je ne gère pas | Ce qui reste à ma charge |
|---|---|---|---|
| App Service for Containers | **PaaS** | Matériel, hyperviseur, système d'exploitation, moteur de conteneur, répartiteur de charge, certificat TLS du domaine `azurewebsites.net`, redémarrage automatique, correctifs de la plateforme | L'**image** (son contenu, ses CVE, sa base), la configuration (réglages d'application, port, sonde de santé), l'identité et les rôles, le dimensionnement du plan (SKU, nombre d'instances), la journalisation et le coût |
| Azure Container Instances | **CaaS** (conteneur à la demande, entre IaaS et PaaS) | Machine, système hôte, orchestrateur : on déclare 1 vCPU et 1,5 Go, on ne gère pas de machine | L'image, le port publié, **le serveur applicatif exposé directement** (nombre de *workers* et de *threads* Gunicorn, sans répartiteur devant), les identifiants du registre (principal de service, donc un secret), la sonde (décrite dans un YAML), l'absence de TLS par défaut, la mise à l'échelle **manuelle** |
| Docker sur mon poste | **Auto-hébergé**, en deçà de l'IaaS : aucun service cloud | Rien : seul Docker Desktop est fourni | Tout : le matériel et sa disponibilité, le système, le moteur, le réseau, l'exposition publique (absente), les correctifs, la sauvegarde, le TLS, la supervision |

### Question 1.2 — Coût du SKU choisi et jours de fonctionnement financés par le crédit

| Donnée | Valeur |
|---|---|
| SKU choisi | **B1 Linux** (tier Basic, 1 instance), confirmé par la création du plan |
| Coût mensuel annoncé, région `germanywestcentral` | **0,0159 €/h** pour « Azure App Service Basic Plan - Linux », B1, `germanywestcentral` (API publique de prix, relevé du 26/10 à 11:55), soit **≈ 11,61 €/mois** (× 730 h) et **0,382 €/jour**. En dollars : 0,01802 $/h, ≈ 13,15 $/mois (cohérent avec les ≈ 13,14 $ lus à la création). Le registre Basic : 0,1466 €/jour (+ 0,088 €/Go/mois de stockage, négligeable pour une image de 0,15 Go). L'API du plan renvoie un champ `freeOfferExpirationTime` (2027-04-26) dont je n'ai pas vérifié ce qu'il implique pour la facturation : je calcule donc au tarif plein, par prudence |
| Crédit restant (Cost Management) | **88 € sur 88 €** affichés (valeur arrondie par le portail), coûts d'octobre **0,33 €**, expiration le **06/10/2027** (345 jours), relevé le 26/10/2026 vers 16:00. Dernier relevé antérieur : ≈ 87,72 € le 09/10. Le coût du jour n'est pas forcément complet : Cost Management a un retard de quelques heures |

Calcul : `jours = crédit ÷ coût par jour`, avec le crédit relevé aujourd'hui (88 − 0,33 = 87,67 €) et les prix en euros ci-dessus : B1 seul ≈ **229 jours** (87,67 ÷ 0,382) ; B1 **et** registre (0,382 + 0,1466 = 0,5286 €/jour) ≈ **166 jours** ; registre seul ≈ **598 jours**. Le crédit expire dans 345 jours : en fonctionnement continu et sans autre dépense, B1 seul et B1 avec registre épuiseraient le crédit avant l'expiration ; le registre seul le dépasserait.

Ce chiffre ne dit pas « je suis en danger tout de suite » : un plan oublié un week-end coûte ≈ 1,3 USD. Il dit que la facturation est **à l'heure, trafic ou non**, qu'elle s'ajoute à celle du registre qui doit survivre jusqu'à la soutenance, et qu'un crédit épuisé fait basculer l'abonnement sur l'offre Starter, qui interdit `Microsoft.ContainerRegistry` : on perdrait le registre, donc les séances 4, 5 et le projet. C'est cela qui justifie le nettoyage de fin de séance, pas le montant d'un seul jour.
