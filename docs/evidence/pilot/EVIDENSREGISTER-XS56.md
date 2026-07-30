# Evidensregister XS-56 — vad som committas, vad som inte gör det, och varför

XS-55:s register skiljde *preflight* från *förstagångsstart*. XS-56 har inte den
tvetydigheten — ingen formell acceptans kördes (villkoret för C5 var inte
uppfyllt) — men den har en annan: **vilket material får lämna maskinen.**

Journalen har sedan XS-55 en öppen omfångsavvikelse: installationsadministratörens
konto innehåller operatörens **verkliga namn och e-postadress** i `data/auth.db`.
Allt som innehåller `auth.db`, direkt eller i ett arkiv, är därför en
personuppgiftsfråga och inte bara en fil.

---

## Klass K — committad evidens

**Vad den bevisar:** vad som faktiskt stod i produktens gränssnitt under de tre
passen, och att varje citat löser mot extraherad sidtext.

| Fil | SHA-256 | Innehåll |
| --- | --- | --- |
| `slinga3-upprepade-arbetspass.md` | *(texten själv)* | narrativ evidens, mätvärden, felinjektioner, BP4-3-rekommendation |
| `xs56/fragesvar-pass1.json` | `1ef534a753f6685b9d1c933a12ecfdf421d77eb09428c91965d39448069f2c5f` | pass 1: 15 frågor, svar, citatchips, svarstider, `field_verified` |
| `xs56/fragesvar-pass2.json` | `b3f2907d36c7707e682ca075488d7725a2ab5ac78b63de58efc03228babada4e` | pass 2: samma, kört efter leverantörsbortfall och återhämtning |
| `xs56/fragesvar-pass3.json` | `781e6a7d90b6d1fdbc4b8e8e0654758d11d4a6b4e3250d767c03f92945373275` | pass 3: samma, kört efter backendens död och omstart |
| `xs56/pass3-grundat-svar-efter-omstart.json` | `170cc99b29fbbc21f269a597e449445e3b4eca37caade4bbb5a10c2766309263` | det obligatoriska enskilda kontrollsvaret (g19) efter omstarten |

De tre passfilerna är **exakt lika stora** (15 824 byte) men har **olika**
SHA-256. Det är ingen kopieringsmiss: svarstexterna är tecken för tecken
identiska över de tre passen, och det enda som skiljer är svarstiderna. Att
storleken sammanfaller är alltså en följd av just den reproducerbarhet filen
redovisar, och skillnaden i summa är beviset för att det är tre skilda körningar.

### Ingen maskering behövs — och det är kontrollerat, inte antaget

De fyra JSON-filerna är avläsningar av **chattkolumnen** i a11y-trädet
(`0.1.0.0.0.0.2.*`). Kontot och avataren ligger i navigationslandmärket
(`…1.*`), utanför det avlästa området. Kontrollerat mekaniskt före commit:

| Mönster | Träffar i de fyra filerna |
| --- | --- |
| `Simon` | **0** |
| e-postadress (`[\w.+-]+@[\w-]+\.[\w.]+`) | **0** |
| `/home/aidev` | **0** |
| `proton.me` / `gmail.com` | **0** |

Filerna committas därför omaskerade. Det enda kontoartefakt som förekommer i
XS-56:s texter är den redan hashade administratörs-id:n `fc69c8f41250`, som
produkten själv skriver i loggen och som XS-55:s journal redan använder öppet.

---

## Klass U — medvetet **inte** committad

| Artefakt | Var den finns | Varför den inte committas |
| --- | --- | --- |
| `brfv2-backup-20260730-110753-c54d.zip` | `~/.local/share/…/backups/` + `agenntserver:~/pilot-sakerhetskopior/` | innehåller `auth.db` med operatörens **verkliga namn och e-postadress**. Aldrig i Git. Kontrollerad post för post i stället, och summan redovisad nedan |
| `data/`-katalogen | `~/.local/share/se.brfdokumentai.desktop/data` | samma skäl. Runbookens S1-rutin säger att `data-snapshot` går att dela "just därför att korpusen är syntetisk" — det stämmer **inte** utan förbehåll så länge `auth.db` ligger där, vilket journalen har öppet sedan XS-55 |
| `logs/backend.log`, `logs/backend.log.1` | samma katalog | inga personuppgifter observerade, men de committas inte som filer. Det som behövdes är citerat ordagrant i evidensfilen, och filernas SHA-256 står där som bevis för att de var oförändrade över backendens död |
| Skärmbilder | *(finns inte)* | **inga skärmbilder togs.** Läsningen gjordes ur a11y-trädet, inte ur bilder, så det finns ingen identitetsbärande bild att maskera eller undanta |
| Agentens verktygsskript | sessionens scratchpad | mätinstrument, inte evidens. De hör inte i produktens repo, och deras utdata är det som redovisas |

### Säkerhetskopians identitet, redovisad utan att filen delas

| | Värde |
| --- | --- |
| Filnamn | `brfv2-backup-20260730-110753-c54d.zip` |
| Skapad | 2026-07-30 13:07:53 via **Appinställningar → Skapa säkerhetskopia nu** |
| Storlek / poster | 62 578 byte, 16 filer, `unzip -t` utan fel |
| Index i arkivet | 5 dokument / 13 chunks |
| SHA-256, lokalt | `e7fd00d42103789ecd767ebcd06349fc63b4612ab376a6a878055eae92381883` |
| SHA-256, annan media | `e7fd00d42103789ecd767ebcd06349fc63b4612ab376a6a878055eae92381883` — **identisk** |
| Rättigheter, fjärrsidan | katalog `700`, fil `600` |
| XS-55:s kopia | kvar och oförändrad, `3ec8b4c331f063532ebd5bbca92fadbf3f7486e05740a76ee3dde0890d448719` |

**Återställning är inte prövad.** Arkivet är kontrollerat post för post, men att
det går att *läsa tillbaka* är slinga 4:s fråga (XS-57) och påstås inte här.

---

## Fingeravtryck som bevisar att ingenting rördes

Tagna före och efter felinjektionen i pass 3, med de kommandon evidensfilen anger:

| Objekt | Före | Efter | Utfall |
| --- | --- | --- | --- |
| `data/` hela trädet | `23e2724658b914487c3baf58cd94324108fff484ad70fcd33ceb2f32341b5b49` | samma | **oförändrat** |
| `logs/backend.log` | `4c08f92254ff2af3d3cd31994d2d3f1b2b985edcfca5c1fa5f69f71fa2003312` | samma | **oförändrat** |
| `logs/backend.log.1` | `c979d759da27f45d88f08c183b2bfe8cf76ad66143a25ca075258cdae8d907fb` | samma | **oförändrat** |
| efter omstart: `backend.log.1` | — | `4c08f922…` | den kraschade instansens logg **bevarad av rotationen** |

Artefaktens identitet, oförändrad genom alla tre passen och båda injektionerna:

| | Värde |
| --- | --- |
| RPM SHA-256 | `6ba028fb0498da34ddd25c89366da98ec1ec96618ac6a607236cb58ab345e98d` |
| `deliveryTree` (installerat + repo) | `a702a3378ec524d8d2d4ff2603d0f00d35c2881d34bfc9640715f896a181e083` |
| `rpm --verify brf-dokument-ai` | exitkod `0` |
| `inspect_payload --installed` | 45 kontroller / **0 fynd** |
