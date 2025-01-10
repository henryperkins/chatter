// static/js/base.js

/**
 * Sets the default CSRF token header for Axios requests.
 */
axios.defaults.headers.common["X-CSRFToken"] = getCSRFToken();

/**
 * Overrides the native fetch function to include the CSRF token in all requests.
 * @function fetch
 * @param {string | URL | Request} url - The URL or Request object.
 * @param {object} [options] - The fetch options.
 * @param {object} [options.headers] - The request headers.
 * @returns {Promise<Response>} The fetch promise.
 */
const originalFetch = window.fetch;
window.fetch = function (url, options = {}) {
  if (!options.headers) {
    options.headers = {};
  }

  // Add CSRF token if not already present
  if (!options.headers["X-CSRFToken"]) {
    options.headers["X-CSRFToken"] = getCSRFToken();
  }

  return originalFetch(url, options);
};

/**
 * Initializes the mobile menu toggle functionality.
 * @function initializeMobileMenu
 * @listens DOMContentLoaded
 */
document.addEventListener("DOMContentLoaded", () => {
  const sidebarToggle = document.getElementById("sidebar-toggle");
  const offCanvasMenu = document.getElementById("off-canvas-menu");
  const overlay = document.getElementById("overlay");
  const closeButton = document.getElementById("off-canvas-close");

  /**
   * Toggles the visibility of the mobile menu and overlay.
   * @function toggleMenu
   */
  function toggleMenu() {
    offCanvasMenu.classList.toggle("hidden");
    overlay.classList.toggle("hidden");
    document.body.classList.toggle("overflow-hidden");
  }

  if (sidebarToggle && offCanvasMenu && overlay && closeButton) {
    sidebarToggle.addEventListener("click", toggleMenu);
    closeButton.addEventListener("click", toggleMenu);
    overlay.addEventListener("click", toggleMenu);
  }
});

/**
 * Handles global click events for dynamic elements (e.g., feedback close buttons).
 * @listens click
 */
document.addEventListener("click", (event) => {
  // Handle feedback close button clicks
  if (event.target.matches("#feedback-close")) {
    const feedbackMessage = document.getElementById("feedback-message");
    if (feedbackMessage) {
      feedbackMessage.classList.add("hidden");
    }
  }
});

/**
 * Handles global keydown events (e.g., closing modals with the Escape key).
 * @listens keydown
 */
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    const modals = document.querySelectorAll(".modal:not(.hidden)");
    modals.forEach((modal) => {
      modal.classList.add("hidden");
    });
  }
});

/**
 * Initializes tooltips for elements with the `data-tooltip` attribute.
 * @function initializeTooltips
 * @listens DOMContentLoaded
 */
document.addEventListener("DOMContentLoaded", () => {
  const tooltipElements = document.querySelectorAll("[data-tooltip]");
  tooltipElements.forEach((element) => {
    const tooltipText = element.getAttribute("data-tooltip");
    const tooltip = document.createElement("div");
    tooltip.className =
      "tooltip hidden bg-black text-white text-sm px-2 py-1 rounded absolute z-50";
    tooltip.textContent = tooltipText;
    element.appendChild(tooltip);

    element.addEventListener("mouseenter", () => {
      tooltip.classList.remove("hidden");
    });

    element.addEventListener("mouseleave", () => {
      tooltip.classList.add("hidden");
    });
  });
});

/**
 * Initializes dropdown menus for elements with the `data-dropdown` attribute.
 * @function initializeDropdowns
 * @listens DOMContentLoaded
 */
document.addEventListener("DOMContentLoaded", () => {
  const dropdownElements = document.querySelectorAll("[data-dropdown]");
  dropdownElements.forEach((element) => {
    const dropdownMenu = element.querySelector(".dropdown-menu");
    if (dropdownMenu) {
      element.addEventListener("click", (event) => {
        event.stopPropagation();
        dropdownMenu.classList.toggle("hidden");
      });

      document.addEventListener("click", () => {
        dropdownMenu.classList.add("hidden");
      });
    }
  });
});

/**
 * Initializes modals for elements with the `data-modal` attribute.
 * @function initializeModals
 * @listens DOMContentLoaded
 */
document.addEventListener("DOMContentLoaded", () => {
  const modalTriggers = document.querySelectorAll("[data-modal-target]");
  modalTriggers.forEach((trigger) => {
    const modalId = trigger.getAttribute("data-modal-target");
    const modal = document.getElementById(modalId);
    if (modal) {
      trigger.addEventListener("click", () => {
        modal.classList.remove("hidden");
      });

      const closeButtons = modal.querySelectorAll("[data-modal-close]");
      closeButtons.forEach((button) => {
        button.addEventListener("click", () => {
          modal.classList.add("hidden");
        });
      });
    }
  });
});

/**
 * Handles form submissions with the `ajax-form` class.
 * @function handleAjaxFormSubmit
 * @listens submit
 */
document.addEventListener("submit", async (event) => {
  if (event.target.classList.contains("ajax-form")) {
    event.preventDefault();
    const form = event.target;
    const formData = new FormData(form);

    try {
      const response = await fetch(form.action, {
        method: form.method,
        body: formData,
        headers: {
          "X-CSRFToken": getCSRFToken(),
          Accept: "application/json",
        },
      });

      const data = await response.json();
      if (response.ok && data.success) {
        showFeedback(data.message || "Operation successful!", "success");
        if (data.redirect) {
          window.location.href = data.redirect;
        }
      } else {
        showFeedback(data.error || "An error occurred.", "error");
      }
    } catch (error) {
      console.error("Error submitting form:", error);
      showFeedback("An error occurred while submitting the form.", "error");
    }
  }
});
