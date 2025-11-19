#!/usr/bin/env python3
from datetime import datetime, timedelta
from flask import (
    Blueprint,
    render_template,
    request,
    jsonify,
    abort,
    redirect,
    url_for,
    flash,
    session,
)
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import SignatureExpired, BadSignature
from sqlalchemy import func, case
from markupsafe import Markup
import yaml, requests, os, xml.etree.ElementTree as ET
from urllib.parse import quote_plus

from shared.db import db
from webapp.account_utils import ensure_user_stub
from webapp.models import (
    User,
    Paper,
    UserPreference,
    Subscriber,
    Feedback,
    PreferenceConfig,
    RecommendationSnapshot,
    GmailWatchState,
    DeliveryEvent,
)
from shared.utils import get_user_by_email, fetch_arxiv_feed, strip_html_tags
from shared.mail import send_reset_email, get_serializer, send_email
from filters import score_paper

SUBCATEGORY_EXPANSIONS = {
    "astro-ph": [
        "astro-ph.CO",
        "astro-ph.EP",
        "astro-ph.GA",
        "astro-ph.HE",
        "astro-ph.IM",
        "astro-ph.SR",
    ],
    "cond-mat": [
        "cond-mat.dis-nn",
        "cond-mat.mes-hall",
        "cond-mat.mtrl-sci",
        "cond-mat.other",
        "cond-mat.quant-gas",
        "cond-mat.soft",
        "cond-mat.stat-mech",
        "cond-mat.str-el",
        "cond-mat.supr-con",
    ],
    "cs": [
        "cs.AI",
        "cs.AR",
        "cs.CC",
        "cs.CE",
        "cs.CG",
        "cs.CL",
        "cs.CR",
        "cs.CV",
        "cs.CY",
        "cs.DB",
        "cs.DC",
        "cs.DL",
        "cs.DM",
        "cs.DS",
        "cs.ET",
        "cs.FL",
        "cs.GL",
        "cs.GR",
        "cs.GT",
        "cs.HC",
        "cs.IR",
        "cs.IT",
        "cs.LG",
        "cs.LO",
        "cs.MA",
        "cs.MM",
        "cs.MS",
        "cs.NA",
        "cs.NE",
        "cs.NI",
        "cs.OH",
        "cs.OS",
        "cs.PF",
        "cs.PL",
        "cs.RO",
        "cs.SC",
        "cs.SD",
        "cs.SE",
        "cs.SI",
        "cs.SY",
    ],
    "econ": [
        "econ.EM",
        "econ.GN",
        "econ.TH",
    ],
    "eess": [
        "eess.AS",
        "eess.IV",
        "eess.SP",
        "eess.SY",
    ],
    "math": [
        "math.AC",
        "math.AG",
        "math.AP",
        "math.AT",
        "math.CA",
        "math.CO",
        "math.CT",
        "math.CV",
        "math.DG",
        "math.DS",
        "math.FA",
        "math.GM",
        "math.GN",
        "math.GR",
        "math.GT",
        "math.HO",
        "math.IT",
        "math.KT",
        "math.LO",
        "math.MG",
        "math.MP",
        "math.NA",
        "math.NT",
        "math.OA",
        "math.OC",
        "math.PR",
        "math.QA",
        "math.RA",
        "math.RT",
        "math.SG",
        "math.SP",
        "math.ST",
    ],
    "nlin": [
        "nlin.AO",
        "nlin.CD",
        "nlin.CG",
        "nlin.PS",
        "nlin.SI",
    ],
    "physics": [
        "physics.acc-ph",
        "physics.ao-ph",
        "physics.app-ph",
        "physics.atm-clus",
        "physics.atom-ph",
        "physics.bio-ph",
        "physics.chem-ph",
        "physics.class-ph",
        "physics.comp-ph",
        "physics.data-an",
        "physics.ed-ph",
        "physics.flu-dyn",
        "physics.gen-ph",
        "physics.geo-ph",
        "physics.hist-ph",
        "physics.ins-det",
        "physics.med-ph",
        "physics.optics",
        "physics.plasm-ph",
        "physics.pop-ph",
        "physics.soc-ph",
        "physics.space-ph",
    ],
    "q-bio": [
        "q-bio.BM",
        "q-bio.CB",
        "q-bio.GN",
        "q-bio.MN",
        "q-bio.NC",
        "q-bio.OT",
        "q-bio.PE",
        "q-bio.QM",
        "q-bio.SC",
        "q-bio.TO",
    ],
    "q-fin": [
        "q-fin.CP",
        "q-fin.EC",
        "q-fin.GN",
        "q-fin.MF",
        "q-fin.PM",
        "q-fin.PR",
        "q-fin.RM",
        "q-fin.ST",
        "q-fin.TR",
    ],
    "stat": [
        "stat.AP",
        "stat.CO",
        "stat.ME",
        "stat.ML",
        "stat.OT",
        "stat.TH",
    ],
    "gr-qc": ["gr-qc"],
    "hep-ex": ["hep-ex"],
    "hep-lat": ["hep-lat"],
    "hep-ph": ["hep-ph"],
    "hep-th": ["hep-th"],
    "math-ph": ["math-ph"],
    "nucl-ex": ["nucl-ex"],
    "nucl-th": ["nucl-th"],
}

