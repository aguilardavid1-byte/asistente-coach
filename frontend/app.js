/* ═══════════════════════════════════════════════════
   Asistente Coach V2 — Frontend JavaScript
   ═══════════════════════════════════════════════════ */

(function () {
  "use strict";

  /* ─── DOM Refs ─────────────────────────────────── */
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => [...document.querySelectorAll(sel)];

  const navEl = $("#nav");
  const messagesEl = $("#messages");
  const chatTitleEl = $("#chat-title");
  const chatSubtitleEl = $("#chat-subtitle");
  const inputEl = $("#message-input");
  const sendBtn = $("#send-btn");
  const attachBtn = $("#attach-btn");
  const fileInput = $("#file-input");
  const previewEl = $("#image-preview");
  const previewImg = $("#preview-img");
  const removeImgBtn = $("#remove-image-btn");

  const hamburgerBtn = $("#hamburger-btn");
  const sidebarEl = $("#sidebar");
  const overlayEl = $("#sidebar-overlay");

  let currentChatId = null;
  let streaming = false;
  let imageBase64 = null;

  /* ─── Helpers ──────────────────────────────────── */
  function escHtml(str) {
    const d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML;
  }

  function mdToHtml(text) {
    let html = escHtml(text);
    // Bold: **text**
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // Italic: *text*
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
    // Headers: ## text, ### text
    html = html.replace(/^### (.+)$/gm, '<h5>$1</h5>');
    html = html.replace(/^## (.+)$/gm, '<h4>$1</h4>');
    // Inline code: `text`
    html = html.replace(/`(.+?)`/g, '<code>$1</code>');
    // Unordered list: - item or * item
    html = html.replace(/^[-*] (.+)$/gm, '\u2022 $1');
    // Horizontal rules
    html = html.replace(/^---+$/gm, '<hr>');
    // Newlines
    html = html.replace(/\n/g, '<br>');
    return html;
  }

  function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function now() {
    return new Date().toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit" });
  }

  /* ─── API ──────────────────────────────────────── */
  async function apiNav() {
    const r = await fetch("/api/nav");
    return r.json();
  }

  async function apiChat(id) {
    const r = await fetch(`/api/chat/${id}`);
    if (!r.ok) throw new Error("Chat no encontrado");
    return r.json();
  }

  /* ─── Image handling ──────────────────────────── */
  attachBtn.addEventListener("click", () => fileInput.click());

  fileInput.addEventListener("change", () => {
    const file = fileInput.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      imageBase64 = e.target.result;
      previewImg.src = imageBase64;
      previewEl.classList.remove("hidden");
    };
    reader.readAsDataURL(file);
  });

  removeImgBtn.addEventListener("click", () => {
    imageBase64 = null;
    previewEl.classList.add("hidden");
    previewImg.src = "";
    fileInput.value = "";
  });

  /* ─── Paste image support ─────────────────────── */
  document.addEventListener("paste", (e) => {
    const items = (e.clipboardData || e.originalEvent?.clipboardData)?.items;
    if (!items) return;

    for (const item of items) {
      if (!item.type.startsWith("image/")) continue;

      // Focus check: solo pegar si el foco está en el input o en el chat area
      const active = document.activeElement;
      const isChatFocused = active === inputEl || active === messagesEl || active?.closest("#chat-area");
      if (!isChatFocused) continue;

      e.preventDefault();
      const blob = item.getAsFile();
      if (!blob) break;

      const reader = new FileReader();
      reader.onload = (evt) => {
        imageBase64 = evt.target.result;
        previewImg.src = imageBase64;
        previewEl.classList.remove("hidden");
        inputEl.focus();

        // Notificación visual temporal
        const note = document.createElement("div");
        note.id = "paste-notification";
        note.textContent = "📎 Imagen lista para enviar";
        document.body.appendChild(note);
        setTimeout(() => note.remove(), 3000);
      };
      reader.readAsDataURL(blob);
      break; // Solo la primera imagen
    }
  });

  /* ─── Render Nav ──────────────────────────────── */
  function renderNav(data) {
    navEl.innerHTML = "";

    // ── Chats directos ──
    if (data.chats_directos && data.chats_directos.length) {
      const section = document.createElement("div");
      section.className = "nav-section";
      section.innerHTML = `<span class="nav-section-title">Conversaciones</span>`;

      for (const c of data.chats_directos) {
        const item = document.createElement("div");
        item.className = "nav-item";
        item.dataset.chatId = c.id;
        item.innerHTML = `
          <span class="icon">💬</span>
          <span class="label">${escHtml(c.nombre)}</span>
        `;
        if (c.id === currentChatId) item.classList.add("active");
        item.addEventListener("click", () => selectChat(c.id, c.nombre));
        section.appendChild(item);
      }
      navEl.appendChild(section);
    }

    // ── Grupos ──
    if (data.grupos && data.grupos.length) {
      const section = document.createElement("div");
      section.className = "nav-section";
      section.innerHTML = `<span class="nav-section-title">Grupos</span>`;

      for (const g of data.grupos) {
        renderGrupo(section, g, 0);
      }
      navEl.appendChild(section);
    }

  function renderGrupo(container, g, depth) {
    const hasChat = g.chat_id != null;
    const isSubgrupo = depth > 0;
    const header = document.createElement("div");
    header.className = "nav-grupo-header" + (isSubgrupo ? " nav-subgrupo-header" : "");
    if (hasChat) header.style.cursor = "pointer";
    header.innerHTML = `
      <span class="arrow collapsed">▼</span>
      <span class="icon">${escHtml(g.icono || "📁")}</span>
      <span class="label">${escHtml(g.nombre)}</span>
      ${g.tareas_pendientes > 0 ? `<span class="badge">${g.tareas_pendientes}</span>` : ""}
    `;

    const children = document.createElement("div");
    children.className = "nav-grupo-children collapsed";

    // Subgrupos anidados
    if (g.subgrupos && g.subgrupos.length) {
      for (const sg of g.subgrupos) {
        renderGrupo(children, sg, depth + 1);
      }
    }

    // Tareas directas
    if (g.chats && g.chats.length) {
      for (const ct of g.chats) {
        const item = document.createElement("div");
        const prioridadCls = `prioridad-${ct.prioridad || "media"}`;
        item.className = `nav-item ${prioridadCls}`;
        if (isSubgrupo) item.classList.add("nav-item-sub");
        item.dataset.chatId = ct.id;
        item.innerHTML = `
          <span class="estado-dot ${ct.estado || "pendiente"}"></span>
          <span class="label">${escHtml(ct.nombre)}</span>
        `;
        if (ct.id === currentChatId) item.classList.add("active");
        item.addEventListener("click", (e) => {
          e.stopPropagation();
          selectChat(ct.id, ct.nombre);
        });
        children.appendChild(item);
      }
    }

    let isOpen = false;
    function toggle() {
      isOpen = !isOpen;
      header.querySelector(".arrow").classList.toggle("collapsed", !isOpen);
      if (isOpen) {
        children.classList.remove("collapsed");
        children.style.maxHeight = "";
      } else {
        children.style.maxHeight = children.scrollHeight + "px";
        requestAnimationFrame(() => {
          children.classList.add("collapsed");
          children.style.maxHeight = "0";
        });
      }
    }
    header.addEventListener("click", (e) => {
      if (e.target.closest(".arrow")) {
        toggle();
        return;
      }
      if (hasChat) {
        selectChat(g.chat_id, g.nombre);
      }
      if (!isOpen) toggle();
    });

    container.appendChild(header);
    container.appendChild(children);
  }

    // ── Tareas sueltas ──
    if (data.tareas_sueltas && data.tareas_sueltas.length) {
      const section = document.createElement("div");
      section.className = "nav-section";
      section.innerHTML = `<span class="nav-section-title">Tareas sueltas</span>`;

      for (const t of data.tareas_sueltas) {
        const item = document.createElement("div");
        const prioridadCls = `prioridad-${t.prioridad || "media"}`;
        item.className = `nav-item ${prioridadCls}`;
        item.dataset.chatId = t.id;
        item.innerHTML = `
          <span class="estado-dot ${t.estado || "pendiente"}"></span>
          <span class="label">${escHtml(t.nombre)}</span>
        `;
        if (t.id === currentChatId) item.classList.add("active");
        item.addEventListener("click", () => selectChat(t.id, t.nombre));
        section.appendChild(item);
      }
      navEl.appendChild(section);
    }
  }

  /* ─── Select Chat ─────────────────────────────── */
  async function selectChat(chatId, nombre) {
    if (chatId === currentChatId) return;
    if (streaming) return;

    // Cerrar sidebar en móvil
    if (window.innerWidth <= 640) {
      sidebarEl.classList.remove("open");
      overlayEl.classList.remove("visible");
    }

    currentChatId = chatId;
    chatTitleEl.textContent = nombre;

    // Update active state in nav
    $$(".nav-item.active").forEach((el) => el.classList.remove("active"));
    const activeItem = document.querySelector(`.nav-item[data-chat-id="${chatId}"]`);
    if (activeItem) activeItem.classList.add("active");

    // Load messages
    messagesEl.innerHTML = '<div class="empty-state">Cargando...</div>';

    try {
      const data = await apiChat(chatId);
      chatTitleEl.textContent = data.nombre || nombre;

      // Subtitle based on chat type
      if (data.tipo === "tarea" && data.ref_id) {
        chatSubtitleEl.textContent = "Tarea • Conversación contextual";
      } else if (data.tipo === "grupo") {
        chatSubtitleEl.textContent = "Grupo • Conversación grupal";
      } else {
        chatSubtitleEl.textContent = "Coach personal";
      }

      messagesEl.innerHTML = "";
      if (data.mensajes && data.mensajes.length) {
        for (const m of data.mensajes) {
          const imgUrl = (m.tiene_imagen && m.tiene_imagen !== "0") ? ("/imagenes/" + m.tiene_imagen) : null;
          appendMessage(m.rol, m.contenido, false, imgUrl);
        }
      } else {
        messagesEl.innerHTML = '<div class="empty-state">No hay mensajes aún</div>';
      }
      scrollToBottom();
    } catch (err) {
      messagesEl.innerHTML = `<div class="empty-state">Error: ${err.message}</div>`;
    }
  }

  /* ─── Append Message ──────────────────────────── */
  function appendMessage(rol, contenido, animate = false, imagenBase64 = null) {
    // Remove empty state
    const empty = messagesEl.querySelector(".empty-state");
    if (empty) empty.remove();

    // Remove typing indicator from previous assistant messages
    if (rol === "assistant") {
      const typing = messagesEl.querySelector(".typing-indicator");
      if (typing) typing.remove();
    }

    const div = document.createElement("div");
    div.className = `bubble ${rol}`;

    // Show image if present
    if (imagenBase64) {
      const img = document.createElement("img");
      img.className = "msg-image";
      img.src = imagenBase64;
      div.appendChild(img);
    }
    const textDiv = document.createElement("div");
    textDiv.innerHTML = mdToHtml(contenido);
    div.appendChild(textDiv);

    const time = document.createElement("span");
    time.className = "time";
    time.textContent = now();
    div.appendChild(time);

    if (animate) {
      div.style.opacity = "0";
      div.style.transform = "translateY(8px)";
      messagesEl.appendChild(div);
      requestAnimationFrame(() => {
        div.style.transition = "opacity 0.2s, transform 0.2s";
        div.style.opacity = "1";
        div.style.transform = "translateY(0)";
      });
    } else {
      messagesEl.appendChild(div);
    }
    scrollToBottom();
  }

  /* ─── Show typing indicator ───────────────────── */
  function showTyping() {
    const div = document.createElement("div");
    div.className = "bubble assistant typing-indicator";
    div.innerHTML = `<div class="typing"><span></span><span></span><span></span></div>`;
    messagesEl.appendChild(div);
    scrollToBottom();
  }

  function addStatusBar(text) {
    const existing = document.getElementById("status-bar");
    if (existing) existing.remove();
    const bar = document.createElement("div");
    bar.id = "status-bar";
    bar.className = "status-bar";
    bar.textContent = text;
    const inputBar = document.getElementById("input-bar");
    if (inputBar) {
      inputBar.parentNode.insertBefore(bar, inputBar);
    }
    scrollToBottom();
  }

  function removeStatusBar() {
    const bar = document.getElementById("status-bar");
    if (bar) bar.remove();
  }

  /* ─── SSE Streaming ───────────────────────────── */
  async function connectSSE(chatId, message, imgB64) {
    const response = await fetch("/api/chat/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id: chatId,
        mensaje: message,
        imagen_base64: imgB64 || null,
      }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({ error: "Error del servidor" }));
      appendMessage("assistant", `[Error: ${err.error || "Error de conexión"}]`);
      return 0;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let fullText = "";
    let assistantBubble = null;
    let nuevasTareas = 0;

    addStatusBar('Procesando con Gemini y DeepSeek...');
    showTyping();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n");
      buffer = parts.pop() || "";

      for (const line of parts) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data: ")) continue;

        try {
          const data = JSON.parse(trimmed.slice(6));

          if (data.tipo === "confirmaciones") {
            // Mostrar confirmaciones PRIMERO (antes del mensaje del coach)
            const confirmaciones = data.confirmaciones || [];
            if (confirmaciones.length > 0) {
              const box = document.createElement("div");
              box.className = "confirmacion-box";
              confirmaciones.forEach((c) => {
                const item = document.createElement("div");
                item.className = c.exito ? "confirm-exito" : "confirm-error";
                item.textContent = (c.exito ? "✓ " : "✗ ") + c.texto;
                box.appendChild(item);
              });
              messagesEl.appendChild(box);
              scrollToBottom();
            }
          } else if (data.tipo === "chunk") {
            // Remove typing indicator on first chunk
            if (!assistantBubble) {
              const typing = messagesEl.querySelector(".typing-indicator");
              if (typing) typing.remove();

              removeStatusBar();
              assistantBubble = document.createElement("div");
              assistantBubble.className = "bubble assistant";
              messagesEl.appendChild(assistantBubble);
            }

            fullText += data.texto;
            assistantBubble.innerHTML =
              mdToHtml(fullText);
            scrollToBottom();
          } else if (data.tipo === "fin") {
            removeStatusBar();
            nuevasTareas = data.tareas_nuevas || 0;

            // Add timestamp
            if (assistantBubble) {
              const time = document.createElement("span");
              time.className = "time";
              time.textContent = now();
              assistantBubble.appendChild(time);
            }
          } else if (data.tipo === "error") {
            const typing = messagesEl.querySelector(".typing-indicator");
            if (typing) typing.remove();
            removeStatusBar();
            appendMessage("assistant", `[Error: ${data.texto}]`);
          }
        } catch (e) {
          // Skip malformed JSON
        }
      }
    }

    // If streaming ended but no chunks came, finalize
    if (!assistantBubble && !messagesEl.querySelector(".typing-indicator")) {
      // Stream ended without content — do nothing
    }

    return nuevasTareas;
  }

  /* ─── Send Message ────────────────────────────── */
  async function sendMessage() {
    const message = inputEl.value.trim();
    if (!message && !imageBase64) return;
    if (!currentChatId) return;
    if (streaming) return;

    streaming = true;
    sendBtn.disabled = true;
    sendBtn.textContent = "...";
    inputEl.disabled = true;
    inputEl.placeholder = "Procesando...";

    // Show user message with image if present
    const imgToSend = imageBase64;
    appendMessage("user", message || "(imagen)", false, imgToSend);
    inputEl.value = "";

    if (imageBase64) {
      previewEl.classList.add("hidden");
      previewImg.src = "";
      fileInput.value = "";
      imageBase64 = null;
    }

    try {
      const nuevas = await connectSSE(currentChatId, message, imgToSend);

      // Siempre refrescar la nav: pueden haber ocurrido cambios estructurales
      // (eliminar, mover) además de creación de tareas
      const navData = await apiNav();
      renderNav(navData);
    } catch (err) {
      removeStatusBar();
      appendMessage("assistant", `[Error de conexión: ${err.message}]`);
    } finally {
      streaming = false;
      sendBtn.disabled = false;
      sendBtn.textContent = "Enviar";
      inputEl.disabled = false;
      inputEl.placeholder = "Escribe un mensaje...";
      inputEl.focus();
    }
  }

  /* ─── Hamburger menu ──────────────────────────── */
  if (hamburgerBtn) {
    hamburgerBtn.addEventListener("click", () => {
      sidebarEl.classList.toggle("open");
      overlayEl.classList.toggle("visible");
    });
    overlayEl.addEventListener("click", () => {
      sidebarEl.classList.remove("open");
      overlayEl.classList.remove("visible");
    });
  }

  /* ─── Event Listeners ──────────────────────────── */
  sendBtn.addEventListener("click", sendMessage);

  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  /* ─── Profile / Logout ──────────────────────────── */
  async function cargarPerfil() {
    try {
      const r = await fetch("/auth/me");
      if (!r.ok) return;
      const data = await r.json();
      document.getElementById("user-name").textContent = data.nombre || data.email || "";
    } catch {}
  }

  document.getElementById("logout-btn").addEventListener("click", () => {
    window.location.href = "/auth/logout";
  });

  /* ─── Init ─────────────────────────────────────── */
  async function init() {
    try {
      await cargarPerfil();
      const navData = await apiNav();
      renderNav(navData);

      // Load first chat (General)
      if (navData.chats_directos && navData.chats_directos.length) {
        const first = navData.chats_directos[0];
        await selectChat(first.id, first.nombre);
      }
    } catch (err) {
      messagesEl.innerHTML = `<div class="empty-state">Error al cargar: ${err.message}</div>`;
    }
  }

  init();
})();
