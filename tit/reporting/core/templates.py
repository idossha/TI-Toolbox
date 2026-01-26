"""
CSS and JavaScript templates for TI-Toolbox reports.

This module contains the default styling and interactivity for generated reports.
"""

DEFAULT_CSS_STYLES = """
/* TI-Toolbox Report Styles */
:root {
    --primary-gradient-start: #667eea;
    --primary-gradient-end: #764ba2;
    --success-color: #28a745;
    --warning-color: #ffc107;
    --error-color: #dc3545;
    --info-color: #17a2b8;
    --text-color: #333;
    --text-muted: #6c757d;
    --bg-light: #f8f9fa;
    --bg-white: #ffffff;
    --border-color: #dee2e6;
    --shadow-sm: 0 1px 3px rgba(0,0,0,0.1);
    --shadow-md: 0 4px 6px rgba(0,0,0,0.1);
    --shadow-lg: 0 10px 25px rgba(0,0,0,0.15);
    --border-radius: 8px;
    --spacing-xs: 0.25rem;
    --spacing-sm: 0.5rem;
    --spacing-md: 1rem;
    --spacing-lg: 1.5rem;
    --spacing-xl: 2rem;
}

* {
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    line-height: 1.6;
    color: var(--text-color);
    background: var(--bg-light);
    margin: 0;
    padding: 0;
}

.report-container {
    max-width: 1200px;
    margin: 0 auto;
    padding: var(--spacing-lg);
}

/* Header */
.report-header {
    background: linear-gradient(135deg, var(--primary-gradient-start), var(--primary-gradient-end));
    color: white;
    padding: var(--spacing-xl);
    border-radius: var(--border-radius);
    margin-bottom: var(--spacing-xl);
    box-shadow: var(--shadow-lg);
}

.report-header h1 {
    margin: 0 0 var(--spacing-sm) 0;
    font-size: 2rem;
    font-weight: 600;
}

.report-header .subtitle {
    font-size: 1.1rem;
    opacity: 0.9;
    margin: 0;
}

.header-meta {
    display: flex;
    flex-wrap: wrap;
    gap: var(--spacing-md);
    margin-top: var(--spacing-md);
    font-size: 0.9rem;
    opacity: 0.85;
}

.header-meta span {
    display: flex;
    align-items: center;
    gap: var(--spacing-xs);
}

/* Navigation / TOC */
.report-nav {
    background: var(--bg-white);
    padding: var(--spacing-lg);
    border-radius: var(--border-radius);
    margin-bottom: var(--spacing-xl);
    box-shadow: var(--shadow-sm);
    position: sticky;
    top: var(--spacing-md);
    z-index: 100;
}

.report-nav h2 {
    margin: 0 0 var(--spacing-md) 0;
    font-size: 1.1rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

.toc-list {
    display: flex;
    flex-wrap: wrap;
    gap: var(--spacing-sm);
    list-style: none;
    padding: 0;
    margin: 0;
}

.toc-list a {
    display: inline-block;
    padding: var(--spacing-xs) var(--spacing-md);
    background: var(--bg-light);
    color: var(--text-color);
    text-decoration: none;
    border-radius: 20px;
    font-size: 0.9rem;
    transition: all 0.2s;
}

.toc-list a:hover {
    background: var(--primary-gradient-start);
    color: white;
}

/* Main Content */
.report-main {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-xl);
}

/* Sections */
.report-section {
    background: var(--bg-white);
    padding: var(--spacing-xl);
    border-radius: var(--border-radius);
    box-shadow: var(--shadow-sm);
}

.report-section h2.section-title {
    margin: 0 0 var(--spacing-lg) 0;
    font-size: 1.5rem;
    color: var(--primary-gradient-start);
    border-bottom: 2px solid var(--bg-light);
    padding-bottom: var(--spacing-md);
}

.section-description {
    color: var(--text-muted);
    margin-bottom: var(--spacing-lg);
}

.section-content {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-lg);
}

/* Reportlets */
.reportlet {
    margin-bottom: var(--spacing-md);
}

.reportlet h3 {
    margin: 0 0 var(--spacing-md) 0;
    font-size: 1.1rem;
    color: var(--text-color);
}

/* Metadata Reportlet - Table Mode */
.metadata-table {
    width: 100%;
    border-collapse: collapse;
}

.metadata-table td {
    padding: var(--spacing-sm) var(--spacing-md);
    border-bottom: 1px solid var(--border-color);
}

.metadata-table .key-cell {
    width: 35%;
    font-weight: 500;
    color: var(--text-muted);
    background: var(--bg-light);
}

.metadata-table .value-cell {
    color: var(--text-color);
}

/* Metadata Reportlet - Card Mode */
.card-grid {
    display: grid;
    gap: var(--spacing-md);
}

.card-grid.columns-2 {
    grid-template-columns: repeat(2, 1fr);
}

.card-grid.columns-3 {
    grid-template-columns: repeat(3, 1fr);
}

.card-grid.columns-4 {
    grid-template-columns: repeat(4, 1fr);
}

.metadata-card {
    background: var(--bg-light);
    padding: var(--spacing-md);
    border-radius: var(--border-radius);
    text-align: center;
}

.card-label {
    font-size: 0.85rem;
    color: var(--text-muted);
    margin-bottom: var(--spacing-xs);
}

.card-value {
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--text-color);
}

/* Image Reportlet */
.image-figure {
    margin: 0;
    text-align: center;
}

.report-image {
    max-width: 100%;
    height: auto;
    border-radius: var(--border-radius);
    box-shadow: var(--shadow-sm);
}

.image-caption {
    margin-top: var(--spacing-sm);
    font-size: 0.9rem;
    color: var(--text-muted);
    font-style: italic;
}

.image-placeholder {
    background: var(--bg-light);
    padding: var(--spacing-xl);
    text-align: center;
    border-radius: var(--border-radius);
    color: var(--text-muted);
}

/* Table Reportlet */
.table-wrapper {
    overflow-x: auto;
}

.data-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
}

.data-table th,
.data-table td {
    padding: var(--spacing-sm) var(--spacing-md);
    text-align: left;
    border-bottom: 1px solid var(--border-color);
}

.data-table th {
    background: var(--bg-light);
    font-weight: 600;
    color: var(--text-color);
    position: sticky;
    top: 0;
}

.data-table.striped tbody tr:nth-child(even) {
    background: var(--bg-light);
}

.data-table.compact th,
.data-table.compact td {
    padding: var(--spacing-xs) var(--spacing-sm);
}

.data-table tbody tr:hover {
    background: rgba(102, 126, 234, 0.05);
}

/* Text Reportlet */
.text-content {
    line-height: 1.8;
}

.text-content.monospace {
    font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
    background: var(--bg-light);
    padding: var(--spacing-lg);
    border-radius: var(--border-radius);
    font-size: 0.9rem;
    white-space: pre-wrap;
}

.text-content.copyable {
    position: relative;
}

.copy-btn {
    background: var(--primary-gradient-start);
    color: white;
    border: none;
    padding: var(--spacing-xs) var(--spacing-md);
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.85rem;
    margin-bottom: var(--spacing-sm);
    transition: background 0.2s;
}

.copy-btn:hover {
    background: var(--primary-gradient-end);
}

.copy-btn.copied {
    background: var(--success-color);
}

/* Error Reportlet */
.error-reportlet.success {
    background: rgba(40, 167, 69, 0.1);
    border: 1px solid var(--success-color);
    padding: var(--spacing-md);
    border-radius: var(--border-radius);
}

.success-message {
    color: var(--success-color);
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);
    font-weight: 500;
}

.status-icon {
    font-size: 1.2rem;
}

.messages-list {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-sm);
}

.message-item {
    display: flex;
    gap: var(--spacing-sm);
    padding: var(--spacing-sm) var(--spacing-md);
    border-radius: var(--border-radius);
    align-items: flex-start;
}

.message-item.error,
.message-item.critical {
    background: rgba(220, 53, 69, 0.1);
    border-left: 3px solid var(--error-color);
}

.message-item.warning {
    background: rgba(255, 193, 7, 0.1);
    border-left: 3px solid var(--warning-color);
}

.message-item.info {
    background: rgba(23, 162, 184, 0.1);
    border-left: 3px solid var(--info-color);
}

.severity-icon {
    font-size: 1rem;
    flex-shrink: 0;
}

.message-content {
    flex: 1;
}

.error-context {
    color: var(--text-muted);
    margin-right: var(--spacing-xs);
    font-size: 0.85rem;
}

.error-step {
    display: block;
    font-size: 0.8rem;
    color: var(--text-muted);
    margin-top: var(--spacing-xs);
}

/* References Reportlet */
.references-list {
    list-style: none;
    padding: 0;
    margin: 0;
}

.reference-item {
    padding: var(--spacing-sm) 0;
    border-bottom: 1px solid var(--border-color);
    display: flex;
    gap: var(--spacing-md);
}

.reference-item:last-child {
    border-bottom: none;
}

.ref-key {
    color: var(--primary-gradient-start);
    font-weight: 600;
    flex-shrink: 0;
}

.ref-citation {
    color: var(--text-color);
}

.ref-citation a {
    color: var(--primary-gradient-start);
    text-decoration: none;
    margin-left: var(--spacing-xs);
}

.ref-citation a:hover {
    text-decoration: underline;
}

/* Processing Steps */
.processing-step {
    border: 1px solid var(--border-color);
    border-radius: var(--border-radius);
    margin-bottom: var(--spacing-md);
    overflow: hidden;
}

.step-header {
    display: flex;
    align-items: center;
    gap: var(--spacing-md);
    padding: var(--spacing-md);
    background: var(--bg-light);
    cursor: pointer;
}

.step-status {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.8rem;
    color: white;
    flex-shrink: 0;
}

.step-status.completed {
    background: var(--success-color);
}

.step-status.failed {
    background: var(--error-color);
}

.step-status.skipped {
    background: var(--text-muted);
}

.step-status.running {
    background: var(--info-color);
}

.step-status.pending {
    background: var(--border-color);
    color: var(--text-muted);
}

.step-name {
    font-weight: 500;
    flex: 1;
}

.step-duration {
    color: var(--text-muted);
    font-size: 0.9rem;
}

.step-content {
    padding: var(--spacing-md);
    display: none;
}

.step-content.expanded {
    display: block;
}

/* Conductivity Table */
.conductivity-table {
    width: 100%;
}

.conductivity-table th {
    background: linear-gradient(135deg, var(--primary-gradient-start), var(--primary-gradient-end));
    color: white;
}

/* Image Grid */
.image-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: var(--spacing-md);
}

.slice-series {
    display: flex;
    gap: var(--spacing-sm);
    justify-content: center;
    flex-wrap: wrap;
}

.slice-image {
    flex: 1;
    min-width: 80px;
    max-width: 150px;
}

/* Footer */
.report-footer {
    text-align: center;
    padding: var(--spacing-xl);
    color: var(--text-muted);
    font-size: 0.9rem;
}

.report-footer a {
    color: var(--primary-gradient-start);
    text-decoration: none;
}

.report-footer a:hover {
    text-decoration: underline;
}

/* Responsive */
@media (max-width: 768px) {
    .report-container {
        padding: var(--spacing-md);
    }

    .report-header {
        padding: var(--spacing-lg);
    }

    .report-header h1 {
        font-size: 1.5rem;
    }

    .card-grid.columns-2,
    .card-grid.columns-3,
    .card-grid.columns-4 {
        grid-template-columns: 1fr;
    }

    .report-nav {
        position: static;
    }

    .toc-list {
        flex-direction: column;
    }

    .metadata-table .key-cell {
        width: 40%;
    }
}

/* Print styles */
@media print {
    .report-nav {
        display: none;
    }

    .report-header {
        background: var(--primary-gradient-start) !important;
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
    }

    .report-section {
        break-inside: avoid;
    }

    .copy-btn {
        display: none;
    }
}
"""