ONBOARDING_DOMAINS = [
    {
        "key": "physics",
        "label": "physics",
        "description": "astro, condensed matter, relativity, etc.",
        "categories": [
            "astro-ph",
            "astro-ph.CO",
            "astro-ph.GA",
            "astro-ph.HE",
            "astro-ph.IM",
            "astro-ph.EP",
            "astro-ph.SR",
            "cond-mat",
            "gr-qc",
            "hep-th",
            "hep-ph",
            "hep-ex",
            "hep-lat",
        ],
    },
    {
        "key": "mathematics",
        "label": "mathematics",
        "description": "analysis, geometry, algebra",
        "categories": ["math"],
    },
    {
        "key": "computer_science",
        "label": "computer science",
        "description": "AI, ML, vision, theory",
        "categories": ["cs"],
    },
    {
        "key": "quant_bio",
        "label": "quantitative biology",
        "description": "bioinformatics, genomics",
        "categories": ["q-bio"],
    },
    {
        "key": "quant_finance",
        "label": "quantitative finance",
        "description": "econ, finance models",
        "categories": ["q-fin"],
    },
    {
        "key": "statistics",
        "label": "statistics",
        "description": "methodology, applications",
        "categories": ["stat"],
    },
    {
        "key": "eess",
        "label": "electrical engineering & systems",
        "description": "signal processing, control",
        "categories": ["eess"],
    },
    {
        "key": "economics",
        "label": "economics",
        "description": "econ theory, metrics",
        "categories": ["econ"],
    },
]

ONBOARDING_TOPIC_SUGGESTIONS = [
    {
        "label": "event horizon telescope",
        "keywords": ["black hole", "event horizon", "EHT", "VLBI"],
        "categories": ["astro-ph.HE", "astro-ph.GA", "astro-ph.IM"],
        "domains": ["physics"],
    },
    {
        "label": "gravitational waves",
        "keywords": ["gravitational waves", "LIGO", "LISA", "black hole binary"],
        "categories": ["gr-qc", "astro-ph.HE"],
        "domains": ["physics"],
    },
    {
        "label": "galaxy evolution",
        "keywords": ["galaxy", "star formation", "feedback", "turbulence"],
        "categories": ["astro-ph.GA", "astro-ph.CO"],
        "domains": ["physics"],
    },
    {
        "label": "exoplanets",
        "keywords": ["exoplanet", "transit", "debris disk", "habitable zone"],
        "categories": ["astro-ph.EP", "astro-ph.SR"],
        "domains": ["physics"],
    },
    {
        "label": "cosmology",
        "keywords": ["dark energy", "CMB", "BAO", "cosmic microwave background"],
        "categories": ["astro-ph.CO", "gr-qc"],
        "domains": ["physics"],
    },
    {
        "label": "compact objects",
        "keywords": ["pulsar", "neutron star", "tidal disruption", "accretion"],
        "categories": ["astro-ph.HE", "astro-ph.GA"],
        "domains": ["physics"],
    },
    {
        "label": "condensed matter",
        "keywords": ["condensed matter", "superconductivity", "strongly correlated"],
        "categories": ["cond-mat", "cond-mat.supr-con", "cond-mat.str-el"],
        "domains": ["physics"],
    },
    {
        "label": "particle physics",
        "keywords": ["particle physics", "LHC", "standard model"],
        "categories": ["hep-ph", "hep-ex", "hep-th"],
        "domains": ["physics"],
    },
    {
        "label": "quantum information",
        "keywords": ["quantum computing", "quantum information"],
        "categories": ["quant-ph"],
        "domains": ["physics", "computer_science"],
    },
    {
        "label": "analysis & PDEs",
        "keywords": ["analysis", "partial differential equations", "dynamics"],
        "categories": ["math.AP", "math.CA", "math.DS"],
        "domains": ["mathematics"],
    },
    {
        "label": "geometry & topology",
        "keywords": ["geometry", "topology"],
        "categories": ["math.GT", "math.DG", "math.AT"],
        "domains": ["mathematics"],
    },
    {
        "label": "algebra & number theory",
        "keywords": ["algebra", "number theory"],
        "categories": ["math.NT", "math.AG", "math.GR"],
        "domains": ["mathematics"],
    },
    {
        "label": "machine learning",
        "keywords": ["machine learning", "deep learning", "AI"],
        "categories": ["cs.LG", "stat.ML"],
        "domains": ["computer_science", "statistics"],
    },
    {
        "label": "computer vision",
        "keywords": ["computer vision", "image recognition"],
        "categories": ["cs.CV"],
        "domains": ["computer_science"],
    },
    {
        "label": "algorithms & theory",
        "keywords": ["algorithms", "complexity", "data structures"],
        "categories": ["cs.DS", "cs.CC"],
        "domains": ["computer_science"],
    },
    {
        "label": "bioinformatics",
        "keywords": ["genomics", "bioinformatics", "systems biology"],
        "categories": ["q-bio.GN", "q-bio.BM"],
        "domains": ["quant_bio"],
    },
    {
        "label": "systems & control",
        "keywords": ["control theory", "autonomous systems"],
        "categories": ["eess.SY", "cs.SY"],
        "domains": ["eess"],
    },
    {
        "label": "signal processing",
        "keywords": ["signal processing", "communications"],
        "categories": ["eess.SP", "eess.AS"],
        "domains": ["eess"],
    },
    {
        "label": "economics",
        "keywords": [
            "economics",
            "macroeconomics",
            "policy",
            "development economics",
            "finance",
        ],
        "categories": ["econ.EM", "econ.GN", "q-fin.EC"],
        "domains": ["economics", "quant_finance"],
    },
    {
        "label": "econometrics",
        "keywords": [
            "econometrics",
            "quantitative finance",
            "risk management",
            "trading",
        ],
        "categories": ["econ.EM", "q-fin.TR", "q-fin.RM"],
        "domains": ["economics", "quant_finance", "statistics"],
    },
    {
        "label": "financial markets",
        "keywords": ["market microstructure", "asset pricing", "derivatives"],
        "categories": ["q-fin.MF", "q-fin.PM"],
        "domains": ["quant_finance"],
    },
]

