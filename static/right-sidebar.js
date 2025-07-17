/**
 * Right Sidebar Controller
 * Manages the right sidebar functionality with state persistence and accessibility
 */
class RightSidebar {
  constructor(options = {}) {
    this.config = {
      width: options.width || 300,
      defaultState: options.defaultState || 'closed',
      animationDuration: options.animationDuration || 300,
      breakpoint: options.breakpoint || 768,
      storageKey: options.storageKey || 'right-sidebar-state',
      ...options
    };
    
    this.isOpen = false;
    this.elements = {};
    this.isMobile = window.innerWidth < this.config.breakpoint;
    
    this.init();
  }

  /**
   * Initialize the sidebar
   */
  init() {
    try {
      this.findElements();
      this.createMobileBackdrop();
      this.bindEvents();
      this.restoreState();
      this.updateAriaAttributes();
    } catch (error) {
      console.warn('Right sidebar initialization failed:', error);
    }
  }

  /**
   * Find required DOM elements
   */
  findElements() {
    this.elements.sidebar = document.getElementById('right-sidebar');
    this.elements.toggle = document.getElementById('right-sidebar-toggle');
    this.elements.appContainer = document.querySelector('.app-container');
    
    if (!this.elements.sidebar || !this.elements.toggle) {
      throw new Error('Required sidebar elements not found');
    }
  }

  /**
   * Create mobile backdrop element
   */
  createMobileBackdrop() {
    this.elements.backdrop = document.createElement('div');
    this.elements.backdrop.className = 'right-sidebar-backdrop';
    this.elements.backdrop.setAttribute('aria-hidden', 'true');
    document.body.appendChild(this.elements.backdrop);
  }

