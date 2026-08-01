# Överlämningsindex — Fedora desktop-pilot

Vad som finns, var det ligger, vad det bevisar och vad det **inte** bevisar.
Skrivet för någon som inte var med.

**Linje:** `bp6/fedora-pilot-closeout`, tagg `v0.2.0-fedora-pilot`
**Förälder:** `d6e73bf280390995847b87cdd092acc9fa211014`
**Denna linje är fryst.** Fortsatt produktutveckling sker inte här — se §7.

---

## 1. Läs i den här ordningen

| Ordning | Fil | Varför just den |
| -- | -- | -- |
| 1 | `docs/pilot/SLUTRAPPORT-DESKTOP-PILOT.md` | Vad piloten var, vad den bevisade, vad den inte bevisade |
| 2 | `docs/pilot/BP6-BESLUTSUNDERLAG.md` | Grindkriterier, verifieringar körda vid avslut, rekommendation |
| 3 | `docs/pilot/BP5-COLD-REVIEW.md` | Den oberoende granskningen — läs den **innan** du litar på 1 och 2 |
| 4 | Detta index | Var allt annat ligger |
| 5 | `docs/pilot/PILOTPLAN.md` | Planen som genomförandet mättes mot (läs §9 med slutrapport §4 bredvid) |
| 6 | `docs/pilot/JOURNAL.md` | Kronologin, avvikelserna, rättelserna. Den ärligaste filen i materialet |

---

## 2. Grindunderlag

| Grind | Fil | Utfall |
| -- | -- | -- |
| BP2 | Linear XS-52, 2026-07-29 | `PASS BP2 — TAURI 2 FOR CONTROLLED FEDORA PILOT` |
| BP3 | `docs/pilot/BP3-BESLUTSUNDERLAG.md` | `PASS TO EXECUTION`, K1–K10 uppfyllda |
| BP4-3 | `docs/pilot/BP4-3-BESLUTSUNDERLAG.md` | Slinga 3 |
| BP4-4 | `docs/pilot/BP4-4-BESLUTSUNDERLAG.md` | Slinga 4 |
| BP5 | `docs/pilot/BP5-COLD-REVIEW.md` | `PASS BP5 — CONTROLLED SINGLE-OPERATOR FEDORA PILOT VERIFIED` |
| BP6 | `docs/pilot/BP6-BESLUTSUNDERLAG.md` | Rekommendation `PASS BP6 — PROJECT MAY CLOSE` |

**Varning:** `docs/SLUTRAPPORT.md` (2026-07-28) är **webb-MVP:ns** slutrapport
och tillhör en annan grindkedja. Den redovisar sitt eget `PASS BP5` och
rekommenderar sitt eget `PASS BP6`, och dess påstående att "projektmaterialet är
arkiverat" är inaktuellt i förhållande till allt pilotmaterial som tillkom
2026-07-29 → 07-31. Blanda inte ihop de två cyklerna.

---

## 3. Evidens per slinga

| Slinga | Arbetspunkter | Evidensfiler | Commit |
| -- | -- | -- | -- |
| 1 — återställbar pilotmiljö | A1–A5 | `docs/evidence/pilot/slinga1-startevidens.md` | `7cd1f92` |
| 2 — okonfigurerad maskin → fungerande installation | B0–B5 | `docs/evidence/pilot/slinga2-forstastart.md`, `slinga2-atertagning-efter-vardkrasch.md`, `EVIDENSREGISTER-XS55.md` | `c6db95a` |
| 3 — upprepade arbetspass med felinjektion | C1–C5 | `docs/evidence/pilot/slinga3-upprepade-arbetspass.md`, `xs56/fragesvar-pass{1,2,3}.json`, `xs56/pass3-grundat-svar-efter-omstart.json`, `EVIDENSREGISTER-XS56.md` | `df9f664`, `813f26d` |
| 4 — backup, restore, paketbyte, katastrof | D1–D4 | `docs/evidence/pilot/slinga4-sakerhetskopiering-och-paketbyte.md` | `e96db7d`, `298337a`, `a5a112b` |
| BP5-kallgranskning | — | `docs/pilot/BP5-COLD-REVIEW.md`, `docs/evidence/pilot/bp5-cold-review/{cold-review-results.json,inspect-installed.json,inspect-installed.txt,integrity-summary.txt}` | `d6e73bf` |

### 3.1 Rådataidentiteter (XS-56)

