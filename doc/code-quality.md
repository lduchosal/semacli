# Code quality — critères, baseline et paliers

> Tâche fondatrice : ken #828 — port du harnais qualité de kenboard
> (kenboard ken #783/#788, voir `kenboard/PHILOSOPHY.md`). Objectif :
> des critères **mesurables et rejouables**, un gate **bloquant**, une
> progression **par paliers** et un **ratchet best-ever** qui interdit
> toute régression.

## Mesurer

```sh
pdm run metrics            # snapshot des critères (table)
pdm run metrics-record     # idem + append dans doc/quality-history.csv
pdm run metrics-gate       # gate bloquant : plafonds + ratchet, exit 1 si violation
```

Le script (`scripts/quality_metrics.py`) n'utilise que les outils déjà
installés dans la venv (ruff, mypy, vulture, refurb, interrogate, coverage) +
l'AST stdlib — zéro dépendance ajoutée. `test_cov` lit le dernier run de
`pdm run test` (lancer avant pour une valeur fraîche).

L'historique vit dans [`quality-history.csv`](quality-history.csv) (une ligne
par snapshot, committée). Convention : enregistrer un snapshot à la fin de
chaque palier, au minimum à chaque release.

Le gate est exécuté par `pdm run check` **et** par `publish.sh` (étape 8,
juste après la suite complète pour lire une couverture fraîche).

## Critères suivis

