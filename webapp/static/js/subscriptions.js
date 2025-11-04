document.addEventListener("DOMContentLoaded", () => {
  const form =
    document.querySelector("#subscribe-form") ||
    document.querySelector("#unsubscribe-form");

  if (!form) return;

  const msgBox = document.createElement("p");
  msgBox.id = "sub-status";
  msgBox.style.opacity = 0;
  msgBox.style.transition = "opacity 0.6s ease-in-out";
  msgBox.style.marginTop = "1em";
  form.after(msgBox);

  const showMessage = (text, color) => {
    msgBox.textContent = text;
    msgBox.style.color = color;
    msgBox.style.opacity = 1;
    setTimeout(() => (msgBox.style.opacity = 0), 3000);
  };

  form.addEventListener("submit", (e) => {
    e.preventDefault();  // prevent full page reload

    const email = form.querySelector("input[name='email']").value.trim();
    if (!email) return showMessage("please enter your email", "red");

    fetch(window.location.pathname, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    })
      .then((r) => r.json())
      .then((data) => {
        const color =
          data.status === "success"
            ? "green"
            : data.status === "info"
            ? "#555"
            : "red";
        showMessage(data.message, color);
        form.reset();
      })
      .catch(() => showMessage("server error — try again later.", "red"));
  });
});
