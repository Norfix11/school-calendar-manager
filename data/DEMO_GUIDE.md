# Sprievodca demo súbormi

## Čo jednotlivé ukážky demonštrujú

| Názov v rozhraní | Súbor | Čo demonštruje |
| --- | --- | --- |
| Learning & weekly recurrence | `demo_01_learning.json` | Ako história skutočných časov upravuje pôvodné odhady podľa predmetu a ako aplikácia predpovedá týždenné zadania s rôznym počtom úloh. |
| Deadline crunch | `demo_02_deadline_crunch.json` | Ako nahromadené deadliney a nastavená pohodlná náročnosť ovplyvňujú plán a riziko preťaženia. Demonštruje aj vynechanie plánovania úlohy po deadline a plánovanie úloh deň vopred pri skorom čase deadlinu. |
| Mixed patterns & a holiday | `demo_03_mixed_patterns.json` | Ako aplikácia vyhodnocuje týždenné, dvojtýždenné a nepravidelné zadania a ako prestávky ovplyvňujú predikcie. |
| Large benchmark · 396 tasks | `demo_04_large_benchmark.json` | Rýchlosť plánovania 72 nedokončených úloh pri histórii 324 dokončených úloh zo šiestich predmetov. Ukazuje využitie opakujúcich sa dĺžok pri zoskupovaní a predikciu zadaní pri veľkom množstve historických dát. |

Pri pôvodných nastaveniach prvé tri ukážky vytvoria postupne **9, 12 a 4 predikcie**. Veľká ukážka vytvorí **6 predikcií**, každú s pravdepodobnosťou výskytu **95 %**. Ide o predikcie celých zadaní, ktoré môžu obsahovať viac úloh.

Veľká ukážka zámerne obsahuje veľa úloh s rovnakou očakávanou dĺžkou, aby ukázala rýchlosť vďaka zoskupovaniu. Pri predvolených pohodlných hodinách výrazne prevyšuje dostupnú rezervu, preto môže riziko vychádzať po zaokrúhlení 100 %. Na porovnanie skúste napríklad 7 hodín denne a potom ich postupne znižujte.

## Čo sa nastaví pri otvorení dema

- **Planning start:** 24.09.2026.
- **Forecast through:** 21.10.2026.
- **Assignment breaks:** pri *Mixed patterns & a holiday* sa vyplní `5.10.2026-11.10.2026`. Pri ostatných demách sa prestávky vymažú.

Pohodlné hodiny a hranica upozornenia sa pri otvorení dema nemenia. Ak ste ich už upravili, výsledky sa budú líšiť od uvedených počtov. Pôvodné pohodlné hodiny od pondelka do nedele sú **1, 3, 3, 2, 3, 1, 2** a hranica upozornenia je **50 %**.

Pri otvorení bežného súboru zostanú aktuálne plánovacie dátumy aj prestávky zachované. Automatické nastavenia sa pre demo aplikujú iba cez **Open dataset**, nie cez **Merge into current**.

## Ukladanie upravených ukážok

**Save / Save a copy** tu nedáva užívateľovi povolenie prepísať pôvodný súbor:

- **Demo súbor:** rozhranie navrhne názov `my_deadlines.json`. Môžete zvoliť iný názov, čím sa zmeny uložia do bežného (už nie demo) súboru, ale uloženie pod pôvodným názvom niektorej zo štyroch ukážok je zablokované. Demo tak zostane nezmenené.
- **Bežný súbor:** rozhranie navrhne aktuálny názov. Ak iba potvrdíte prepísanie, zmeny sa uložia do pôvodného súboru. Iný názov vytvorí kópiu alebo po potvrdení prepíše už existujúci súbor s týmto názvom.

Formát uložených údajov je v oboch prípadoch rovnaký. Výpočet používa pre demo aj bežné údaje rovnaké algoritmy.