DEFAULT_JS_SCRIPTS = """
// TI-Toolbox Report Scripts

// Copy to clipboard functionality
function copyToClipboard(elementId) {
    const element = document.getElementById(elementId);
    if (!element) return;

    const text = element.innerText || element.textContent;

    navigator.clipboard.writeText(text).then(() => {
        // Find the button that triggered this
        const buttons = document.querySelectorAll('.copy-btn');
        buttons.forEach(btn => {
            if (btn.getAttribute('onclick').includes(elementId)) {
                const originalText = btn.textContent;
                btn.textContent = 'Copied!';
                btn.classList.add('copied');
                setTimeout(() => {
                    btn.textContent = originalText;
                    btn.classList.remove('copied');
                }, 2000);
            }
        });
    }).catch(err => {
        console.error('Failed to copy: ', err);
    });
}

// Toggle collapsible sections
function toggleSection(sectionId) {
    const section = document.getElementById(sectionId);
    if (!section) return;

    const content = section.querySelector('.section-content');
    if (content) {
        content.classList.toggle('collapsed');
    }
}

// Toggle processing step details
function toggleStep(stepId) {
    const content = document.getElementById(stepId + '-content');
    if (content) {
        content.classList.toggle('expanded');
    }
}

// Smooth scroll to section
document.addEventListener('DOMContentLoaded', function() {
    const tocLinks = document.querySelectorAll('.toc-list a');
    tocLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const targetId = this.getAttribute('href').substring(1);
            const target = document.getElementById(targetId);
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });
});

// Highlight current section in TOC while scrolling
document.addEventListener('DOMContentLoaded', function() {
    const sections = document.querySelectorAll('.report-section');
    const tocLinks = document.querySelectorAll('.toc-list a');

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const id = entry.target.getAttribute('id');
                tocLinks.forEach(link => {
                    link.classList.remove('active');
                    if (link.getAttribute('href') === '#' + id) {
                        link.classList.add('active');
                    }
                });
            }
        });
    }, { threshold: 0.3 });

    sections.forEach(section => observer.observe(section));
});
"""


