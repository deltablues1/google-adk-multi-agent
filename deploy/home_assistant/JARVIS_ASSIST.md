# Jarvis kao Home Assistant glasovni agent

## Zašto integracija, a ne postavka

Home Assistant ne može uputiti Assist na proizvoljni HTTP servis. Ugrađene su
samo OpenAI, Anthropic i Google integracije, a svaka od njih bila bi *drugi*
asistent — bez Jarvisovih alata (Gmail, kalendar, TV, MQTT, senzori i njihova
povijest, raspored). Ova integracija tu rupu zatvara: prosljeđuje ono što je
korisnik rekao na Jarvisov web API i vraća njegov odgovor Assistu.

```
mobitel / zvučnik → HA Assist → ova integracija → POST /api/chat na Jarvisa
                                                → orkestrator i alati
                              ← odgovor ←
```

## Preduvjet: Jarvis mora biti dostupan s HA-a

Jarvisov web servis po zadanom sluša samo na `127.0.0.1`, pa ga Home Assistant s
druge adrese ne vidi. U `.env` na Jarvis Pi-u:

```
WEB_HOST=0.0.0.0
WEB_PORT=8000
```

i u `adk-web.service` ukloniti `--host 127.0.0.1 --port 8000` iz `ExecStart`
(bez tih zastavica `run_web.py` čita `WEB_HOST` i `WEB_PORT` iz okoline, pa se
ubuduće mijenja u `.env` bez roota).

`API_TOKEN` mora biti postavljen — profil `rpi-home` ga ionako zahtijeva. Bez
njega bi Jarvisov API bio otvoren svakome na kućnoj mreži.

Provjera s bilo kojeg računala na mreži:

```bash
curl -H "Authorization: Bearer <API_TOKEN>" http://192.168.100.105:8000/api/status
```

## Instalacija na Home Assistant

1. Kopiraj mapu `custom_components/jarvis/` u `/config/custom_components/` na HA-u
   (preko *File editor*, *Studio Code Server* ili Sambe)
2. Restart Home Assistanta
3. **Settings → Devices & Services → Add Integration → Jarvis**
4. Upiši adresu (`http://192.168.100.105:8000`) i `API_TOKEN`

Config flow prije spremanja pozove `/api/status`, pa se pogrešna adresa ili
token vide odmah, a ne tek kad nešto pitaš.

## Uključivanje u Assist

**Settings → Voice assistants → Add assistant** → za *Conversation agent*
odaberi **Jarvis**. STT i TTS ostaju oni koje već koristiš.

Na mobitelu: Companion app → Settings → Companion app → Assist → odaberi taj
pipeline.

## Kako provjeriti da odgovara baš Jarvis

Pitaj nešto što HA-ov ugrađeni Assist ne može znati:

> „koja je danas bila najviša vanjska temperatura"

Ugrađeni Assist čita samo trenutna stanja entiteta; povijesnu statistiku ima
jedino Jarvis (`home_climate_history`).

## Detalji koje je dobro znati

- **Kontinuitet razgovora**: HA-ov `conversation_id` se pamti i preslikava na
  Jarvisov `session_id`, pa „a ugasi i ono drugo" ima na što se osloniti.
- **Vremensko ograničenje** je 90 s jer zahtjev koji pokrene lanac alata
  legitimno zna trajati pola minute. Kraće bi izgledalo kao pokvaren agent.
- **Čišćenje za govor**: iz odgovora se prije izgovaranja miču markdown znakovi
  i emoji — Jarvis njima ukrašava chat, ali izgovoreni su šum.
- **Greške se ne prešućuju**: istek vremena, odbijen token i nedostupan servis
  vraćaju različite poruke, da se iz odgovora vidi što je zapravo palo.
