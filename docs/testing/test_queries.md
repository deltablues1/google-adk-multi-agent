# Test Queries za main.py - Svi Mogući Workflowi

## Kategorija 1: Jednostavni Single-Agent Upiti

### 1.1 Mailer (Email Operations)
```
1. "Pokaži mi zadnjih 5 emailova"
2. "Pokaži mi nepročitane emailove od Marka"
3. "Pošalji email na marko@example.com sa naslovom 'Test' i porukom 'Ovo je test'"
4. "Pretraži emailove sa ključnom riječi 'invoice'"
5. "Pokaži mi sve emailove iz proslog tjedna"
```

**Očekivano:** Single-agent, brz odgovor, Mailer direktno poziva Gmail API

---

### 1.2 Secretary (Calendar/Meetings)
```
6. "Koja mi je prva obaveza danas?"
7. "Stvori sastanak sutra u 14:00 sa naslovom 'Team standup'"
8. "Pokaži mi sve sastanke za sljedeći tjedan"
9. "Otkaži sastanak sa ID calendar_event_123"
10. "Pronađi slobodan termin ovaj petak između 10-16h"
```

**Očekivano:** Single-agent, Secretary koristi Google Calendar API, RFC3339 format

---

### 1.3 Rolodex (Contacts)
```
11. "Dodaj novi kontakt: Ime 'Ana Horvat', email 'ana@example.com', telefon '099-123-4567'"
12. "Pokaži mi sve kontakte sa prezimenom 'Kovač'"
13. "Pronađi kontakt sa emailom marko@example.com"
14. "Ažuriraj broj telefona za kontakt contact_001 na '098-999-8888'"
15. "Pokaži mi sve kontakte iz tvrtke 'Google'"
```

**Očekivano:** Single-agent, Rolodex pretraživanje Firestore, duplicate detection

---

### 1.4 Tracker (Task Management)
```
16. "Dodaj zadatak: 'Napisati izvještaj' do petka"
17. "Pokaži mi sve moje zadatke sa visokim prioritetom"
18. "Označi zadatak task_001 kao gotov"
19. "Koji mi zadaci kasne (overdue)?"
20. "Kreiraj zadatak 'Kupiti mlijeko' za danas navečer"
```

**Očekivano:** Single-agent, Tracker koristi Firestore, eksplicitni datumi

---

### 1.5 Librarian (Google Drive)
```
21. "Pronađi sve PDF dokumente u mom Drive-u"
22. "Stvori novu mapu 'Q1 Reports 2026'"
23. "Uploadaj file sa patha C:\\Users\\Tomislav\\Desktop\\test.pdf"
24. "Pokaži mi datoteke modificirane u zadnjih 7 dana"
25. "Pretraži dokumente sa riječi 'invoice' u nazivu"
```

**Očekivano:** Single-agent, Librarian koristi Google Drive API

---

### 1.6 Analyst (Google Sheets)
```
26. "Koliko ukupno prodaje imam u Sheet-u 'Sales Q4 2025'?"
27. "Izračunaj prosjek kolone 'Revenue' u sheet_id_123"
28. "Pronađi red gdje je 'Status' = 'Pending'"
29. "Koliko redova ima sheet 'Customers'?"
30. "Koja je najveća vrijednost u koloni 'Amount'?"
```

**Očekivano:** Single-agent, Analyst čita/analizira Google Sheets

---

### 1.7 Scraper (Web Extraction)
```
31. "Izvuci naslov i cijenu sa stranice https://www.njuskalo.hr/neki-oglas"
32. "Daj mi sve iPhone oglase sa Njuškalo kategorije 'Mobiteli'"
33. "Koja je trenutna cijena bitcoina na nekom crypto portalu?"
34. "Izvuci tablicu cijena sa stranice https://cprz.hr/cjenik-usluga"
35. "Pronađi najjeftiniji rabljeni auto na Njuškalu u Zagrebu"
```

**Očekivano:** Single-agent, Scraper koristi AgentQL, Croatian portal support

---

### 1.8 Expense (Receipt OCR)
```
36. "Analiziraj račun sa slike: C:\\Users\\Tomislav\\Desktop\\receipt.jpg"
37. "Izvuci podatke iz ovog invoicea: image_url_here"
38. "Spremi trošak: Vendor 'Konzum', Amount 123.45, Date '2026-01-15'"
39. "Pokaži mi sve troškove iz zadnjih 30 dana"
40. "Koja je suma svih troškova za siječanj 2026?"
```

**Očekivano:** Single-agent, Expense koristi Gemini Flash OCR, confidence scoring

---

