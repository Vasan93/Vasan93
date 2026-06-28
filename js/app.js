document.addEventListener('DOMContentLoaded', function () {
    var form = document.getElementById('proposal-form');
    var generateBtn = document.getElementById('generate-btn');
    var previewContent = document.getElementById('preview-content');
    var previewActions = document.getElementById('preview-actions');
    var copyBtn = document.getElementById('copy-btn');
    var downloadBtn = document.getElementById('download-btn');
    var toast = document.getElementById('toast');
    var toastMessage = document.getElementById('toast-message');

    var remaining = parseInt(localStorage.getItem('qp_remaining') || '3');
    updateRemainingCount();

    form.addEventListener('submit', function (e) {
        e.preventDefault();

        if (remaining <= 0) {
            showToast('Upgrade to Pro for unlimited proposals!');
            return;
        }

        var data = {
            yourName: document.getElementById('your-name').value,
            yourRole: document.getElementById('your-role').value,
            yourEmail: document.getElementById('your-email').value,
            clientName: document.getElementById('client-name').value,
            clientIndustry: document.getElementById('client-industry').value,
            projectType: document.getElementById('project-type').value,
            projectDescription: document.getElementById('project-description').value,
            timeline: document.getElementById('timeline').value,
            budget: document.getElementById('budget').value,
            tone: document.getElementById('tone').value,
        };

        generateBtn.querySelector('.btn-text').style.display = 'none';
        generateBtn.querySelector('.btn-loading').style.display = 'inline-flex';
        generateBtn.disabled = true;

        setTimeout(function () {
            var proposal = generateProposal(data);
            previewContent.innerHTML = proposal;
            previewActions.style.display = 'flex';

            remaining--;
            localStorage.setItem('qp_remaining', remaining.toString());
            updateRemainingCount();

            generateBtn.querySelector('.btn-text').style.display = 'inline';
            generateBtn.querySelector('.btn-loading').style.display = 'none';
            generateBtn.disabled = false;

            showToast('Proposal generated successfully!');
        }, 1500);
    });

    copyBtn.addEventListener('click', function () {
        var text = previewContent.innerText;
        navigator.clipboard.writeText(text).then(function () {
            showToast('Proposal copied to clipboard!');
        });
    });

    downloadBtn.addEventListener('click', function () {
        var content = previewContent.innerHTML;
        var html = '<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Proposal</title>' +
            '<style>body{font-family:Arial,sans-serif;max-width:800px;margin:40px auto;padding:20px;color:#1e293b;line-height:1.7}' +
            'h1{color:#4f46e5;text-align:center}h2{color:#4f46e5;border-bottom:1px solid #e2e8f0;padding-bottom:4px;margin-top:24px}' +
            'table{width:100%;border-collapse:collapse;margin:12px 0}th,td{padding:10px 12px;text-align:left;border-bottom:1px solid #e2e8f0;font-size:14px}' +
            'th{background:#f8fafc;font-weight:600}.total-row{font-weight:700;background:#eef2ff}' +
            '.meta{display:flex;justify-content:space-between;background:#f8fafc;padding:16px;border-radius:8px;margin-bottom:24px}' +
            '</style></head><body>' + content + '</body></html>';

        var blob = new Blob([html], { type: 'text/html' });
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = 'proposal.html';
        a.click();
        URL.revokeObjectURL(url);
        showToast('Proposal downloaded!');
    });

    function updateRemainingCount() {
        document.getElementById('remaining-count').textContent = Math.max(0, remaining);
    }

    function showToast(message) {
        toastMessage.textContent = message;
        toast.style.display = 'block';
        setTimeout(function () {
            toast.style.display = 'none';
        }, 3000);
    }

    function generateProposal(data) {
        var today = new Date();
        var dateStr = today.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
        var validUntil = new Date(today.getTime() + 30 * 24 * 60 * 60 * 1000);
        var validStr = validUntil.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });

        var budget = parseFloat(data.budget) || 0;
        var projectTypeLabels = {
            'website': 'Website Design & Development',
            'mobile-app': 'Mobile App Development',
            'branding': 'Branding & Logo Design',
            'marketing': 'Digital Marketing Campaign',
            'seo': 'SEO & Content Strategy',
            'consulting': 'Consulting & Strategy',
            'video': 'Video Production',
            'copywriting': 'Copywriting & Content',
            'social-media': 'Social Media Management',
            'custom': 'Custom Project'
        };
        var projectLabel = projectTypeLabels[data.projectType] || data.projectType;
        var industryLabels = {
            'technology': 'Technology / SaaS',
            'ecommerce': 'E-Commerce / Retail',
            'healthcare': 'Healthcare',
            'finance': 'Finance / Fintech',
            'education': 'Education',
            'realestate': 'Real Estate',
            'food': 'Food & Beverage',
            'media': 'Media & Entertainment',
            'nonprofit': 'Non-Profit',
            'other': ''
        };
        var industryLabel = industryLabels[data.clientIndustry] || '';

        var greeting = getGreeting(data.tone, data.clientName);
        var deliverables = getDeliverables(data.projectType);
        var process = getProcess(data.projectType);
        var breakdown = getPricingBreakdown(data.projectType, budget);

        var html = '<div class="proposal">';
        html += '<div class="proposal-header">';
        html += '<h1>Project Proposal</h1>';
        html += '<div class="proposal-date">' + dateStr + '</div>';
        html += '</div>';

        html += '<div class="proposal-meta">';
        html += '<div class="proposal-meta-group"><h4>Prepared By</h4><p>' + escapeHtml(data.yourName) + '</p>';
        if (data.yourRole) html += '<p style="font-size:12px;color:#64748b;">' + escapeHtml(data.yourRole) + '</p>';
        if (data.yourEmail) html += '<p style="font-size:12px;color:#64748b;">' + escapeHtml(data.yourEmail) + '</p>';
        html += '</div>';
        html += '<div class="proposal-meta-group"><h4>Prepared For</h4><p>' + escapeHtml(data.clientName) + '</p>';
        if (industryLabel) html += '<p style="font-size:12px;color:#64748b;">' + industryLabel + '</p>';
        html += '</div></div>';

        html += '<div class="proposal-section"><h2>Introduction</h2>';
        html += '<p>' + greeting + '</p>';
        html += '<p>This proposal outlines our approach to your <strong>' + escapeHtml(projectLabel) + '</strong> project, including scope of work, timeline, deliverables, and investment details.</p>';
        html += '</div>';

        html += '<div class="proposal-section"><h2>Project Understanding</h2>';
        html += '<p>' + escapeHtml(data.projectDescription) + '</p>';
        html += '<p>' + getUnderstanding(data.projectType, data.clientIndustry, data.clientName) + '</p>';
        html += '</div>';

        html += '<div class="proposal-section"><h2>Scope & Deliverables</h2>';
        html += '<p>The following deliverables are included in this engagement:</p><ul>';
        deliverables.forEach(function (d) {
            html += '<li>' + d + '</li>';
        });
        html += '</ul></div>';

        html += '<div class="proposal-section"><h2>Our Process</h2>';
        html += '<p>We follow a proven methodology to ensure quality results:</p><ul>';
        process.forEach(function (p) {
            html += '<li><strong>' + p.phase + ':</strong> ' + p.desc + '</li>';
        });
        html += '</ul></div>';

        html += '<div class="proposal-section"><h2>Timeline</h2>';
        html += '<p>Estimated project duration: <strong>' + escapeHtml(data.timeline) + '</strong></p>';
        html += '<p>We will begin work within 5 business days of proposal acceptance. Regular progress updates will be provided throughout the engagement.</p>';
        html += '</div>';

        html += '<div class="proposal-section"><h2>Investment</h2>';
        html += '<table class="proposal-pricing-table"><thead><tr><th>Item</th><th>Amount</th></tr></thead><tbody>';
        breakdown.forEach(function (item) {
            html += '<tr><td>' + item.item + '</td><td>$' + item.amount.toLocaleString() + '</td></tr>';
        });
        html += '<tr class="total-row"><td>Total Investment</td><td>$' + budget.toLocaleString() + '</td></tr>';
        html += '</tbody></table>';
        html += '<p><strong>Payment Terms:</strong> 50% upon acceptance, 50% upon project completion.</p>';
        html += '</div>';

        html += '<div class="proposal-section"><h2>Why Choose Us</h2>';
        html += '<ul>';
        html += '<li>Proven track record with similar ' + (industryLabel || 'industry') + ' projects</li>';
        html += '<li>Dedicated communication and transparent process</li>';
        html += '<li>Post-project support and maintenance options</li>';
        html += '<li>100% satisfaction guarantee on all deliverables</li>';
        html += '</ul></div>';

        html += '<div class="proposal-section"><h2>Next Steps</h2>';
        html += '<p>To move forward, simply reply to this proposal to confirm acceptance. We look forward to bringing your vision to life.</p>';
        html += '<p>This proposal is valid until <strong>' + validStr + '</strong>.</p>';
        html += '</div>';

        html += '<div class="proposal-footer">';
        html += '<p><strong>' + escapeHtml(data.yourName) + '</strong></p>';
        if (data.yourEmail) html += '<p>' + escapeHtml(data.yourEmail) + '</p>';
        html += '<p style="margin-top:12px;font-size:11px;color:#94a3b8;">Generated by QuickProposal</p>';
        html += '</div></div>';

        return html;
    }

    function getGreeting(tone, clientName) {
        var name = escapeHtml(clientName);
        var greetings = {
            'professional': 'Dear ' + name + ', thank you for considering us for this project. We are pleased to present this comprehensive proposal for your review and consideration.',
            'friendly': 'Hi ' + name + '! Thanks so much for reaching out about this project. We\'re really excited about the opportunity to work together, and we\'ve put together this proposal to show you exactly how we can help.',
            'bold': name + ', let\'s cut to the chase — you need results, and we deliver them. Here\'s exactly what we\'ll do for you and why we\'re the right team for the job.',
            'minimal': 'Thank you for your interest, ' + name + '. Below you\'ll find our proposed scope, timeline, and investment for your project.'
        };
        return greetings[tone] || greetings['friendly'];
    }

    function getUnderstanding(projectType, industry, clientName) {
        var contexts = {
            'website': 'A strong web presence is essential for growth. We will create a website that not only looks stunning but converts visitors into customers through strategic design and user experience.',
            'mobile-app': 'Mobile-first experiences are key to reaching today\'s users. We will build an app that is intuitive, performant, and designed to keep users engaged.',
            'branding': 'Your brand is your first impression. We will craft a visual identity that communicates your values, differentiates you from competitors, and resonates with your target audience.',
            'marketing': 'Strategic digital marketing drives measurable growth. We will create campaigns that reach the right audience with the right message at the right time.',
            'seo': 'Organic visibility is the foundation of sustainable growth. We will optimize your content and technical infrastructure to improve rankings and drive qualified traffic.',
            'consulting': 'Strategic guidance can transform how you operate. We will analyze your current state, identify opportunities, and deliver actionable recommendations.',
            'video': 'Video content drives engagement like no other medium. We will produce compelling visual content that tells your story and connects with your audience.',
            'copywriting': 'Words drive action. We will craft compelling copy that speaks directly to your audience and motivates them to engage with your brand.',
            'social-media': 'Social media presence builds community and drives brand awareness. We will create and manage a strategy that grows your following and engagement.',
            'custom': 'We understand the unique requirements of your project and are excited to bring our expertise to deliver exceptional results.'
        };
        return contexts[projectType] || contexts['custom'];
    }

    function getDeliverables(projectType) {
        var deliverables = {
            'website': [
                'Custom website design (mockups & prototypes)',
                'Responsive development (mobile, tablet, desktop)',
                'Content management system (CMS) integration',
                'SEO-optimized pages and meta tags',
                'Contact forms and analytics setup',
                'Cross-browser testing & QA',
                'Launch support and handover documentation'
            ],
            'mobile-app': [
                'UI/UX design with interactive prototypes',
                'Native or cross-platform app development',
                'Backend API development and integration',
                'Push notifications and user authentication',
                'App store submission and optimization',
                'Testing across devices and OS versions',
                'Post-launch bug fixes (30 days)'
            ],
            'branding': [
                'Brand strategy and positioning document',
                'Logo design (3 concepts, 2 revision rounds)',
                'Color palette and typography selection',
                'Brand guidelines document',
                'Business card and letterhead design',
                'Social media profile assets',
                'Source files in all formats'
            ],
            'marketing': [
                'Marketing strategy and campaign plan',
                'Target audience research and personas',
                'Ad creative design and copywriting',
                'Campaign setup (Google Ads, Social Ads)',
                'A/B testing and optimization',
                'Weekly performance reports',
                'End-of-campaign analysis and recommendations'
            ],
            'seo': [
                'Comprehensive SEO audit',
                'Keyword research and strategy',
                'On-page optimization (meta, content, structure)',
                'Technical SEO fixes and improvements',
                'Content strategy and editorial calendar',
                'Link building outreach plan',
                'Monthly ranking and traffic reports'
            ],
            'consulting': [
                'Discovery sessions and stakeholder interviews',
                'Current state analysis and assessment',
                'Market and competitor research',
                'Strategic recommendations document',
                'Implementation roadmap with priorities',
                'Presentation to leadership team',
                'Follow-up review session (30 days)'
            ],
            'video': [
                'Creative brief and storyboard',
                'Script writing and review',
                'Professional video production (filming)',
                'Post-production editing and color grading',
                'Motion graphics and animations',
                'Music and sound design',
                'Final delivery in multiple formats'
            ],
            'copywriting': [
                'Content strategy and messaging framework',
                'Website copy (up to 10 pages)',
                'SEO-optimized blog posts (4 articles)',
                'Email sequence copy (5 emails)',
                'Social media caption templates',
                'Two rounds of revisions',
                'Style guide for future content'
            ],
            'social-media': [
                'Social media audit and strategy',
                'Content calendar (30 days)',
                'Custom graphic design for posts',
                'Community management and engagement',
                'Hashtag and growth strategy',
                'Monthly analytics and insights reports',
                'Competitor monitoring'
            ],
            'custom': [
                'Project discovery and requirements gathering',
                'Detailed project plan and milestones',
                'Design and/or development work',
                'Quality assurance and testing',
                'Documentation and handover',
                'Two rounds of revisions',
                'Post-delivery support (14 days)'
            ]
        };
        return deliverables[projectType] || deliverables['custom'];
    }

    function getProcess(projectType) {
        return [
            { phase: 'Discovery', desc: 'We start by deeply understanding your goals, audience, and requirements through collaborative sessions.' },
            { phase: 'Strategy & Planning', desc: 'We create a detailed project plan with milestones, ensuring alignment before any work begins.' },
            { phase: 'Design & Creation', desc: 'Our team brings the vision to life with iterative design and development, with checkpoints for your feedback.' },
            { phase: 'Review & Refinement', desc: 'We incorporate your feedback through structured revision rounds to ensure the final product exceeds expectations.' },
            { phase: 'Delivery & Launch', desc: 'We handle the launch process, provide all deliverables and documentation, and ensure a smooth handover.' }
        ];
    }

    function getPricingBreakdown(projectType, totalBudget) {
        var breakdowns = {
            'website': [
                { item: 'Discovery & Strategy', pct: 0.15 },
                { item: 'UI/UX Design', pct: 0.25 },
                { item: 'Development & Integration', pct: 0.40 },
                { item: 'Testing & QA', pct: 0.10 },
                { item: 'Launch & Documentation', pct: 0.10 }
            ],
            'mobile-app': [
                { item: 'Discovery & Planning', pct: 0.10 },
                { item: 'UI/UX Design & Prototyping', pct: 0.20 },
                { item: 'App Development', pct: 0.45 },
                { item: 'Testing & QA', pct: 0.15 },
                { item: 'Store Submission & Launch', pct: 0.10 }
            ],
            'branding': [
                { item: 'Brand Strategy & Research', pct: 0.25 },
                { item: 'Logo Design', pct: 0.30 },
                { item: 'Visual Identity System', pct: 0.25 },
                { item: 'Brand Guidelines', pct: 0.15 },
                { item: 'Asset Production', pct: 0.05 }
            ],
            'default': [
                { item: 'Discovery & Strategy', pct: 0.20 },
                { item: 'Core Project Work', pct: 0.45 },
                { item: 'Review & Revisions', pct: 0.15 },
                { item: 'Testing & QA', pct: 0.10 },
                { item: 'Delivery & Support', pct: 0.10 }
            ]
        };

        var template = breakdowns[projectType] || breakdowns['default'];
        return template.map(function (item) {
            return { item: item.item, amount: Math.round(totalBudget * item.pct) };
        });
    }

    function escapeHtml(str) {
        var div = document.createElement('div');
        div.appendChild(document.createTextNode(str || ''));
        return div.innerHTML;
    }
});
