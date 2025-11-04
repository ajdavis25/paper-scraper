async function sendReaction(title, reaction, btn) {
  btn.disabled = true;
  const paperDiv = btn.closest('.paper');
  paperDiv.style.opacity = 0.4;

  try {
    const res = await fetch('/api/recommendation-feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, reaction })
    });

    if (res.ok) {
      paperDiv.style.transition = "opacity 0.4s ease-out";
      paperDiv.style.opacity = 0;
      setTimeout(() => paperDiv.remove(), 400);
    } else {
      console.error('server error while sending reaction.');
      paperDiv.style.opacity = 1;
    }
  } catch (err) {
    console.error('network error:', err);
    paperDiv.style.opacity = 1;
  }
}