def get_html_template(
    title: str,
    content: str,
    toc_html: str = "",
    metadata_html: str = "",
    footer_html: str = "",
    custom_css: str = "",
    custom_js: str = "",
) -> str:
    """
    Generate a complete HTML document with the report content.

    Args:
        title: The report title
        content: The main HTML content
        toc_html: Table of contents HTML
        metadata_html: Header metadata HTML
        footer_html: Footer HTML
        custom_css: Additional CSS styles
        custom_js: Additional JavaScript

    Returns:
        Complete HTML document as a string
    """
    css = DEFAULT_CSS_STYLES
    if custom_css:
        css += f"\n/* Custom Styles */\n{custom_css}"

    js = DEFAULT_JS_SCRIPTS
    if custom_js:
        js += f"\n// Custom Scripts\n{custom_js}"

    nav_html = ""
    if toc_html:
        nav_html = f'''
        <nav class="report-nav">
            <h2>Contents</h2>
            {toc_html}
        </nav>
        '''

    footer = footer_html or '''
        <footer class="report-footer">
            <p>Generated by <a href="https://github.com/idossha/TI-toolbox" target="_blank">TI-Toolbox</a></p>
        </footer>
    '''

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
{css}
    </style>
</head>
<body>
    <div class="report-container">
        <header class="report-header">
            <h1>{title}</h1>
            {metadata_html}
        </header>

        {nav_html}

        <main class="report-main">
            {content}
        </main>

        {footer}
    </div>

    <script>
{js}
    </script>
</body>
</html>
'''
