from flask import Flask, render_template, request, jsonify, session
import os
import base64
import json
import re
import uuid
import tempfile
from googlesearch import search
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', os.urandom(24))
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
# Temp dir for per-user image storage
TEMP_DIR = tempfile.mkdtemp(prefix='baagundhaaa_')

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("CRITICAL: GEMINI_API_KEY not found. Check your .env file.")
else:
    genai.configure(api_key=api_key)

model = genai.GenerativeModel('gemini-2.5-flash')

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])


# ── Full HSR scoring prompt ────────────────────────────────────────────────────
HSR_ANALYSIS_PROMPT = """
You are a certified food label analyst. Carefully examine this food product label image.

STEP 1 — DETECT CATEGORY
First, identify the product category from the label. Choose ONE from:
- "beverage" (juices, soft drinks, water, tea, coffee, energy drinks, milk drinks)
- "dairy" (milk, yogurt, cheese, paneer, butter, cream)
- "snack" (chips, biscuits, cookies, namkeen, crackers, wafers, chocolates, candy)
- "cereal" (breakfast cereals, oats, muesli, granola)
- "instant_meal" (instant noodles, pasta, ready meals, soups)
- "condiment" (sauces, ketchup, pickles, jams, spreads, dressings)
- "staple" (rice, flour, lentils, whole grains, bread)
- "health_product" (protein powder, nutrition bars, health drinks, supplements)
- "fruit_vegetable" (packaged fruits, vegetable products, fruit purees)
- "other" (anything that does not fit above)

STEP 2 — READ NUTRITION VALUES
Extract values shown on the label per 100g (solids) or per 100ml (beverages/liquids):
- Energy (kJ) — if only kcal shown, multiply by 4.18
- Saturated Fat (g)
- Total Sugars (g)
- Sodium (mg) — if only Salt shown, divide by 2.5
- Protein (g) — use 0 if not listed (common for snacks/confectionery)
- Dietary Fibre (g) — use 0 if not listed
- Fruit/Vegetable/Nut/Legume % — use 0 if not stated

STEP 3 — APPLY CATEGORY-APPROPRIATE SCORING
Use the correct thresholds based on category:

FOR BEVERAGES (per 100ml):
  Energy: 0pts=≤33kJ, +1pt per 6.7kJ, max 10pts
  Sat Fat: 0pts=≤0.1g, +1pt per 0.14g, max 10pts
  Sugars:  0pts=≤0.5g, +1pt per 2.25g, max 10pts
  Sodium:  0pts=≤30mg, +1pt per 90mg, max 10pts
  Protein modifying: NOT applied for beverages (use 0)
  Fibre modifying: NOT applied for beverages (use 0)

FOR DAIRY (per 100g or 100ml):
  Use solid thresholds for solid dairy, liquid thresholds for liquid dairy.
  Protein IS counted as a modifying point.
  Calcium-rich products get a bonus — add 1 modifying point if calcium > 100mg/100g.

FOR SNACKS / CONFECTIONERY (per 100g):
  Energy: 0pts=≤335kJ, +1pt per 67kJ, max 10pts
  Sat Fat: 0pts=≤1g, +1pt per 1.4g, max 10pts
  Sugars:  0pts=≤1g, +1pt per 4.5g, max 10pts
  Sodium:  0pts=≤90mg, +1pt per 270mg, max 10pts
  Protein: apply only if > 5g/100g (snacks rarely have significant protein)
  Fibre: apply normally — rewards whole grain snacks

FOR ALL OTHER SOLIDS (per 100g):
  Energy: 0pts=≤335kJ, +1pt per 67kJ, max 10pts
  Sat Fat: 0pts=≤1g, +1pt per 1.4g, max 10pts
  Sugars:  0pts=≤1g, +1pt per 4.5g, max 10pts
  Sodium:  0pts=≤90mg, +1pt per 270mg, max 10pts
  Protein: 0pts=≤1g, +1pt per 1.4g, max 5pts
  Fibre:   0pts=≤0.9g, +1pt per 1g, max 5pts
  FVNL%:   0pts=≤40%, +1pt per 10%, max 8pts

Baseline = Energy + Sat Fat + Sugars + Sodium pts (max 40)
Modifying = Protein + Fibre + FVNL pts (apply only what is relevant for category)
Final Rating = normalize (Baseline minus Modifying) to a 1–5 scale. Round to nearest 0.5.
★5 = healthiest, ★1 = least healthy. Never return 0 — minimum is 0.5.

STEP 4 — INGREDIENTS ANALYSIS
Scan the full ingredients list carefully:

HSR Bad ingredients:
  Artificial colours: E102 (Tartrazine), E104, E110 (Sunset Yellow), E122, E124, E129, E133, E142, E151, E155
  Preservatives: E211 (Sodium Benzoate), E212, E213, E220, E221, E222, E223, E224, E249, E250, E251, E252
  Artificial sweeteners: Aspartame (E951), Saccharin (E954), Acesulfame-K (E950), Sucralose (E955), Cyclamate (E952)
  Trans fats: Hydrogenated oil, Partially hydrogenated oil, Vanaspati
  Other: High-fructose corn syrup, MSG (E621), TBHQ (E319), BHA (E320), BHT (E321), Carrageenan (E407)

FSSAI (India) restricted/banned additives — flag these separately as they are specifically restricted for Indian consumers:
  - Potassium Bromate (E924) — banned in India for use in bread/flour
  - Rhodamine B — banned food colourant found in street food/snacks
  - Metanil Yellow (E105) — banned artificial colour in India
  - Argemone Oil — toxic adulterant banned in India
  - Brominated Vegetable Oil (BVO) — restricted in India
  - Coal Tar dyes — banned in India
  - Any additive listed as "not permitted" under FSSAI regulations

Good ingredients:
  Whole grains, oats, millets (ragi, jowar, bajra), nuts, seeds, legumes,
  natural fibre, vitamins (A, B, C, D, E, K), minerals (calcium, iron, zinc),
  probiotics, prebiotics, omega-3, antioxidants, natural fruit/vegetable content.

List only ingredients actually visible on this label. Do not guess or invent.

STEP 5 — EXPIRY DATE
Find Best Before / Use By / Expiry / MFG date on the label. Return it or "Not visible".

STEP 6 — READING CONFIDENCE
Assess how clearly you could read this label:
- "high" = nutrition table and ingredients list fully visible and readable
- "medium" = partially visible, some values estimated or inferred
- "low" = label is blurry, angled, poorly lit, or mostly unreadable — results may be inaccurate

OUTPUT — Reply ONLY in this exact JSON with no markdown, no extra text:
{
  "category": "<one of the category strings from Step 1>",
  "rating": "<number 0.5 to 5, nearest 0.5>",
  "confidence": "<high|medium|low>",
  "score_breakdown": {
    "energy_pts": <number>,
    "satfat_pts": <number>,
    "sugar_pts": <number>,
    "sodium_pts": <number>,
    "protein_pts": <number>,
    "fibre_pts": <number>,
    "fvnl_pts": <number>,
    "baseline": <number>,
    "modifying": <number>
  },
  "good_ingredients": ["<ingredient>"],
  "bad_ingredients": ["<ingredient>"],
  "fssai_flags": ["<FSSAI-restricted ingredient if found, else empty list>"],
  "reason": "<2-3 sentences on key health concerns or positives, mention category context — in English>",
  "reason_hi": "<same summary translated into simple Hindi (Devanagari script) — easy to understand for a common Indian consumer>",
  "reason_te": "<same summary translated into simple Telugu (Telugu script) — easy to understand for a common Indian consumer>",
  "expiry": "<date or Not visible>"
}
""".strip()

