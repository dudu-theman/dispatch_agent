// Minimal chat client for the Dispatch Agent API. The conversation id from
// POST /conversations is the only session state; it lives in memory, so a reload
// or "New chat" starts over.
const API_URL = "http://localhost:8000";

const messages = document.getElementById("messages");
const form = document.getElementById("composer");
const input = document.getElementById("input");
const sendButton = form.querySelector("button");

let conversationId = null;

function add(text, ...classes) {
  const li = document.createElement("li");
  li.className = ["msg", ...classes].join(" ");
  li.textContent = text;
  messages.append(li);
  li.scrollIntoView({ block: "end" });
  return li;
}

function setEnabled(enabled) {
  input.disabled = sendButton.disabled = !enabled;
  if (enabled) input.focus();
}

async function post(path, body) {
  const response = await fetch(API_URL + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body && JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
  return data;
}

function field(dl, label, value) {
  if (!value) return;
  const dt = document.createElement("dt");
  const dd = document.createElement("dd");
  dt.textContent = label;
  dd.textContent = value;
  dl.append(dt, dd);
}

function showLead(lead) {
  const li = add("", "lead");
  const dl = document.createElement("dl");
  field(dl, "Problem", lead.problem_summary);
  field(dl, "Category", lead.category);
  field(dl, "Urgency", lead.urgency);
  field(dl, "ZIP", lead.zip_code);
  field(dl, "Contact", `${lead.contact_name} · ${lead.contact_phone}`);
  li.append(dl);

  if (!lead.providers.length) return;
  const heading = document.createElement("h2");
  heading.textContent = "Providers";
  li.append(heading);
  for (const p of lead.providers) {
    const div = document.createElement("div");
    div.className = "provider";
    const name = document.createElement("strong");
    name.textContent = p.name;
    const meta = document.createElement("span");
    meta.textContent = `★ ${p.rating} (${p.review_count} reviews) · ${p.distance_miles.toFixed(1)} mi · ${p.phone}`;
    div.append(name, meta);
    if (p.website) {
      const link = document.createElement("a");
      link.href = p.website;
      link.target = "_blank";
      link.rel = "noopener";
      link.textContent = " Website";
      div.append(link);
    }
    li.append(div);
  }
  li.scrollIntoView({ block: "end" });
}

async function startChat() {
  conversationId = null;
  messages.replaceChildren();
  setEnabled(false);
  try {
    const started = await post("/conversations");
    conversationId = started.conversation_id;
    add(started.message, "agent");
    setEnabled(true);
  } catch (err) {
    add(`Couldn't reach the API: ${err.message}`, "error");
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text || !conversationId) return;
  input.value = "";
  add(text, "user");
  setEnabled(false);
  const pending = add("…", "agent", "pending");
  try {
    const turn = await post(`/conversations/${conversationId}/messages`, { message: text });
    pending.remove();
    add(turn.message, "agent", ...(turn.safety_alert ? ["alert"] : []));
    if (turn.type === "lead") {
      showLead(turn.lead);
      return; // the conversation is closed; "New chat" starts another
    }
    setEnabled(true);
  } catch (err) {
    pending.remove();
    add(err.message, "error");
    setEnabled(true);
  }
});

document.getElementById("new-chat").addEventListener("click", startChat);
startChat();
