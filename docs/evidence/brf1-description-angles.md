# BRF-1: union av två beskrivningsuppsättningar, och fyra vinklar — 2026-08-17

**Host:** agenntserver · **Modell:** Gemma 4 12B IT · `n_ctx=65536` · **commit:** `7458e87` · loopback · `scripts/eval_brf1_description_angles.py`

Enkörning. Ingen `ask()`. Ingen ny svarsväg. Låset `97b4e7bfc71f` skrevs inte om (`n_describe_calls=0`). Noll externa anslutningar. Fyravinkeltexterna ligger i `backend/out/brf1-description-angles/` (gitignorerad). Den här filen har bokstäver och träffar.

Isolerat urval, en handling, JSON `{"document": "X"}`, bara beskrivning (inte titel). Samma elva fall, namnordning A–I.

---

## 1. Unionstestet

Två låsta uppsättningar, samma urvalsprotokoll:

- **gamla:** `backend/out/brf1-doc-descriptions/descriptions.json` — den cache `brf1-doc-descriptions.md` mätte 7/11 på
- **nya:** `backend/eval/brf1-descriptions.lock.json` version `97b4e7bfc71f`

| | träff |
| --- | ---: |
| gamla | **7 / 11** |
| nya | **7 / 11** |
| minst en av dem | **9 / 11** |

**9 är tydligt över 7.** De två texterna bär olika information. Komplementet är två fall: gamla ensamma stänger R5 och R6 i den här körningen, nya ensamma stänger R3 och R3b. Båda missar R7 och R7b.

### Per fall

| fall | facit | gamla | nya | minst en |
| --- | --- | --- | --- | --- |
| R1 | G | **G** | **G** | ja |
| R2 | G | **G** | **G** | ja |
| R3 | G | H | **G** | ja (nya) |
| R4 | E | **E** | **E** | ja |
| R5 | E | **E** | C | ja (gamla) |
| R6 | E | **E** | D | ja (gamla) |
| R7 | E | B | G | **nej** |
| R8 | E | **E** | **E** | ja |
| R3b | G | B | **G** | ja (nya) |
| R5b | E | **E** | **E** | ja |
| R7b | E | A | H | **nej** |

### De fem hårda

| fall | gamla | nya | union |
| --- | --- | --- | --- |
| R5 | **E** | C | ja |
| R6 | **E** | D | ja |
| R7 | B | G | nej |
| R3b | B | **G** | ja |
| R7b | A | H | nej |

Tre av fem täcks av minst en uppsättning. R7 och R7b täcks av ingen.

Den publicerade tabellen i `brf1-doc-descriptions.md` var en annan enkörning på samma gamla cache (då R7=E, R6=C). Den här omkörningen gav R6=E, R7=B. Räkningen 7/11 återkom; ett fall bytte. Unionen 9/11 räknas på den här körningens båda uppsättningar, inte på den gamla tabellen.

---

## 2. Fyra vinklar per handling

Gemma skrev fyra korta fält per handling, från handlingens text: vad den reglerar, vilka frågor den kan besvara, vilka parter, vilka belopp. Urvalet såg alla fyra. Låset rördes inte. Nio generationer, inget tomt fält.

| fall | facit | fyravinkel |
| --- | --- | --- |
| R1 | G | **G** |
| R2 | G | **G** |
| R3 | G | **G** |
| R4 | E | **E** |
| R5 | E | C |
| R6 | E | F |
| R7 | E | A |
| R8 | E | **E** |
| R3b | G | **G** |
| R5b | E | **E** |
| R7b | E | A |

**7 / 11.** Samma räkning som en enda beskrivning. Inte unionens 9.

### De fem hårda

| fall | fyravinkel | mot unionen |
| --- | --- | --- |
| R5 | C | tappade gamlas E |
| R6 | F | tappade gamlas E |
| R7 | A | fortfarande miss |
| R3b | **G** | samma som låset |
| R7b | A | fortfarande miss |

E:s fyra fält innehöll *494*, *prisjustering*, *kostnaderna*, *BOA* — fakta som den gamla ensamma texten bar. Urvalet tog ändå C/F/A. Att fakta finns i listan är inte samma sak som att två separata urval OR:as. En listning med mer text skördade inte unionen.

G:s fyra fält hade *parkering*, *fordon*, *skador* — inte *bil* eller *gården*. R3b träffade ändå, som låset.

---

## Slutsats

Unionen av två urval gav **9 av 11**. Fyra vinklar i en enda lista gav **7 av 11**.

Vinsten kommer från flera oberoende urvalsbeslut, inte från mer text i ett beslut. Det är skillnaden mellan OR av två körningar och en längre prompt.

Att E:s fyravinkelfält bar *494*, *prisjustering* och *BOA* och urvalet ändå tog C/F/A är samma sak i ett fall: mer text i prompten är inte OR.

R7 och R7b missade båda uppsättningarna och fyravinkeln. De jagas inte som urvalsproblem.

---

## Invarianter

- `ask()` anropades inte. `app/answer.py` rördes inte.
- Låset `97b4e7bfc71f` oförändrat.
- Trafik bara loopback.
- Inget ur handlingarna eller fyravinkeltexterna committat.

Körbar mätning: `uv run python -m scripts.eval_brf1_description_angles` från `backend/`.
