console.log("recommendations.js loaded!");

// helper: get current logged-in user email
// (flask template should define this variable)
const CURRENT_USER_EMAIL = window.CURRENT_USER_EMAIL || "";


// attach one listener for all like/dislike buttons
document.addEventListener("click", (e) => {
  const btn = e.target.closest(".like-btn, .dislike-btn");
  if (!btn) return;

  const paperDiv = btn.closest(".paper");
  const title = paperDiv.dataset.title;
  const link = paperDiv.dataset.link;
  const liked = btn.classList.contains("like-btn");

  sendReaction({ title, link, liked, btn, paperDiv });
});


function typesetMath() {
  if (window.MathJax?.typesetPromise) {
    MathJax.typesetPromise().catch((err) =>
      console.warn("[mathjax] typeset error:", err)
    );
  }
}

if (document.readyState === "complete") {
  typesetMath();
} else {
  window.addEventListener("load", typesetMath);
}


// main async sender
async function sendReaction({ title, link, liked, btn, paperDiv }) {
  btn.disabled = true;
  paperDiv.style.opacity = 0.4;

  // build payload to match flask /api/recommendation-feedback
  const payload = {
    email: CURRENT_USER_EMAIL,   // required by flask
    link: link,
    reaction: liked,             // boolean, not string
    title: title || ""
  };

  try {
    const res = await fetch("/api/recommendation-feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (res.ok) {
      console.log(`[feedback] recorded ${liked ? "like" : "dislike"} for`, link);
      paperDiv.style.transition = "opacity 0.4s ease-out";
      paperDiv.style.opacity = 0;
      setTimeout(() => paperDiv.remove(), 400);
    } else {
      const errText = await res.text();
      console.error("server error while sending reaction:", errText);
      paperDiv.style.opacity = 1;
      btn.disabled = false;
    }
  } catch (err) {
    console.error("network error:", err);
    paperDiv.style.opacity = 1;
    btn.disabled = false;
  }
}
