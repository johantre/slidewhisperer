# SlideWhisperer 🐴

Automatically convert a Google Drive folder of PDF slides into an interactive HTML study guide, powered by the Gemini API.

---

## Requirements

- Python 3.11+
- A Google Cloud project with:
  - **Gemini API** enabled
  - **Google Drive API** enabled
- A Cloudflare account with a domain (for public access via tunnel)

---

## 1. Google Gemini API key

1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Create a new API key
3. Save the key — you'll need it in `.env`

---

## 2. Google Service Account (Drive access)

The app reads PDF files from a shared Google Drive folder via a service account (server-to-server, no browser login required).

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → **IAM & Admin** → **Service Accounts**
2. Click **Create Service Account** → give it a name (e.g. `slidewhisperer-drive`)
3. Click on the created service account → **Keys** tab → **Add Key** → **JSON**
4. Download the JSON file and save it as `service_account.json` in the project folder
5. Note the **email address** of the service account (e.g. `slidewhisperer-drive@your-project.iam.gserviceaccount.com`)

**Sharing a Drive folder with the service account:**

For each Drive folder you want to process:
1. Right-click the folder in Google Drive → **Share**
2. Add the service account email address as a **Viewer**

---

## 3. Installation

```bash
git clone https://github.com/johantre/slidewhisperer.git
cd slidewhisperer

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Create secrets (one-time, never in git):**

```bash
cp .env.example .env
# Fill in your Gemini API key and other values
nano .env
```

Also place the downloaded service account JSON file in the project folder:
```bash
mv ~/Downloads/your-project-xxxx.json service_account.json
```

---

## 4. Running locally

```bash
source .venv/bin/activate
python3 app.py
```

App is available at `http://localhost:5001`

---

## 5. Production as a systemd service

```bash
sudo cp slidewhisperer.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable slidewhisperer
sudo systemctl start slidewhisperer
```

Follow logs:
```bash
sudo journalctl -u slidewhisperer -f
```

---

## 6. Cloudflare Tunnel (public access)

Makes the app accessible via your own domain (e.g. `slidewhisperer.yourdomain.com`) without opening ports.

### One-time installation of cloudflared

```bash
# Debian/Ubuntu
curl -L https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt update && sudo apt install cloudflared
```

### Creating a tunnel (via Cloudflare dashboard)

1. Go to [Cloudflare Zero Trust](https://one.dash.cloudflare.com/) → **Networks** → **Tunnels**
2. Click **Create a tunnel** → give it a name (e.g. `my-server`)
3. Go to **Public Hostnames** → **Add a public hostname**:
   - Subdomain: `slidewhisperer`
   - Domain: `yourdomain.com`
   - Service: `http://localhost:5001`
4. Copy the tunnel token

### Installing the tunnel as a service

If a cloudflared service is already running (e.g. for other apps on the same server), simply add the extra hostname to the existing tunnel via the dashboard. No new service needed.

If no service exists yet:
```bash
sudo cloudflared service install <YOUR_TUNNEL_TOKEN>
sudo systemctl start cloudflared
```

### Securing access with Google SSO (optional but recommended)

1. Go to Zero Trust → **Access** → **Applications** → **Add an application**
2. Choose **Self-hosted**
3. Set the URL to `slidewhisperer.yourdomain.com`
4. Add a **Google** identity provider and define who gets access (e.g. specific email addresses)

---

## 7. Deploying updates

```bash
cd /home/your-user/slidewhisperer
git pull
sudo systemctl restart slidewhisperer
```

Secrets (`.env` and `service_account.json`) are left untouched — they are not in git.

---

## File structure

```
slidewhisperer/
├── app.py                    # Flask application
├── templates/
│   └── index.html            # Web UI
├── prompts/
│   ├── system_prompt_html.md     # HTML layout & structure instructions (in git)
│   └── system_prompt_content.md  # Summarisation style instructions (in git)
├── requirements.txt
├── slidewhisperer.service    # systemd unit file
├── .env.example              # Template for .env (no real values)
├── .gitignore
│
├── .env                      # ← NOT in git (contains API key)
└── service_account.json      # ← NOT in git (contains credentials)
```

---

## Sensitive files

| File | In git? | Notes |
|---|---|---|
| `.env` | ❌ Never | Contains Gemini API key |
| `service_account.json` | ❌ Never | Google Drive credentials |
| `cache/` | ❌ Never | Downloaded PDFs |
| `output/` | ❌ Never | Generated HTML + PDFs |
| `prompts/system_prompt_html.md` | ✅ Yes | HTML layout instructions, no secrets |
| `prompts/system_prompt_content.md` | ✅ Yes | Summarisation instructions, no secrets |

---

## Future roadmap

SlideWhisperer is a working single-user tool. Below are known limitations and areas for future improvement:

### Authentication & multi-user
- No built-in login or user accounts — access control currently relies entirely on Cloudflare Access (Google SSO)
- No per-user isolation of results or prompts
- No rate limiting on generation requests

### Infrastructure & deployment
- No CI/CD pipeline — updates are deployed manually via `git pull` + `systemctl restart`
- No self-hosted runner or container setup (Docker/Compose)
- Single-server deployment only — no horizontal scaling

### Features
- PDF only — PPTX and other slide formats are not supported (slide-level deep links don't work outside PDF)
- No export to other formats (DOCX, Markdown)
- Prompt history is git-based and local — no cloud backup
