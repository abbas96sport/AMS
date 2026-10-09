/**
 * Football Academic Management System - Main JavaScript
 * Handles interactive functionality and user experience enhancements
 */

// Initialize application when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    initializeApplication();
});

/**
 * Initialize all application functionality
 */
function initializeApplication() {
    initializeTooltips();
    initializeFormValidation();
    initializeTableFeatures();
    initializeAttendanceFeatures();
    initializeGradeCalculations();
    initializeSearchFilters();
    initializeAlerts();
    initializeKeyboardShortcuts();
}

/**
 * Initialize Bootstrap tooltips
 */
function initializeTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

/**
 * Enhanced form validation
 */
function initializeFormValidation() {
    // Student ID validation
    const studentIdInputs = document.querySelectorAll('input[name="student_id"]');
    studentIdInputs.forEach(input => {
        input.addEventListener('blur', validateStudentId);
    });

    // Grade input validation
    const gradeInputs = document.querySelectorAll('input[type="number"][step="0.01"]');
    gradeInputs.forEach(input => {
        input.addEventListener('input', validateGradeInput);
    });

    // Form submission handling
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', handleFormSubmission);
    });
}

/**
 * Validate student ID format
 */
function validateStudentId(event) {
    const input = event.target;
    const value = input.value.trim();
    
    // Basic validation - customize based on your university's ID format
    const idPattern = /^[0-9A-Z]{6,15}$/;
    
    if (value && !idPattern.test(value)) {
        showInputError(input, 'Invalid student ID format');
    } else {
        clearInputError(input);
    }
}

/**
 * Validate grade inputs
 */
function validateGradeInput(event) {
    const input = event.target;
    const value = parseFloat(input.value);
    const max = parseFloat(input.getAttribute('max') || input.getAttribute('data-max'));
    
    if (isNaN(value)) return;
    
    if (value < 0) {
        input.value = 0;
        showInputWarning(input, 'Grade cannot be negative');
    } else if (max && value > max) {
        input.value = max;
        showInputWarning(input, `Grade cannot exceed ${max}`);
    } else {
        clearInputError(input);
    }
    
    // Update grade totals if on grades page
    updateGradeTotals();
}

/**
 * Show input error
 */
function showInputError(input, message) {
    clearInputError(input);
    input.classList.add('is-invalid');
    
    const errorDiv = document.createElement('div');
    errorDiv.className = 'invalid-feedback';
    errorDiv.textContent = message;
    input.parentNode.appendChild(errorDiv);
}

/**
 * Show input warning
 */
function showInputWarning(input, message) {
    clearInputError(input);
    
    const warningDiv = document.createElement('div');
    warningDiv.className = 'text-warning small';
    warningDiv.textContent = message;
    input.parentNode.appendChild(warningDiv);
    
    setTimeout(() => {
        if (warningDiv.parentNode) {
            warningDiv.parentNode.removeChild(warningDiv);
        }
    }, 3000);
}

/**
 * Clear input errors
 */
function clearInputError(input) {
    input.classList.remove('is-invalid');
    const errorElements = input.parentNode.querySelectorAll('.invalid-feedback, .text-warning');
    errorElements.forEach(el => el.remove());
}

/**
 * Handle form submission
 */
function handleFormSubmission(event) {
    const form = event.target;
    
    // Show loading state
    const submitButton = form.querySelector('button[type="submit"]');
    if (submitButton) {
        const originalText = submitButton.innerHTML;
        submitButton.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Saving...';
        submitButton.disabled = true;
        
        // Re-enable after 5 seconds as fallback
        setTimeout(() => {
            submitButton.innerHTML = originalText;
            submitButton.disabled = false;
        }, 5000);
    }
}

/**
 * Initialize table features
 */
function initializeTableFeatures() {
    // Make table rows clickable where appropriate
    const clickableRows = document.querySelectorAll('table tbody tr[data-href]');
    clickableRows.forEach(row => {
        row.style.cursor = 'pointer';
        row.addEventListener('click', function() {
            window.location.href = this.getAttribute('data-href');
        });
    });

    // Add sorting to table headers
    const sortableHeaders = document.querySelectorAll('th[data-sort]');
    sortableHeaders.forEach(header => {
        header.style.cursor = 'pointer';
        header.addEventListener('click', function() {
            sortTable(this);
        });
    });
}

/**
 * Sort table by column
 */
function sortTable(header) {
    const table = header.closest('table');
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    const columnIndex = Array.from(header.parentNode.children).indexOf(header);
    const isNumeric = header.getAttribute('data-sort') === 'number';
    
    // Toggle sort direction
    const isAscending = header.getAttribute('data-sort-direction') !== 'asc';
    header.setAttribute('data-sort-direction', isAscending ? 'asc' : 'desc');
    
    // Sort rows
    rows.sort((a, b) => {
        const aValue = a.children[columnIndex].textContent.trim();
        const bValue = b.children[columnIndex].textContent.trim();
        
        let comparison = 0;
        if (isNumeric) {
            comparison = parseFloat(aValue) - parseFloat(bValue);
        } else {
            comparison = aValue.localeCompare(bValue);
        }
        
        return isAscending ? comparison : -comparison;
    });
    
    // Re-append sorted rows
    rows.forEach(row => tbody.appendChild(row));
    
    // Update header indicators
    updateSortIndicators(header);
}

