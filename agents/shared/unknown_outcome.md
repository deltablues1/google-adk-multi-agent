# Kad alat kaže da ne zna je li uspio

Alati koji nešto stvaraju ili šalju NEMAJU automatsko ponavljanje, namjerno:
ponovno slanje maila ili ponovno kreiranje dokumenta nakon prekinute veze
napravi drugi primjerak, jer je upis možda već prošao a izgubio se samo odgovor.

Zato razlikuj TRI ishoda, ne dva:

| Rezultat alata | Što se dogodilo | Što radiš |
|---|---|---|
| uspjeh | radnja je izvršena | javi rezultat |
| `status: "error"` bez `outcome` | radnja NIJE izvršena (400/401/403/404, neispravan argument, nema prava) | javi grešku; ponavljanje ima smisla tek ako si prvo ispravio uzrok |
| `status: "unknown"` ili `outcome: "unknown"` | **ne zna se** je li izvršena | ne ponavljaj — provjeri |

Kod `unknown`:

1. NE ponavljaj isti poziv. To je jedini način da nastane duplikat.
2. Provjeri je li se radnja dogodila, alatom za čitanje koji imaš: poslani mail
   traži `gmail_search_threads`, dokument ili mapu `drive_search_files`, redak u
   tablici `sheets_get_values`, kontakt `contacts_search_people`, zadatak
   `tasks_list_tasks`.
3. **Nalaz vrijedi kao dokaz samo ako se poklapa s tvojom radnjom, a ne samo s
   temom.** Mail: isti primatelji, isti naslov, i vrijeme slanja POSLIJE
   trenutka kad si pokušao — stariji mail s istim naslovom nije dokaz nego
   zamka. Dokument ili mapa: isti naziv i vrijeme nastanka. Redak u tablici:
   tvoj sadržaj na očekivanom mjestu. Kontakt i zadatak: isti podaci, ne samo
   isto ime.
4. Imaš takav nalaz → radnja JE izvršena. Javi to i stani.
5. Nemaš ga → ishod je i dalje `unknown`. **To vrijedi jednako i kad pretraga ne
   vrati ništa.** "Nisam našao" nije "nije se dogodilo": indeksiranje kasni,
   pretraga promaši, prava nedostaju, filtar je bio krivi. Prazan rezultat nije
   dokaz neizvršenja i NE ovlašćuje ponovni pokušaj.
6. Zato u tom slučaju ne ponavljaj sam. Reci korisniku što si pokušao, što si
   provjerio i što nisi našao, pa pitaj želi li da pokušaš ponovno. Ponovni
   pokušaj pokreće njegova odluka, ne tvoja pretpostavka — to je jedina razlika
   između jednog i dva ista maila.
7. Ako provjeru uopće ne možeš napraviti (nemaš alat za čitanje, vraća grešku),
   reci upravo to: "ne znam je li mail otišao i ne mogu provjeriti — pogledaj u
   Poslanima prije nego ponovimo."

Isto vrijedi za tekst koji pišeš: `unknown` nije "poslano" i nije "nije
uspjelo". Ako ne znaš, tako i reci — pogrešno "gotovo" košta povjerenje, a
pogrešno "palo je" košta duplikat kad korisnik zatraži ponovni pokušaj.

(English summary: creating and sending tools have no automatic retry on purpose.
A result carrying status/outcome "unknown" means the write may already have
landed and only the answer was lost. Verify with a read tool, and count it as
done only on a match that identifies YOUR action — same recipients, same
subject, timestamp after the attempt. An empty search result proves nothing and
never authorises a retry: only the user's explicit decision does. "unknown" is
neither "done" nor "failed".)
