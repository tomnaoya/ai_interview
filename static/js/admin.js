// Flash messages auto-hide
document.querySelectorAll('.alert').forEach(el => {
  setTimeout(() => el.style.opacity = '0', 3000);
});

// Confirm dialogs already handled via inline onsubmit

// Auto-resize textareas
document.querySelectorAll('textarea').forEach(ta => {
  ta.addEventListener('input', function() {
    if (this.dataset.autoResize !== 'false') {
      this.style.height = 'auto';
      this.style.height = Math.min(this.scrollHeight, 500) + 'px';
    }
  });
});

// Sidebar mobile close on overlay click
document.addEventListener('click', e => {
  const sidebar = document.querySelector('.sidebar');
  const toggle = document.querySelector('.sidebar-toggle');
  if (sidebar && sidebar.classList.contains('open') && !sidebar.contains(e.target) && e.target !== toggle) {
    sidebar.classList.remove('open');
  }
});