## Kategorija 2: Multi-Agent Workflows (2 agenta)

### 2.1 Research → Document
```
41. "Istraži najnovije trendove u AI i napiši mi sažetak u Google Doc"
42. "Pronađi informacije o Claude API pricing i stvori dokument sa rezultatima"
43. "Pretraži Drive za 'Q4 Report', onda stvori sažetak u novom dokumentu"
44. "Analiziraj Sheet 'Sales Data' i kreiraj izvještaj u Google Docs"
45. "Izvuci podatke sa Njuškalo oglasa i spremi ih u Google Doc"
```

**Očekivano:** Orchestrator → [Researcher/Librarian/Analyst/Scraper] → Scribe

---

### 2.2 Research → Email
```
46. "Istraži cijene hosting usluga i pošalji rezultate na marko@example.com"
47. "Pronađi kontakt za Ana Horvat i pošalji joj email sa pozdravom"
48. "Pretraži emailove od 'Google' i posalji mi sažetak"
49. "Analiziraj sheet 'Q4 Sales' i emailaj rezultate CEO-u"
50. "Izvuci cijene sa competitor stranice i pošalji marketing timu"
```

**Očekivano:** Orchestrator → [Researcher/Rolodex/Analyst/Scraper] → Mailer

---

### 2.3 Calendar → Tasks
```
51. "Pronađi sve sastanke za sutra i stvori zadatke za pripremu"
52. "Koji sastanak mi je sljedeći i dodaj reminder zadatak 30 min prije"
53. "Pretvori sve sastanke ovog tjedna u zadatke u Trackeru"
54. "Stvori sastanak 'Project kickoff' i dodaj zadatak 'Pripremi prezentaciju'"
55. "Pronađi slobodan termin petak popodne i dodaj zadatak 'Zakaži dentista'"
```

**Očekivano:** Orchestrator → Secretary → Tracker

---

### 2.4 Email → Tasks
```
56. "Izvuci action items iz zadnjih 10 emailova i stvori zadatke"
57. "Pretraži emailove sa 'TODO' i kreiraj zadatke za svaki"
58. "Pokaži nepročitane emailove od šefa i stvori urgentne zadatke"
59. "Pronađi email sa subject 'Invoice due' i dodaj zadatak za plaćanje"
60. "Analiziraj thread sa Markom i izvuci action items kao zadatke"
```

**Očekivano:** Orchestrator → Mailer → Tracker

---

### 2.5 Research → Synthesize
```
61. "Istraži 'Quantum computing advances 2026' i napiši tehnički izvještaj"
62. "Pronađi informacije o 5 AI frameworkova i usporedi ih u executive summary"
63. "Pretraži znanstvene članke o climate change i napiši blog post"
64. "Analiziraj competitor data i kreiraj markdown izvještaj"
65. "Istraži market trends i napiši sažetak za investitore"
```

**Očekivano:** Orchestrator → Researcher → Synthesizer

---

## Kategorija 3: Kompleksni Multi-Agent Workflows (3+ agenata)

### 3.1 Research → Document → Email (Klasični Workflow)
```
66. "Istraži best practices za Python testing, napiši dokument, i pošalji dev timu"
67. "Pronađi najnovije vijesti o OpenAI, stvori sažetak u Doc-u, i emailaj CTO-u"
68. "Analiziraj Sheet 'Customer Feedback', kreiraj izvještaj, pošalji managementu"
69. "Izvuci podatke sa competitor website, dokumentiraj u Google Docs, pošalji marketing timu"
70. "Pretraži Drive za 'Budget 2025', analiziraj brojke, kreiraj summary doc, pošalji CFO-u"
```

**Očekivano:** Orchestrator → Research/Analysis → Scribe → Mailer (3 koraka)

---

### 3.2 Meeting Notes → Tasks → Email Reminders
```
71. "Preuzmi notes sa današnjeg sastanka, izvuci action items, stvori zadatke, pošalji email sa reminder-ima"
72. "Pronađi Google Doc 'Team Standup Notes', izvuci TODO-e, kreiraj zadatke, pošalji assignee-ima"
73. "Analiziraj zadnjih 5 meeting notes, stvori zadatke sa prioritetima, emailaj team lead-u sažetak"
74. "Stvori sastanak 'Sprint Planning', dodaj zadatke za pripremu, pošalji pozivnice sa agendом"
75. "Izvuci sve odluke iz meeting notes doc_123, stvori tracking zadatke, pošalji stakeholderima"
```

**Očekivano:** Orchestrator → Librarian/Scribe → Tracker → Mailer (3-4 koraka)

---