ONBOARDING_CATEGORY_CHOICES = [
    ("astro-ph", "astro-ph (general)"),
    ("astro-ph.CO", "cosmology & nongalactic astro-ph.CO"),
    ("astro-ph.GA", "galaxies (astro-ph.GA)"),
    ("astro-ph.HE", "high energy astrophysics"),
    ("astro-ph.IM", "instrumentation / methods"),
    ("astro-ph.SR", "stellar / solar physics"),
    ("gr-qc", "general relativity (gr-qc)"),
    ("hep-lat", "lattice hep (hep-lat)"),
    ("cond-mat", "condensed matter"),
    ("cond-mat.supr-con", "condensed matter: superconductivity"),
    ("cond-mat.str-el", "condensed matter: strongly correlated"),
    ("hep-ph", "high energy physics: phenomenology"),
    ("hep-ex", "high energy physics: experiment"),
    ("hep-th", "high energy physics: theory"),
    ("quant-ph", "quantum physics"),
    ("math", "mathematics (general)"),
    ("math.AP", "analysis of PDEs"),
    ("math.GT", "geometry and topology"),
    ("math.NT", "number theory"),
    ("cs.LG", "computer science: machine learning"),
    ("cs.CV", "computer science: computer vision"),
    ("cs.DS", "computer science: data structures"),
    ("q-bio", "quantitative biology"),
    ("eess.SP", "electrical engineering: signal processing"),
    ("eess.SY", "electrical engineering: systems and control"),
    ("econ.EM", "economics: econometrics"),
    ("econ.GN", "economics: general"),
    ("q-fin.TR", "quantitative finance: trading"),
    ("q-fin.RM", "quantitative finance: risk management"),
    ("q-fin.MF", "quantitative finance: mathematical finance"),
    ("q-fin.PM", "quantitative finance: portfolio management"),
    ("stat.ML", "statistics: machine learning"),
]


def _expand_categories(selected):
    expanded = []
    seen = set()
    for cat_name in selected:
        if not cat_name:
            continue
        key = cat_name.lower()
        expansions = SUBCATEGORY_EXPANSIONS.get(key)
        if expansions:
            for sub in expansions:
                sub_clean = sub.strip()
                if sub_clean and sub_clean not in seen:
                    expanded.append(sub_clean)
                    seen.add(sub_clean)
            continue
        if cat_name not in seen:
            expanded.append(cat_name)
            seen.add(cat_name)
    return expanded


def _display_category(preference_cat, paper):
    pref = (preference_cat or "").strip().lower()
    paper_categories = paper.get("categories") or []
    if pref:
        matching = []
        for term in paper_categories:
            term_clean = (term or "").strip()
            if not term_clean:
                continue
            term_lower = term_clean.lower()
            if term_lower == pref or term_lower.startswith(f"{pref}."):
                matching.append(term_clean)
        if matching:
            return max(matching, key=len)

    primary = (paper.get("primary_category") or "").strip()
    if primary:
        return primary
    if paper_categories:
        return paper_categories[0]
    return preference_cat or ""


def _format_relevance(details):
    if not details:
        return ""
    parts = []
    matched_keywords = [kw for kw in (details.get("matched_any_keywords") or []) if kw]
    if matched_keywords:
        parts.append("keywords: " + ", ".join(matched_keywords))
    matched_authors = [au for au in (details.get("matched_authors") or []) if au]
    if matched_authors:
        parts.append("authors: " + ", ".join(matched_authors))
    bias = details.get("feedback_bias")
    if bias:
        parts.append(f"feedback boost {bias:+.1f}")
    return "; ".join(parts)


def _generate_recommendations_payload(prefs, *, limit=10):
    keywords = [k.strip() for k in (prefs.get("keywords") or []) if k and k.strip()]
    if not keywords:
        return (
            [],
            [],
            "no keywords found in preferences. add some to get recommendations.",
        )

    encoded_terms = [f'all:"{quote_plus(k)}"' for k in keywords if k]
    if not encoded_terms:
        return [], [], "no valid keywords provided."

    selected_categories = [c.strip() for c in (prefs.get("categories") or []) if c]
    if not selected_categories:
        selected_categories = ["astro-ph"]
    categories = _expand_categories(selected_categories) or ["astro-ph"]
    min_score = prefs.get("min_score", 1.0) or 1.0

    excluded_terms = [
        term.strip()
        for term in (prefs.get("excluded_keywords") or [])
        if term and term.strip()
    ]
    excluded_terms_lower = [term.lower() for term in excluded_terms]
    scoring_prefs = {
        "any_keywords": keywords,
        "all_keywords": [],
        "exclude_keywords": excluded_terms,
        "authors": [],
    }

    all_recs = []
    for cat in categories:
        cat = cat.strip()
        if not cat:
            continue
        query = "+OR+".join(encoded_terms) + f"+AND+cat:{quote_plus(cat)}"
        url = (
            "https://export.arxiv.org/api/query?"
            f"search_query={query}&start=0&max_results=25&sortBy=submittedDate&sortOrder=descending"
        )
        print(f"[recommendations] fetching from {cat}: {url}")
        try:
            recs = fetch_arxiv_feed(url)
            for r in recs:
                r["category"] = _display_category(cat, r)
                r["summary_plain"] = strip_html_tags(r.get("summary", "") or "")
            all_recs.extend(recs)
        except Exception as e:
            print(f"[recommendations] error fetching {cat}: {e}")

    dedup = {}
    for r in all_recs:
        link = r.get("link") or r.get("id") or ""
        if link and link not in dedup:
            dedup[link] = r

    scored = []
    for r in dedup.values():
        text = f"{r.get('title','')} {r.get('summary','')}".lower()
        if excluded_terms_lower and any(term in text for term in excluded_terms_lower):
            continue
        score, details = score_paper(
            r.get("title", ""),
            r.get("summary", ""),
            r.get("authors"),
            scoring_prefs,
        )
        if score >= min_score:
            r["score"] = score
            r["details"] = details
            scored.append(r)

    scored.sort(key=lambda x: x.get("score", 0), reverse=True)
    scored = scored[:limit]

    display_labels = selected_categories or categories
    if scored:
        msg = (
            f"showing {len(scored)} recent papers across {', '.join(display_labels)} "
            f"with score >= {min_score}."
        )
    else:
        msg = "no papers met your minimum relevance threshold."
    return scored, display_labels, msg


frontend = Blueprint("frontend", __name__)


@frontend.route("/")
def index():
    return render_template("index.html", user=current_user)