| Fil | SHA-256 |
| -- | -- |
| `xs56/fragesvar-pass1.json` | `1ef534a753f6685b9d1c933a12ecfdf421d77eb09428c91965d39448069f2c5f` |
| `xs56/fragesvar-pass2.json` | `b3f2907d36c7707e682ca075488d7725a2ab5ac78b63de58efc03228babada4e` |
| `xs56/fragesvar-pass3.json` | `781e6a7d90b6d1fdbc4b8e8e0654758d11d4a6b4e3250d767c03f92945373275` |
| `xs56/pass3-grundat-svar-efter-omstart.json` | `170cc99b29fbbc21f269a597e449445e3b4eca37caade4bbb5a10c2766309263` |

De tre passfilerna är exakt 15 824 byte var med olika summor och olika
`elapsed_s` — tre inspelningar, inte tre kopior av en fil.

### 3.2 Skärmbildernas gräns

Slinga 3 och slinga 4 har **inga skärmbilder alls**; läsningen gjordes ur
a11y-trädet. De enda pilotskärmbilderna är fem klass-P-filer
(`docs/evidence/xs55-slinga2-installed-desktop-*.png`) från acceptanskörningen,
som visar acceptansens syntetiska förening `Brf Gjutformen 12` i ett tillfälligt
datahem — **inte pilotinstallationen**.

Äldre skärmbilder (`xs46-*`, `xs47-*`, `xs49-*`, `xs51-*`) tillhör tidigare
artefaktgenerationer. `xs49-*`-acceptansfilerna bär `deliveryTree 9c996ddf…` och
artefakt `f8ddb770…` och är **inte** evidens för pilotens artefakt.

---

## 4. Artefakten

| | |
| -- | -- |
| Filnamn | `brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm` |
| Storlek | 574 604 029 byte |
| SHA-256 | `6ba028fb0498da34ddd25c89366da98ec1ec96618ac6a607236cb58ab345e98d` |
| RPM-header SHA-256 | `5fc97bcef7da938e658cd486443f5110d97f26ce7b86bd0facadc9ae233243fe` |
| Signatur | `(none)` |
| `deliveryTree` | `a702a3378ec524d8d2d4ff2603d0f00d35c2881d34bfc9640715f896a181e083` |
| Källcommit | `84b6fc853ec047fe9b438f2e1c0a2aed08cfe754`, `dirty: false` |
| `sourceDateEpoch` | `1785196800` (2026-07-28T00:00:00Z) |
| `BUILDHOST` | `reproducible.brfdokumentai.se` |
| Skalbinär | `/usr/bin/brfv2-desktop`, `d3cb3c02ab82e201af88f8e4f8769bf2f8bb37d0d1a41076edc1e660eb529b08` |
| Arkiv | `~/pilot-artefakter/` (`0444`) med `*.provenance.json` (51 155 byte, `bbf6ee99120d2a5397c919f4fe10457888eea5db143c3d54c0276e9dc60f565f`) och `SHA256SUMS` |

**Tre payload-hashar som inte får förväxlas:**

| Omfång | Filer | Byte | SHA-256 |
| -- | -- | -- | -- |
| `staged-runtime` (det `BUNDLE.json` beskriver) | 4 668 | 804 362 039 | `9fe3f0e36989f19261d4b6e47a3aa6fb03832e3df7732de95e89699d5b5139a5` |
| `installed` | 4 675 | 809 792 406 | `55c20520e4a5054c08fe019654156457d0bc5f52af747eb381587acebe90b205` |
| hela artefakten | 4 679 | — | `b44a5bb286e4dba0bca2b5c65962486d6afb479f99c14cf268c11573e1b86964` |

**Reproducerbarhet:** `docs/evidence/xs51-reproducibility.json` — två checkouter
med olika sökvägslängd, båda `6ba028fb…`, `cmp -s` identiska. Piloten byggde
själv en tredje identisk kopia i slinga 1 (A1).

**Pinnade indata:** `ops/pins.json` — CPython 3.12.13 (`5854aa6e…`), uv 0.11.32
(`aab924fd…`), embeddervikter `minishlab/potion-multilingual-128M` rev
`73908c34…`, tauri 2.11.5 / tauri-build 2.6.3, rustc 1.97.1, Node v22.22.2,
rpmbuild 6.0.2, add-determinism 0.7.3. Modell: Gemma 4 12B,
`unsloth/gemma-4-12b-it-GGUF`, snapshot `d997c805aafe035a8024f961c6e1afd6b30d79a5`.