ALTERNATIVE_PROMPT_TEMPLATE = """
You are a nutrition expert helping Indian consumers find healthier food choices.

The scanned product is: {product_name}
The brand of the scanned product is: {brand_name}

Web search results:
{search_results}

Your task — ALWAYS provide TWO recommendations:

RECOMMENDATION 1 — SAME BRAND VARIANT:
Check if "{brand_name}" makes a healthier variant of "{product_name}".
Examples: whole wheat, low-sugar, baked instead of fried, lite/light, multigrain, high-fibre version.
If a real same-brand variant exists, name it specifically.
If absolutely no same-brand variant exists, set same_brand_name to null and same_brand_reason to "No healthier variant available from this brand."

RECOMMENDATION 2 — DIFFERENT BRAND:
Identify the single BEST alternative brand product for "{product_name}" available in India
(Amazon.in, BigBasket, DMart, Flipkart, health food stores).
Must be a real, named commercial product — no home-made options.
Explain specific nutritional advantages (lower sugar, no trans fat, higher fibre, etc.).

Reply ONLY in this exact JSON format with no markdown, no extra text:
{{
  "same_brand_name": "<Brand — Healthier Variant Name, or null if none exists>",
  "same_brand_reason": "<why this variant is healthier, or explanation if none exists>",
  "same_brand_buy": "<where to buy in India>",
  "alt_brand_name": "<Different Brand — Product Name>",
  "alt_brand_reason": "<2-3 sentences on specific nutritional advantages>",
  "alt_brand_buy": "<where to buy in India>"
}}
""".strip()