  /**
   * Bind event listeners
   */
  bindEvents() {
    // Toggle button click
    this.elements.toggle.addEventListener('click', (e) => {
      e.preventDefault();
      this.toggle();
    });

    // Backdrop click (mobile)
    this.elements.backdrop.addEventListener('click', () => {
      if (this.isMobile && this.isOpen) {
        this.close();
      }
    });

    // Keyboard events
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this.isOpen) {
        this.close();
        this.elements.toggle.focus();
      }
    });

    // Window resize
    window.addEventListener('resize', this.debounce(() => {
      const wasMobile = this.isMobile;
      this.isMobile = window.innerWidth < this.config.breakpoint;
      
      if (wasMobile !== this.isMobile) {
        this.handleResponsiveChange();
      }
    }, 250));

    // Focus management
    this.elements.sidebar.addEventListener('keydown', (e) => {
      if (e.key === 'Tab') {
        this.handleTabNavigation(e);
      }
    });
  }

  /**
   * Toggle sidebar open/closed
   */
  toggle() {
    if (this.isOpen) {
      this.close();
    } else {
      this.open();
    }
  }

  /**
   * Open the sidebar
   */
  open() {
    if (this.isOpen) return;
    
    this.isOpen = true;
    this.elements.sidebar.classList.add('open');
    this.elements.toggle.classList.add('sidebar-open');
    
    if (this.elements.appContainer) {
      this.elements.appContainer.classList.add('right-sidebar-open');
    }

    if (this.isMobile) {
      this.elements.backdrop.classList.add('show');
      document.body.style.overflow = 'hidden';
    }

    this.updateAriaAttributes();
    this.saveState();
    this.announceToScreenReader('Right sidebar opened');
  }

  /**
   * Close the sidebar
   */
  close() {
    if (!this.isOpen) return;
    
    this.isOpen = false;
    this.elements.sidebar.classList.remove('open');
    this.elements.toggle.classList.remove('sidebar-open');
    
    if (this.elements.appContainer) {
      this.elements.appContainer.classList.remove('right-sidebar-open');
    }

    if (this.isMobile) {
      this.elements.backdrop.classList.remove('show');
      document.body.style.overflow = '';
    }

    this.updateAriaAttributes();
    this.saveState();
    this.announceToScreenReader('Right sidebar closed');
  }

  /**
   * Handle responsive breakpoint changes
   */
  handleResponsiveChange() {
    if (this.isOpen) {
      if (this.isMobile) {
        this.elements.backdrop.classList.add('show');
        document.body.style.overflow = 'hidden';
      } else {
        this.elements.backdrop.classList.remove('show');
        document.body.style.overflow = '';
      }
    }
  }

  /**
   * Handle tab navigation within sidebar
   */
  handleTabNavigation(e) {
    if (!this.isOpen) return;

    const focusableElements = this.elements.sidebar.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    
    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];

    if (e.shiftKey && document.activeElement === firstElement) {
      e.preventDefault();
      lastElement.focus();
    } else if (!e.shiftKey && document.activeElement === lastElement) {
      e.preventDefault();
      firstElement.focus();
    }
  }

  /**
   * Update ARIA attributes for accessibility
   */
  updateAriaAttributes() {
    this.elements.toggle.setAttribute('aria-expanded', this.isOpen.toString());
    this.elements.sidebar.setAttribute('aria-hidden', (!this.isOpen).toString());
    
    if (this.isOpen) {
      this.elements.sidebar.setAttribute('tabindex', '0');
    } else {
      this.elements.sidebar.removeAttribute('tabindex');
    }
  }

  /**
   * Announce state changes to screen readers
   */
  announceToScreenReader(message) {
    const announcement = document.createElement('div');
    announcement.setAttribute('aria-live', 'polite');
    announcement.setAttribute('aria-atomic', 'true');
    announcement.className = 'sr-only';
    announcement.style.cssText = 'position: absolute; left: -10000px; width: 1px; height: 1px; overflow: hidden;';
    announcement.textContent = message;
    
    document.body.appendChild(announcement);
    
    setTimeout(() => {
      document.body.removeChild(announcement);
    }, 1000);
  }

  /**
   * Save sidebar state to sessionStorage
   */
  saveState() {
    try {
      const state = {
        isOpen: this.isOpen,
        timestamp: Date.now()
      };
      sessionStorage.setItem(this.config.storageKey, JSON.stringify(state));
    } catch (error) {
      console.warn('Failed to save sidebar state:', error);
    }
  }

  /**
   * Restore sidebar state from sessionStorage
   */
  restoreState() {
    try {
      const stored = sessionStorage.getItem(this.config.storageKey);
      if (stored) {
        const state = JSON.parse(stored);
        // Only restore if timestamp is recent (within 24 hours)
        if (Date.now() - state.timestamp < 24 * 60 * 60 * 1000) {
          if (state.isOpen) {
            this.open();
          }
          return;
        }
      }
    } catch (error) {
      console.warn('Failed to restore sidebar state:', error);
    }
    
    // Default to closed state
    this.close();
  }

  /**
   * Debounce utility function
   */
  debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  }

  /**
   * Destroy the sidebar instance
   */
  destroy() {
    try {
      // Remove event listeners
      this.elements.toggle.removeEventListener('click', this.toggle);
      this.elements.backdrop.removeEventListener('click', this.close);
      
      // Remove backdrop
      if (this.elements.backdrop && this.elements.backdrop.parentNode) {
        this.elements.backdrop.parentNode.removeChild(this.elements.backdrop);
      }
      
      // Reset body overflow
      document.body.style.overflow = '';
      
      // Clear storage
      sessionStorage.removeItem(this.config.storageKey);
    } catch (error) {
      console.warn('Error destroying sidebar:', error);
    }
  }
}

/**
 * Auto-initialize right sidebar when DOM is ready
 */
function initRightSidebar() {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      window.rightSidebar = new RightSidebar();
    });
  } else {
    window.rightSidebar = new RightSidebar();
  }
}

// Auto-initialize
initRightSidebar();

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
  module.exports = RightSidebar;
}

// Example of how to use the sidebar from other scripts
// window.rightSidebar.open();
// window.rightSidebar.close();
// window.rightSidebar.toggle();
// window.rightSidebar.isOpen;
// window.rightSidebar.destroy();