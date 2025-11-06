import sys, os, traceback

# make sure vercel's lambda can see the webapp/ package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
print("=== PATH FIXED ===", file=sys.stderr)

try:
    from webapp import create_app
    print("=== IMPORTED WEBAPP SUCCESSFULLY ===", file=sys.stderr)

    app = create_app()
    application = app  # for vercel/werkzeug
    print("=== APP CREATED SUCCESSFULLY ===", file=sys.stderr)

except Exception:
    print("=== SERVERLESS STARTUP CRASH ===", file=sys.stderr)
    traceback.print_exc()
    raise