### 3.3 Contact Research → Document → Schedule Meeting → Email
```
76. "Pronađi kontakt za 'John Smith' iz tvrtke 'Acme Corp', stvori meeting brief, zakaži sastanak, pošalji pozivnicu"
77. "Istraži kompaniju 'TechStartup', pronađi decision makere, kreiraj outreach dokument, zakaži call, pošalji email"
78. "Pretraži Rolodex za kontakte u 'Zagreb', kreiraj mailing list dokument, zakaži team sync, pošalji invite"
```

**Očekivano:** Orchestrator → Rolodex/Researcher → Scribe → Secretary → Mailer (4 koraka)

---

### 3.4 Invoice Processing → Expense → Document → Email
```
79. "Analiziraj invoice PDF sa Drive-a, spremi kao trošak, kreiraj approval dokument, pošalji na odobrenje"
80. "Izvuci podatke iz receipt slike, dodaj u Expense tracking, generiraj monthly report, emailaj accounting timu"
81. "Pronađi sve PDF račune u Drive folderu 'Invoices', OCR svaki, spremi troškove, kreiraj summary report"
```

**Očekivano:** Orchestrator → Librarian → Expense → Scribe → Mailer (4 koraka)

---

### 3.5 Competitive Analysis → Marketing Campaign
```
82. "Istraži competitor pricing na njihovom websiteu, analiziraj podatke, kreiraj ad campaign strategy"
83. "Izvuci product features sa competitor stranice, usporedi sa našim, generiraj marketing copy, stvori draft Google Ads kampanju"
84. "Pretraži tržišne trendove, sintetiziraj insights, kreiraj campaign brief, generiraj ad assets (ČEKAJ APPROVAL!)"
```

**Očekivano:** Orchestrator → Scraper/Researcher → Analyst/Synthesizer → Marketing (3-4 koraka, SA APPROVAL!)

---

## Kategorija 4: Edge Cases i Error Handling

### 4.1 Missing Information (Agent mora pitati)
```
85. "Pošalji email Marku" (Nema sadržaja - mora pitati što napisati)
86. "Stvori sastanak" (Nema vremena/datuma - mora pitati)
87. "Dodaj zadatak" (Nema opisa zadatka - mora pitati)
88. "Pronađi kontakt" (Nije jasno koji - mora pitati ime/email)
89. "Analiziraj podatke" (Nije jasno koji sheet - mora pitati)
```

**Očekivano:** Agent detektira nedostajuće informacije, pita korisnika

---

### 4.2 Duplicate Detection
```
90. "Dodaj kontakt 'Marko Kovač', email 'marko@example.com'" (2x - duplicate!)
91. "Stvori zadatak 'Napisati izvještaj' do petka" (Već postoji - duplicate!)
92. "Spremi trošak: Konzum, 50 EUR, danas" (Već snimljen isti račun - duplicate!)
93. "Zakaži sastanak 'Team standup' sutra u 10:00" (Već postoji u to vrijeme - conflict!)
```

**Očekivano:** Agent detektira duplikat, upozori korisnika, pita što napraviti

---

### 4.3 Invalid Data
```
94. "Pošalji email na 'marko_bez_at_znaka'" (Invalid email format)
95. "Stvori sastanak jučer u 15:00" (Past date - invalid)
96. "Dodaj trošak: Konzum, -50 EUR" (Negative amount - invalid)
97. "Ažuriraj zadatak sa ID 'ne_postoji_123'" (Invalid ID)
98. "Uploadaj file sa patha 'C:\\ne\\postoji\\file.pdf'" (File not found)
```

**Očekivano:** Agent validira input, vraća clear error, traži ispravak

---

### 4.4 Permission/Access Issues
```
99. "Obriši sve emailove u inboxu" (Destructive action - mora tražiti potvrdu)
100. "Stvori Google Ads kampanju sa budgetom 1000 EUR" (Must show preview + APPROVAL)
101. "Promijeni sve kontakte u Rolodexu" (Bulk operation - mora tražiti potvrdu)
102. "Uploadaj file u tuđi Google Drive folder" (Permission denied potencijalno)
```

**Očekivano:** Agent traži explicit confirmation prije destructive/expensive operacija

---

### 4.5 API Rate Limits & Timeouts
```
103. "Pretraži sve moje emailove od 2020 do danas" (HUGE query - rate limit možda)
104. "Analiziraj 500 redova Sheet podataka i generiraj report za svaki" (Long operation)
105. "Izvuci podatke sa 50 različitih Njuškalo oglasa" (Multiple scraping - slow)
106. "OCR-aj 100 receipt slika odjednom" (Batch operation - može biti slow)
```