| Critère | Définition | Baseline (2026-06-11, v0.5.17, ken #828) | Direction |
|---|---|---:|---|
| `loc_src` | lignes totales `semacli/**/*.py` | 6 153 | informatif |
| `max_file_lines` | plus gros fichier | 413 (`cli/commands/integrations.py`) | ↓ → ≤ 300 |
| `files_over_500` | fichiers > 500 lignes | 0 | = 0 (gate) |
| `files_over_300` | fichiers > 300 lignes | 5 | ↓ → 0 |
| `functions` | fonctions définies (AST) | 268 | informatif |
| `max_func_lines` | plus longue fonction | 316 (`register_integrations_commands`) | ↓ → ≤ 50 |
| `funcs_over_50` | fonctions > 50 lignes | 18 | ↓ → 0 |
| `c901_over_10` | complexité cyclomatique > 10 (ruff C901, config active) | 0 | = 0 (gate) |
| `ruff_debt` | findings du jeu de règles ruff *non encore imposées* | 345 | ↓ → 0 |
| `ignored_debt` | dette masquée par les per-file-ignores ken #800 (C901, PLR0913, PLR0915 en `--isolated`) | 59 | ↓ → 0 |
| `mypy_errors` | erreurs mypy strict | 0 | = 0 (gate) |
| `vulture` | code mort (confiance ≥ 80, whitelist `vulture_whitelist.py`) | 0 | = 0 (gate) |
| `refurb` | findings refurb | 0 | = 0 (gate) |
| `docstring_cov` | couverture docstrings (interrogate) | 80.5 % | ↑ → ≥ 95 |
| `test_cov` | couverture de tests (unit + integration replay) | 73.6 % | ↑ → ≥ 90 |
| `min_file_cov` | pire couverture par fichier | 28.0 % (`core/client/_integrations.py`) | ↑ → ≥ 75 |

Le jeu `ruff_debt` (constante `DEBT_SELECT` du script) au palier 1 :
`ANN401,ARG,BLE,EM,FBT,PERF,PLR,PTH,RUF,TRY` — dominé par BLE001 ×78
(blind except), FBT ×83 (booléens positionnels), TRY003 ×66 + EM ×66
(hygiène des messages d'exception), ANN401 ×36 (`Any` nus).
Verrouillées dès le palier 1 (déjà à zéro dans `semacli/`) : `DTZ`, `G`,
`SLF`, `PLC0415` — actives dans `[tool.ruff.lint] select`, tests exemptés.

**Principe ratchet** : quand une famille du jeu `ruff_debt` tombe à zéro,
on l'ajoute au `[tool.ruff.lint] select` du gate pour verrouiller l'acquis,
et on la retire de `DEBT_SELECT`.

## Gate bloquant (ken #828)

`pdm run metrics-gate` échoue (exit 1) dès qu'une règle est violée. Trois
mécanismes complémentaires (mêmes verrous que kenboard) :

1. **Verrous ruff** — chaque famille tombée à zéro est activée dans
   `[tool.ruff.lint] select` : échec dès `pdm run lint`.
2. **Cibles par paliers** (`GATE_MAX`/`GATE_MIN` du script) — le palier
   courant est `GATE_PALIER` dans `scripts/quality_metrics.py`.
3. **Ratchet best-ever** (vs `quality-history.csv`) — aucun compteur
   (`files_over_300`, `funcs_over_50`, `c901_over_10`, `ruff_debt`,
   `ignored_debt`) ne peut dépasser son meilleur niveau historique, et
   `test_cov` ne peut pas tomber plus de 0,5 pt sous son record.

### Paliers

Régime kenboard (PHILOSOPHY.md) : le développement étant 100 % agentique,
la dette se paie en heures d'agent — chaque palier est **bloquant** dès son
activation, un gate vert est le signal de resserrage, jamais un état de
repos. Un ken par palier ; commit + publish à chaque palier vert.

| Palier | `max_file` | `max_func` | `ruff_debt` | `ignored_debt` | `docstr` | `test_cov` | `min_file_cov` | Chantier principal |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| 1 — ✓ fait 2026-06-11 (ken #828) | ≤ 450 | ≤ 320 | ≤ 350 | ≤ 60 | ≥ 80 | ≥ 73 | ≥ 25 | outillage ; vulture/refurb → 0 ; DTZ/G/SLF/PLC0415 verrouillés |
| 2 — ✓ fait 2026-06-11 (ken #829) | ≤ 400 | ≤ 80 | ≤ 250 | ≤ 35 | ≥ 85 | ≥ 78 | ≥ 40 | register-closures cassés (max_func 316 → 64, C901/PLR0915 → 0), funnel `fail_on_error` (BLE001 78 → 2), +87 tests (cov 73.6 → 86.6) — ARG/PERF/PTH/RUF verrouillés |
| 3 — ✓ fait 2026-06-11 (ken #831) | ≤ 350 | ≤ 60 | ≤ 50 | ≤ 35 | ≥ 88 | ≥ 82 | ≥ 55 | BLE/TRY/EM/FBT → 0 et verrouillés, RUF100 levée ; sous-groupes extraits (matchers/members/tokens/admin) ; docstrings 100 % ; cov 93.5 % |
| 4 — ✓ fait 2026-06-11 (ken #832) | ≤ 300 | ≤ 50 | ≤ 40 | ≤ 35 | ≥ 95 | ≥ 90 | ≥ 75 | files>300 = 0 (satellite _task_views), funcs>50 = 0, cov 94.2 %, min_file 78.4 % |
| 5 — ✓ fait 2026-06-11 (ken #833) — **verrou** | ≤ 300 | ≤ 50 | = 0 | = 0 | ≥ 95 | ≥ 90 | ≥ 75 | ANN401 → 0 (main_group typé, noqa argumentés aux frontières JSON) ; PLR0913 → 0 (noqa argumentés) ; per-file-ignores ken #800 **levés** ; familles ANN401 + PLR complètes verrouillées — le gate reste en mode verrou |

(`mypy_errors`, `vulture`, `refurb` = 0, `files_over_500` = 0,
`c901_over_10` = 0 et `docstring_cov` ≥ palier courant sont bloquants à
tous les paliers. `[tool.interrogate] fail-under` suit le palier.)

### Procédure d'évolution des paliers

1. **Déclencheur** : `pdm run metrics-gate` passe au vert sur le palier
   courant.
2. **Verrouiller** : `pdm run metrics-record` + commit du CSV (le ratchet
   fige le niveau atteint), puis `sh publish.sh` (release).
3. **Resserrer** : éditer `GATE_PALIER`/`GATE_MAX`/`GATE_MIN` dans
   `scripts/quality_metrics.py` selon le tableau ; activer dans
   `[tool.ruff.lint] select` les familles tombées à zéro et les retirer de
   `DEBT_SELECT` ; aligner `[tool.interrogate] fail-under`.
4. **Ouvrir le chantier** : créer la carte ken « QUALITY / Palier N » avec
   la sortie rouge de `metrics-gate` comme liste de travail.
5. **Palier 5 atteint** : le gate reste en place en mode verrou (cibles +
   ratchet) ; toute évolution ultérieure suit la même procédure.

Règle d'or : on ne **détend jamais** un seuil sans décision humaine
explicite, tracée dans une carte ken et dans l'historique du CSV.

## Hors périmètre local

- **Duplication** : suivie par SonarCloud (`lduchosal_semacli`).
- **Architecture** : verrouillée séparément par import-linter
  (`pdm run arch`, ken #802).
- **UX** : les règles de copy/format CLI vivent dans [`UX.md`](../UX.md) —
  le gate ne mesure que le code.