---

## 5. Så återskapas verifieringarna

Från en ren checkout av den här grenen, på Fedora 44:

```bash
# 1. Leveransträdet ur repot — måste bli a702a337…
source ops/lib/repro.sh && repro_delivery_tree

# 2. Artefaktens identitet
sha256sum ~/pilot-artefakter/brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm

# 3. Installationens integritet och signaturläge
rpm --verify brf-dokument-ai            # exit 0
rpm -q --qf '%{SIGPGP}\n' brf-dokument-ai   # (none)

# 4. Leverantörsuteslutningen — 45 kontroller, 0 fynd
python3 ops/inspect_payload.py --installed --scope installed

# 5. Full regressionssvit med artefakttesterna påslagna — 657 passed, 3 skipped
cd backend && BRFV2_REQUIRE_ARTIFACT=1 \
  BRFV2_RPM=~/pilot-artefakter/brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm \
  uv run pytest -q

# 6. Artefakttesterna ensamt — 40 passed
make desktop-verify-artifact RPM=~/pilot-artefakter/brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm

# 7. Byte-för-byte-reproducerbarhet (bygger om två gånger, tar tid)
make desktop-verify-reproducible
```

Acceptanskörning mot det installerade paketet kräver en nåbar självhostad
modelltjänst:

```bash
ssh -N -o ExitOnForwardFailure=yes -L 8000:127.0.0.1:8000 agenntserver
make desktop-acceptance-installed \
  RPM=~/pilot-artefakter/brf-dokument-ai-0.2.0-1.fc44.x86_64.rpm \
  RUN_LABEL=<din-etikett>
```

`RUN_LABEL` är obligatorisk i praktiken: varje målfil som git redan spårar
stoppar körningen innan den börjar (A3-skyddet), och `--overwrite-evidence`
krävs för att skriva över committad evidens.

---

## 6. Produktförmågorna, med källfil

Det här är vad skrivbordsleveransen faktiskt gör. Läs koden, inte bara raden.

| Förmåga | Var |
| -- | -- |
| Tunt Tauri 2-skal: fönster, sidecarlivscykel, ingen produktlogik | `src-tauri/src/main.rs`, `src-tauri/tauri.conf.json` |
| Ingen IPC-yta (`capabilities: []`, `withGlobalTauri: false`, `freezePrototype`) | `src-tauri/tauri.conf.json` |
| Strikt slumpad loopback-origin och begränsad navigation | `main.rs` `same_origin()`, `on_navigation`, `on_new_window` |
| Readiness-kontrakt `brfv2-desktop-startup/v1`, 120 s timeout | `main.rs` `StartupContract::validate()`, `desktop.py` `_ReadinessServer` |
| Miljöskrubbning före sidecarstart (`ANTHROPIC_API_KEY`, `BRF_LLM*`, `BRF_MODE`, `BRF_DATA_ROOT`) | `main.rs` `spawn_backend` |
| `PR_SET_PDEATHSIG` + processgrupp; `SIGTERM` → 3 s → `SIGKILL` | `main.rs` `pre_exec`, `OwnedBackend::terminate()` |
| Exitkod 86 = omstart (staged restore) utan IPC-behörighet | `main.rs` `supervise()`, `desktop.py` `RESTART_EXIT_CODE` |
| Felfönster som lokal bundlad asset, detaljtext injicerad från Rust | `main.rs`, `src-tauri/shell/` |
| Datakataloger `0700`, loggfil `0600`, loggrotation en generation | `main.rs` `prepare_data_dirs`, `tee_backend_stderr` |
| Exakt Host/Origin-kontroll + säkerhetsheaders på varje svar | `backend/app/desktop.py` `desktop_http_boundary` |
| Installationsspecifik `/api/`-scopad sessionscookie | `desktop.py` `_load_or_create_cookie_name`, `DESKTOP_COOKIE_PATH` |
| First-run-provisionering, permanent stängd när en förening finns | `desktop.py` `POST /api/desktop/setup` |
| Installationsadministratör skild från föreningsadmin, med backfill | `backend/app/auth.py` `installation_admins`, `desktop.py` `installation_admin` |
| Modellgräns: default-deny, loopback + privat nät över https | `backend/app/model_endpoint.py` |
| `BRF_LLM` pinnat till `selfhosted`; konfigfilen är ett förslag, inte ett beslut | `desktop.py` `apply_model_runtime`, `load_config` |
| Backup: hela `data/` zippat, manifest, atomisk publicering, `0600` | `desktop.py` `create_backup` |
| Restore: validering, staging, swap före första store-öppning, rollback | `desktop.py` `read_backup_manifest`, `stage_restore`, `apply_pending_restore` |
| Offlinegräns: bundlade vikter, `HF_HUB_OFFLINE=1`, ingen `backend/scripts/` i bundlen | `desktop.py` `main()`, `ops/build-runtime.sh` |
| Reproducerbar RPM, `REPRO_DELIVERY_PATHS`, smutsig checkout vägras | `ops/lib/repro.sh`, `ops/package-desktop.sh`, `ops/brf-dokument-ai.spec` |
| Leverantörsuteslutningen som byggvillkor (fynd fäller bygget) | `ops/forbidden_providers.json`, `ops/prune_payload.py`, `ops/inspect_payload.py` |

