// Function to apply theme
function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('reaper-theme', theme);
    
    // Optional: Update any theme-specific icons in the UI
    const themeStatus = document.getElementById('theme-status-text');
    if (themeStatus) themeStatus.innerText = theme.toUpperCase() + " MODE";
}

// Initial check on page load
(function() {
    const savedTheme = localStorage.getItem('reaper-theme') || 'dark';
    applyTheme(savedTheme);
})();

// Toggle function for the button in Settings
function toggleAppTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    applyTheme(newTheme);
}
