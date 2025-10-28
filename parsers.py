import io, re, urllib.request
from pdfminer.high_level import extract_text

HEADERS = [r"conclusion[s]?", r"summary", r"concluding remarks", r"discussion"]


def try_extract_conclusion(pdf_url, char_limit=1200):
    try:
        with urllib.request.urlopen(pdf_url, timeout=20) as resp:
            data = resp.read()
        text = extract_text(io.BytesIO(data))
        txt = re.sub(r"[ \t]+", " ", text)
        # look for a header
        for h in HEADERS:
            m = re.search(rf"\n\s*{h}\s*\n", txt, flags=re.IGNORECASE)
            if m:
                start = m.end()
                # cut until next all-caps header or references
                tail = txt[start:]
                stop = re.search(r"\n\s*(references|acknowledg(e)?ments|appendix|section\s+\d)\b",
                                 tail, flags=re.IGNORECASE)
                body = tail[: stop.start()] if stop else tail
                body = body.strip()
                # take first couple of sentences
                body = " ".join(body.split())[:char_limit]
                return body
        # fallback: last paragraph of abstract handled upstream
        return ""
    except Exception:
        return ""
