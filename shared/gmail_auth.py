from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]

flow = InstalledAppFlow.from_client_secrets_file("secrets/credentials.json", SCOPES)
creds = flow.run_local_server(port=8080)

# save the credentials to token.json
with open("token.json", "w") as token:
    token.write(creds.to_json())

print("token.json saved successfully.")