def _session_key():
    """Return a unique key for this user session, creating one if needed."""
    if 'uid' not in session:
        session['uid'] = str(uuid.uuid4())
    return session['uid']


def save_user_image(image_data, mime_type, category=None):
    """Save image bytes to a temp file scoped to this user session."""
    uid = _session_key()
    path = os.path.join(TEMP_DIR, uid + '.bin')
    meta_path = os.path.join(TEMP_DIR, uid + '.json')
    with open(path, 'wb') as f:
        f.write(image_data)
    with open(meta_path, 'w') as f:
        json.dump({'mime': mime_type, 'category': category}, f)


def load_user_image():
    """Load image bytes for this user session. Returns (data, mime, category) or (None,None,None)."""
    uid = session.get('uid')
    if not uid:
        return None, None, None
    path = os.path.join(TEMP_DIR, uid + '.bin')
    meta_path = os.path.join(TEMP_DIR, uid + '.json')
    if not os.path.exists(path):
        return None, None, None
    with open(path, 'rb') as f:
        data = f.read()
    meta = {}
    if os.path.exists(meta_path):
        with open(meta_path, 'r') as f:
            meta = json.load(f)
    return data, meta.get('mime', 'image/jpeg'), meta.get('category')


def clean_json_response(text):
    try:
        text = re.sub(r'```(?:json)?', '', text).strip().strip('`')
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            content = json_match.group()
            content = content.replace("None", "null")
            return json.loads(content)
        return json.loads(text)
    except Exception as e:
        print(f"JSON Parsing Error: {e}\nRaw: {text[:300]}")
        return None


def get_numeric_rating(rating_str):
    try:
        rating_str = str(rating_str).strip()
        if '/' in rating_str:
            return float(rating_str.split('/')[0])
        m = re.search(r'[\d.]+', rating_str)
        if m:
            return float(m.group())
    except Exception:
        pass
    return None


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route('/')
def landing():
    return render_template('landing.html')

@app.route('/app')
def main_page():
    return render_template('index.html', title="Scan Your Label", subtitle="#Label_Samjhega_India", error="")

@app.route('/scan')
def scan_page():
    return render_template('scan.html', title="Scan Label", subtitle="Point your camera at the nutrition label")

@app.route('/faq')
def faq_page():
    return render_template('faq.html', title="FAQ", subtitle="Frequently asked questions")

@app.route('/about')
def about_page():
    return render_template('about.html', title="About", subtitle="Our mission")

@app.route('/how-it-works')
def how_page():
    return render_template('how.html', title="How It Works", subtitle="Understanding your results")


