# JOURNALISATION_INFERENCES.md — Séance 3, partie 6

Auteur : PELLICANO Théo — M2 Industrialisation de l'IA dans le Cloud — YNOV Campus Montpellier — 2026-2027

**Statut.** Ce document est une **spécification**, pas une implémentation : l'API de la séance 2 n'est pas modifiée en S3, et la séance 5 (dérive) consommera ce format. Deux faits de S2 restent vrais aujourd'hui : l'API **ne journalise jamais la charge utile**, et `decision` y prend les valeurs `a_examiner` / `non_signale` (vocabulaire réellement servi par mon API). Le constat réel sur ce que le flux de logs laisse voir est dans la Mesure 9 de `JOURNAL_INCIDENT.md`.

Valeurs de référence de S2 utilisées ici : seuil **0,1714486704741238** (arrondi à 0,171449 dans `MESURES.md`), rappel visé **0,95**, **40** variables d'entrée, 1 042 patients dans le jeu, jusqu'à 9 184 lésions par patient.

---

## 6.1 — Grille : que journaliser, que ne jamais journaliser

| Donnée | Journaliser ? | Forme | Justification |
|---|---|---|---|
| Horodatage de la requête, en UTC | Toujours | Brut | Sans ordre temporel, aucune reconstitution d'incident n'est possible |
| Identifiant de corrélation de la requête | Toujours | Brut, généré si absent | Seul moyen de relier une ligne de log à une réclamation client |
| Version du modèle et digest de l'image | Toujours | Brut | Répond à « quel modèle a produit cette réponse », question n° 1 d'un audit |
| Identifiant du patient (`patient_id`) | **Jamais en clair** | Pseudonymisé : `patient_ref` | Il faut relier les lésions d'un même patient (jusqu'à 9 184) sans pouvoir remonter au patient sans le sel |
| Identifiant de la lésion (`isic_id`) | Non | — | Identifiant public du jeu ISIC : il permet de retrouver l'image et les métadonnées d'origine, donc de réidentifier. `request_id` suffit à corréler ; c'est le poste de consultation qui associe `request_id` ↔ lésion dans le dossier clinique |
| Âge et sexe (`age_approx`, `sex`) | Oui, réduit | Âge en **tranche de 10 ans** (`60-69`), sexe brut | Covariables nécessaires à la dérive (S5) ; l'âge exact n'apporte rien à la dérive et rapproche de l'individu |
| Site anatomique (`anatom_site_general`) | Oui | Brut (modalité à faible cardinalité) | Covariable de dérive. Attention : croisé avec âge et sexe, c'est un quasi-identifiant (voir Q6.2) |
| Valeurs brutes des variables morphologiques (`tbp_lv_*`) | **Non** | — | Trente-cinq mesures continues d'une lésion forment une empreinte quasi unique : c'est de la donnée de santé à haute dimension. Seuls un `tbp_tile_type` et **une** mesure de taille discrétisée sont conservés (voir plus bas) |
| Probabilité maligne prédite | Toujours | Brut, **6 décimales** | Sortie du modèle, non identifiante seule ; indispensable à l'audit et à la dérive de score |
| Seuil appliqué et rappel visé | Toujours | Brut, **précision complète** + `seuil_source` | Un journal qui garde la décision sans le seuil ne permet pas de répondre à l'audit. Précision complète parce que le seuil réel (0,1714486704741238) diffère de sa version arrondie à six décimales (0,171449) : arrondi, il changerait la décision pour toute probabilité comprise entre les deux |
| Décision rendue (`a_examiner` / `non_signale`) | Toujours | Brut | C'est l'objet même de la réclamation |
| Latence d'inférence | Toujours | Brut, en ms | Supervision et SLO ; aucune donnée personnelle |
| Code HTTP et message d'erreur éventuel | Toujours | Code brut ; message **sans valeur de charge** (noms de champs manquants et `nombre_manquantes`, jamais les valeurs reçues) | Diagnostic ; le message d'erreur est le canal par lequel la charge fuit le plus souvent |
| Adresse IP source de l'appel | **Non** dans le journal applicatif | — | Donnée à caractère personnel (art. 4), sans besoin applicatif. Elle reste dans le journal d'accès de la plateforme, à durée courte (voir 6.3) |
| Identité du praticien ayant déclenché l'appel | Oui, **pseudonymisée** — quand l'authentification existera | `praticien_ref` (même mécanisme que `patient_ref`) | Aujourd'hui l'API est publique et **sans authentification** : il n'y a donc rien à journaliser, et c'est en soi un écart à signaler (voir Q0.1). Dès qu'il y a une identité, l'audit voudra savoir *qui* a décidé |
| Jeton d'authentification ou clé d'API | **Jamais** | — | Un journal qui fuit livrerait un accès valide |
| Sel de pseudonymisation `INFERENCE_LOG_SALT` | **Jamais** | — | Sa fuite rend la pseudonymisation réversible par énumération |