**Očekivano:** Agent handla rate limits, pokazuje progress, ne crasha

---

## Kategorija 5: Croatian Language & Format Edge Cases

### 5.1 Croatian Date Formats
```
107. "Stvori sastanak 15.1.2026. u 14:00" (DD.MM.YYYY format)
108. "Pokaži zadatke do 31. siječnja" (Croatian month name)
109. "Pronađi emailove od prošlog utorka" (Relative date - must convert to explicit)
110. "Dodaj event sutra" (MUST convert 'sutra' to explicit date!)
```

**Očekivano:** Agent konvertira Croatian date format u ISO 8601, explicit datumi

---

### 5.2 Croatian Portal Scraping
```
111. "Izvuci cijenu stana sa Njuškalo oglasa: https://www.njuskalo.hr/..."
112. "Koliko košta najjeftiniji iPhone na Njuškalu?"
113. "Pronađi sve oglase za apartmane u Splitu"
114. "Koja je prosječna cijena rabljenih automobila VW Golf?"
```

**Očekivano:** Scraper koristi AgentQL, parsira Croatian price format "1.234,56 EUR"

---

### 5.3 Croatian Email Composition
```
115. "Pošalji email kolegama sa čestitkama za Božić"
116. "Napiši formalni email klijentu sa isprikom za kašnjenje"
117. "Kreiraj newsletter za hrvatske pretplatnike"
118. "Pošalji reminder za sastanak sa hrvatskim frazama"
```

**Očekivano:** Mailer piše prirodan hrvatski tekst, ne Google Translate stilski

---

### 5.4 Croatian Character Preservation
```
119. "Dodaj kontakt 'Željko Čović' sa email 'zeljko@example.com'"
120. "Stvori zadatak 'Završiti godišnji izvještaj'"
121. "Pretraži dokumente sa riječi 'društvene mreže'"
122. "Kreiraj folder 'Računovodstvo 2026'"
```

**Očekivano:** Preserve č, ć, đ, š, ž characters u svim operacijama

---

## Kategorija 6: Performance & Optimization Tests

### 6.1 Gemini Flash OCR (Cost Optimization)
```
123. "OCR-aj 10 različitih računa i usporedi troškove Gemini Flash vs Document AI"
124. "Analiziraj račun sa lošom kvalitetom slike - test confidence scoring"
125. "Batch process 20 receipts odjednom"
```

**Očekivano:** Expense koristi Gemini Flash (1400x cheaper), prikazuje confidence score

---

### 6.2 Firestore Caching
```
126. "Pokaži mi kontakt 'Marko Kovač'" (1st call - Firestore query)
127. "Opet pokaži kontakt 'Marko Kovač'" (2nd call - should be cached)
128. "Lista svih kontakata" (Should use pagination za velike resultate)
```

**Očekivano:** Optimized queries, caching where applicable

---

### 6.3 Batch Operations
```
129. "Stvori 10 zadataka odjednom iz ovog popisa: [...]"
130. "Pošalji isti email na 20 različitih adresa"
131. "Dodaj 15 kontakata iz CSV filea"
```

**Očekivano:** Agents koriste batch API calls gdje moguće

---

## Kategorija 7: Human-in-the-Loop Workflows

### 7.1 Marketing (MUST APPROVE!)
```
132. "Generiraj Google Ads image za yoga studio, ali PRVO mi pokaži preview"
133. "Kreiraj video ad za coffee shop - ČEKAJ MOJ APPROVAL prije create draft"
134. "Napravi kampanju za fitness centar - show me assets BEFORE creating campaign"
```

**Očekivano:** Marketing UVIJEK pokazuje generirana assets, čeka approval, kampanje PAUSED

---

### 7.2 Destructive Operations
```
135. "Obriši sve zadatke starije od 6 mjeseci" (Ask confirmation first!)
136. "Arhiviraj sve stare emailove" (Confirm before acting!)
137. "Obriši duplikat kontakte" (Show which ones, then confirm!)
```

**Očekivano:** Agent traži explicit confirmation prije destructive actions

---

### 7.3 Expensive Operations
```
138. "Uploadaj 5 GB video file na Drive" (Warn about size!)
139. "Analiziraj 10,000 redova Sheet podataka sa kompleksnim izračunima" (Warn about time!)
140. "Pošalji 500 emailova odjednom" (Batch operation - confirm!)
```

**Očekivano:** Agent upozorava na cost/time, traži potvrdu

---

## Kategorija 8: Complex Conditional Logic