/**
 * Update sort indicators
 */
function updateSortIndicators(activeHeader) {
    // Clear all sort indicators
    const headers = activeHeader.closest('table').querySelectorAll('th[data-sort]');
    headers.forEach(h => {
        h.classList.remove('sorted-asc', 'sorted-desc');
    });
    
    // Add indicator to active header
    const direction = activeHeader.getAttribute('data-sort-direction');
    activeHeader.classList.add(`sorted-${direction}`);
}

/**
 * Initialize attendance-specific features
 */
function initializeAttendanceFeatures() {
    // Bulk attendance actions
    const selectAllCheckbox = document.getElementById('selectAll');
    if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener('change', function() {
            toggleAllAttendance();
        });
    }

    // Individual attendance checkboxes
    const attendanceCheckboxes = document.querySelectorAll('.attendance-checkbox');
    attendanceCheckboxes.forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            updateAttendanceCount();
            updateSelectAllState();
        });
    });

    // Attendance quick actions
    initializeAttendanceQuickActions();
}

/**
 * Toggle all attendance checkboxes
 */
function toggleAllAttendance() {
    const selectAll = document.getElementById('selectAll');
    const checkboxes = document.querySelectorAll('.attendance-checkbox');
    
    checkboxes.forEach(checkbox => {
        checkbox.checked = selectAll.checked;
    });
    
    updateAttendanceCount();
}

/**
 * Update attendance count display
 */
function updateAttendanceCount() {
    const checkboxes = document.querySelectorAll('.attendance-checkbox');
    const checkedCount = document.querySelectorAll('.attendance-checkbox:checked').length;
    const totalCount = checkboxes.length;
    
    // Update any count displays
    const countElements = document.querySelectorAll('.attendance-count');
    countElements.forEach(element => {
        element.textContent = `${checkedCount}/${totalCount}`;
    });
}

/**
 * Update select all checkbox state
 */
function updateSelectAllState() {
    const selectAll = document.getElementById('selectAll');
    if (!selectAll) return;
    
    const checkboxes = document.querySelectorAll('.attendance-checkbox');
    const checkedBoxes = document.querySelectorAll('.attendance-checkbox:checked');
    
    if (checkedBoxes.length === 0) {
        selectAll.checked = false;
        selectAll.indeterminate = false;
    } else if (checkedBoxes.length === checkboxes.length) {
        selectAll.checked = true;
        selectAll.indeterminate = false;
    } else {
        selectAll.checked = false;
        selectAll.indeterminate = true;
    }
}

/**
 * Initialize attendance quick actions
 */
function initializeAttendanceQuickActions() {
    // Add keyboard shortcuts for attendance
    document.addEventListener('keydown', function(event) {
        if (event.target.matches('.attendance-checkbox')) {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                event.target.checked = !event.target.checked;
                updateAttendanceCount();
                updateSelectAllState();
            }
        }
    });
}

/**
 * Initialize grade calculation features
 */
function initializeGradeCalculations() {
    const gradeInputs = document.querySelectorAll('input[name*="theory"], input[name*="practical"], input[name*="exam"]');
    
    gradeInputs.forEach(input => {
        input.addEventListener('input', updateGradeTotals);
    });
    
    // Initial calculation
    updateGradeTotals();
}

/**
 * Update grade totals
 */
function updateGradeTotals() {
    // Semester 1 total
    updateSemesterTotal('semester1', ['semester1_theory', 'semester1_practical'], 20);
    
    // Semester 2 total
    updateSemesterTotal('semester2', ['semester2_theory', 'semester2_practical'], 20);
    
    // Final total
    updateSemesterTotal('final', ['final_theory', 'final_practical'], 50);
    
    // Overall total
    updateOverallTotal();
}

/**
 * Update semester total
 */
function updateSemesterTotal(semester, fields, maxTotal) {
    let total = 0;
    let hasValues = false;
    
    fields.forEach(fieldName => {
        const input = document.querySelector(`input[name="${fieldName}"]`);
        if (input && input.value !== '') {
            total += parseFloat(input.value) || 0;
            hasValues = true;
        }
    });
    
    // Add attendance if applicable
    const attendanceInput = document.querySelector(`input[name="${semester}_attendance"]`);
    if (attendanceInput && attendanceInput.value !== '') {
        total += parseFloat(attendanceInput.value) || 0;
    }
    
    // Update display
    const totalElement = document.querySelector(`#${semester}-total, .${semester}-total`);
    if (totalElement) {
        totalElement.textContent = hasValues ? total.toFixed(1) : '0';
        
        // Update progress bar if exists
        const progressBar = totalElement.closest('.card-body')?.querySelector('.progress-bar');
        if (progressBar) {
            const percentage = (total / maxTotal) * 100;
            progressBar.style.width = `${percentage}%`;
        }
    }
}

/**
 * Update overall total
 */
