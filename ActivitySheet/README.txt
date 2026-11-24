Activity Sheet 2.1
==================

Jeden program pro všechny. Běží z tohoto PC (127.0.0.1), ikonka je v trayi u hodin.
Zvenku se stahuje jen seznam činností z tvého serveru a samotný warehouse.

Adresa
------
http://activity-sheet.localhost:8080  (když je port obsazený, program sám použije :28000)
*.localhost vede vždy na tento PC – bez úprav hosts a bez DNS. Změna v Nastavení → O programu.

Spuštění
--------
Spustit.bat (nebo Zastupce-na-plochu.bat → ikonka na ploše).
Ikonka v trayi: levé kliknutí = otevřít, pravé = menu (Správa, Nastavení,
Aktualizovat seznam, Spouštět po přihlášení, Log, Ukončit).
Python: v repozitáři není. Stáhni z python.org „Windows embeddable package (64-bit)“ (3.12 nebo novější)
a rozbal ho do složky  python\  (aby existoval python\pythonw.exe). Nic se neinstaluje.
Spustit.bat i spouštění po přihlášení ho použijí jako první; Python v systému je jen záloha.
Celou složku ActivitySheet stačí zkopírovat na jakékoli PC (flash disk, síťová složka) – i bez Pythonu.
Do složky python\ nic nedoinstalovávej (pip) – program si knihovny nosí ve složce libs\.

Nastavení (tray → Nastavení…)
-----------------------------
• Spouštění po přihlášení do Windows (zástupce ve složce Po spuštění), otevřít okno po startu,
  nechat běžet po zavření okna.
• Režim: Automaticky (operátor pípne kartu, program vyplní warehouse) / Běžně (čárový kód + warehouse).
• Kde otevírat: vlastní okno Edge (nutné pro Automaticky) / výchozí prohlížeč.
• Zdroj seznamu: Ze serveru / Vlastní.

Dvě sady dat
------------
data/server.json   kopie ze serveru – aktualizuje se sama (i když se zrovna nepoužívá)
data/lokalni.json  vlastní seznam tohoto PC – vznikne při prvním přepnutí jako kopie serverového
Zobrazuje se ta, kterou určuje „Zdroj seznamu“. Navzájem se nepřepisují.
Novinky ze serveru do vlastního seznamu: tlačítko „Přidat novinky“ ve Správě nebo v Nastavení.
Přidá jen činnosti, které na serveru nově přibyly – úpravy uživatele i smazané položky zůstanou.
Když server zmizí, program jede dál na poslední kopii; kdokoli si může přepnout na Vlastní.

Správa činností
---------------
• Zdroj Vlastní: úpravy volně, jen pro tento PC.
• Zdroj Ze serveru: úpravy jdou na server pro všechny – vyžaduje přihlášení správce
  (heslo ověřuje server, v programu žádné heslo ani token není).
• Každé uložení zálohuje předchozí stav do data/zalohy/.

Automatický režim – ladění
--------------------------
python ActivitySheet.pyw --zkouska 000000000            (zkouška s neplatnou kartou)
Pomocník zmáčkne Start, vloží kartu a kód práce a zmáčkne Confirm. Výsledek už sám
neověřuje – ukazuje ho warehouse v okně. Když warehouse po kartě nebo kódu ukáže chybu,
pomocník skončí a chybu zobrazí (slova pro chyby: error_words v config.json).

Soubory: config.json (nastavení), activitysheet.log, operace.log, edge-profil/ (vlastní okno).

Nastavení pro vlastní nasazení (config.json vedle programu, vytvoří se při prvním spuštění)
  server_url     adresa serveru se seznamem činností (v repozitáři https://example.com)
  warehouse_url  stránka warehouse, která se zobrazí v okně (v repozitáři ukázková adresa)
Logo: web/static/assets/logo.png (když chybí, zobrazí se text).