### 8.1 If-Then Workflows
```
141. "AKO je danas petak, ONDA pošalji weekly report; INAČE samo pokaži progress"
142. "Pronađi kontakte iz 'Zagreb', pa AKO ih ima više od 10, kreiraj mailing list; inače dodaj sve u jedan email"
143. "Pretraži zadatke, AKO je ijedan overdue SA prioritetom HIGH, pošalji urgent email"
144. "Analiziraj sheet, AKO je revenue < target, kreiraj action plan dokument"
```

**Očekivano:** Orchestrator evaluates conditions, izvršava conditional branches

---

### 8.2 Loop Workflows
```
145. "ZA SVAKI kontakt iz 'Engineering team', stvori zadatak 'Code review reminder'"
146. "Pronađi sve PDF invoices, ZA SVAKI pokreni OCR i spremi expense"
147. "Lista svih sastanaka sutra, ZA SVAKI stvori prep task 30 min prije"
148. "Pretraži top 5 competitor websites, ZA SVAKI izvuci pricing i usporedi"
```

**Očekivano:** Orchestrator iterates through collections, executes for each item

---

### 8.3 Nested Workflows
```
149. "Istraži AI frameworks → ZA SVAKI pronađi pricing → STVORI comparison doc → AKO je najjeftiniji < $100, pošalji preporuku CTO-u"
150. "Lista sastanaka ovaj tjedan → ZA SVAKI stvori prep task → AKO je external meeting, dodaj kontakte u Rolodex → Pošalji summary email"
```

**Očekivano:** Orchestrator handla nested logic sa više razina

---

## Kategorija 9: Error Recovery & Resilience

### 9.1 Partial Failures
```
151. "Pošalji email na 5 adresa: valid1@example.com, invalid_bez_at, valid2@example.com, , valid3@example.com"
152. "Stvori 3 zadatka: [valid task], [task bez opisa], [valid task 2]"
153. "Dodaj kontakte: [valid], [duplicate], [missing email], [valid]"
```

**Očekivano:** Agent procesira validne, reporta failures, nastavlja gdje može

---

### 9.2 API Failures & Retries
```
154. "Uploadaj file na Drive" (simulate network error)
155. "Pošalji email" (simulate Gmail API quota exceeded)
156. "Kreiraj calendar event" (simulate Calendar API timeout)
```

**Očekivano:** Agent retries sa exponential backoff, jasno reporta failures

---

### 9.3 Rollback Scenarios
```
157. "Kreiraj 10 zadataka, ali 5. task je invalid" (Rollback sve ili nastaviti?)
158. "Multi-step workflow: Research → Doc → Email, ali Email fails" (Što sa Doc-om?)
159. "Batch expense upload, 3/10 su duplicates" (Skip ili stop?)
```

**Očekivano:** Clear rollback/continue strategy, user transparency

---

## Kategorija 10: Ambiguous Queries (Orchestrator Decision Making)

### 10.1 Multiple Valid Interpretations
```
160. "Pretraži Apple dokumente" (Apple company ili apple fruit research?)
161. "Pošalji rezultate timu" (Koji tim? Email ili Doc?)
162. "Analiziraj sales data" (Koji sheet? Koji period?)
163. "Dodaj meeting notes" (Create new doc ili append to existing?)
```

**Očekivano:** Orchestrator pita za clarification, ne gađa

---

### 10.2 Intent Detection Challenges
```
164. "Što mi je danas?" (Calendar events, tasks, ili emails?)
165. "Treba mi report" (Analytic report, meeting notes summary, ili nešto treće?)
166. "Kontaktiraj klijenta" (Phone, email, ili schedule meeting?)
167. "Organiziraj project kickoff" (Just calendar event ili full workflow?)
```

**Očekivano:** Orchestrator asks clarifying questions ili pokušava best match

---

## Bonus: Stress Testing

### Extreme Workflows
```
168. "Kreiraj kompletan onboarding workflow za novog zaposlenika: stvori doc sa checklist-om, zakaži 5 intro meetinga sa team memberima, dodaj sve kao zadatke sa deadline-ima, pošalji welcome email, dodaj u Rolodex, stvori Drive folder strukturu"

169. "Competitive intelligence workflow: istraži top 5 competitora, za svakog izvuci pricing sa website-a, analiziraj u Google Sheet sa comparison, generiraj executive summary dokument, stvori marketing campaign strategy, pošalji svim stakeholderima"

170. "End-to-end invoice processing: pretraži Drive folder 'Invoices January 2026', za svaki PDF pokreni OCR extraction, validiraj podatke, detektiraj duplikate, spremi u Expense tracking, ažuriraj master Sheet sa sumama, generiraj monthly report document, pošalji accountantu na approval"
```