@frontend.route("/login", methods=["GET", "POST"])
def login():
    """user login (html form or json)."""
    try:
        if request.method == "POST":
            data = request.get_json(silent=True) or request.form
            email = (data.get("email") or "").strip().lower()
            password = data.get("password") or ""

            if not email or not password:
                flash("please enter both email and password.", "error")
                return redirect(url_for("frontend.login"))

            user = get_user_by_email(email)
            if (
                user
                and user.password_hash
                and check_password_hash(user.password_hash, password)
            ):
                login_user(user)
                # ensure logged-in users are in subscriber list
                normalized_email = email.strip().lower()
                if (
                    normalized_email
                    and not Subscriber.query.filter(
                        func.lower(Subscriber.email) == normalized_email
                    ).first()
                ):
                    db.session.add(Subscriber(email=normalized_email))
                    db.session.commit()
                session["is_admin"] = bool(user.is_admin)
                flash("logged in successfully.", "success")
                return redirect(url_for("frontend.index"))

            if user and not user.password_hash:
                flash(
                    "looks like you subscribed via email earlier. set a password to finish account setup.",
                    "info",
                )
                return redirect(url_for("frontend.signup"))

            if not user:
                subscriber = Subscriber.query.filter(
                    func.lower(Subscriber.email) == email
                ).first()
                if subscriber:
                    ensure_user_stub(email)
                    flash(
                        "looks like you subscribed via email earlier. set a password to finish account setup.",
                        "info",
                    )
                    return redirect(url_for("frontend.signup"))

            flash("invalid email or password.", "error")
            return redirect(url_for("frontend.login"))

        return render_template("login.html")
    except Exception as e:
        print(f"[login] error: {e}")
        return jsonify({"error": str(e)}), 500


@frontend.route("/logout")
def logout():
    session.pop("is_admin", None)
    logout_user()
    return redirect("/")


@frontend.route("/subscribe", methods=["GET", "POST"])
def subscribe():
    if request.method == "POST":
        if request.is_json:
            data = request.get_json(force=True)
            email = data.get("email", "").strip().lower()
        else:
            email = request.form.get("email", "").strip().lower()

        if not email:
            return (
                jsonify({"status": "error", "message": "please enter a valid email."}),
                400,
            )

        try:
            existing = Subscriber.query.filter(
                func.lower(Subscriber.email) == email
            ).first()
            if existing:
                return jsonify({"status": "info", "message": "already subscribed!"})

            new_sub = Subscriber(email=email)
            db.session.add(new_sub)
            ensure_user_stub(email, commit=False)
            db.session.commit()
            _send_subscription_email(email, "welcome")
            return jsonify({"status": "success", "message": "subscribed successfully!"})
        except Exception as e:
            print(f"[subscribe] error: {e}")
            db.session.rollback()
            return jsonify({"status": "error", "message": f"server error: {e}"}), 500

    return render_template("subscribe.html")


@frontend.route("/unsubscribe", methods=["GET", "POST"])
def unsubscribe():
    if request.method == "POST":
        if request.is_json:
            data = request.get_json(force=True)
            email = data.get("email", "").strip().lower()
        else:
            email = request.form.get("email", "").strip().lower()

        if not email:
            return (
                jsonify({"status": "error", "message": "please enter a valid email."}),
                400,
            )

        try:
            sub = Subscriber.query.filter(func.lower(Subscriber.email) == email).first()
            if not sub:
                return jsonify(
                    {
                        "status": "info",
                        "message": "email not found -- you may already be unsubscribed.",
                    }
                )

            db.session.delete(sub)
            db.session.commit()
            print(f"[unsubscribe] removed {email}")

            _send_subscription_email(email, "farewell")

            return jsonify(
                {
                    "status": "success",
                    "message": "you have been unsubscribed. farewell!",
                }
            )

        except Exception as e:
            print(f"[unsubscribe] error: {e}")
            db.session.rollback()
            return jsonify({"status": "error", "message": "server error"}), 500

    return render_template("unsubscribe.html")


@frontend.route("/preferences")
@login_required
def preferences_page():
    return render_template("preferences.html")


@frontend.route("/onboarding")
@login_required
def onboarding_page():
    config = PreferenceConfig.get_or_create_for_user(current_user)
    prefs = config.as_dict() if config else {}
    return render_template(
        "onboarding.html",
        domain_groups=ONBOARDING_DOMAINS,
        topic_groups=ONBOARDING_TOPIC_SUGGESTIONS,
        category_choices=ONBOARDING_CATEGORY_CHOICES,
        existing_prefs=prefs,
    )


@frontend.route("/dashboard")
@login_required
def dashboard_redirect():
    """redirect /dashboard -> /dashboard/<email> if logged in."""
    return redirect(url_for("frontend.dashboard", email=current_user.email))


