document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("prefs-form");
  const status = document.getElementById("save-status");

  form?.addEventListener("submit", async (e) => {
    e.preventDefault();

    const data = {
      keywords: document.getElementById("keywords").value.split(",").map(s => s.trim()).filter(Boolean),
      authors: document.getElementById("authors").value.split(",").map(s => s.trim()).filter(Boolean),
      min_score: parseFloat(document.getElementById("min_score").value) || 1.0,
    };

    try {
      const res = await fetch("/api/preferences", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      const json = await res.json();
      status.textContent = json.message || "saved!";
      status.style.color = "green";
    } catch (err) {
      console.error(err);
      status.textContent = "error saving preferences.";
      status.style.color = "red";
    }
  });
});