**Očekivano:** Orchestrator razbija u korake, executira serijski sa progress updates, resilient na failures

---

## Kako Testirati

### Setup:
1. Pokreni: `python main.py`
2. Copy/paste primjere jedan po jedan
3. Prati console output za logove

### Što Gledati:
- **Agent Selection**: Je li Orchestrator odabrao pravog agenta?
- **Tool Calls**: Koje toolove agent poziva?
- **Error Handling**: Kako agent reagira na errors?
- **Multi-Step**: Prolaze li rezultati između agenata?
- **Croatian Support**: Preservira li karaktere, format?
- **Human-in-Loop**: Traži li approval gdje treba?
- **Performance**: Je li brzo? Ima li rate limit errors?

### Prioriteti:
1. **Prvo testiraj: 1-40** (Single-agent basics) - Mora sve proći!
2. **Onda testiraj: 41-65** (2-agent workflows) - Core functionality
3. **Zatim testiraj: 66-84** (3+ agent workflows) - Complex scenarios
4. **Poslije testiraj: 85-122** (Edge cases) - Resilience
5. **Na kraju testiraj: 132-170** (Human-in-loop + stress tests) - Robustness

---

## Očekivani Outputs

### Single-Agent Success:
```
USER: Pokaži mi zadnjih 5 emailova
ORCHESTRATOR: → Delegate to Mailer
MAILER: [Calls get_gmail_messages with limit=5]
MAILER: Shows 5 emails with subjects, senders, dates
✅ SUCCESS
```

### Multi-Agent Success:
```
USER: Istraži AI trends i pošalji rezultate marko@example.com
ORCHESTRATOR: → Step 1: Researcher
RESEARCHER: [Web search for "AI trends 2026"]
RESEARCHER: Returns research summary
ORCHESTRATOR: → Step 2: Mailer (passes research results)
MAILER: [Calls send_email with research content]
✅ SUCCESS - email sent with research
```

### Error Handling:
```
USER: Pošalji email na "marko_bez_at"
ORCHESTRATOR: → Delegate to Mailer
MAILER: Validation error - invalid email format
MAILER: "Email adresa mora sadržavati @. Molim unesite ispravnu adresu."
❌ EXPECTED FAILURE - clear error message
```

---

## Kategorija 11: Fiskalizacija 2.0 (KRITIČNO!)

### 11.1 Osnovni Fiskalizacija Upiti
```
171. "Validiraj OIB 47034854402"
172. "Provjeri je li OIB 12345678901 ispravan"
173. "Izračunaj porez za neto iznos 1000 EUR sa stopom 25%"
174. "Koja je PDV stopa za uslugu postavljanja stolarije?"
175. "Pronađi KPD kod za uslugu 'montaža prozora'"
```

**Očekivano:** Fiskalni Pripremac validira OIB (Modul 11), izračunava porez, pretražuje KPD kodove

---

### 11.2 Kreiranje i Slanje Računa
```
176. "Kreiraj račun R-001/PP/NU za kupca OIB 12345678903, usluga montaža stolarije, iznos 1000 EUR"
177. "Fiskaliziraj račun: kupac Marko Horvat, OIB 98765432101, iznos 500 EUR, plaćanje gotovina"
178. "Napravi račun za uslugu postavljanja prozora, kupac iz kontakata 'Ana Kovač', iznos 2500 EUR"
179. "Kreiraj avansni račun za polog 30% na ukupnu ponudu od 10000 EUR"
180. "Storniraj račun R-001/PP/NU i kreiraj novi sa ispravnim iznosom"
```

**Očekivano:** Fiskalni pipeline (Pripremac → Validator → Executor), FINA komunikacija, JIR, QR kod

---

### 11.3 Fiskalizacija + Drugi Agenti (Workflow)
```
181. "Pronađi kontakt 'Marko Horvat' i kreiraj račun za 1000 EUR za uslugu montaže"
182. "Napravi račun iz cjenika u Google Sheets 'Cjenik 2026' za stavke: prozor 3x, vrata 2x, za kupca iz kontakata"
183. "Kreiraj račun, fiskaliziraj, pošalji PDF na email kupca, i dodaj termin ugradnje u kalendar za petak"
184. "Pronađi ponudu P-001 u Drive-u, pretvori u račun, fiskaliziraj i arhiviraj"
185. "Učitaj bankovni izvod, pronađi uplate bez računa, kreiraj račune za svaku"
```

**Očekivano:** Multi-agent workflow: Rolodex/Librarian/Analyst → Fiskalizacija → Mailer/Secretary

---