@frontend.route("/dashboard/<email>")
def dashboard(email):
    user = User.query.filter_by(email=email.lower()).first()
    if not user:
        return render_template(
            "dashboard.html", user={"email": email}, prefs=[], message="no user found."
        )

    liked_prefs = (
        UserPreference.query.filter_by(user_id=user.id, liked=True)
        .join(Paper)
        .order_by(UserPreference.created_at.desc())
        .all()
    )

    missing_ids = [
        pref.paper.arxiv_id
        for pref in liked_prefs
        if not (pref.paper.title or "").strip()
    ]
    fetched_titles = _fetch_arxiv_titles(missing_ids)

    prefs = []
    updated = False
    for pref in liked_prefs:
        paper = pref.paper
        display_title = (paper.title or "").strip()
        if not display_title:
            display_title = fetched_titles.get(paper.arxiv_id, "")
            if display_title:
                paper.title = display_title
                updated = True
        if not display_title:
            display_title = f"arXiv:{paper.arxiv_id}"

        link = (paper.link or "").strip()
        if not link:
            link = f"https://arxiv.org/abs/{paper.arxiv_id}"

        prefs.append(
            {
                "display_title": display_title,
                "paper": {
                    "title": paper.title or "",
                    "link": link,
                    "arxiv_id": paper.arxiv_id,
                },
                "timestamp": pref.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    if updated:
        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            print(f"[dashboard] failed to persist fetched titles: {exc}")

    message = "read anything super yet?" if not prefs else None
    return render_template(
        "dashboard.html", user={"email": email}, prefs=prefs, message=message
    )


@frontend.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        existing_user = User.query.filter(func.lower(User.email) == email).first()
        if existing_user:
            if existing_user.password_hash:
                flash("user already exists. try logging in instead.", "error")
                return redirect(url_for("frontend.login"))

            try:
                existing_user.password_hash = generate_password_hash(password)
                db.session.commit()
            except Exception as exc:
                db.session.rollback()
                print(f"[signup] error claiming user: {exc}")
                flash(
                    "we couldn't finish sign-up. please try again in a moment.", "error"
                )
                return redirect(url_for("frontend.signup"))

            login_user(existing_user)
            _send_subscription_email(email, "welcome")
            flash("account claimed! welcome aboard!", "success")
            return redirect(url_for("frontend.dashboard_redirect"))

        try:
            # hash and store the password
            hashed_pw = generate_password_hash(password)
            new_user = User(email=email, password_hash=hashed_pw)
            db.session.add(new_user)

            # automatically subscribe new accounts if they are not already in the list
            existing_sub = Subscriber.query.filter(
                func.lower(Subscriber.email) == email
            ).first()
            if not existing_sub:
                db.session.add(Subscriber(email=email))

            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            print(f"[signup] error saving new user: {exc}")
            flash("we couldn't finish sign up. please try again in a moment.", "error")
            return redirect(url_for("frontend.signup"))

        login_user(new_user)
        _send_subscription_email(email, "welcome")
        flash("sign up complete — welcome aboard!", "success")
        return redirect(url_for("frontend.dashboard_redirect"))

    return render_template("signup.html")


@frontend.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        user = get_user_by_email(email)

        if user:
            token = get_serializer().dumps(email, salt="password-reset")
            reset_url = url_for("frontend.reset_password", token=token, _external=True)
            send_reset_email(user.email, reset_url)
            flash("reset link sent to your email.")
        else:
            flash("no account found with that email.")
        return redirect(url_for("frontend.login"))

    return render_template("forgot_password.html")


@frontend.route("/forgot-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        email = get_serializer().loads(token, salt="password-reset", max_age=3600)
    except SignatureExpired:
        flash("reset link expired.")
        return redirect(url_for("frontend.forgot_password"))
    except BadSignature:
        flash("invalid reset token.")
        return redirect(url_for("frontend.forgot_password"))

    user = get_user_by_email(email)
    if not user:
        flash("user not found.")
        return redirect(url_for("frontend.forgot_password"))

    if request.method == "POST":
        new_password = request.form["password"]
        hashed_pw = generate_password_hash(new_password)

        user.password_hash = hashed_pw
        db.session.commit()

        flash("password reset successful. you can now log in.")
        return redirect(url_for("frontend.login"))

    return render_template("reset_password.html", email=email)


# send feedback (contact form)
def _env_mail_config():
    """
    fallback mail configuration that mirrors config.yaml structure using environment variables.
    expects EMAIL_FROM (and EMAIL_PASS env) already used elsewhere.
    """
    from_addr = (os.getenv("EMAIL_FROM") or "").strip()
    if not from_addr:
        return {}

    def _parse_recipients(raw: str | None):
        if not raw:
            return []
        return [addr.strip() for addr in raw.split(",") if addr.strip()]

    try:
        port = int(os.getenv("SMTP_PORT", "587"))
    except ValueError:
        port = 587

    recipients = _parse_recipients(os.getenv("FEEDBACK_EMAIL"))
    if not recipients:
        recipients = [from_addr]

    return {
        "mail": {
            "smtp_host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
            "smtp_port": port,
            "use_starttls": os.getenv("SMTP_USE_STARTTLS", "true").lower()
            not in {"false", "0", "no"},
            "username": from_addr,
            "from_addr": from_addr,
            "password_env": os.getenv("PASSWORD_ENV", "EMAIL_PASS"),
            "to_addrs": recipients,
        },
        "feedback_email": os.getenv("FEEDBACK_EMAIL"),
    }


def _load_mail_config():
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
            return cfg
    except Exception as e:
        print(f"[mail-config] yaml error: {e}")
        fallback = _env_mail_config()
        if not fallback:
            print(
                "[mail-config] no config.yaml and no MAIL_/EMAIL_ env vars available."
            )
        return fallback


def _send_subscription_email(to_email: str, kind: str = "welcome") -> bool:
    target = (to_email or "").strip()
    if not target:
        return False

    cfg = _load_mail_config()
    if not cfg:
        return False

    if kind == "farewell":
        subject = "you've been unsubscribed from digest"
        text = (
            "we've removed you from the digest mailing list.\n\n"
            "if this was a mistake, you can rejoin any time at https://paperscraper-one.vercel.app/"
            " or by emailing thearxivpaperscraper@gmail.com with the subject 'subscribe'.\n\n"
            "-- digest bot"
        )
        html = (
            "<p>we've removed you from the <strong>digest</strong> mailing list.</p>"
            "<p>changed your mind? hop back in at "
            '<a href="https://paperscraper-one.vercel.app/">paperscraper-one.vercel.app</a> or send an email with the subject '
            "<code>subscribe</code> to thearxivpaperscraper@gmail.com.</p>"
            "<p>clear skies!</p>"
        )
    else:
        subject = "welcome to the digest"
        text = (
            "welcome aboard!\n\n"
            "you'll now receive the daily digest with curated papers.\n"
            "log in at https://paperscraper-one.vercel.app/ to set your preferences or send feedback anytime.\n\n"
            "-- digest bot"
        )
        html = (
            "<p>welcome aboard! you'll now receive the daily <strong>digest</strong>."
            '</p><p>sign up at <a href="https://paperscraper-one.vercel.app/">paperscraper-one.vercel.app</a> to claim your account '
            "and begin customizing your preferences and curate the papers you care about.</p><p>clear skies!</p>"
        )

    email_context = f"lifecycle-{kind}"
    if not send_email(
        cfg, subject, text, html, to_override=[target], context=email_context
    ):
        print(f"[subscription-email] failed to send {kind} email to {target}")
        return False

    print(f"[subscription-email] sent {kind} email to {target}")
    return True


def _fetch_arxiv_titles(arxiv_ids: list[str]) -> dict[str, str]:
    """fetch title data for arXiv ids that lack metadata in the database."""
    ids = [aid for aid in (arxiv_ids or []) if aid]
    if not ids:
        return {}

    titles: dict[str, str] = {}
    base_url = "https://export.arxiv.org/api/query"
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    for i in range(0, len(ids), 20):
        chunk = ids[i : i + 20]
        params = {"id_list": ",".join(chunk)}
        try:
            resp = requests.get(base_url, params=params, timeout=10)
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
            for entry in root.findall("atom:entry", ns):
                entry_id = entry.find("atom:id", ns)
                raw_id = (entry_id.text or "").strip() if entry_id is not None else ""
                arxiv_id = raw_id.split("/abs/")[-1] if raw_id else ""
                title_el = entry.find("atom:title", ns)
                title_text = (
                    (title_el.text or "").strip() if title_el is not None else ""
                )
                if arxiv_id and title_text:
                    titles[arxiv_id] = title_text
        except Exception as exc:
            print(f"[dashboard] failed to fetch arxiv titles: {exc}")

    return titles


@frontend.route("/send-feedback", methods=["GET", "POST"])
def user_feedback():
    """receives user feedback, stores it in the database, and emails it to the bot."""
    if request.method == "GET":
        return render_template("feedback_form.html")

    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "invalid json"}), 400

    name = (data.get("name") or "anonymous").strip()
    email = (data.get("email") or "anonymous@local").strip()
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message cannot be empty"}), 400

    # save to db first
    fb = Feedback(name=name, email=email, message=message, type="contact")
    try:
        db.session.add(fb)
        db.session.commit()
        print(f"[feedback] stored feedback from {email}")
    except Exception as e:
        print(f"[feedback] db save error: {e}")
        db.session.rollback()

    # try to load mail config
    cfg = _load_mail_config()
    if not cfg:
        return jsonify({"message": "feedback stored but mail config missing"}), 202

    # compose email
    subject = f"[arxiv feedback] from {name}"
    text = f"{name} <{email}> wrote:\n\n{message}"
    html = f"<p><strong>{name}</strong> &lt;{email}&gt;</p><p>{message}</p>"

    # send mail
    mail_section = cfg.get("mail") or cfg.get("output", {}).get("email") or {}
    feedback_to = (
        cfg.get("feedback_email")
        or cfg.get("feedback", {}).get("to_addr")
        or mail_section.get("username")
        or mail_section.get("from_addr")
        or os.getenv("FEEDBACK_EMAIL")
    )
    to_list = [feedback_to] if feedback_to else None

    if not send_email(
        cfg, subject, text, html, to_override=to_list, context="feedback-forward"
    ):
        print("[send-feedback] mail send failed")
        # still return success since it was saved in db
        return jsonify({"message": "feedback stored but email failed"}), 202

    print(f"[send-feedback] feedback email sent from {email}")
    return jsonify({"message": "feedback sent!"}), 200


# recommendations page
@frontend.route("/recommendations")
@login_required
def recommendations():
    """
    render personalized arXiv recommendations using saved preferences,
    capped at 10 total results and showing the category of origin.
    """
    from sqlalchemy.exc import SQLAlchemyError

    try:
        config = PreferenceConfig.get_or_create_for_user(current_user)
        prefs = (
            config.as_dict()
            if config
            else {
                "keywords": [],
                "excluded_keywords": [],
                "categories": ["astro-ph"],
                "min_score": 1.0,
            }
        )
    except SQLAlchemyError as e:
        print(f"[recommendations] db error loading prefs: {e}")
        prefs = {
            "keywords": [],
            "excluded_keywords": [],
            "categories": ["astro-ph"],
            "min_score": 1.0,
        }

    scored, display_labels, msg = _generate_recommendations_payload(prefs, limit=10)
    for rec in scored:
        summary_text = rec.get("summary", "") or ""
        escaped = Markup.escape(summary_text)
        rec["summary_html"] = escaped.replace("\n", Markup("<br>"))

    return render_template("recommendations.html", recs=scored, message=msg)


@frontend.route("/api/onboarding-preview", methods=["POST"])
@login_required
def onboarding_preview():
    """return a short preview list for the onboarding wizard."""
    data = request.get_json(force=True) or {}
    prefs = {
        "keywords": data.get("keywords") or [],
        "excluded_keywords": data.get("excluded_keywords") or [],
        "categories": data.get("categories") or [],
        "min_score": data.get("min_score", 1.0) or 1.0,
    }
    records, _, message = _generate_recommendations_payload(prefs, limit=3)
    preview = [
        {
            "title": r.get("title"),
            "category": r.get("category"),
            "score": r.get("score"),
            "summary": r.get("summary_plain") or strip_html_tags(r.get("summary", "")),
            "link": r.get("link") or r.get("id") or "",
            "why": _format_relevance(r.get("details")),
        }
        for r in records
    ]
    return jsonify({"records": preview, "message": message})


# record recommendation feedback (like/dislike)
def _record_recommendation_feedback(
    email: str,
    arxiv_id: str,
    liked: bool,
    source: str = "recommendations",
    timestamp: datetime | None = None,
):
    """shared helper to store recommendation feedback."""
    email = (email or "").strip().lower()
    arxiv_id = (arxiv_id or "").strip()
    if not email or not arxiv_id:
        raise ValueError("missing email or arxiv_id")

    user = User.query.filter(func.lower(User.email) == email).first()

    paper = Paper.query.filter_by(arxiv_id=arxiv_id).first()
    if not paper:
        paper = Paper(
            arxiv_id=arxiv_id, title="", link=f"https://arxiv.org/abs/{arxiv_id}"
        )
        db.session.add(paper)
        db.session.flush()

    if user:
        pref = UserPreference.query.filter_by(
            user_id=user.id, paper_id=paper.id
        ).first()
        if not pref:
            pref = UserPreference(user_id=user.id, paper_id=paper.id, liked=liked)
            db.session.add(pref)
        else:
            pref.liked = liked

        snapshot = RecommendationSnapshot.query.filter_by(
            user_id=user.id, arxiv_id=arxiv_id
        ).first()
        if snapshot:
            snapshot.feedback = liked
    else:
        print(
            f"[recommendation-feedback] no user account for {email}; skipping preference sync."
        )

    fb_entry = Feedback(
        name="system",
        email=email,
        message=f"reaction {'like' if liked else 'dislike'} for {arxiv_id}",
        type="recommendation",
        arxiv_id=arxiv_id,
        liked=liked,
        source=source,
        timestamp=timestamp or datetime.utcnow(),
    )
    db.session.add(fb_entry)
    db.session.commit()

    print(
        f"[recommendation-feedback] saved like={liked} for {arxiv_id} ({email}) via {source}"
    )


@frontend.route("/api/recommendation-feedback", methods=["POST"])
def recommendation_feedback():
    """store recommendation reactions directly in the database."""
    data = request.get_json(force=True)
    email = data.get("email")
    link = data.get("link") or ""
    liked = bool(data.get("reaction", True))

    arxiv_id = link.split("arxiv.org/abs/")[-1].strip()
    if not email or not arxiv_id:
        return jsonify({"error": "missing email or link"}), 400

    try:
        _record_recommendation_feedback(
            email, arxiv_id, liked, source="recommendations"
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 500

    return jsonify({"status": "ok"})


@frontend.route("/like")
def like_from_email():
    """handle email like/dislike links."""
    email = request.args.get("email", "")
    arxiv_id = request.args.get("arxiv_id", "")
    liked_param = request.args.get("liked", "true")
    liked = str(liked_param).lower() in {"1", "true", "yes", "on"}

    try:
        _record_recommendation_feedback(email, arxiv_id, liked, source="email")
        heading = "thanks for your feedback!"
        message = (
            f"we recorded your {'like' if liked else 'dislike'} for arXiv:{arxiv_id}."
        )
        status = 200
    except ValueError:
        heading = "missing information"
        message = "we couldn't record your feedback because the link was incomplete."
        status = 400
    except Exception as exc:
        heading = "something went wrong"
        message = "we couldn't record your feedback. please try again later."
        status = 500
        print(f"[like_from_email] error storing feedback: {exc}")

    return (
        render_template(
            "email_feedback.html",
            heading=heading,
            message=message,
        ),
        status,
    )


# admin dashboard helpers
def _date_label(value):
    if not value:
        return "-"
    try:
        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d")
    except Exception:
        pass
    return str(value)


@frontend.route("/admin/ops", methods=["GET"])
@login_required
def admin_ops_dashboard():
    """surface subscriber, engagement, delivery, and gmail watch health."""
    if not current_user.is_admin:
        abort(403)

    now = datetime.utcnow()

    # subscriber growth (last 30 days)
    growth_window = now - timedelta(days=30)
    growth_day = func.date(Subscriber.created_at)
    growth_rows = (
        db.session.query(growth_day.label("day"), func.count(Subscriber.id).label("count"))
        .filter(Subscriber.created_at >= growth_window)
        .group_by(growth_day)
        .order_by(growth_day)
        .all()
    )
    growth_series = [
        {"day": _date_label(row.day), "count": int(row.count or 0)} for row in growth_rows
    ]
    subs_total = db.session.query(func.count(Subscriber.id)).scalar() or 0
    subs_7d = (
        db.session.query(func.count(Subscriber.id))
        .filter(Subscriber.created_at >= now - timedelta(days=7))
        .scalar()
        or 0
    )
    subs_24h = (
        db.session.query(func.count(Subscriber.id))
        .filter(Subscriber.created_at >= now - timedelta(days=1))
        .scalar()
        or 0
    )
    growth_total = sum(point["count"] for point in growth_series)
    avg_daily_growth = round(growth_total / len(growth_series), 2) if growth_series else 0
    subscriber_metrics = {
        "total": subs_total,
        "new_24h": subs_24h,
        "new_7d": subs_7d,
        "series": growth_series,
        "avg_daily": avg_daily_growth,
    }

    # engagement metrics from recommendation feedback
    engagement_window = now - timedelta(days=14)
    fb_day = func.date(Feedback.timestamp)
    engagement_rows = (
        db.session.query(
            fb_day.label("day"),
            func.count(Feedback.id).label("total"),
            func.sum(case((Feedback.source == "email", 1), else_=0)).label("email_clicks"),
            func.sum(case((Feedback.liked == True, 1), else_=0)).label("likes"),
        )
        .filter(
            Feedback.type == "recommendation",
            Feedback.timestamp >= engagement_window,
        )
        .group_by(fb_day)
        .order_by(fb_day)
        .all()
    )
    engagement_series = [
        {
            "day": _date_label(row.day),
            "total": int(row.total or 0),
            "email": int(row.email_clicks or 0),
            "likes": int(row.likes or 0),
        }
        for row in engagement_rows
    ]
    total_clicks = sum(point["total"] for point in engagement_series)
    email_clicks = sum(point["email"] for point in engagement_series)
    like_count = sum(point["likes"] for point in engagement_series)
    like_rate = round((like_count / total_clicks) * 100.0, 1) if total_clicks else 0.0
    engagement_metrics = {
        "total_clicks": total_clicks,
        "email_clicks": email_clicks,
        "web_clicks": max(total_clicks - email_clicks, 0),
        "like_rate": like_rate,
        "series": engagement_series,
    }

    # delivery failures
    failure_window = now - timedelta(days=7)
    failure_day = func.date(DeliveryEvent.created_at)
    failure_rows = (
        db.session.query(
            failure_day.label("day"),
            func.count(DeliveryEvent.id).label("count"),
        )
        .filter(
            DeliveryEvent.created_at >= failure_window,
            DeliveryEvent.status != "sent",
        )
        .group_by(failure_day)
        .order_by(failure_day)
        .all()
    )
    failure_series = [
        {"day": _date_label(row.day), "count": int(row.count or 0)} for row in failure_rows
    ]
    failures_7d = sum(point["count"] for point in failure_series)
    failures_24h = (
        DeliveryEvent.query.filter(
            DeliveryEvent.created_at >= now - timedelta(days=1),
            DeliveryEvent.status != "sent",
        ).count()
        or 0
    )
    recent_failures = (
        DeliveryEvent.query.filter(
            DeliveryEvent.created_at >= failure_window, DeliveryEvent.status != "sent"
        )
        .order_by(DeliveryEvent.created_at.desc())
        .limit(15)
        .all()
    )
    failure_entries = [
        {
            "recipient": entry.recipient,
            "subject": entry.subject or "(no subject)",
            "context": entry.context or "-",
            "error": entry.error or "",
            "timestamp": entry.created_at.strftime("%Y-%m-%d %H:%M")
            if entry.created_at
            else "-",
        }
        for entry in recent_failures
    ]
    delivery_metrics = {
        "failures_24h": failures_24h,
        "failures_7d": failures_7d,
        "series": failure_series,
        "recent": failure_entries,
    }

    # gmail watch health check
    stale_hours = 6
    watch_state = None
    try:
        watch_state = GmailWatchState.get_state()
    except Exception as exc:
        print(f"[admin/ops] unable to load Gmail watch state: {exc}")
    last_heartbeat = None
    if watch_state:
        last_heartbeat = watch_state.updated_at or watch_state.created_at
    stale_cutoff = now - timedelta(hours=stale_hours)
    is_stale = (last_heartbeat is None) or (last_heartbeat < stale_cutoff)
    missing_history = bool(watch_state) and not (watch_state.history_id or "").strip()
    gmail_alerts = []
    if is_stale:
        gmail_alerts.append(f"no webhook activity detected in the past {stale_hours}h.")
    if missing_history:
        gmail_alerts.append("gmail watch history id missing; webhook may need re-init.")
    gmail_watch = {
        "history_id": watch_state.history_id if watch_state else None,
        "label_id": watch_state.label_id if watch_state else None,
        "last_heartbeat": last_heartbeat.strftime("%Y-%m-%d %H:%M")
        if last_heartbeat
        else "never",
        "status": "ok" if not gmail_alerts else "warning",
        "alerts": gmail_alerts,
    }

    return render_template(
        "admin_dashboard.html",
        subscriber_metrics=subscriber_metrics,
        engagement_metrics=engagement_metrics,
        delivery_metrics=delivery_metrics,
        gmail_watch=gmail_watch,
    )


# view feedback (admin-only page)
@frontend.route("/view-feedback", methods=["GET"])
@login_required
def view_feedback_page():
    """show recorded likes/dislikes from UserPreference joined with paper & user."""
    if not current_user.is_admin:
        abort(403)

    # pull direct feedback entries so we preserve the original source label
    rows = (
        Feedback.query.filter(Feedback.type == "recommendation")
        .order_by(Feedback.timestamp.desc())
        .limit(200)
        .all()
    )

    feedback = []
    seen_pairs = set()

    def _add_entry(email, arxiv_id, liked, timestamp, source):
        ts_dt = timestamp if isinstance(timestamp, datetime) else None
        key = ((email or "").strip().lower(), (arxiv_id or "").strip())
        seen_pairs.add(key)
        feedback.append(
            {
                "email": email or "-",
                "arxiv_id": arxiv_id,
                "liked": bool(liked),
                "timestamp": ts_dt.strftime("%Y-%m-%d %H:%M") if ts_dt else "-",
                "timestamp_raw": ts_dt or datetime.min,
                "source": source or "-",
            }
        )

    for entry in rows:
        _add_entry(entry.email, entry.arxiv_id, entry.liked, entry.timestamp, entry.source)

    # fall back to canonical preference data so local dev databases still show rows
    legacy_rows = (
        db.session.query(
            User.email.label("email"),
            Paper.arxiv_id.label("arxiv_id"),
            UserPreference.liked.label("liked"),
            UserPreference.created_at.label("timestamp"),
        )
        .join(UserPreference, UserPreference.user_id == User.id)
        .join(Paper, UserPreference.paper_id == Paper.id)
        .order_by(UserPreference.created_at.desc())
        .limit(200)
        .all()
    )

    for row in legacy_rows:
        key = ((row.email or "").strip().lower(), (row.arxiv_id or "").strip())
        if key in seen_pairs:
            continue
        _add_entry(row.email, row.arxiv_id, row.liked, row.timestamp, "recommendations")

    feedback.sort(key=lambda entry: entry["timestamp_raw"], reverse=True)
    for entry in feedback:
        entry.pop("timestamp_raw", None)

    return render_template("feedback.html", feedback=feedback)



# info page
@frontend.route("/info")
def info_page():
    """show information about the digest and usage."""
    sample_digest = [
        {
            "title": "probing dark matter substructure with lensed quasars",
            "category": "astro-ph.CO",
            "score": 3.0,
            "authors": "author 1, author 2, author 3",
            "summary": "concise analysis of strong-lensing flux anomalies as subhalo probes.",
        },
        {
            "title": "machine-learning forecasts for gravitational-wave events",
            "category": "astro-ph.IM",
            "score": 4.0,
            "authors": "author 1, author 2, author 3, author 4",
            "summary": "overview of a random-forest pipeline that predicts merger rates from detector telemetry.",
        },
        {
            "title": "turbulence-regulated star formation in molecular clouds",
            "category": "astro-ph.GA",
            "score": 2.0,
            "authors": "author 1, author 2",
            "summary": "simulation-driven insight into how feedback preserves Larson-like scaling.",
        },
    ]
    return render_template("info.html", sample_digest=sample_digest)
