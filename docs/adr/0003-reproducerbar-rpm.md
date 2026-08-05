# ADR 0003 — Reproducerbar RPM: artefakten är en funktion av källorna

Status: **antagen** (XS-49, 2026-07-28)

## Problemet

XS-47:s RPM gick inte att reproducera. Två rena checkouter av samma commit,
byggda på olika sökvägar, gav olika filer. Det gör tre saker omöjliga på en
gång: att verifiera att en levererad artefakt motsvarar den granskade koden,
att jämföra två byggen efter en incident, och att över huvud taget påstå att
"acceptansen kördes mot den här commiten".

Fem separata orsaker hittades, och varje orsak behövde sin egen åtgärd.

## Beslut och åtgärder

### 1. Kompilerad bytekod bar byggsökvägen

`compileall` skriver källfilens sökväg i varje `.pyc`, plus källans mtime i
headern.

Åtgärd: en enda deterministisk kompilering av *hela* trädet med
`-s "$RUNTIME" -p "/usr/lib/Träff/runtime"`, vilket skriver den
sökväg filen får när den är **installerad**, och
`--invalidation-mode unchecked-hash`, som tar bort mtime ur headern helt. Det
installerade trädet är skrivskyddat, så det finns inget att invalidera mot.

Hela trädet, inte bara det som installeras här: tolkarkivet levererar egna
`.pyc` kompilerade hos distributören, och allt som importerar under stegningen
kan skriva över en av dem med en kopia kompilerad på *den här* checkoutens
sökväg. `PYTHONDONTWRITEBYTECODE=1` stänger sidoeffekten, en pass över allt
normaliserar resten.

### 2. `CARGO_MANIFEST_DIR` i skalbinären

`--remap-path-prefix` räcker inte. Den skriver om sökvägar *kompilatorn* avger;
`tauri::generate_context!` läser `CARGO_MANIFEST_DIR` ur miljön och bakar in
strängen vid makroexpansion, utom räckhåll för omskrivningen.

Åtgärd: skalet kompileras genom en kanonisk symlänk
(`/var/tmp/brfv2-desktop-shell`), så `CARGO_MANIFEST_DIR` blir densamma från
varje checkout. Target-katalogen ligger kvar i checkouten; bara namnet delas.
Det är samma grepp som en distribution använder när den alltid bygger i
`/builddir`. `~/.cargo` och `~/.rustup` skrivs om på vanligt sätt, annars
hamnar byggarens användarnamn i den levererade binären.

### 3. `RECORD` beskrev konsolskript som tagits bort

`uv pip install --target` lägger konsolskript i `site-packages/bin` med en
absolut shebang. Skripten togs redan bort — men varje pakets `RECORD` fortsatte
lista dem med hash och längd, och längden beror på byggsökvägen.

Åtgärd: `bin/`-raderna tas bort ur `RECORD` samtidigt som filerna. Metadatan
blir både deterministisk och sann.

### 4. Tidsstämplar

Filernas mtime, RPM:ens `BUILDTIME` och `BUILDHOST` kom från byggtillfället och
byggmaskinen.

Åtgärd: en **fast** byggepok deklarerad i `ops/pins.json` (`build.epoch`), satt
som `SOURCE_DATE_EPOCH`, stämplad på hela buildroot, och given till rpmbuild via
`use_source_date_epoch_as_buildtime` och
`build_mtime_policy clamp_to_source_date_epoch`. `%_buildhost` sätts till ett
fast namn.

Epoken är medvetet **inte** commitens tidsstämpel. Se nedan.

### 5. Vaktposten som aldrig larmade

Kontrollen "innehåller binären checkout-sökvägen?" var skriven som
`strings … | grep -q …` inuti ett `if`. Under `set -o pipefail` dör `strings` av
SIGPIPE så fort `grep -q` hittar något, pipeline-statusen blir 141, och `if`
läser det som "ingen träff". Vakten var alltså garanterat tyst i exakt det fall
den fanns för.

Åtgärd: `grep -c`, som läser till slutet. Kontrollen fångade omedelbart både
checkout-sökvägen och 195 förekomster av byggarens hemkatalog.

## Varför en fast epok och inte commit-tidsstämpeln

Den här leveransen ska ligga i **en** commit tillsammans med sin
acceptansevidens. Om artefakten berodde på commitens tidsstämpel eller SHA
skulle det bli cirkulärt: evidensen namnger artefakten, artefakten beror på
commiten, commiten innehåller evidensen.

Därför är artefakten en funktion av *leveranskällorna*, inte av commiten.
`ops/lib/repro.sh` listar exakt vilka spårade sökvägar det är
(`REPRO_DELIVERY_PATHS`) och `repro_delivery_tree` hashar dem. Dokumentation och
evidens står inte på listan, så att committa evidensen kan inte flytta en enda
byte i paketet — och en granskare kan bygga om från den slutliga commiten och
landa på den SHA-256 evidensen anger.

`BUNDLE.json` i paketet bär därför `deliveryTree`, inte `commit`. Commiten
finns i kvittot bredvid artefakten (`dist/*.rpm.provenance.json`) och i
evidensen, där den inte påverkar bytesen.

## Konsekvenser

* **Paketering kräver ren arbetskatalog.** En smutsig checkout ger bytes ingen
  kan reproducera; `ops/package-desktop.sh` vägrar i stället för att varna.
* **Den stegade körmiljön måste tillhöra samma källor.** Paketeringen jämför
  `BUNDLE.json`s `deliveryTree` med checkoutens och avbryter vid skillnad, i
  stället för att packa ihop en Python-miljö från en revision med ett skal från
  en annan.
* **`ops/verify-reproducible.sh` är en del av leveransen.** Påståendet
  "reproducerbar" är värt något bara om det går att köra om: skriptet klonar två
  checkouter på olika sökvägar, bygger i båda och jämför byte för byte.
* Kvar utanför: `%{dist}`-makrot (`.fc44`) kommer från byggdistributionen och
  ingår medvetet i artefaktens identitet. Reproducerbarheten som visas är på
  samma Fedora-version, inte tvärs över distributioner.
