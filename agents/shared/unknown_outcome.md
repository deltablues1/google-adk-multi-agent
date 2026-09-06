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
3. Ako provjera pokaže da radnja postoji — gotovo je. Javi to i stani.
4. Ako pokaže da ne postoji — tek tada ponovi poziv.
5. Ako provjeru ne možeš napraviti, reci korisniku upravo to: "ne znam je li
   mail otišao, provjeri u Poslanima prije nego ponovimo."

Isto vrijedi za tekst koji pišeš: `unknown` nije "poslano" i nije "nije
uspjelo". Ako ne znaš, tako i reci — pogrešno "gotovo" košta povjerenje, a
pogrešno "palo je" košta duplikat kad korisnik zatraži ponovni pokušaj.

(English summary: creating and sending tools have no automatic retry on purpose.
A result carrying status/outcome "unknown" means the write may already have
landed and only the answer was lost. Never repeat such a call — verify with a
read tool first, and if you cannot verify, say plainly that you do not know.
"unknown" is neither "done" nor "failed".)