function updateOverallTotal() {
    const semester1 = parseFloat(document.querySelector('#semester1-total, .semester1-total')?.textContent || 0);
    const midyear = parseFloat(document.querySelector('input[name="midyear_exam"]')?.value || 0);
    const semester2 = parseFloat(document.querySelector('#semester2-total, .semester2-total')?.textContent || 0);
    const final = parseFloat(document.querySelector('#final-total, .final-total')?.textContent || 0);
    
    const total = semester1 + midyear + semester2 + final;
    
    // Update total display
    const totalElements = document.querySelectorAll('.total-grade, #total-grade');
    totalElements.forEach(element => {
        element.textContent = total.toFixed(1);
    });
    
    // Update pass/fail status
    const resultElements = document.querySelectorAll('.grade-result, #grade-result');
    resultElements.forEach(element => {
        const passed = total >= 50;
        element.textContent = passed ? 'PASS' : 'FAIL';
        element.className = element.className.replace(/bg-(success|danger)/, '');
        element.classList.add(passed ? 'bg-success' : 'bg-danger');
    });
}

/**
 * Initialize search and filter features
 */
function initializeSearchFilters() {
    // Live search functionality
    const searchInputs = document.querySelectorAll('input[type="search"], input[placeholder*="search" i]');
    searchInputs.forEach(input => {
        input.addEventListener('input', debounce(performLiveSearch, 300));
    });

    // Filter dropdowns auto-submit
    const filterSelects = document.querySelectorAll('select[onchange*="submit"]');
    filterSelects.forEach(select => {
        select.addEventListener('change', function() {
            showLoadingState();
        });
    });
}

/**
 * Perform live search
 */
function performLiveSearch(event) {
    const searchTerm = event.target.value.toLowerCase();
    const targetTable = event.target.getAttribute('data-search-target') || 'table tbody tr';
    const rows = document.querySelectorAll(targetTable);
    
    rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        const matches = text.includes(searchTerm);
        row.style.display = matches ? '' : 'none';
    });
    
    // Update result count
    const visibleRows = document.querySelectorAll(`${targetTable}:not([style*="display: none"])`);
    const countElement = document.querySelector('.search-count');
    if (countElement) {
        countElement.textContent = `${visibleRows.length} results`;
    }
}

/**
 * Show loading state
 */
function showLoadingState() {
    const loader = document.createElement('div');
    loader.className = 'loading-overlay';
    loader.innerHTML = `
        <div class="text-center">
            <i class="fas fa-spinner fa-spin fa-3x text-primary"></i>
            <p class="mt-2">Loading...</p>
        </div>
    `;
    document.body.appendChild(loader);
}

/**
 * Initialize alert auto-dismiss
 */
function initializeAlerts() {
    const alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
    alerts.forEach(alert => {
        setTimeout(() => {
            if (alert.parentNode) {
                alert.style.opacity = '0';
                alert.style.transform = 'translateY(-20px)';
                setTimeout(() => {
                    if (alert.parentNode) {
                        alert.parentNode.removeChild(alert);
                    }
                }, 300);
            }
        }, 5000);
    });
}

/**
 * Initialize keyboard shortcuts
 */
function initializeKeyboardShortcuts() {
    document.addEventListener('keydown', function(event) {
        // Ctrl+S to save forms
        if (event.ctrlKey && event.key === 's') {
            event.preventDefault();
            const submitButton = document.querySelector('button[type="submit"]');
            if (submitButton) {
                submitButton.click();
            }
        }
        
        // Escape to close modals
        if (event.key === 'Escape') {
            const openModal = document.querySelector('.modal.show');
            if (openModal) {
                const modal = bootstrap.Modal.getInstance(openModal);
                if (modal) modal.hide();
            }
        }
        
        // Ctrl+F to focus search
        if (event.ctrlKey && event.key === 'f') {
            const searchInput = document.querySelector('input[type="search"], input[placeholder*="search" i]');
            if (searchInput) {
                event.preventDefault();
                searchInput.focus();
            }
        }
    });
}

/**
 * Utility function: Debounce
 */
function debounce(func, wait) {
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
 * Utility function: Format number
 */
function formatNumber(num, decimals = 1) {
    return parseFloat(num).toFixed(decimals);
}

/**
 * Utility function: Show notification
 */
function showNotification(message, type = 'success') {
    const notification = document.createElement('div');
    notification.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
    notification.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        if (notification.parentNode) {
            notification.classList.remove('show');
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 150);
        }
    }, 4000);
}

/**
 * Export functions for global access
 */
window.FootballAcademicSystem = {
    showNotification,
    formatNumber,
    updateGradeTotals,
    toggleAllAttendance: window.toggleAllAttendance || toggleAllAttendance,
    markAllPresent: window.markAllPresent || function() {
        document.querySelectorAll('.attendance-checkbox').forEach(cb => cb.checked = true);
        updateAttendanceCount();
        updateSelectAllState();
    },
    markAllAbsent: window.markAllAbsent || function() {
        document.querySelectorAll('.attendance-checkbox').forEach(cb => cb.checked = false);
        updateAttendanceCount();
        updateSelectAllState();
    }
};
