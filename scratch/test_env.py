import smtplib, os
from dotenv import load_dotenv
load_dotenv()

EMAIL = os.getenv("EMAIL_FROM")
PASS = os.getenv("EMAIL_PASS")

with smtplib.SMTP("smtp.gmail.com", 587) as s:
    s.starttls()
    s.login(EMAIL, PASS)
    print("gmail login success!")
