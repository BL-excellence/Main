// Utility Functions
const Utils = {
  getCookie(name) {
    let cookieValue = null
    if (document.cookie && document.cookie !== "") {
      const cookies = document.cookie.split(";")
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim()
        if (cookie.substring(0, name.length + 1) === name + "=") {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1))
          break
        }
      }
    }
    return cookieValue
  },

  showToast(type, message) {
    // Create toast if it doesn't exist
    let toast = document.getElementById("toast")
    if (!toast) {
      toast = document.createElement("div")
      toast.id = "toast"
      toast.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 1rem 1.5rem;
        border-radius: 12px;
        font-weight: 600;
        z-index: 9999;
        display: none;
        animation: slideIn 0.3s ease;
      `
      document.body.appendChild(toast)
    }

    const styles = {
      success: "background: #10b981; color: white;",
      error: "background: #ef4444; color: white;",
      info: "background: #0ea5e9; color: white;",
    }

    toast.style.cssText += styles[type] || styles.info
    toast.textContent = message
    toast.style.display = "block"

    setTimeout(() => {
      toast.style.display = "none"
    }, 3000)
  },
}

// File Upload Handler
class FileUploadHandler {
  constructor(dropZoneId, fileInputId, fileInfoId) {
    this.dropZone = document.getElementById(dropZoneId)
    this.fileInput = document.getElementById(fileInputId)
    this.fileInfo = document.getElementById(fileInfoId)

    if (this.dropZone && this.fileInput) {
      this.init()
    }
  }

  init() {
    // Prevent default drag behaviors
    ;["dragenter", "dragover", "dragleave", "drop"].forEach((eventName) => {
      this.dropZone.addEventListener(eventName, this.preventDefaults, false)
      document.body.addEventListener(eventName, this.preventDefaults, false)
    })

    // Highlight drop zone
    ;["dragenter", "dragover"].forEach((eventName) => {
      this.dropZone.addEventListener(eventName, () => this.highlight(), false)
    })
    ;["dragleave", "drop"].forEach((eventName) => {
      this.dropZone.addEventListener(eventName, () => this.unhighlight(), false)
    })

    // Handle drop
    this.dropZone.addEventListener("drop", (e) => this.handleDrop(e), false)

    // Handle click
    this.dropZone.addEventListener("click", () => this.fileInput.click())

    // Handle file selection
    this.fileInput.addEventListener("change", (e) => this.handleFiles(e.target.files), false)
  }

  preventDefaults(e) {
    e.preventDefault()
    e.stopPropagation()
  }

  highlight() {
    this.dropZone.classList.add("dragover")
  }

  unhighlight() {
    this.dropZone.classList.remove("dragover")
  }

  handleDrop(e) {
    const dt = e.dataTransfer
    const files = dt.files
    this.handleFiles(files)
  }

  handleFiles(files) {
    if (files.length === 0) return

    const file = files[0]
    const allowedTypes = ["application/pdf", "application/zip", "application/x-zip-compressed"]

    if (!allowedTypes.includes(file.type)) {
      Utils.showToast("error", "Veuillez sélectionner un fichier PDF ou ZIP.")
      return
    }

    // Set the file to the input
    const dataTransfer = new DataTransfer()
    dataTransfer.items.add(file)
    this.fileInput.files = dataTransfer.files

    // Update UI
    this.dropZone.classList.add("has-file")
    if (this.fileInfo) {
      this.fileInfo.textContent = `Fichier sélectionné: ${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)`
    }
  }
}

// Metadata Manager
class MetadataManager {
  constructor(formId, docId) {
    this.form = document.getElementById(formId)
    this.docId = docId
  }

  async reextract() {
    if (!this.docId) {
      Utils.showToast("error", "Le document doit être sauvegardé avant de réextraire.")
      return
    }

    if (!confirm("Relancer l'extraction automatique ?")) return

    try {
      const response = await fetch(`/edit/${this.docId}/reextract/`, {
        method: "POST",
        headers: { "X-CSRFToken": Utils.getCookie("csrftoken") },
      })

      const data = await response.json()

      if (!data.success) {
        Utils.showToast("error", data.error || "Erreur lors de la réextraction")
        return
      }

      // Update form fields
      const metadata = data.metadata || {}
      this.updateFormFields(metadata)
      Utils.showToast("success", "Réextraction terminée et champs mis à jour")
    } catch (error) {
      Utils.showToast("error", "Erreur réseau: " + error.message)
    }
  }

  updateFormFields(metadata) {
    const fields = [
      "title",
      "type",
      "context",
      "language",
      "publication_date",
      "version",
      "source",
      "url_source",
      "country",
    ]

    fields.forEach((field) => {
      const input = document.querySelector(`[name="${field}"]`)
      if (input && metadata[field]) {
        input.value = metadata[field]
      }
    })
  }

  async save() {
    if (!this.form) return

    const formData = new FormData(this.form)

    try {
      const response = await fetch(this.form.action, {
        method: "POST",
        body: formData,
        headers: { "X-CSRFToken": Utils.getCookie("csrftoken") },
      })

      if (response.ok) {
        Utils.showToast("success", "Métadonnées sauvegardées avec succès")
      } else {
        Utils.showToast("error", "Erreur lors de la sauvegarde")
      }
    } catch (error) {
      Utils.showToast("error", "Erreur réseau: " + error.message)
    }
  }
}

// Custom Fields Manager
class CustomFieldsManager {
  constructor(containerId) {
    this.container = document.getElementById(containerId)
  }

  addField(name, type, value = "") {
    if (!this.container || document.getElementById(`custom_${name}`)) return

    const fieldDiv = document.createElement("div")
    fieldDiv.className = "form-field"

    const safeValue = this.escapeHtml(value)
    let inputHtml = ""

    switch (type) {
      case "textarea":
        inputHtml = `<textarea name="custom_${name}" id="custom_${name}" class="form-input" rows="3" placeholder="${name}">${safeValue}</textarea>`
        break
      case "date":
        inputHtml = `<input type="date" name="custom_${name}" id="custom_${name}" value="${safeValue}" class="form-input">`
        break
      case "number":
        inputHtml = `<input type="number" name="custom_${name}" id="custom_${name}" value="${safeValue}" class="form-input">`
        break
      default:
        inputHtml = `<input type="text" name="custom_${name}" id="custom_${name}" value="${safeValue}" class="form-input" placeholder="${name}">`
    }

    fieldDiv.innerHTML = `
      <label class="field-label" for="custom_${name}">
        <i class="fas fa-plus"></i>
        ${name}
        <span class="auto-badge">Personnalisé</span>
      </label>
      ${inputHtml}
    `

    this.container.appendChild(fieldDiv)
  }

  async saveField(name, type, docId) {
    try {
      const response = await fetch("/add-field/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": Utils.getCookie("csrftoken"),
        },
        body: JSON.stringify({ name, type, doc_id: docId }),
      })

      const data = await response.json()

      if (data.success) {
        this.addField(name, type)
        Utils.showToast("success", data.message)
        return true
      } else {
        Utils.showToast("error", data.message)
        return false
      }
    } catch (error) {
      Utils.showToast("error", "Erreur réseau: " + error.message)
      return false
    }
  }

  escapeHtml(text) {
    const div = document.createElement("div")
    div.textContent = text
    return div.innerHTML
  }
}

// Modal Manager
class ModalManager {
  static show(config) {
    const { title, message, icon, iconClass, onConfirm, onCancel } = config

    const modal = document.createElement("div")
    modal.className = "modal-overlay active"
    modal.innerHTML = `
      <div class="modal">
        <i class="fas ${icon} modal-icon ${iconClass}"></i>
        <h3 class="modal-title">${title}</h3>
        <p class="modal-text">${message}</p>
        <div class="modal-actions">
          <button class="btn btn-primary" id="modalConfirm">Oui</button>
          <button class="btn btn-outline" id="modalCancel">Non</button>
        </div>
      </div>
    `

    document.body.appendChild(modal)

    document.getElementById("modalConfirm").addEventListener("click", () => {
      if (onConfirm) onConfirm()
      modal.remove()
    })

    document.getElementById("modalCancel").addEventListener("click", () => {
      if (onCancel) onCancel()
      modal.remove()
    })

    modal.addEventListener("click", (e) => {
      if (e.target === modal) {
        if (onCancel) onCancel()
        modal.remove()
      }
    })
  }

  static showValidation(onConfirm) {
    this.show({
      title: "Confirmation de validation",
      message: "Êtes-vous sûr ? Une fois validé, le document sera envoyé à l'annotateur pour annotation.",
      icon: "fa-exclamation-triangle",
      iconClass: "warning",
      onConfirm,
    })
  }
}

// Multi-document navigation functions
let currentDocIndex = 0
let totalDocuments = 0

// Initialize multi-document viewer
function initMultiDocViewer() {
  const docContents = document.querySelectorAll(".doc-content")
  totalDocuments = docContents.length

  if (totalDocuments > 0) {
    currentDocIndex = 0
    updateDocCounter()
    updateNavigationButtons()

    // Set first document as active
    switchDocument(0)
  }
}

// Switch to a specific document
function switchDocument(index) {
  if (index < 0 || index >= totalDocuments) return

  // Update active carousel card
  document.querySelectorAll(".doc-selector-card").forEach((card) => {
    card.classList.remove("active")
  })

  const activeCard = document.querySelector(`.doc-selector-card[data-doc-index="${index}"]`)
  if (activeCard) {
    activeCard.classList.add("active")
    // Scroll card into view in carousel
    activeCard.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" })
  }

  // Hide all document contents
  document.querySelectorAll(".doc-content").forEach((doc) => {
    doc.classList.add("hidden")
  })

  // Show selected document
  const selectedDoc = document.getElementById(`doc-${index}`)
  if (selectedDoc) {
    selectedDoc.classList.remove("hidden")
  }

  currentDocIndex = index
  updateDocCounter()
  updateNavigationButtons()
}

// Navigate to previous/next document
function navigateDoc(direction) {
  const newIndex = currentDocIndex + direction
  if (newIndex >= 0 && newIndex < totalDocuments) {
    switchDocument(newIndex)
  }
}

// Update document counter
function updateDocCounter() {
  const currentNum = currentDocIndex + 1

  const currentDocNum = document.getElementById("currentDocNum")
  const navCurrentDoc = document.getElementById("navCurrentDoc")

  if (currentDocNum) currentDocNum.textContent = currentNum
  if (navCurrentDoc) navCurrentDoc.textContent = currentNum
}

// Update navigation button states
function updateNavigationButtons() {
  const prevBtn = document.getElementById("prevDocBtnTop")
  const nextBtn = document.getElementById("nextDocBtnTop")

  if (prevBtn) {
    prevBtn.disabled = currentDocIndex === 0
  }

  if (nextBtn) {
    nextBtn.disabled = currentDocIndex === totalDocuments - 1
  }
}

// Reextract document
function reextractDoc(docId) {
  if (!confirm("Relancer l'extraction automatique pour ce document ?")) return

  fetch(`/edit/${docId}/reextract/`, {
    method: "POST",
    headers: { "X-CSRFToken": Utils.getCookie("csrftoken") },
  })
    .then((response) => response.json())
    .then((data) => {
      if (data.success) {
        Utils.showToast("success", "Réextraction terminée")
        location.reload()
      } else {
        Utils.showToast("error", data.error || "Erreur lors de la réextraction")
      }
    })
    .catch((error) => {
      Utils.showToast("error", "Erreur réseau: " + error.message)
    })
}

// Validate document
function validateDoc(docId) {
  ModalManager.showValidation(() => {
    const form = document.querySelector(`.metadata-form-multi[data-doc-id="${docId}"]`)
    if (form) {
      const input = document.createElement("input")
      input.type = "hidden"
      input.name = "validate_document"
      input.value = docId
      form.appendChild(input)
      form.submit()
    }
  })
}

// Content Editor Manager
class ContentEditorManager {
  constructor() {
    this.editModeStates = new Map() // Track edit mode for each document
  }

  // Initialize single document editor
  initSingleEditor() {
    const toggleBtn = document.getElementById("toggleEditBtnSingle")
    const saveBtn = document.getElementById("saveContentBtnSingle")
    const copyBtn = document.getElementById("copyHtmlBtnSingle")
    const downloadBtn = document.getElementById("downloadHtmlBtnSingle")

    if (toggleBtn) {
      toggleBtn.addEventListener("click", () => this.toggleEditMode("single"))
    }

    if (saveBtn) {
      saveBtn.addEventListener("click", () => this.saveContent("single"))
    }

    if (copyBtn) {
      copyBtn.addEventListener("click", () => this.copyHtml("single"))
    }

    if (downloadBtn) {
      downloadBtn.addEventListener("click", () => this.downloadHtml("single"))
    }
  }

  // Initialize multi-document editors
  initMultiEditors() {
    // Toggle edit buttons
    document.querySelectorAll(".toggle-edit-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        const docIndex = e.currentTarget.getAttribute("data-doc-index")
        this.toggleEditMode(docIndex)
      })
    })

    // Save content buttons
    document.querySelectorAll(".save-content-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        const docIndex = e.currentTarget.getAttribute("data-doc-index")
        this.saveContent(docIndex)
      })
    })

    // Copy HTML buttons
    document.querySelectorAll(".copy-html-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        const docIndex = e.currentTarget.getAttribute("data-doc-index")
        this.copyHtml(docIndex)
      })
    })

    // Download HTML buttons
    document.querySelectorAll(".download-html-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        const docIndex = e.currentTarget.getAttribute("data-doc-index")
        this.downloadHtml(docIndex)
      })
    })
  }

  // Toggle edit mode for a specific document
  toggleEditMode(docIndex) {
    const isEditMode = this.editModeStates.get(docIndex) || false
    const newEditMode = !isEditMode

    let container, toggleBtn, saveBtn

    if (docIndex === "single") {
      container = document.getElementById("zoomContainerSingle")
      toggleBtn = document.getElementById("toggleEditBtnSingle")
      saveBtn = document.getElementById("saveContentBtnSingle")
    } else {
      container = document.getElementById(`zoom-container-multi-${docIndex}`)
      toggleBtn = document.querySelector(`.toggle-edit-btn[data-doc-index="${docIndex}"]`)
      saveBtn = document.querySelector(`.save-content-btn[data-doc-index="${docIndex}"]`)
    }

    if (!container) return

    // Make content editable
    const editableSelectors = [
      ".editable-content",
      ".pdf-text-element",
      ".pdf-cell",
      "p",
      "h1",
      "h2",
      "h3",
      "h4",
      "h5",
      "h6",
      "li",
      "td",
      "th",
    ]

    editableSelectors.forEach((selector) => {
      container.querySelectorAll(selector).forEach((el) => {
        el.setAttribute("contenteditable", newEditMode ? "true" : "false")
        el.spellcheck = false
        if (newEditMode) {
          el.style.outline = "2px dashed rgba(14,165,233,0.3)"
          el.style.outlineOffset = "2px"
        } else {
          el.style.outline = ""
          el.style.outlineOffset = ""
        }
      })
    })

    // Update button states
    if (toggleBtn) {
      toggleBtn.innerHTML = newEditMode
        ? '<i class="fas fa-eye"></i>'
        : '<i class="fas fa-edit"></i>'
      toggleBtn.title = newEditMode ? "Mode lecture" : "Mode édition"
      toggleBtn.style.background = newEditMode ? "#f59e0b" : ""
    }

    if (saveBtn) {
      saveBtn.style.display = newEditMode ? "inline-flex" : "none"
    }

    this.editModeStates.set(docIndex, newEditMode)

    Utils.showToast(
      "success",
      newEditMode ? "Mode édition activé" : "Mode lecture activé"
    )
  }

  // Save content for a specific document
  async saveContent(docIndex) {
    let container
    let docId
    let saveUrl

    if (docIndex === "single") {
      container = document.getElementById("zoomContainerSingle")
      const saveBtn = document.getElementById("saveContentBtnSingle")
      docId = saveBtn ? saveBtn.getAttribute("data-doc-id") : null
      saveUrl = saveBtn ? saveBtn.getAttribute("data-save-url") : null
    } else {
      container = document.getElementById(`zoom-container-multi-${docIndex}`)
      const saveBtn = document.querySelector(
        `.save-content-btn[data-doc-index="${docIndex}"]`
      )
      docId = saveBtn ? saveBtn.getAttribute("data-doc-id") : null
      saveUrl = saveBtn ? saveBtn.getAttribute("data-save-url") : null
    }

    if (!container || !docId || !saveUrl) {
      Utils.showToast("error", "Impossible de sauvegarder le contenu")
      return
    }

    const formatted_content = container.innerHTML

    Utils.showToast("info", "Sauvegarde en cours...")

    try {
      const response = await fetch(saveUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": Utils.getCookie("csrftoken"),
        },
        body: JSON.stringify({
          formatted_content: formatted_content,
        }),
      })

      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`HTTP ${response.status}: ${errorText}`)
      }

      const data = await response.json()

      if (data && data.success) {
        Utils.showToast(
          "success",
          data.message || "Contenu sauvegardé avec succès"
        )
      } else {
        Utils.showToast(
          "error",
          (data && data.error) || "Erreur lors de la sauvegarde"
        )
      }
    } catch (error) {
      const message = error && error.message ? error.message : "Erreur réseau lors de la sauvegarde"
      Utils.showToast("error", message)
      console.error("Save error:", error)
    }
  }

  // Copy HTML to clipboard
  copyHtml(docIndex) {
    let container

    if (docIndex === "single") {
      container = document.getElementById("zoomContainerSingle")
    } else {
      container = document.getElementById(`zoom-container-multi-${docIndex}`)
    }

    if (!container) return

    const html = container.innerHTML

    if (navigator.clipboard) {
      navigator.clipboard
        .writeText(html)
        .then(() => Utils.showToast("success", "HTML copié dans le presse-papiers"))
        .catch(() => this.fallbackCopy(html))
    } else {
      this.fallbackCopy(html)
    }
  }

  // Fallback copy method
  fallbackCopy(text) {
    const ta = document.createElement("textarea")
    ta.value = text
    ta.style.position = "fixed"
    ta.style.left = "-9999px"
    document.body.appendChild(ta)
    ta.select()
    try {
      document.execCommand("copy")
      Utils.showToast("success", "HTML copié")
    } catch (err) {
      Utils.showToast("error", "Impossible de copier le HTML")
    }
    document.body.removeChild(ta)
  }

  // Download HTML file
  downloadHtml(docIndex) {
    let container, docId

    if (docIndex === "single") {
      container = document.getElementById("zoomContainerSingle")
      const saveBtn = document.getElementById("saveContentBtnSingle")
      docId = saveBtn ? saveBtn.getAttribute("data-doc-id") : "0"
    } else {
      container = document.getElementById(`zoom-container-multi-${docIndex}`)
      const saveBtn = document.querySelector(
        `.save-content-btn[data-doc-index="${docIndex}"]`
      )
      docId = saveBtn ? saveBtn.getAttribute("data-doc-id") : docIndex
    }

    if (!container) return

    const html = container.innerHTML
    const blob = new Blob([html], { type: "text/html;charset=utf-8" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    const filename = `document_${docId}_structured.html`

    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)

    Utils.showToast("success", "HTML téléchargé")
  }
}

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
  // Initialize file upload
  new FileUploadHandler("dropZone", "pdf_file", "fileInfo")

  // Initialize metadata manager
  const docId = document.querySelector('input[name="doc_id"]')?.value
  const metadataManager = new MetadataManager("metadataForm", docId)

  // Initialize content editor
  const contentEditor = new ContentEditorManager()

  // Initialize single document editor if present
  if (document.getElementById("zoomContainerSingle")) {
    contentEditor.initSingleEditor()
  }

  // Initialize multi-document editors if present
  if (document.querySelector(".zoom-container-multi")) {
    contentEditor.initMultiEditors()
  }

  // Reextract button
  const reextractBtn = document.getElementById("reextractBtn")
  if (reextractBtn) {
    reextractBtn.addEventListener("click", () => metadataManager.reextract())
  }

  // Validate button
  const validateBtn = document.getElementById("validateBtn")
  if (validateBtn) {
    validateBtn.addEventListener("click", (e) => {
      e.preventDefault()
      ModalManager.showValidation(() => {
        const form = document.getElementById("metadataForm")
        const input = document.createElement("input")
        input.type = "hidden"
        input.name = "validate_document"
        input.value = docId
        form.appendChild(input)
        form.submit()
      })
    })
  }

  // Custom fields
  const customFieldsManager = new CustomFieldsManager("customFields")

  // Add field button
  const addFieldBtn = document.getElementById("addFieldBtn")
  if (addFieldBtn) {
    addFieldBtn.addEventListener("click", () => {
      const name = prompt("Nom du champ:")
      const type = prompt("Type (text/textarea/date/number):", "text")
      if (name) {
        customFieldsManager.saveField(name, type, docId)
      }
    })
  }

  // Load existing custom fields
  if (window.customFieldsData) {
    window.customFieldsData.forEach((field) => {
      customFieldsManager.addField(field.name, field.type, field.value)
    })
  }

  const tabButtons = document.querySelectorAll(".tab-btn")
  const splitView = document.getElementById("splitView")
  const structuredPanel = document.getElementById("structuredPanel")
  const pdfPanel = document.getElementById("pdfPanel")

  if (tabButtons.length > 0 && splitView && structuredPanel && pdfPanel) {
    tabButtons.forEach((tab) => {
      tab.addEventListener("click", function () {
        const view = this.getAttribute("data-view")

        // Update active tab
        tabButtons.forEach((btn) => btn.classList.remove("active"))
        this.classList.add("active")

        // Show/hide panels based on selected view
        if (view === "split") {
          // Split view: show both panels side by side
          splitView.style.display = "flex"
          structuredPanel.style.display = "block"
          pdfPanel.style.display = "block"
        } else if (view === "structured") {
          // Structured only: show only structured panel
          splitView.style.display = "block"
          structuredPanel.style.display = "block"
          pdfPanel.style.display = "none"
        } else if (view === "pdf") {
          // PDF only: show only PDF panel
          splitView.style.display = "block"
          structuredPanel.style.display = "none"
          pdfPanel.style.display = "block"
        }
      })
    })
  }

  // PDF controls
  const refreshPdfBtn = document.getElementById("refreshPdfBtn")
  const fullscreenPdfBtn = document.getElementById("fullscreenPdfBtn")
  const pdfFrame = document.getElementById("pdfFrame")

  if (refreshPdfBtn && pdfFrame) {
    refreshPdfBtn.addEventListener("click", () => {
      pdfFrame.src = pdfFrame.src
    })
  }

  if (fullscreenPdfBtn && pdfFrame) {
    fullscreenPdfBtn.addEventListener("click", () => {
      if (pdfFrame.requestFullscreen) {
        pdfFrame.requestFullscreen()
      }
    })
  }

  // PDF fallback functions
  window.reloadPdfFrame = () => {
    if (pdfFrame) {
      const fallback = document.getElementById("pdfFallback")
      if (fallback) fallback.style.display = "none"
      pdfFrame.src = pdfFrame.src
    }
  }

  window.switchToObjectView = () => {
    const pdfFrameEl = document.getElementById("pdfFrame")
    const pdfObject = document.getElementById("pdfObject")
    const fallback = document.getElementById("pdfFallback")

    if (pdfFrameEl && pdfObject) {
      pdfFrameEl.style.display = "none"
      pdfObject.style.display = "block"
      if (fallback) fallback.style.display = "none"
      Utils.showToast("success", "Basculé vers le mode alternatif")
    }
  }

  // Initialize multi-document viewer if present
  if (document.querySelector(".multi-document-container")) {
    initMultiDocViewer()
  }
})

// Carousel navigation functions for horizontal document selector
function scrollCarousel(direction) {
  const carouselTrack = document.querySelector(".carousel-track")
  if (!carouselTrack) return

  const cardWidth = document.querySelector(".doc-selector-card")?.offsetWidth || 280
  const gap = 16 // 1rem gap
  const scrollAmount = (cardWidth + gap) * direction

  carouselTrack.scrollBy({
    left: scrollAmount,
    behavior: "smooth",
  })
}

// Keyboard navigation for carousel
document.addEventListener("keydown", (e) => {
  if (document.querySelector(".multi-document-container")) {
    if (e.key === "ArrowLeft") {
      e.preventDefault()
      navigateDoc(-1)
    } else if (e.key === "ArrowRight") {
      e.preventDefault()
      navigateDoc(1)
    }
  }
})
