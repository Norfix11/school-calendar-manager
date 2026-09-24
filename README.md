# School Calendar Manager

## 1. Zadanie problému

Počas druhého semestra som si uvedomil, že každý deň 20 minút preklikávam medzi ReCodExom, Sovičkou a predmetovými stránkami. Preto som ako každý rozumný človek začal programovať Python aplikáciu, ktorá deadliney zozbiera a uloží do Apple kalendára, aby som mal všetko na jednom mieste.
Samotný kalendár iba hovorí, kedy treba úlohy odovzdať, no tam som narazil na ďalšiu optimalizačnú úlohu. Musím vedieť určiť, ktorou úlohou začať a kedy.

Cieľom projektu je vytvoriť Python aplikáciu, ktorá tieto deadliney zozbiera, zjednotí a uloží ich históriu. Z deadlineov a pôvodných odhadov náročnosti zostaví plán, ktorý hovorí užívateľovi, v ktorý deň má vypracovať ktoré úlohy. Užívateľ si preto nastaví, koľko hodín chce pohodlne stráviť domácimi úlohami jednotlivé dni v týždni. Po dokončení úlohy môže zaznamenať skutočnú dĺžku trvania jej vypracovania, čo aplikácia použije pre tvorbu presnejších odhadov.

Aplikácia tiež uvažuje periodicky opakujúce sa zadania a na základe odhadovaných a už známych deadlineov určí náročnosť najbližších týždňov.

Výstupom je plán známych úloh, pravdepodobnosť prekročenia pohodlnej náročnosti, upozornenia na rizikové týždne a export deadlineov do kalendára.

## 2. Používateľská časť

### Inštalácia a spustenie