@app.route('/capture', methods=['POST'])
def capture_image():
    try:
        if 'file' in request.files:
            file = request.files['file']
            if not file or file.filename == '':
                return render_template('index.html', title="Scan Your Label", subtitle="#Label_Samjhega_India",
                                       error="No file selected. Please choose an image.")
            image_data = file.read()
            mime_type = 'image/jpeg' if file.filename.lower().endswith(('.jpg', '.jpeg')) else 'image/png'

        elif 'image_data' in request.form:
            image_data_url = request.form['image_data']
            if ',' not in image_data_url:
                return render_template('index.html', title="Scan Your Label", subtitle="#Label_Samjhega_India",
                                       error="Invalid image data. Please try again.")
            _, encoded = image_data_url.split(',', 1)
            image_data = base64.b64decode(encoded)
            mime_type = 'image/jpeg'
        else:
            return render_template('index.html', title="Scan Your Label", subtitle="#Label_Samjhega_India",
                                   error="No image received. Please try again.")

        # Save image scoped to this user's session (safe for concurrent users)
        save_user_image(image_data, mime_type)

        picture = {'mime_type': mime_type, 'data': image_data}
        response = model.generate_content([HSR_ANALYSIS_PROMPT, picture])
        result = clean_json_response(response.text)

        if not result:
            result = {}

        result.setdefault('rating', 'N/A')
        result.setdefault('confidence', 'medium')
        result.setdefault('reason_hi', '')
        result.setdefault('reason_te', '')
        # Cache category with image for faster /process
        save_user_image(image_data, mime_type, category=result.get('category', 'other'))
        result.setdefault('reason', 'Unable to fully analyze this label.')
        result.setdefault('expiry', 'Not visible')
        result.setdefault('good_ingredients', [])
        result.setdefault('bad_ingredients', [])
        result.setdefault('fssai_flags', [])
        result.setdefault('score_breakdown', {})

        numeric_rating = get_numeric_rating(result['rating'])
        show_alternative = numeric_rating is not None and numeric_rating < 5

        return render_template('results.html',
                               title="Your Results",
                               subtitle="",
                               response=result,
                               show_alternative=show_alternative)

    except Exception as e:
        print(f"Capture error: {e}")
        return render_template('index.html', title="Scan Your Label", subtitle="#Label_Samjhega_India",
                               error=f"Analysis failed: {str(e)}")


