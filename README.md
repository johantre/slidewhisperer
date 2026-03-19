# SlideWhisperer 🐴

Zet een Google Drive map met PDF-slides automatisch om naar een interactief HTML-studieoverzicht, aangedreven door de Gemini API.

---

## Vereisten

- Python 3.11+
- Een Google Cloud project met:
  - **Gemini API** ingeschakeld
  - **Google Drive API** ingeschakeld
- Een Cloudflare account met een domein (voor publieke toegang via tunnel)

---

## 1. Google Gemini API key

1. Ga naar [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Maak een nieuwe API key aan
3. Bewaar de key — je hebt hem nodig in `.env`

---

## 2. Google Service Account (Drive-toegang)

De app leest PDF-bestanden uit een gedeelde Google Drive map via een service account (server-to-server, geen browserlogin nodig).

1. Ga naar [Google Cloud Console](https://console.cloud.google.com/) → **IAM & Admin** → **Service Accounts**
2. Klik **Create Service Account** → geef een naam (bijv. `slidewhisperer-drive`)
3. Klik op de aangemaakte service account → tabblad **Keys** → **Add Key** → **JSON**
4. Download het JSON-bestand en sla het op als `service_account.json` in de projectmap
5. Noteer het **e-mailadres** van het service account (bijv. `slidewhisperer-drive@jouw-project.iam.gserviceaccount.com`)

**Google Drive map delen met het service account:**

Voor elke Drive-map die je wil verwerken:
1. Rechtsklik op de map in Google Drive → **Delen**
2. Voeg het e-mailadres van het service account toe als **Viewer**

---

## 3. Installatie

```bash
git clone https://github.com/jouw-gebruiker/slidewhisperer.git
cd slidewhisperer

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Secrets aanmaken (eenmalig, nooit in git):**

```bash
cp .env.example .env
# Vul .env in met je Gemini API key en andere waarden
nano .env
```

Zet ook het gedownloade service account JSON-bestand in de projectmap:
```bash
mv ~/Downloads/jouw-project-xxxx.json service_account.json
```

---

## 4. Lokaal draaien

```bash
source .venv/bin/activate
python3 app.py
```

App is bereikbaar op `http://localhost:5001`

---

## 5. Productie als systemd service

```bash
sudo cp slidewhisperer.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable slidewhisperer
sudo systemctl start slidewhisperer
```

Logs volgen:
```bash
sudo journalctl -u slidewhisperer -f
```

---

## 6. Cloudflare Tunnel (publieke toegang)

Zodat de app bereikbaar is via een eigen domein (bijv. `slidewhisperer.jouwdomein.be`) zonder poorten open te zetten.

### Eenmalige installatie van cloudflared

```bash
# Debian/Ubuntu
curl -L https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt update && sudo apt install cloudflared
```

### Tunnel aanmaken (via Cloudflare dashboard)

1. Ga naar [Cloudflare Zero Trust](https://one.dash.cloudflare.com/) → **Networks** → **Tunnels**
2. Klik **Create a tunnel** → geef een naam (bijv. `mijn-server`)
3. Ga naar **Public Hostnames** → **Add a public hostname**:
   - Subdomain: `slidewhisperer`
   - Domain: `jouwdomein.be`
   - Service: `http://localhost:5001`
4. Kopieer de tunnel token

### Tunnel installeren als service

Als er al een cloudflared service draait (bijv. voor andere apps op dezelfde server), voeg dan enkel de extra hostname toe aan de bestaande tunnel via het dashboard. Geen nieuwe service nodig.

Als er nog geen service is:
```bash
sudo cloudflared service install <JOUW_TUNNEL_TOKEN>
sudo systemctl start cloudflared
```

### Toegang beveiligen met Google SSO (optioneel maar aanbevolen)

1. Ga naar Zero Trust → **Access** → **Applications** → **Add an application**
2. Kies **Self-hosted**
3. Stel de URL in op `slidewhisperer.jouwdomein.be`
4. Voeg een **Google** identity provider toe en definieer wie toegang mag krijgen (bijv. specifieke e-mailadressen)

---

## 7. Updates deployen

```bash
cd /home/jouw-gebruiker/slidewhisperer
git pull
sudo systemctl restart slidewhisperer
```

Secrets (`.env` en `service_account.json`) blijven onaangeroerd — die zitten niet in git.

---

## Bestandsstructuur

```
slidewhisperer/
├── app.py                    # Flask applicatie
├── templates/
│   └── index.html            # Web UI
├── prompts/
│   └── system_prompt.md      # Aanpasbare Gemini prompt (zit WEL in git)
├── requirements.txt
├── slidewhisperer.service    # systemd unit file
├── .env.example              # Template voor .env (geen echte waarden)
├── .gitignore
│
├── .env                      # ← NIET in git (bevat API key)
└── service_account.json      # ← NIET in git (bevat credentials)
```

---

## Gevoelige bestanden

| Bestand | In git? | Uitleg |
|---|---|---|
| `.env` | ❌ Nooit | Bevat Gemini API key |
| `service_account.json` | ❌ Nooit | Google Drive credentials |
| `cache/` | ❌ Nooit | Gedownloade PDFs |
| `output/` | ❌ Nooit | Gegenereerde HTML + PDFs |
| `prompts/system_prompt.md` | ✅ Ja | Prompt-tekst, geen secrets |