**Sous-ensemble de covariables conservé** (réponse à la question de la séance 5 posée en 6.2) :
`age_tranche`, `sex`, `anatom_site_general`, `tbp_tile_type`, `clin_size_long_diam_mm_bin` (décile calculé sur la distribution d'entraînement S2).

---

## 6.2 — Format d'une ligne de journal d'inférence

Une ligne JSON par inférence, UTF-8, sans retour à la ligne interne.

```json
{"ts":"2026-10-26T14:03:17.482Z","request_id":"3f6c2a1e-8d0b-4c59-9a47-1b2e5d7c9f10","model_version":"1.0.0","image_digest":"sha256:<digest-relevé-en-2.1>","patient_ref":"9d41f07a3c5be812","probabilite_maligne":0.031763,"seuil_applique":0.1714486704741238,"seuil_source":"paquet","rappel_cible":0.95,"decision":"non_signale","covariables":{"age_tranche":"60-69","sex":"male","anatom_site_general":"posterior torso","tbp_tile_type":"3D: white","clin_size_long_diam_mm_bin":"D7"},"inference_ms":3.4,"http_status":200,"input_schema_version":"1.0"}
```

| Champ | Forme | Décision et justification |
|---|---|---|
| `ts` | UTC ISO 8601, milliseconde, suffixe `Z` | Imposé |
| `request_id` | UUID v4 | Repris de l'en-tête `X-Request-ID` si l'appelant le fournit **et** s'il est valide (UUID ou chaîne ≤ 64 caractères alphanumériques) ; sinon **généré par le service**, puis renvoyé dans l'en-tête de réponse pour que le poste de consultation puisse l'archiver |
| `model_version` | chaîne SemVer | Source : **le paquet sérialisé**, c'est-à-dire le modèle réellement chargé. La variable `MODEL_VERSION` est déclarative : une variable d'environnement peut mentir (oubli, copier-coller), le paquet non. Si les deux divergent, c'est un avertissement à journaliser, pas une raison de choisir la variable |
| `image_digest` | `sha256:…` | **Digest et non tag** : le tag est mutable (Q2.1 de `DEPLOIEMENT.md`), le digest désigne un contenu. Une image ne peut pas connaître son propre digest à la construction : il est injecté **au déploiement** par un réglage `IMAGE_DIGEST`, relevé en 2.1 |
| `patient_ref` | 16 hex | Pseudonyme stable, voir plus bas. Absent (`null`) si l'appelant ne fournit pas `X-Patient-Ref` |
| `probabilite_maligne` | nombre ∈ [0, 1], **6 décimales** | Avec 4 décimales, la décision n'est plus reproductible à la frontière : p = 0,17145 arrondi contre un seuil 0,171449 ne dit rien. Six décimales coûtent quelques octets et conservent la finesse nécessaire à une analyse de dérive de score sur la queue basse (la plupart des scores sont autour de 0,03) |
| `seuil_applique` | nombre, **précision complète** (16 chiffres significatifs) | **Le seuil effectif au moment de l'appel.** Source : la variable `SEUIL` si elle est définie, sinon le paquet. Les deux ne disent pas la même chose : le paquet est la décision d'entraînement (rappel visé 0,95 mesuré sur le test), la variable est un **remplacement opérationnel**, modifiable sans redéploiement. D'où le champ suivant |
| `seuil_source` | `"paquet"` ou `"env"` | Champ ajouté par rapport au modèle imposé, et justifié en Q3.4 de `DEPLOIEMENT.md` : c'est lui qui permet de découvrir, après coup, qu'un collègue a abaissé le seuil en production |
| `rappel_cible` | 0,95 | Contexte du seuil : sans lui, 0,1714487 n'est qu'un nombre |
| `decision` | `a_examiner` / `non_signale` | Vocabulaire repris de la séance 2 |
| `covariables` | objet | Voir la décision ci-dessous |
| `inference_ms` | nombre, ms | Chronomètre `perf_counter` autour de **la construction de la ligne d'entrée et de `predict_proba` seulement**. Exclut le réseau, la lecture du JSON et l'écriture du journal. La latence vue par le client (réseau + file d'attente Gunicorn) se lit dans le journal d'accès, pas ici |
| `http_status` | entier | Rien à décider |
| `input_schema_version` | chaîne | À incrémenter quand le **contrat d'entrée** change : liste, ordre ou type des 40 colonnes, domaine des catégories acceptées, règle de complétude. Pas à incrémenter lors d'un ré-entraînement qui garde le même contrat |

### Covariables : sous-ensemble ou rien ?

**Je conserve un sous-ensemble, discrétisé.** Cinq variables : `age_tranche`, `sex`, `anatom_site_general`, `tbp_tile_type` et une mesure de taille en décile.

- *Pour* : la détection de dérive de la séance 5 compare la distribution des entrées servies à celle de l'entraînement. Sans covariables dans le journal, il faudrait un second dispositif de collecte (échantillonnage de charges utiles dans un stockage séparé, à accès restreint), c'est-à-dire un second traitement de données de santé à déclarer et à protéger. Garder cinq variables grossières dans la ligne de journal est moins risqué que d'en collecter quarante ailleurs.
- *Contre, et limite assumée* : cinq variables sur quarante ne permettent pas de détecter une dérive sur les trente-cinq autres, notamment les mesures `tbp_lv_*` (la dérive d'un nouvel appareil de capture se verrait justement là). C'est un compromis : la séance 5 pourra proposer un échantillon de 1 % dans un stockage séparé si la dérive sur ces cinq variables s'avère insuffisante.
- Ces cinq variables restent des **quasi-identifiants** quand elles sont croisées avec `patient_ref` et l'horodatage : voir Q6.2.

### Pseudonymisation de `patient_id`

`patient_id` n'est pas une variable du modèle (absent des 40 colonnes de `charge.json`). Il arrive hors charge utile, dans un en-tête `X-Patient-Ref` émis par le poste de consultation.

Transformation de référence : concaténer le sel lu dans l'environnement, un séparateur `:` et l'identifiant ; hacher en SHA-256 ; garder les **16 premiers caractères hexadécimaux** (64 bits).

```python
import hashlib
import os

def pseudonymiser(patient_id: str) -> str:
    """patient_ref stable dans le temps, mais non réversible sans le sel."""
    SEL = os.environ["INFERENCE_LOG_SALT"]  # jamais en dur dans le code
    return hashlib.sha256(f"{SEL}:{patient_id}".encode("utf-8")).hexdigest()[:16]
```

- Le sel est `openssl rand -hex 16` : **128 bits** d'entropie, ce qui interdit toute énumération sans lui.
- Collisions : avec 1 042 patients et 64 bits, la probabilité d'une collision est de l'ordre de n²/2⁶⁵ ≈ 3 × 10⁻¹⁴, négligeable.
- Évolution recommandée, non demandée aujourd'hui : un **HMAC-SHA256** (`hmac.new(sel, patient_id, sha256)`) est la construction standard pour une empreinte à clé ; `sha256(sel:id)` est acceptable ici car l'identifiant et le sel ont des formats de longueur fixe.

---

## 6.3 — Durées de conservation

*Durées proposées, à valider avec le délégué à la protection des données et la directrice médicale ; chaque durée est justifiée par un besoin nommé.*

| Catégorie de trace | Durée de conservation | Besoin qui la justifie | Ce qui se passe à l'échéance |
|---|---|---|---|
| Journal d'inférence complet (pseudonymisé) | **12 mois** | Instruire une réclamation : le cas d'école est un patient qui revient six mois plus tard ; un an couvre un cycle de suivi dermatologique annuel avec marge de dépôt de la réclamation | Purge automatique des lignes. Les agrégats sans identifiant (taux de `a_examiner`, distribution de score, version, seuil) sont extraits **avant** la purge. Tout cas faisant l'objet d'une réclamation ouverte est placé sous conservation séparée (*legal hold*), hors purge automatique, le temps de la procédure |
| Journal d'erreurs applicatives | **90 jours** | Diagnostiquer un incident récurrent ; passé ce délai, un défaut non diagnostiqué ne l'est plus par ses traces. Il ne contient ni charge utile ni valeur, seulement `request_id`, code et noms de champs | Suppression automatique |
| Métriques agrégées, sans identifiant | **13 mois** | Comparer une période à la même période l'an passé (saisonnalité des consultations, dérive lente) : il faut une année pleine plus un mois | Ré-échantillonnage en agrégats journaliers, puis suppression. Hors RGPD tant qu'aucun identifiant n'y figure |
| Journal d'accès de la plateforme | **30 jours** | Sécurité : détecter un balayage ou une rafale d'appels, reconstituer un incident. Il porte l'adresse IP de l'appelant (donnée à caractère personnel), donc la durée doit rester courte | Suppression automatique par la plateforme |

### Question 6.1 — Qualification RGPD des quatre cas

1. **`tbp_lv_*` seules, sans identifiant** — *Ni art. 4 ni art. 9, sous réserve.* Aucune personne n'est désignée. Mais ce n'est pas un acquis : un vecteur de trente-cinq mesures continues d'une lésion peut suffire à isoler un individu si quelqu'un détient déjà la même mesure. L'absence de caractère personnel doit être **démontrée**, pas présumée.
2. **Les mêmes + `patient_id`** — *Art. 4 et art. 9.* La personne est identifiée directement et les mesures décrivent un état de santé cutané : donnée concernant la santé. Un patient portant jusqu'à 9 184 lésions rend le rattachement encore plus net : le volume suffit à désigner un individu. Le pseudonyme `patient_ref` ne sort pas du champ : tant que le sel existe, c'est toujours une donnée à caractère personnel (considérant 26).
3. **Les mêmes + `age_approx`, `sex`, `anatom_site_general`, sans `patient_id`** — *Art. 4, et donc art. 9.* Aucun identifiant direct, mais la combinaison est un quasi-identifiant qui peut redevenir identifiante dans un petit centre (Q6.2) ; et comme le contenu est de santé, dès qu'il y a réidentifiabilité raisonnable le régime de l'art. 9 s'applique. Par prudence, je traite ce cas comme de la donnée de santé.
4. **Probabilité maligne + patient identifiable** — *Art. 4 et art. 9.* Que la donnée soit **produite** par DermaScan et non collectée auprès du patient ne change pas sa qualification : l'art. 4 vise toute information se rapportant à une personne, et le considérant 35 range parmi les données de santé celles qui révèlent un état de santé ou un risque, quelle que soit leur source. Une prédiction sur un patient identifié est une donnée de santé produite ; c'est aussi un résultat de profilage (art. 4, 4°).

### Question 6.2 — À partir de combien de variables un patient redevient-il identifiable ?

Mon estimation : **trois à quatre variables croisées** suffisent, dans un centre de taille modeste. Âge approché (≈ 18 tranches de cinq ans) × sexe (2) × site anatomique (≈ 6 modalités) donne de l'ordre de 200 cases ; un centre n'a que quelques centaines de patients, donc beaucoup de cases contiennent 0 ou 1 personne. Ajouter une taille de lésion fait disparaître l'ambiguïté résiduelle. Ce chiffre est une **hypothèse** : je ne peux pas le calculer aujourd'hui.

**La mesure qu'il faudrait** : la **k-anonymité** observée, c'est-à-dire, pour chaque combinaison de *m* quasi-identifiants, la taille de la plus petite classe d'équivalence (*k*) et la part des enregistrements dont la classe est de taille 1, 2 puis < 5. En pandas : `df.groupby(quasi_identifiants).size()`, puis la part de lignes dont la classe est `< 5`, en faisant croître *m* de 1 à 5 et **par centre** (`attribution`). La valeur de *m* où cette part dépasse un seuil accepté (par exemple 5 % de lignes uniques) est la réponse.

### Question 6.3 — Fuite intégrale du journal sur un forum public

| Ligne marquée « Toujours » | Ce que l'attaquant en tire |
|---|---|
| Horodatage UTC | Rythme d'usage |
| Identifiant de corrélation | Rien (aléatoire) |
| Version du modèle et digest | Empreinte de la version à attaquer |
| Probabilité maligne | Score de risque, non rattaché à un nom |
| Seuil appliqué et rappel visé | Politique de décision |
| Décision rendue | Résultat sans identité |
| Latence d'inférence | Rien d'exploitable |
| Code HTTP et erreur | Rien (aucune valeur de charge) |

Aucune ligne seule n'est dangereuse. Le risque est **la jointure** : `patient_ref` + covariables + horodatage. Si l'attaquant sait qu'une personne de son entourage est venue en consultation un jour donné, l'horodatage restreint les candidats, `age_tranche` + `sex` + site anatomique confirment la ligne, et il lit alors sa décision et son score. C'est pour cela que `patient_ref` **n'est pas marqué « Toujours »** mais « pseudonymisé » (gardé pour relier, jamais seul), et que l'âge exact, `isic_id`, l'IP et les `tbp_lv_*` ont été exclus.

**Une fuite de prédiction est-elle moins grave qu'une fuite de diagnostic ?** *Moins exacte, pas moins grave.* Mon score est non calibré : à 0,17 la fréquence réelle est ≈ 0,3 % (S2), donc il n'établit rien. Mais il fuit une information de santé ; relié à une personne, `a_examiner` se lit socialement comme « on soupçonne un cancer » et peut être utilisé contre elle (assurance, employeur), indépendamment de sa justesse. Juridiquement, c'est de l'art. 9 dans les deux cas. En revanche, la fuite d'une prédiction fausse fait un tort propre : une inquiétude infondée.

### Question 6.4 — Le sel

1. **Pourquoi le sel est indispensable.** Sans sel, `sha256(patient_id)` est une fonction publique : l'attaquant hache chaque identifiant candidat et compare. Les identifiants ISIC suivent un format régulier (de type `IP_` suivi de sept chiffres, à vérifier sur mon CSV) : dix millions de candidats se hachent en quelques secondes sur un portable, et il n'y a que 1 042 patients à retrouver. Avec un sel de 128 bits tenu secret, l'énumération est impossible sans lui.
2. **La stabilité.** Nécessaire : un patient porte plusieurs lésions (jusqu'à 9 184) et il faut pouvoir les relier pour le suivi et pour mesurer la charge d'alertes par patient. Faiblesse : n'importe qui ayant accès au journal reconstitue **tout l'historique** d'un patient pseudonyme, et une seule réidentification dévoile toutes ses lignes.
3. **Qui remonte de `patient_ref` à `patient_id`, et comment.** Le délégué à la protection des données et le médecin responsable, seuls, pour une réclamation instruite. Le moyen n'est pas d'« inverser » le hachage mais de **recalculer en avant** : à partir de la liste des patients du centre (détenue par le système clinique), on calcule `patient_ref` avec le sel pour chacun et on compare. Le sel est conservé dans un coffre (Azure Key Vault, voir Q3.2), accès restreint et journalisé.
4. **Rotation du sel.** Tout `patient_ref` change : l'historique ne se relie plus à l'avenir, et les anciennes lignes ne peuvent plus être rattachées à un patient (si l'ancien sel est détruit). C'est **les deux à la fois** : un défaut pour la continuité d'un audit, une propriété recherchée pour la minimisation (effacement cryptographique). Ma position : propriété recherchée, **à condition de la déclencher volontairement** à l'échéance de conservation et non par accident.

### Question 6.5 — Minimisation contre auditabilité

Les deux exigences : la **minimisation et la limitation de conservation** (RGPD art. 5, § 1, c et e), qui poussent à garder peu et peu longtemps ; et la **capacité d'audit a posteriori** (responsabilité, art. 5 § 2, et responsabilité médicale), qui pousse à garder assez pour reconstituer une décision.

Le mécanisme qui satisfait les deux est celui de la troisième ligne de la grille : **la version du modèle et le digest de l'image**, combinés au seuil appliqué. On ne conserve pas l'entrée pour pouvoir juger la décision : on conserve de quoi **rejouer** la décision. Une image désignée par son digest est immuable ; à partir du digest, du seuil et de la charge que le praticien peut re-soumettre depuis son dossier, on reproduit la décision sans que DermaScan ait jamais gardé les quarante variables. La pseudonymisation salée complète le dispositif : l'auditabilité survit tant que le sel existe, et l'effacement du sel à l'échéance supprime le lien avec la personne sans toucher aux agrégats.

Condition : la rejouabilité exige que **l'image du digest journalisé existe encore**. Mon propre cas le montre : j'ai supprimé le registre le 09/10 pour ne rien dépenser, et le digest de `dermascan-api:1.0.0` est devenu irrécupérable (un rebuild produit un autre digest). Une politique de conservation des journaux doit donc s'accompagner d'une politique de conservation des images référencées.

### Question 6.6 — Où configurer la purge

La purge se configure **au niveau de la plateforme** : durée de rétention de l'espace Log Analytics ou d'Application Insights (par table), règle de cycle de vie du compte de stockage qui reçoit les journaux exportés, durée de rétention des journaux du système de fichiers d'App Service. Si elle n'est configurée que dans le code applicatif, elle ne supprime que ce que l'application a écrit elle-même : **la plateforme conserve ses propres copies** (journaux de conteneur, flux de diagnostic, exports) qui survivent à la purge du code. DermaScan affirmerait alors une durée de conservation qui n'est pas celle réellement appliquée, ce qui est pire que de ne pas en annoncer : c'est une fausse déclaration de conformité.
