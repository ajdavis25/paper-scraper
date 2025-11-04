console.log("recommendations.js loaded!");

document.addEventListener("click", (e) => {
  const btn = e.target;
  if (btn.classList.contains("like-btn") || btn.classList.contains("dislike-btn")) {
    const paperDiv = btn.closest(".paper");
    const title = paperDiv.dataset.title;
    const reaction = btn.classList.contains("like-btn") ? "like" : "dislike";
    sendReaction(title, reaction, btn);
  }
});

async function sendReaction(title, reaction, btn) {
  btn.disabled = true;
  const paperDiv = btn.closest(".paper");
  paperDiv.style.opacity = 0.4;

  try {
    const res = await fetch("/api/recommendation-feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, reaction }),
    });

    if (res.ok) {
      console.log(`recorded ${reaction} for`, title);
      paperDiv.style.transition = "opacity 0.4s ease-out";
      paperDiv.style.opacity = 0;
      setTimeout(() => paperDiv.remove(), 400);
    } else {
      console.error("server error while sending reaction.");
      paperDiv.style.opacity = 1;
    }
  } catch (err) {
    console.error("network error:", err);
    paperDiv.style.opacity = 1;
  }
}