### 11.4 Fiskalizacija Error Handling
```
186. "Fiskaliziraj račun sa OIB-om 00000000000" (Nevažeći OIB - mora odbiti)
187. "Kreiraj račun sa negativnim iznosom -500 EUR" (Invalid - mora odbiti)
188. "Fiskaliziraj isti račun R-001/PP/NU dvaput" (Idempotency test - mora vratiti isti JIR)
189. "Kreiraj račun bez OIB-a kupca za B2B transakciju" (Mora tražiti OIB)
190. "Fiskaliziraj račun kada je FINA nedostupna" (Retry queue test)
```

**Očekivano:** Jasne error poruke, idempotency, retry mehanizam za FINA greške

---

### 11.5 Fiskalizacija Izvještaji
```
191. "Pokaži mi sve fiskalizirane račune za danas"
192. "Koliki je ukupni promet za siječanj 2026?"
193. "Koji računi su u retry queue-u?"
194. "Generiraj PDF za račun sa JIR-om XYZ123"
195. "Pokaži mi QR kod za račun R-005/PP/NU"
```

**Očekivano:** Pregled iz ledgera, generiranje PDF-a, QR kodovi

---

## Kategorija 12: Socrates/Classroom Mode

### 12.1 Ulazak u Classroom
```
196. "Pokreni Sokratovu metodu"
197. "Uđi u filozofski razgovor"
198. "Želim učiti kroz Sokratov dijalog"
199. "Classroom mode"
200. "Razgovarajmo filozofski"
```

**Očekivano:** Master Router detektira intent, prebacuje u CLASSROOM mode, Socrates agent preuzima

---

### 12.2 Filozofske Teme
```
201. "Što je pravda?"
202. "Objasni mi Platonovu alegoriju špilje"
203. "Kako stoici gledaju na sreću?"
204. "Koja je razlika između etike i morala?"
205. "Što bi Aristotel rekao o umjetnoj inteligenciji?"
```

**Očekivano:** Socrates koristi Sokratovu metodu (pitanja, ne odgovori), duboko razmišljanje

---

### 12.3 Izlazak iz Classroom
```
206. "Izađi iz classroom moda"
207. "Vrati se u normalni način rada"
208. "Dosta filozofije, trebam pomoć s emailom"
209. "/leave"
210. "Prekini Sokratov dijalog"
```

**Očekivano:** Vraća se u LEGACY mode, Master Router preuzima

---

## Kategorija 13: Kompletni Poslovni Workflowi (End-to-End)

### 13.1 Stolarija/Zanatstvo Workflow
```
211. "Pronađi kontakt 'Pero Perić', napravi ponudu za 3 prozora i 2 vrata iz cjenika, pošalji na email"
212. "Pretvori ponudu P-001 u račun, fiskaliziraj, pošalji kupcu, dodaj termin ugradnje za sljedeći utorak u 9h"
213. "Učitaj sve ponude iz Drive foldera 'Ponude 2026', pronađi one starije od 30 dana bez odgovora, pošalji reminder email"
214. "Kreiraj tjedni izvještaj: svi računi, ukupni promet, nadolazeći termini, pošalji mi na email"
215. "Pronađi sve kupce koji su platili avans ali nemaju zakazan termin ugradnje, kreiraj listu i pošalji podsjetnik"
```

**Očekivano:** Kompleksni multi-agent workflow s 4+ agenata, human-in-the-loop za potvrdu

---

### 13.2 Dnevne Operacije
```
216. "Što mi je danas na rasporedu? Pokaži sastanke, zadatke i račune za naplatu"
217. "Pošalji jutarnji briefing: nepročitani emailovi, današnji kalendar, overdue tasks"
218. "Kreiraj dnevni izvještaj i spremi u Drive folder 'Izvještaji/2026/01'"
219. "Pronađi sve nenaplaćene račune starije od 30 dana i pošalji opomene"
220. "Analiziraj troškove za prošli mjesec, usporedi s budgetom, napravi report"
```

**Očekivano:** Orchestrator koordinira više agenata, agregira rezultate

---

### 13.3 CRM Workflow (Kontakti + Prodaja)
```
221. "Dodaj novog klijenta: Tvrtka ABC d.o.o., OIB 11122233344, kontakt osoba Ivan Ivić, email ivan@abc.hr"
222. "Pronađi sve klijente iz Zagreba koji nisu imali narudžbu zadnjih 6 mjeseci"
223. "Za svakog klijenta bez emaila, pronađi email na webu i ažuriraj kontakt"
224. "Kreiraj email kampanju za sve klijente: Nova godina, popust 10%, pošalji personalizirano"
225. "Analiziraj koji klijenti donose najviše prihoda, kreiraj VIP listu"
```