Arkitekturbeslut: `docs/adr/0001-desktop-python-runtime.md`,
`0002-model-endpoint-boundary.md`, `0003-reproducerbar-rpm.md`.
Användar- och byggguide: `docs/DESKTOP-FEDORA.md` (notera: den utelämnar `logs/`
ur sin kataloglayout och dess `dnf install`-exempel saknar `.fc44`).

---

## 7. Repositorytopologi och vart arbetet tog vägen

```
1cd65ca  gemensam webbaslinje
   │
   ├── desktoplinjen (FRYST — denna linje)
   │     XS-46 → XS-47 → XS-49 → XS-51 → XS-53 → XS-54 → XS-55 → XS-56 → XS-57
   │     → d6e73bf BP5-kallgranskning
   │     → bp6/fedora-pilot-closeout, taggad v0.2.0-fedora-pilot
   │
   └── produktlinjen (LEVANDE)
         → acd39de origin/main
         → 3bc78bd feat/kalla-mobile-pwa, taggad traff-mobile-rc1
         → feat/desktop-styrelsearbetsyta
```

Den här grenen ändras inte mer. Desktopens **produktförmågor** (§6) har förts
fram semantiskt till produktlinjen; pilotens **historiska evidens** har det inte,
och ska inte göra det — den är evidens om den här artefakten, inte om någon
annan.

Sök porteringens motivering och vad som bevarades från mobilspåret i
`docs/POST-BP6-PRODUKTBAS.md` på grenen `feat/desktop-styrelsearbetsyta`.

---

## 8. Backlog som lämnas över

**Klass F — produktändringar som pausades av `REPRO_DELIVERY_PATHS`:**
Shift+Enter / flerradig inmatning (`brfv2-mockup/src/App.jsx:1522–1526`,
`1107–1111`) · `tabIndex` till `Appinställningar`
(`brfv2-mockup/src/App.jsx:863`) · `pending-restore.zip` `0644`
(`backend/app/desktop.py` `stage_restore`) · `Settings.aiModel`-defaulten
(`backend/app/schemas.py`).

**Öppna grindfrågor:** villkoret för obesvarbara frågor · D4:s karantänmetod ·
aggregatsummans formel · omtagning av M10 · begränsning 3:s premiss.

**Före bredare pilot:** slutrapport §5, B1–B12.
**Före distribution:** slutrapport §6, P1–P10.

**Erfarenhetsåterföring utan produktändring:** `OTILLRÄCKLIGT UNDERLAG`
återanvänds vid leverantörsfel · `backend.log` saknar tidsstämplar och nämner
inte backendens död · `ERROR`-nivå för förväntat förstagångsläge · dubbletter
togs emot utan varning · överinkluderande svar på g17 och g44 · minnestopp
2,1 GB / 787,8 MB swap.

---

## 9. Var saker *inte* finns

* **Ingen `auth.db`, ingen säkerhetskopia, ingen datakatalog** är committad.
  Pilotens driftdata innehåller operatörens riktiga namn och e-postadress och
  ligger endast på pilotmaskinen och i `~/pilot-sakerhetskopior/` på
  `agenntserver`.
* **Ingen riktig BRF-korpus.** Allt i repot är syntetiskt.
* **Ingen byggd RPM och inget `src-tauri/runtime/`** — båda är gitignorerade och
  reproducerbara från källan.
* **XS-58 finns inte i repot.** Numret existerar bara i Linear; sakfrågan är
  Shift+Enter-fyndet i slutrapport §4.2.
