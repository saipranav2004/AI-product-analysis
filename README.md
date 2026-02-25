# Baagundhaaa? 🌿

> *"Baagundhaaa?"* (బాగుందా?) means *"Is it good?"* in Telugu.

An AI-powered food label scanner built for Indian consumers. Scan any packaged food label and instantly get a health rating, ingredient analysis, FSSAI compliance check, and a healthier alternative — all in seconds.

**#Label_Samjhega_India**

---

## Features

### 🔍 Label Analysis
- 📷 **Scan** with your phone/webcam camera or **upload** an image
- ⭐ **Health rating 1–5 stars** using the Australian HSR system with category-aware scoring
- 📊 **Score breakdown** — individual points for energy, fat, sugar, sodium, protein, fibre
- 📸 **Confidence indicator** — AI tells you if it read the label clearly, partially, or poorly
- 🗓️ **Expiry date** extraction from the label

### 🧪 Ingredients
- ⚠️ **Harmful ingredient detection** — artificial colours, preservatives, sweeteners, trans fats, MSG and more
- 💡 **Ingredient info popups** — tap any flagged ingredient to learn what it is, why it's harmful, and which products commonly contain it
- 🚫 **FSSAI cross-reference** — flags ingredients banned or restricted by India's own food regulator (Potassium Bromate, Rhodamine B, Metanil Yellow etc.)
- ✅ **Positive nutrients** — highlights beneficial ingredients like whole grains, fibre, vitamins

### 🥗 Alternatives
- 🔄 **Same-brand variant** — checks if the same brand makes a healthier version first
- 🆕 **Different brand** — recommends the best alternative available in India (BigBasket, Amazon.in, DMart)
- Two-tab UI so users can pick whichever they prefer

### ⚡ Compare
- Side-by-side comparison of two products
- Full nutrient table with green/red highlights for better/worse values
- Clear winner declaration with star difference

### 📤 Share
- Share your result as a branded image card via WhatsApp, Instagram, or any platform
- Works natively on Android and iOS via Web Share API

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python · Flask |
| AI | Google Gemini 2.5 Flash |
| Web Search | googlesearch-python |
| Frontend | Vanilla JS · CSS (dark glassmorphism) |
| Fonts | Playfair Display · DM Sans |

---

## Setup

### 1. Clone and install

```bash
git clone <repo-url>
cd baagundhaaa
pip install -r requirements.txt
```

### 2. Configure environment

Copy `.env.example` to `.env` and fill in your keys:

```
GEMINI_API_KEY=your_gemini_api_key_here
SECRET_KEY=any_long_random_string_here
```

- Get a **free Gemini API key** at: https://aistudio.google.com/app/apikey  
  (Free tier: 1,000 requests/day — no credit card needed)
- Generate a **secret key**: `python -c "import secrets; print(secrets.token_hex(32))"`

### 3. Run

```bash
python app.py
```

Open: `http://localhost:8000`

---

## Deployment

### Gunicorn (recommended)

```bash
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

### Notes for production
- Set `SECRET_KEY` to a fixed value in `.env` — do not use a random one or sessions will break on restart
- The app stores uploaded images as temporary files in a system temp directory, scoped per user session — safe for concurrent users
- Temp files are automatically cleaned up by the OS; for long-running servers add a cron to purge `baagundhaaa_*` temp dirs periodically

---

## Project Structure

```
baagundhaaa/
├── app.py                    # Flask backend — routes, prompts, AI calls
├── requirements.txt
├── .env                      # Your keys (never commit this)
├── .env.example              # Template for .env
├── .gitignore
├── README.md
├── static/
│   ├── camera.js             # Browser camera capture with JPEG compression
│   └── styles.css            # Dark glassmorphism theme
└── templates/
    ├── layout.html           # Base template with navbar
    ├── landing.html          # Marketing home page (/)
    ├── index.html            # Scanner app page (/app)
    ├── scan.html             # Camera scan page
    ├── results.html          # Analysis results with gauge, chips, share
    ├── alternative.html      # Same-brand + different-brand alternatives
    ├── compare.html          # Side-by-side product comparison
    ├── how.html              # How it works page
    ├── faq.html              # FAQ with accordion
    └── about.html            # About page
```

---

## Pages

| Route | Description |
|-------|-------------|
| `/` | Landing / home page |
| `/app` | Main scanner — upload or go to camera |
| `/scan` | Live camera scan |
| `/capture` | POST — processes uploaded/captured image |
| `/process` | GET — finds healthier alternatives (called by JS) |
| `/alternative` | Alternative suggestions page |
| `/compare` | Compare two products |
| `/compare/analyse` | POST — analyses both products (called by JS) |
| `/how-it-works` | How the rating system works |
| `/faq` | Frequently asked questions |
| `/about` | About the project |

---

## How the Rating Works

The AI uses a **category-aware** version of the Australian Health Star Rating (HSR) system:

1. **Detects category** — beverage, snack, dairy, cereal, instant meal, condiment, staple, etc.
2. **Applies the right thresholds** — beverages are scored per 100ml; snacks don't get penalised for lacking protein
3. **Calculates baseline points** — energy, saturated fat, sugars, sodium (higher = worse)
4. **Calculates modifying points** — protein, fibre, FVNL% (higher = better)
5. **Normalises to 1–5 stars** — ★5 is healthiest, ★1 is least healthy

---

## Privacy

- 📵 No photos are stored permanently — images are saved to a temp file scoped to your session and discarded
- 🔕 No accounts, no tracking, no cookies beyond the session token
- 📢 No ads, ever

---

Open source — contributions welcome! 🇮🇳