@app.route('/process', methods=['GET'])
def process_data():
    image_data, mime_type, cached_category = load_user_image()

    if not image_data:
        return jsonify({"alt_brand_name": "No image found",
                        "alt_brand_reason": "Please go back and scan a product first.",
                        "alt_brand_buy": "",
                        "same_brand_name": None,
                        "same_brand_reason": "",
                        "same_brand_buy": ""})
    try:
        picture = {'mime_type': mime_type, 'data': image_data}

        # Use cached category if available, else re-identify (saves one AI call)
        if cached_category and cached_category != 'other':
            product_name = cached_category.replace('_', ' ')
            # Still need brand — quick single-field call
            brand_resp = model.generate_content([
                "Look at this food product label. What is the brand name printed on it? "
                "Reply with ONLY the brand name — nothing else. If not visible, reply: Unknown",
                picture
            ])
            brand_name = brand_resp.text.strip().strip('"').strip("'")
        else:
            id_prompt = (
                "Look at this food product label. Reply ONLY in this exact JSON format with no extra text, no markdown: "
                '{"product_type": "<2-4 words for product category e.g. instant noodles, potato chips>", '
                '"brand": "<brand name as printed on label, or Unknown if not visible>"}'
            )
            id_resp = model.generate_content([id_prompt, picture])
            id_data = clean_json_response(id_resp.text) or {}
            product_name = id_data.get('product_type', 'food product').strip().strip('"')
            brand_name   = id_data.get('brand', 'Unknown').strip().strip('"')
        print(f"Product: {product_name} | Brand: {brand_name}")

        # Search 1: same brand healthier variant
        same_brand_results = ""
        if brand_name and brand_name.lower() != 'unknown':
            q1 = f"{brand_name} healthier variant {product_name} India"
            r1 = list(search(q1, num_results=3, advanced=True))
            for r in r1:
                try: same_brand_results += f"Title: {r.title}\nSnippet: {r.description}\nURL: {r.url}\n\n"
                except: same_brand_results += str(r) + "\n\n"

        # Search 2: best alternative brand in India
        q2 = f"healthiest {product_name} brand India nutritious"
        r2 = list(search(q2, num_results=4, advanced=True))
        alt_results = ""
        for r in r2:
            try: alt_results += f"Title: {r.title}\nSnippet: {r.description}\nURL: {r.url}\n\n"
            except: alt_results += str(r) + "\n\n"

        results_text = same_brand_results + alt_results

        prompt = ALTERNATIVE_PROMPT_TEMPLATE.format(
            product_name=product_name,
            brand_name=brand_name,
            search_results=results_text
        )

        rec = model.generate_content(prompt)
        data = clean_json_response(rec.text)

        if not data:
            data = {}

        data.setdefault('same_brand_name', None)
        data.setdefault('same_brand_reason', 'No healthier variant found from this brand.')
        data.setdefault('same_brand_buy', 'Check brand website')
        data.setdefault('alt_brand_name', 'Not found')
        data.setdefault('alt_brand_reason', 'Could not determine a specific alternative at this time.')
        data.setdefault('alt_brand_buy', 'Check BigBasket or Amazon.in')

        return jsonify(data)

    except Exception as e:
        print(f"Process error: {e}")
        return jsonify({"Alternative": "Unavailable", "Reason": str(e), "Where_to_Buy": ""})


@app.route('/alternative')
def alternative_page():
    return render_template('alternative.html', title="Healthier Alternative", subtitle="Finding the best option for you...")


@app.route('/compare')
def compare_page():
    return render_template('compare.html', title="Compare Products", subtitle="Which one is healthier?")


@app.route('/compare/analyse', methods=['POST'])
def compare_analyse():
    try:
        results = []
        for slot in ['product_a', 'product_b']:
            # Accept either file upload or base64 camera data
            if slot + '_file' in request.files:
                f = request.files[slot + '_file']
                if not f or f.filename == '':
                    return jsonify({'error': f'No file for {slot}'}), 400
                image_data = f.read()
                mime_type = 'image/jpeg' if f.filename.lower().endswith(('.jpg','.jpeg')) else 'image/png'
            elif slot + '_data' in request.form:
                raw = request.form[slot + '_data']
                if ',' not in raw:
                    return jsonify({'error': f'Invalid image data for {slot}'}), 400
                _, encoded = raw.split(',', 1)
                image_data = base64.b64decode(encoded)
                mime_type = 'image/jpeg'
            else:
                return jsonify({'error': f'Missing image for {slot}'}), 400

            picture = {'mime_type': mime_type, 'data': image_data}
            response = model.generate_content([HSR_ANALYSIS_PROMPT, picture])
            result = clean_json_response(response.text)

            if not result:
                result = {}

            result.setdefault('category', 'other')
            result.setdefault('rating', 'N/A')
            result.setdefault('reason', 'Unable to analyze.')
            result.setdefault('expiry', 'Not visible')
            result.setdefault('good_ingredients', [])
            result.setdefault('bad_ingredients', [])
            result.setdefault('score_breakdown', {})
            results.append(result)

        # Determine winner
        r_a = get_numeric_rating(results[0]['rating']) or 0
        r_b = get_numeric_rating(results[1]['rating']) or 0
        if r_a > r_b:
            winner = 'a'
        elif r_b > r_a:
            winner = 'b'
        else:
            winner = 'tie'

        return jsonify({
            'product_a': results[0],
            'product_b': results[1],
            'winner': winner
        })

    except Exception as e:
        print(f"Compare error: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8000, debug=True)
