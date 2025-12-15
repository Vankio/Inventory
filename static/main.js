document.addEventListener('DOMContentLoaded', function() {
    const sidebar = document.querySelector('.sidebar');
    const mainContent = document.querySelector('.main-content');
    const toggleBtn = document.getElementById('sidebar-toggle-btn');
    const componentsMenuToggle = document.getElementById('components-menu-toggle');
    const componentsSubmenu = document.getElementById('components-submenu');
    const navArrow = componentsMenuToggle ? componentsMenuToggle.querySelector('.nav-arrow i') : null;

    function toggleSidebar() {
        if (!sidebar || !mainContent || !toggleBtn) return;
        
        sidebar.classList.toggle('collapsed');
        mainContent.classList.toggle('sidebar-collapsed');
        toggleBtn.classList.toggle('collapsed');
        
        const icon = toggleBtn.querySelector('i');
        if (sidebar.classList.contains('collapsed')) {
            icon.classList.remove('fa-chevron-left');
            icon.classList.add('fa-chevron-right');
            localStorage.setItem('sidebarState', 'collapsed');
        } else {
            icon.classList.remove('fa-chevron-right');
            icon.classList.add('fa-chevron-left');
            localStorage.setItem('sidebarState', 'expanded');
        }
    }

    function toggleComponentsMenu() {
        if (componentsSubmenu && navArrow) {
            componentsSubmenu.classList.toggle('active');
            navArrow.classList.toggle('rotated');
            if (componentsSubmenu.classList.contains('active')) {
                localStorage.setItem('componentsMenu', 'open');
            } else {
                localStorage.setItem('componentsMenu', 'closed');
            }
        }
    }

    if (toggleBtn) {
        toggleBtn.addEventListener('click', toggleSidebar);
    }
    
    if (componentsMenuToggle) {
        componentsMenuToggle.addEventListener('click', toggleComponentsMenu);
    }

    // Restore sidebar state
    const sidebarState = localStorage.getItem('sidebarState');
    if (sidebarState === 'collapsed') {
        if (sidebar && !sidebar.classList.contains('collapsed')) {
             sidebar.classList.add('collapsed');
             if (mainContent) mainContent.classList.add('sidebar-collapsed');
             if (toggleBtn) {
                toggleBtn.classList.add('collapsed');
                const icon = toggleBtn.querySelector('i');
                if (icon) {
                    icon.classList.remove('fa-chevron-left');
                    icon.classList.add('fa-chevron-right');
                }
             }
        }
    }

    // Restore components menu state based on active item
    // This is a more robust way to ensure the menu is open if a child is active.
    const activeSubmenuItem = document.querySelector('.submenu-item.active');
    if (activeSubmenuItem && componentsSubmenu && !componentsSubmenu.classList.contains('active')) {
        componentsSubmenu.classList.add('active');
        if (navArrow) {
            navArrow.classList.add('rotated');
        }
        // Also save the state to localStorage so it persists on other pages
        localStorage.setItem('componentsMenu', 'open');
    } else {
        // If no submenu item is active, check localStorage
        const componentsMenuState = localStorage.getItem('componentsMenu');
        if (componentsMenuState === 'open' && componentsSubmenu && !componentsSubmenu.classList.contains('active')) {
            componentsSubmenu.classList.add('active');
            if (navArrow) {
                navArrow.classList.add('rotated');
            }
        }
    }
    
    // Remove the no-transition class after the page is loaded to re-enable animations
    window.addEventListener('load', () => {
        document.body.classList.remove('no-transition');
    });
});