Program je určený pre verziu Python 3.11 alebo novšie verzie. Do zložky projektu nainštalujte knižnice a spustite aplikáciu:

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
python main.py
```

Otvorí sa lokálne webové rozhranie. Terminál musí zostať spustený, server nevyžaduje žiadnu externú webovú službu. Ak sa prehliadač neotvorí, adresu nájdete v termináli. Konzolový režim bez rozhrania je dostupný cez `python main.py --cli`, jeho nastavenia sú vo funkcii `main()`.

### Bežné používanie

1. Vyberte JSON súbor a stlačte **Open dataset**. V **Tasks & History** sa objavia úlohy z vybraného súboru spolu s ich parametrami. Vlastné JSON súbory patria do zložky `data`. **Merge into current** pridá úlohy z vybraného súboru do aktívneho zoznamu úloh (zoznam úloh v **Tasks & History** pod **All tasks**). Ak už je daná úloha v zozname, aktualizuje jej parametre.
2. Nastavte začiatok plánovania (štandardne dnešný dátum), koniec predpovede, pohodlnú náročnosť pre jednotlivé dni v týždni a hranicu upozornenia. V **Assignment breaks** je možné uviesť prestávky (bežne napríklad prázdniny), počas ktorých aplikácia nebude očakávať žiadny deadline, každú ako rozsah `5.10.2026-11.10.2026`. Počas prestávky je možné vypracovávanie úloh, teda plán môže obsahovať úlohy počas nich.
3. **Build my plan** zanalyzuje dataset a vypočíta výsledky. **Work plan** obsahuje naplánované vypracovanie úloh, **Weekly outlook** týždennú náročnosť s uvážením predikcií a **Predictions** odhadované nové zadania. Úlohy v pláne, naplánované na rovnaký deň, nemajú konkrétne vzájomné poradie.
4. V **Tasks & History** je možné upraviť parametre úlohy alebo ju označiť za dokončenú a zadať skutočnú dĺžku trvania jej vypracovania cez **Edit / Feedback**. Po zmene je nutné výsledky prepočítať cez **Build my plan**.
5. **Save / Save a copy** uloží aktívny zoznam úloh s aktualizovanými údajmi do otvoreného JSON súboru. Všetky neuložené úpravy zostávajú iba v pamäti servera, neukladajú sa do súborov. Nastavenia plánovania sa neukladajú.

**Refresh sources** načíta vypísané úlohy z vybraných školských stránok a zlúči ich s aktívnym zoznamom úloh. Pri Sovičke a ReCodExe je potrebné sa prihlásiť v externom prehliadači, ktorý sa sám otvorí a po prihlásení bez ďalšej činnosti v prehliadači stlačiť Enter v termináli. Obnovenie neukladá súbor ani neprepočítava plán.

**Export calendar** stiahne do zložky projektu aktívny zoznam deadlinov vo formáte ICS. Pri macOS je možné kalendár priamo synchronizovať, kde po potvrdení nahradí obsah existujúceho kalendára **Homework Deadlines**. Predikcie ani plánované dni vypracovania úloh sa neexportujú. Pri ukončení uložte zmeny, zavrite kartu v prehliadači a server ukončite stlačením Ctrl+C v termináli.

V zložke `data` sú predpripravené umelo vytvorené demo súbory `demo_01_learning.json` až `demo_04_large_benchmark.json`. Demonštrujú, ako aplikácia pracuje s učením z histórie, nahromadenými deadlineami, rôznymi vzormi opakovania a prestávkami, a väčším vstupom. Posledný demo súbor obsahuje 396 úloh, z toho 72 je nedokončených. Rozhranie pri ich otvorení samo nastaví plánovacie dátumy, upravené demo sa ukladá vždy ako kópia. Podrobnejší popis je v [sprievodcovi demo súbormi](data/DEMO_GUIDE.md).

## 3. Programátorská časť

### Rozdelenie programu a údaje

| Súbor | Úloha |
| --- | --- |
| `deadline_sources.py` | Získavanie deadlineov cez Requests, BeautifulSoup a Playwright. |
| `event_storage.py` | Načítanie, ukladanie, zlučovanie a zaznamenanie dokončenia úloh. |
| `risk_analysis.py` | Odhady trvania úloh, plánovanie, predikcia zadaní a výpočet rizika. |
| `calendar_export.py` | ICS export a **synchronizácia cez AppleScript*. |
| `frontend.py`, `frontend.html` | **Lokálny HTTP server, spracovanie užívateľových akcií a webové rozhranie*. |
| `main.py` | Spúšťanie aplikácie a **výpis výpočtov*. |

**Časti označené hviezdičkou boli vygenerované pomocou GPT*

Úlohy sú uložené ako zoznam slovníkov s kľúčmi `title`, `subject`, `due_date`, `description`, `est_hours`, `actual_hours` a `completed`. Deadline je v pamäti `date` alebo `datetime`, v JSON súbore text v ISO formáte. Pri zlučovaní slúži dvojica `(subject, title)` ako kľúč, teda dve úlohy sú považované za rovnaké ak sa zhodujú v `subject` aj `title`. Nové údaje aktualizujú deadliney, ale zachovávajú pôvodné odhady a spätnú väzbu. Staré úlohy zostávajú zachované v histórii.

### Využitie GPT

Pracoval som s Codexom, ktorý naprogramoval funkciu `sync_to_apple_calendar`, keďže neviem pracovať s AppleScript a táto časť projektu nie je zaujímavá algoritmicky. Ďalej Codex vygeneroval Front-end, teda rozhranie, konkrétnejšie súbory `frontend.py`, `frontend.html` a spojenie rozhrania s mojimi funkciami v `main.py` časti `if __name__ == "__main__":`. Finálne v `main.py` vygeneroval funkciu `print_analysis`, pretože som nechcel strácať čas s formátovaním testovacích printov, ktoré koncový užívateľ neuvidí. Nakoniec vygeneroval demo dataset, teda 4 umelo vytvorené súbory, ktoré som všetky testoval a napísal k nim sprievodcu podľa toho, čo mi k nim Codex povedal, mojich testov a promptu, ktorý som mu zadal. Žiadna z týchto funkcii nemá vplyv na použité algoritmy a zvyšný kód som písal sám, vrátane `deadline_sources.py`, kvôli ktorému som sa naučil používať knižnice na sourceovanie z internetu.

### Hlavné algoritmy

**Odhad trvania.** Skutočné časy dokončených úloh uložíme podľa predmetu do slovníka, pretože vyhľadanie hodnoty podľa kľúča má priemerne časovú zložitosť O(1). Pre každú nedokončenú úlohu skombinujeme pôvodný odhad so skutočnými časmi starších úloh rovnakého predmetu. Pôvodnému odhadu priradíme váhu `initial_weight`, takže sa správa ako niekoľko umelých pozorovaní a malé množstvo histórie ho okamžite neprepíše.

Očakávaný čas vypočítame ako vážený priemer

`expected_hours = (initial_weight * est_hours + sum(past_hours)) / total_weight`.

Pôvodnému odhadu zároveň priradíme počiatočnú smerodajnú odchýlku `relative_deviation * est_hours` a jej druhú mocninu použijeme ako počiatočný rozptyl. Pri spájaní tohto rozptylu s historickými dátami musíme spočítať nový rozptyl bez dát generujúcich pôvodný rozptyl, pretože nový spoločný priemer `expected_hours` je posunutý oproti pôvodnému priemeru `est_hours`. Preto počítame

`initial_variance + (est_hours - expected_hours)^2`.

Takto prepočítame pôvodný rozptyl vzhľadom na nový priemer. Po vynásobení `initial_weight` dostaneme súčet štvorcov odchýlok umelých dát. K nemu pripočítame `sum((hours - expected_hours)^2)`, súčet štvorcov odchýlok skutočných historických časov a vydelením celkovou váhou získame výsledný rozptyl.

Zo strednej hodnoty a rozptylu následne vypočítame parametre Gamma distribúcie. Pre Gamma distribúciu platí `mean = shape * scale` a `variance = shape * scale^2`, teda vypočítame neznáme `shape` a `scale` vyriešením sústavy:

`shape = expected_hours^2 / variance`

a

`scale = variance / expected_hours`.

Zo `shape` a `scale` vytvoríme celé pravdepodobnostné rozdelenie trvania úlohy, nie iba jeden odhad. Gamma distribúciu používame preto, že čas trvania je kladný a môže mať pravý chvost.

**Plánovanie celých úloh.** Vo funkcii `build_timeline` zaokrúhlime trvania nahor na polhodinové jednotky a úlohy rovnakej dĺžky zoskupíme v slovníku. V každej skupine ich zoradíme podľa deadlineu, čo je súčasťou inicializácie a nepridáva na komplexite. Aktuálny stav reprezentujeme aktuálnym dňom a n-ticou počtov už priradených úloh z jednotlivých skupín. N-ticu používame preto, že je nemenná a hashovateľná, takže ju môžeme použiť ako súčasť kľúča v slovníku `best_seen`.

Rekurzívnym DFS prehľadávame stavový priestor, pričom vždy zavoláme funkciu do každého legálneho naplánovania zvyšných úloh na aktuálny deň a posunieme funkcii ďalší deň. Slovník `best_seen` používame na memoizáciu. Kontrola už navštíveného stavu má priemerne časovú zložitosť O(1), takže ak rovnaký stav dosiahneme s horším skóre, celú vetvu ďalej neprehľadávame.

Skóre uložíme ako n-ticu a porovnávame ho lexikograficky. Najskôr minimalizujeme súčet denných penalizácií za prekročenie pohodlnej dennej náročnosti. Štandardne používame penalizáciu `max(0, hours - allowance)^2`, takže denný plán pod limitom má nulovú penalizáciu a každé ďalšie preťaženie je horšie, pretože funkcia je konvexná (konvexitu požadujeme). Ako druhú zložku skóre používame súčet súčinov indexu dňa a počtu priradených polhodín. Pri rovnakom preťažení tak vyhrá skoršie vypracovanie úloh.

Vo funkcii `greedy_benchmark_score` najskôr greedy a rýchlo vytvoríme legálny plán. Každú úlohu priradíme na legálny deň s najnižším prírastkom penalizácie pri jej priradení. Jeho skóre potom použijeme ako hornú hranicu pre DFS.

Vo funkcii `relaxed_remaining_score` vypočítame optimistickú dolnú hranicu. Zvyšné úlohy dočasne rozdelíme na samostatné polhodinové jednotky a vždy vyberieme deň s najnižším prírastkom penalizácie. Ponuky uložíme do min-haldy. Vloženie aj odobratie minima má časovú zložitosť O(log n), namiesto opakovaného hľadania minima v zozname s časovou zložitosťou O(n). Keďže používame konvexnú penalizáciu, cena ďalšej polhodiny na rovnakom dni neklesá. Každé rozdelenie, do ktorého sa z aktuálneho stavu môžeme legálne dostať je podmnožinou rozdelení, do ktorých sa mohla dostať táto funkcia nelegálnym rozdelením, teda ak ani toto nelegálne skóre nedokáže prekonať najlepšie už nájdené skóre, celú DFS vetvu zahodíme.

Prehľadávame stavový priestor do hĺbky, pretože tak najskôr dostaneme výsledné skóre lepšie ako greedy horná hranica, pomocou ktorého
následne môžeme odrezať veľa vetiev, ktorých optimistické skóre je horšie.

**Riziko preťaženia.** Každú úlohu reprezentujeme spojitou Gamma distribúciou trvania. Pre ďalšie výpočty ju prevedieme na diskrétnu mriežku, ktorá odpovedá na otázku aká je pravdepodobnosť, že trvanie úlohy s touto distribúciou v hodinách spadne do `(a, b]`. Ak `f(x)` predstavuje hustotu pravdepodobnosti a `F(x)` distribučnú funkciu, potom pre interval `(a, b]` platí

`P(a < duration <= b) = ∫_a^b f(x) dx = F(b) - F(a)`.

Vo funkcii `event_duration_probabilities` preto vypočítame distribučnú funkciu v bodoch mriežky a rozdielmi susedných hodnôt získame pravdepodobnosti jednotlivých intervalov. Takto prevedieme spojitý počet možných trvaní na konečné pole pravdepodobností.

Rozdelenia nezávislých úloh spojíme konvolúciou. Pre dve diskrétne rozdelenia platí

`P(A + B = k) = sum_i P(A = i) * P(B = k - i)`.

Vo funkcii `convolve_workload_probabilities` použijeme FFT konvolúciu. Pre pole dĺžky n má približne časovú zložitosť O(n log n), namiesto priamej konvolúcie s O(n²), ako som sa dočítal v dokumentácii SciPy. Výsledné pole uchováme iba po hranicu povolenej náročnosti, takže dĺžka mriežky je konštantná a nepredlžujeme zoznamy, čo by pridalo komplexitu. Hľadanú informáciu o očakávanom preťažení tak ale nestratíme, keďže súčet zachovaných pravdepodobností predstavuje `P(workload <= allowance)`, teda riziko preťaženia vypočítame ako

`P(overload) = 1 - P(workload <= allowance)`.

Denné riziko vypočítame z Gamma distribúcií úloh, ktoré plán priradil na daný deň. Pri týždennom riziku rovnakým spôsobom skombinujeme konvolúciou distribúcie známych nedokončených úloh a predikovaných zadanií, ak spadajú do uvažovaného týždňa. Tým dostaneme pravdepodobnostnú mriežku trvania úloh v danom týždni.

**Predikcia zadaní.** Vo funkcii `predict_events` zoskupíme najskôr podľa predmetu a potom podľa dátumu do vnoreného slovníka. Ako hodnotu pri dátume uložíme počet úloh, ktoré sa v daný deň objavili. Pre každý predmet uvažujeme opakovanie po 7 a 14 dňoch a všetky možné posuny.

Historické dátumy zoradíme a pomocou `bisect_left` nájdeme pozíciu očakávaného dátumu binárnym vyhľadávaním s časovou zložitosťou O(log n), namiesto prehľadávania celého zoznamu s O(n). Najbližší deadline potom musí byť jeden z dvoch susedných prvkov. Deadline v tolerovanom okolí považujeme za trafenie. Presnému trafeniu priradíme váhu 1 a posunutým trafeniam nižšiu váhu určenú funkciou v závislosti na vzdialenosti, ktorá je štandardne `1 - distance / (tolerance + 1)`.

Každému takémuto modelu určenému posunom a periódou priradíme skóre vo forme n-tice. Skóre porovnávame lexikograficky, v poradí fit, potom počet trafení, celkový posun a dĺžku periódy. Fit vypočítame ako:

`fit = matched_weight / (evaluated_centers + unmatched_dates)`

kde `matched_weight` predstavuje vážený počet trafení, teda ešte penalizujeme model každým netrafeným očakávaným dátumom, aj deadlinom, ktorý je vypísaný ale tento model ho netrafil. Tým dostaneme pre daný predmet najlepší model.

Pravdepodobnosť ďalšieho výskytu vypočítame ako `(matched_centers + 1) / (evaluated_centers + 2)`, teda priemerný počet trafení. Pridaním jedného trafenia a jedného netrafenia znovu vyhladíme priemer. Očakávaný počet úloh pri výskyte vypočítame ako `matched_events / matched_centers`, teda priemerný počet úloh, ktoré jeden očakávaný dátum trafil.

Trvanie budúcich úloh nepredikujeme v `predict_events`. V spájacej funkcii `analyze_events` najskôr pre predmet vypočítame priemer pôvodných `est_hours`, ak užívateľ nezadá vlastný override, a následne z neho a historických skutočných časov vytvoríme Gamma distribúciu rovnakým postupom ako pri známych úlohách.

Vo funkcii `predicted_workload_probabilities` nakoniec spojíme tri druhy neistoty. Vypočítame pre `k` iterujúce od 1 po maximálny počet úloh, ktorý trafil nejaký očakávaný dátum (jednoduchšie je uvažovať, že sme v skutočnosti prešli všetky prirodzené `k`, pretože väčšie `k` ako tie, cez ktoré iterujeme dajú následovnú pravdepodobnosť 0):

`P(count = k | recurrence) = centers_with_k_events / matched_centers`.

Teda pravdepodobnosť, že predikcia bude mať skupinu `k` eventov, ak naozaj nastane opakovanie. 

Najskôr máme distribúciu trvania jednej úlohy. V cykle ju postupne konvolvujeme samu so sebou, takže po k-tom prechode `total_probabilities` opisuje distribúciu súčtu presne `k` nezávislých úloh.

Pre každé možné `k` potom použijeme pravidlo podmienenej pravdepodobnosti a danú distribúciu po prvkoch vynásobíme

`P(recurrence) * P(count = k | recurrence)`.

Tým dostaneme pravdepodobnosť, že sa zadanie objaví, bude obsahovať práve `k` úloh a ich spoločné trvanie skončí v konkrétnom intervale mriežky. Tieto možnosti pre všetky `k` sčítame. Možnosti, že trvanie bude nulové, priradíme pravdepodobnosť `1 - P(recurrence)`, ktorú konvolúcia nezmení. Výsledná mriežka tak obsahuje celé pravdepodobnostné rozdelenie trvania jednej predikovanej skupiny, pričom už v sebe zahŕňa neistotu výskytu, počtu úloh aj ich trvania.

Očakávaný počet hodín počítame osobitne ako

`P(recurrence) * E[count | recurrence] * E[hours per event]`.

Nepočítame ho z výslednej mriežky, pretože tú pri výpočte rizika odrežeme na hranici povolenej náročnosti, teda skreslíme priemer. Takto získanú distribúciu použijeme na už spomenutý výpočet pravdepodobnosti týždňového preťaženia.