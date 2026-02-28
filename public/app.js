const listEl = document.getElementById("list");
const countEl = document.getElementById("count");
const form = document.getElementById("memoryForm");
const contentInput = document.getElementById("contentInput");
const tagsInput = document.getElementById("tagsInput");
const editIdInput = document.getElementById("editId");
const submitBtn = document.getElementById("submitBtn");
const cancelBtn = document.getElementById("cancelBtn");
const reloadBtn = document.getElementById("reloadBtn");

function parseTags(value) {
  return value
    .split(",")
    .map((t) => t.trim())
    .filter((t) => t.length > 0);
}

function setEditMode(memory) {
  editIdInput.value = memory.id;
  contentInput.value = memory.content;
  tagsInput.value = (memory.tags || []).join(", ");
  submitBtn.textContent = "Сохранить";
  cancelBtn.classList.remove("hidden");
}

function clearEditMode() {
  editIdInput.value = "";
  contentInput.value = "";
  tagsInput.value = "";
  submitBtn.textContent = "Добавить";
  cancelBtn.classList.add("hidden");
}

async function fetchMemories() {
  const res = await fetch("/api/memories");
  if (!res.ok) {
    throw new Error("Failed to fetch memories");
  }
  return res.json();
}

function render(memories) {
  listEl.innerHTML = "";
  countEl.textContent = memories.length.toString();

  if (memories.length === 0) {
    const empty = document.createElement("div");
    empty.className = "card";
    empty.textContent = "Пока нет фактов. Добавьте первый.";
    listEl.appendChild(empty);
    return;
  }

  memories.forEach((memory) => {
    const card = document.createElement("div");
    card.className = "card";

    const content = document.createElement("div");
    content.textContent = memory.content;
    card.appendChild(content);

    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = memory.id;
    card.appendChild(meta);

    if (memory.tags && memory.tags.length > 0) {
      const tagRow = document.createElement("div");
      tagRow.className = "meta";
      memory.tags.forEach((tag) => {
        const chip = document.createElement("span");
        chip.className = "tag";
        chip.textContent = tag;
        tagRow.appendChild(chip);
      });
      card.appendChild(tagRow);
    }

    const actions = document.createElement("div");
    actions.className = "actions";

    const editBtn = document.createElement("button");
    editBtn.className = "btn ghost";
    editBtn.textContent = "Редактировать";
    editBtn.addEventListener("click", () => setEditMode(memory));
    actions.appendChild(editBtn);

    const deleteBtn = document.createElement("button");
    deleteBtn.className = "btn ghost";
    deleteBtn.textContent = "Удалить";
    deleteBtn.addEventListener("click", async () => {
      if (!confirm("Удалить факт?")) {
        return;
      }
      await fetch(`/api/memories/${memory.id}`, { method: "DELETE" });
      await load();
    });
    actions.appendChild(deleteBtn);

    card.appendChild(actions);
    listEl.appendChild(card);
  });
}

async function load() {
  try {
    const memories = await fetchMemories();
    render(memories);
  } catch (err) {
    listEl.innerHTML = "";
    const error = document.createElement("div");
    error.className = "card";
    error.textContent = "Ошибка загрузки.";
    listEl.appendChild(error);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const content = contentInput.value.trim();
  const tags = parseTags(tagsInput.value);
  if (!content) {
    alert("Введите текст факта");
    return;
  }

  const editId = editIdInput.value.trim();
  if (editId) {
    await fetch(`/api/memories/${editId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content, tags }),
    });
  } else {
    await fetch("/api/memories", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content, tags }),
    });
  }

  clearEditMode();
  await load();
});

cancelBtn.addEventListener("click", () => {
  clearEditMode();
});

reloadBtn.addEventListener("click", () => {
  load();
});

load();