**Očekivano:** Rolodex + Analyst + Mailer koordinacija, batch operacije

---

### 13.4 Financijski Workflow
```
226. "Učitaj bankovni izvod iz Drive-a, pronađi uplate, poveži s računima"
227. "Koji računi su plaćeni a koji ne? Generiraj izvještaj"
228. "Izračunaj PDV za ovaj mjesec: svi izdani računi, svi primljeni računi"
229. "Kreiraj cashflow projekciju za sljedeća 3 mjeseca na temelju ponuda i ugovora"
230. "Pronađi sve troškove bez računa i označi ih za provjeru"
```

**Očekivano:** Analyst + Expense + Librarian, financijski izračuni

---

## Kategorija 14: Multi-Tenant Priprema (Budući Testovi)

### 14.1 Izolacija Korisnika
```
231. "Pokaži račune za korisnika A" (ne smije vidjeti račune korisnika B)
232. "Pristupi Drive-u korisnika koji nema OAuth token" (mora tražiti autorizaciju)
233. "Koristi certifikat korisnika X za fiskalizaciju" (izolacija certifikata)
```

**Očekivano:** Podaci su izolirani po API ključu/korisniku

---

### 14.2 Rate Limiting
```
234. "Pošalji 100 upita u 1 minuti" (rate limit test)
235. "Korisnik na FREE planu pokušava batch operaciju" (limit po planu)
236. "Korisnik je prešao mjesečni limit upita" (graceful degradation)
```

**Očekivano:** Rate limiting po korisniku, jasne poruke o limitima

---

## Napomene

- Zamijeni `marko@example.com` sa stvarnim email adresama gdje treba
- Zamijeni `contact_001`, `task_001` sa stvarnim ID-evima iz Firestore-a
- Za Scraper primjere, koristi stvarne Njuškalo URL-ove
- Za Expense OCR, pripremi nekoliko test receipt slika
- Marketing primjeri MORAJU pokazati approval workflow

**VAŽNO:** Nemoj pokretati Marketing kampanje (132-134) bez explicitnog approval-a!

---

## Ažurirani Prioriteti Testiranja

### FAZA 1: Osnove (PRVO OVO!)
```
Upiti: 1-40 (Single-agent)
Vrijeme: 1-2 dana
Cilj: Svaki agent mora raditi samostalno
```

### FAZA 2: Koordinacija
```
Upiti: 41-84 (Multi-agent workflows)
Vrijeme: 2-3 dana
Cilj: Orchestrator pravilno delegira i agregira
```

### FAZA 3: Fiskalizacija (KRITIČNO!)
```
Upiti: 171-195 (Fiskalizacija 2.0)
Vrijeme: 3-5 dana
Cilj: FINA komunikacija, JIR, QR - sve mora raditi
```

### FAZA 4: Edge Cases
```
Upiti: 85-140 (Error handling, Croatian support)
Vrijeme: 2-3 dana
Cilj: Sustav se oporavlja od grešaka
```

### FAZA 5: Poslovni Workflowi
```
Upiti: 211-230 (End-to-end business)
Vrijeme: 3-5 dana
Cilj: Kompleksni scenariji za stvarno korištenje
```

### FAZA 6: Classroom (Bonus)
```
Upiti: 196-210 (Socrates)
Vrijeme: 1 dan
Cilj: Filozofski dijalog radi (nice-to-have)
```

---

## Checklist za Testiranje

### Prije Pokretanja:
- [ ] OAuth token aktivan (provjeri `token.json`)
- [ ] FINA certifikat učitan (za fiskalizaciju)
- [ ] Firestore pristup konfiguriran
- [ ] Google API-ji omogućeni u Cloud Console
- [ ] Test kontakti dodani u Google Contacts
- [ ] Test sheet kreiran ("Cjenik 2026")
- [ ] Test folder u Drive-u ("Test Documents")

### Tijekom Testiranja:
- [ ] Zapisuj sve greške u log
- [ ] Screenshot-aj neočekivano ponašanje
- [ ] Mjeri vrijeme odgovora za spore upite
- [ ] Provjeri Croatian characters (č, ć, đ, š, ž)

### Nakon Testiranja:
- [ ] Dokumentiraj što radi / što ne radi
- [ ] Prioritiziraj bugove (Critical/High/Medium/Low)
- [ ] Kreiraj GitHub issues za bugove

---

Sretno sa testiranjem! 🚀

---

*Dokument ažuriran: 24.01.2026*
*Verzija: 2.0 - Dodana Fiskalizacija, Socrates, Business Workflows*
