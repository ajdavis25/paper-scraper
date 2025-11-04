from flask import Blueprint, render_template, request, redirect, url_for, flash
import os, yaml

frontend = Blueprint("frontend", __name__, template_folder="templates")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "../astroph-bot/config.yaml")


@frontend.route("/")
def index():
    return render_template("index.html")


@frontend.route("/subscribe", methods=["GET", "POST"])
def subscribe():
    if request.method == "POST":
        email = request.form.get("email")
        if not email:
            flash("please enter an email.", "error")
            return redirect(url_for("frontend.index"))

        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        to_addrs = cfg["output"]["email"]["to_addrs"]

        if email not in to_addrs:
            to_addrs.append(email)
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                yaml.safe_dump(cfg, f)
            flash("subscribed successfully!", "success")
        else:
            flash("you're already subscribed.", "info")

        return redirect(url_for("frontend.index"))
    return render_template("subscribe.html")


@frontend.route("/unsubscribe", methods=["GET", "POST"])
def unsubscribe():
    if request.method == "POST":
        email = request.form.get("email")

        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        to_addrs = cfg["output"]["email"]["to_addrs"]

        if email in to_addrs:
            to_addrs.remove(email)
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                yaml.safe_dump(cfg, f)
            flash("unsubscribed successfully.", "success")
        else:
            flash("email not found in the list.", "error")

        return redirect(url_for("frontend.index"))
    return render_template("unsubscribe.html")
