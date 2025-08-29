document.addEventListener('DOMContentLoaded', () => {
  const fileInput = document.getElementById('file-upload');
  const hungryMonster = document.getElementById('monster-hungry');
  const yummyMonster = document.getElementById('monster-yummy');
  const statusText = document.getElementById('status-text');
  const reuploadBtn = document.getElementById('reupload-btn');
  const uploadArea = document.getElementById('upload-area');
  const toast = document.getElementById('toast');
  const uploadForm = document.getElementById('upload-form');

  uploadForm.addEventListener('submit', e => e.preventDefault());

  function showToast(message, type = "success") {
    toast.textContent = message;
    toast.style.backgroundColor = type === "error"
      ? "rgba(220, 38, 38, 0.9)"
      : "rgba(34, 197, 94, 0.9)";
    toast.classList.remove("hidden");
    toast.classList.add("show");

    setTimeout(() => {
      toast.classList.remove("show");
      setTimeout(() => toast.classList.add("hidden"), 500);
    }, 2500);
  }

  function setMonsterEating() {
    hungryMonster.classList.remove('hidden');
    yummyMonster.classList.add('hidden');
    statusText.textContent = 'Nom nom...';
  }

  function setMonsterYummy() {
    hungryMonster.classList.add('hidden');
    yummyMonster.classList.remove('hidden');
    statusText.textContent = 'Yummy!';
    uploadArea.classList.add('hidden');
    reuploadBtn.classList.remove('hidden');
  }

  function setMonsterHungry() {
    hungryMonster.classList.remove('hidden');
    yummyMonster.classList.add('hidden');
    statusText.textContent = 'Feed Me!';
    uploadArea.classList.remove('hidden');
    reuploadBtn.classList.add('hidden');
    fileInput.value = '';
  }

  fileInput.addEventListener('change', async e => {
    const file = e.target.files[0];
    if (!file) return;

    // 🟢 Start chewing immediately
    setMonsterEating();

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('http://127.0.0.1:5000/upload', {
        method: 'POST',
        body: formData
      });

      const result = await response.json();

      // 🟢 Force delay: chew for 2s even if upload finished instantly
      setTimeout(() => {
        setMonsterYummy();

        if (response.ok) {
          showToast(result.message, "success");
        } else {
          showToast("Upload failed: " + (result.error || "Unknown error"), "error");
        }
      }, 2000); // adjust chewing duration here
    } catch (err) {
      console.error(err);

      setTimeout(() => {
        setMonsterYummy();
        showToast("Network error or backend not running.", "error");
      }, 2000);
    }
  });

  reuploadBtn.addEventListener('click', e => {
    e.preventDefault();
    setMonsterHungry();
  });
});
