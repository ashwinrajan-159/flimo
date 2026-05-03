const API_BASE = '';
// DEBUG MODE: Can be enabled via ?debug=true query param or this flag
const urlParams = new URLSearchParams(window.location.search);
const DEBUG_MODE = true; // Force true as per requirements

const routes = {
    "/": { viewId: "view-home", init: () => { discoverMode = 'popular'; initHome(); syncHomeMode(); }, title: "Home" },
    "/trending": { viewId: "view-search", init: () => { configureStandaloneGrid('trending'); }, title: "Trending Now" },
    "/latest": { viewId: "view-search", init: () => { configureStandaloneGrid('latest'); }, title: "New Releases" },
    "/search": { viewId: "view-search", init: () => { restoreExploreView(); }, title: "Explore" },
    "/saved": { viewId: "view-saved", init: initSaved, title: "Watchlist" },
    "/community": { viewId: "view-community", init: initCommunity, title: "Community" },
    "/profile": { viewId: "view-profile", title: "Profile" }
};

function configureStandaloneGrid(category) {
    const topBar = document.querySelector('.search-top-bar');
    if (topBar) topBar.classList.add('hidden');
    searchState.category = category;
    syncSearchCategory();
    initSearch();
}

function restoreExploreView() {
    const topBar = document.querySelector('.search-top-bar');
    if (topBar) topBar.classList.remove('hidden');
    searchState.category = 'popular';
    syncSearchCategory();
    initSearch();
}

function syncSearchCategory() {
    document.querySelectorAll('.category-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.category === searchState.category);
    });
}

function syncHomeMode() {
    document.querySelectorAll('.discover-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.mode === discoverMode);
    });
    if (homeInitDone && document.getElementById('discover-results-grid')) {
        const triggerEvent = new Event('triggerSearchDiscover');
        window.dispatchEvent(triggerEvent);
    }
}

/* --- SAVED MANAGER (Moved to Top for Availability) --- */
const SavedManager = {
    getSaved: () => {
        try {
            const items = JSON.parse(localStorage.getItem('streamai_saved')) || [];
            return items.map(i => ({ status: 'queued', ...i }));
        } catch { return []; }
    },
    isSaved: (id) => {
        const saved = SavedManager.getSaved();
        return saved.some(item => item.content_id === id);
    },
    toggle: (item) => {
        let saved = SavedManager.getSaved();
        const existingIndex = saved.findIndex(i => i.content_id === item.content_id);

        if (existingIndex >= 0) {
            saved.splice(existingIndex, 1);
        } else {
            saved.push({ ...item, status: 'queued', saved_at: Date.now() });
        }
        localStorage.setItem('streamai_saved', JSON.stringify(saved));

        // Update UI if on saved page
        const savedView = document.getElementById('view-saved');
        if (savedView && !savedView.classList.contains('hidden')) {
            if (typeof initSaved === 'function') initSaved();
        }
        // Update all buttons for this item
        SavedManager.updateButtons(item.content_id);
    },
    toggleWatched: (id) => {
        let saved = SavedManager.getSaved();
        const item = saved.find(i => i.content_id === id);
        if (item) {
            item.status = item.status === 'watched' ? 'queued' : 'watched';
            localStorage.setItem('streamai_saved', JSON.stringify(saved));
            if (typeof initSaved === 'function') initSaved(); // Refresh UI
        }
    },
    updateButtons: (id) => {
        const isSaved = SavedManager.isSaved(id);
        document.querySelectorAll(`.save-btn-${id}`).forEach(btn => {
            if (btn.tagName === 'BUTTON' && btn.id === 'panel-watchlist') { // Detail panel button
                btn.innerHTML = `<span class="material-symbols-outlined" style="font-size:16px;">bookmark</span> ${isSaved ? 'Remove from Watchlist' : 'Watchlist'}`;
                btn.style.background = isSaved ? '#ef4444' : '';
                btn.style.borderColor = isSaved ? '#ef4444' : '';
            } else {
                btn.innerHTML = `<span class="material-symbols-outlined" style="font-size:18px;font-variation-settings:'FILL' ${isSaved ? 1 : 0};">bookmark</span>`;
                btn.classList.toggle('active', isSaved);
            }
        });
    }
};

// Expose to window for onclick handlers (must be global)
window.toggleSave = (event, itemStr) => {
    event.stopPropagation();
    try {
        const item = JSON.parse(decodeURIComponent(itemStr));
        SavedManager.toggle(item);
    } catch (e) {
        console.error("Error toggling save:", e);
    }
};

window.toggleWatched = (event, id) => {
    event.stopPropagation();
    SavedManager.toggleWatched(id);
};

function navigateTo(url) {
    history.pushState(null, null, url);
    handleRoute();
}

function handleRoute() {
    const path = window.location.pathname;
    const route = routes[path] || routes["/"];

    document.querySelectorAll('.view-section').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));

    const view = document.getElementById(route.viewId);
    if (view) view.classList.remove('hidden');

    const navLink = document.querySelector(`.nav-item[href="${path}"]`);
    if (navLink) navLink.classList.add('active');

    // Update Header Title
    const pageTitle = document.getElementById('page-title');
    if (pageTitle && route.title) pageTitle.innerText = route.title;

    if (route.init) route.init();
}

window.addEventListener("popstate", handleRoute);
document.addEventListener("DOMContentLoaded", () => {
    initAuth();
    
    document.body.addEventListener("click", e => {
        const link = e.target.closest("[data-link]");
        if (link) {
            e.preventDefault();
            navigateTo(link.href);
        }
    });
    handleRoute();
    setupGlobalSearch();
    if (typeof initRightSidebar === 'function') initRightSidebar();

    // Trailer Modal Global Handlers
    const trailerModal = document.getElementById('trailer-modal');
    const trailerClose = document.getElementById('trailer-modal-close');
    const trailerBackdrop = document.getElementById('trailer-modal-backdrop');
    const trailerIframe = document.getElementById('trailer-iframe');

    const closeTrailerModal = () => {
        if (trailerModal) trailerModal.classList.add('hidden');
        if (trailerIframe) trailerIframe.src = ""; // Stop video playback
    };

    if (trailerClose) trailerClose.addEventListener('click', closeTrailerModal);
    if (trailerBackdrop) trailerBackdrop.addEventListener('click', closeTrailerModal);
});

/* --- RIGHT SIDEBAR INIT --- */
async function initRightSidebar() {
    const trendingList = document.getElementById('rp-trending-list');
    const newReleasesList = document.getElementById('rp-new-releases');
    
    // Fetch YouTube Trending Trailers
    if (trendingList) {
        try {
            const res = await fetch(`${API_BASE}/browse/youtube-trending?limit=5`);
            if (res.ok) {
                const data = await res.json();
                if (data.results && data.results.length > 0) {
                    trendingList.innerHTML = data.results.map(item => createTrailerCard(item)).join('');
                } else {
                    trendingList.innerHTML = '<p class="text-muted">No trailers available</p>';
                }
            }
        } catch (e) {
            trendingList.innerHTML = '<p class="text-muted">Failed to load trailers</p>';
        }
    }

    // Fetch New Releases
    if (newReleasesList) {
        try {
            const res = await fetch(`${API_BASE}/browse/latest?page=1&limit=2`);
            if (res.ok) {
                const data = await res.json();
                newReleasesList.innerHTML = data.results.map(item => createRightPanelImageCard(item)).join('');
                newReleasesList.querySelectorAll('.animate-on-scroll').forEach(el => window.observeElement(el));
            }
        } catch (e) {
            newReleasesList.innerHTML = '<p class="text-muted">Failed to load</p>';
        }
    }

    const seeAllNrBtn = document.querySelector('.rp-see-all');
    if (seeAllNrBtn) {
        seeAllNrBtn.addEventListener('click', (e) => {
            e.preventDefault();
            navigateTo('/latest');
        });
    }
}

function createTrailerCard(item) {
    const embedUrl = item.url || `https://www.youtube.com/embed/${item.video_id}?autoplay=1`;
    return `
        <div class="rp-trailer-card" onclick="openTrailerModal('${embedUrl}')">
            <div class="rp-trailer-thumb-wrapper">
                <img class="rp-trailer-thumb" src="${item.thumbnail}" alt="${item.title}" loading="lazy">
                <div class="rp-trailer-play-overlay">
                    <span class="material-symbols-outlined" style="font-size:28px; font-variation-settings:'FILL' 1; color:#fff;">play_arrow</span>
                </div>
            </div>
            <div class="rp-trailer-info">
                <div class="rp-trailer-title">${item.title}</div>
                <div class="rp-trailer-meta">${item.channel} • ${item.views}</div>
            </div>
        </div>
    `;
}

function openTrailerModal(url) {
    const modal = document.getElementById('trailer-modal');
    const iframe = document.getElementById('trailer-iframe');
    if (modal && iframe) {
        iframe.src = url;
        modal.classList.remove('hidden');
    }
}

function createRightPanelImageCard(item) {
    // We add 'animate-on-scroll' so the MutationObserver or inline script can catch it.
    // However, innerHTML doesn't trigger MutationObserver easily for individual elements without deeper wiring.
    // Instead of wiring MutationObserver, we'll embed an onload trick, OR we can just select all .animate-on-scroll after innerHTML.
    // We will do a global querySelector after innerHTML replaces the content.

    return `
        <div class="rp-nr-card animate-on-scroll" data-id="${item.content_id}" data-type="${item.content_type}" onclick="openDetail('${item.content_id}')">
            <img class="rp-nr-img" src="${item.thumbnail_url || 'https://via.placeholder.com/300x170/1A1608/F2CC0D?text=No+Image'}" alt="${item.title}">
            <div class="rp-nr-overlay"></div>
            <div class="rp-nr-content">
                <div class="rp-nr-label">NEW</div>
                <div class="rp-nr-title">${item.title}</div>
            </div>
        </div>
    `;
}


/* --- 2. INFINITE SCROLLER UTILITY --- */
class InfiniteScroller {
    constructor(containerId, fetchFn, options = {}) {
        this.container = document.getElementById(containerId);
        this.fetchFn = fetchFn;
        // Ensure the container exists before proceeding
        if (!this.container) {
            console.warn(`InfiniteScroller: Container with ID '${containerId}' not found.`);
            return;
        }
        this.page = 1;
        this.loading = false;
        this.finished = false;
        this.triggerId = options.triggerId;

        this.renderedIds = new Set();

        // Initial load
        this.loadNext();

        // Scroll Observer
        if (this.triggerId) {
            this.setupObserver();
        } else {
            // Horizontal scroll listener fallback
            this.container.addEventListener('scroll', () => this.checkHorizontalScroll());
        }
    }

    setupObserver() {
        const trigger = document.getElementById(this.triggerId);
        if (!trigger) return;

        const observer = new IntersectionObserver((entries) => {
            if (entries[0].isIntersecting) {
                this.loadNext();
            }
        }, { threshold: 0.1 });

        observer.observe(trigger);
    }

    checkHorizontalScroll() {
        const { scrollLeft, scrollWidth, clientWidth } = this.container;
        if (scrollLeft + clientWidth >= scrollWidth * 0.8) this.loadNext();
    }

    async loadNext() {
        if (this.loading || this.finished) return;
        this.loading = true;

        try {
            const items = await this.fetchFn(this.page);
            if (!items || items.length === 0) {
                this.finished = true;
                if (this.page === 1 && this.container) {
                    // If first page is empty, showing a message might be good, 
                    // but for infinite-scroll rows (like trending), empty usually means nothing to show, 
                    // so we just leave it or hide container?
                    // For debugging, let's log.
                    console.log(`InfiniteScroller: No items found for ${this.container.id}`);
                }
            } else {
                this.render(items);
                this.page++;
            }
        } catch (e) {
            console.error("Fetch error for " + (this.container?.id || 'unknown'), e);
            if (this.page === 1 && this.container) {
                this.container.innerHTML = `<div class="error-message p-4 text-red-500">Failed to load content. <button onclick="location.reload()" class="underline">Retry</button></div>`;
            }
        } finally {
            this.loading = false;
        }
    }

    render(items) {
        // Filter duplicates
        const newItems = items.filter(item => {
            if (this.renderedIds.has(item.content_id)) return false;
            this.renderedIds.add(item.content_id);
            return true;
        });

        if (newItems.length === 0) return;

        const html = newItems.map(createCardHTML).join('');
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = html;
        Array.from(tempDiv.children).forEach(child => {
            this.container.appendChild(child);
            window.observeElement(child); // Observe each new card
        });
    }
}

function createCardHTML(item) {
    const img = item.thumbnail_url || 'https://via.placeholder.com/200x300/1A1608/F2CC0D?text=No+Image';
    const contentId = item.content_id || '';

    const isSaved = (typeof SavedManager !== 'undefined') ? SavedManager.isSaved(contentId) : false;
    const itemStr = encodeURIComponent(JSON.stringify(item));

    const reason = item.reason || '';
    const title = item.title || 'Untitled';
    const rating = item.rating ? item.rating.toFixed(1) : '-';
    const year = item.release_year || '';
    const lang = item.original_language ? item.original_language.toUpperCase() : 'EN';
    const cert = item.adult ? 'A' : 'UA';

    return `
        <div class="card animate-on-scroll" onclick="openDetail('${contentId}')" data-reason="${encodeURIComponent(reason)}">
            <div class="card-image-wrapper">
                <img src="${img}" class="card-img" loading="lazy" alt="${title}">
                <div class="card-overlay"></div>
                <div class="card-rating-badge">
                    <span class="material-symbols-outlined" style="font-size:12px;font-variation-settings:'FILL' 1;">star</span> ${rating}
                </div>
                <!-- Play button overlay -->
                <div class="card-play-btn">
                    <div class="card-play-icon">
                        <span class="material-symbols-outlined" style="font-size:32px;font-variation-settings:'FILL' 1;">play_arrow</span>
                    </div>
                </div>
                <button class="save-btn save-btn-${contentId} ${isSaved ? 'active' : ''}" 
                     onclick="window.toggleSave(event, '${itemStr}')" title="Watchlist">
                     <span class="material-symbols-outlined" style="font-size:18px;font-variation-settings:'FILL' ${isSaved ? 1 : 0};">bookmark</span>
                </button>
            </div>
            <div class="card-info">
                <div class="card-title">${title}</div>
                <div class="card-meta">
                    <span>${cert}</span>
                    <span class="meta-separator"></span>
                    <span>${lang}</span>
                    ${year ? `<span class="meta-separator"></span><span>${year}</span>` : ''}
                </div>
            </div>
        </div>
    `;
}

/* --- FULL PAGE DETAIL VIEW --- */
async function openDetail(contentId) {
    if (!contentId) return;

    // View Switching
    document.querySelectorAll('.view-section').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    const view = document.getElementById('view-detail');
    if (view) view.classList.remove('hidden');

    view.dataset.contentId = contentId;

    // Track in Continue Watching (localStorage)
    trackRecentlyViewed(contentId);

    // Setup Back button
    const backBtn = document.getElementById('detail-back-btn');
    if (backBtn) {
        backBtn.onclick = () => {
            // Re-run router to go back to active page based on URL
            if (typeof handleRoute === 'function') handleRoute();
        };
    }

    try {
        const res = await fetch(`${API_BASE}/content/${contentId}`);
        if (!res.ok) throw new Error('Not found');
        const data = await res.json();

        // Hero Background
        const heroBg = document.getElementById('detail-hero-bg');
        if (heroBg) {
            const imgUrl = data.thumbnail_url || 'https://via.placeholder.com/1200x500/1A1608/F2CC0D?text=No+Image';
            heroBg.style.backgroundImage = `linear-gradient(to top, var(--bg-dark), rgba(26, 22, 8, 0.4), transparent), url('${imgUrl}')`;
        }

        // Title
        document.getElementById('detail-main-title').innerText = data.title || 'Untitled';

        // Badges
        const trendingBadge = document.getElementById('detail-badge-trending');
        if (trendingBadge) {
            if (data.rating > 8.0) trendingBadge.classList.remove('hidden');
            else trendingBadge.classList.add('hidden');
        }

        // Meta Text (Year • Runtime)
        const metaText = document.getElementById('detail-meta-text');
        if (metaText) {
            const parts = [];
            if (data.release_year) parts.push(data.release_year);
            parts.push(data.adult ? 'A' : 'UA');
            if (data.runtime) {
                const hrs = Math.floor(data.runtime / 60);
                const mins = data.runtime % 60;
                parts.push(hrs > 0 ? `${hrs}h ${mins}m` : `${mins}m`);
            }
            metaText.innerText = parts.join(' • ');
        }

        // Rating
        const ratingVal = data.rating || 0;
        document.getElementById('detail-main-rating').innerText = ratingVal ? ratingVal.toFixed(1) : '-';
        const sideRating = document.getElementById('detail-side-rating');
        if (sideRating) sideRating.innerText = ratingVal ? ratingVal.toFixed(1) : '-';

        const ratingBarsContainer = document.getElementById('detail-rating-bars');
        if (ratingBarsContainer) {
            if (ratingVal > 0) {
                // Generate mock distribution based on the score (0-10)
                const pct = ratingVal / 10;
                let five = Math.round(pct * 100);
                let four = Math.round((1 - pct) * 80);
                let three = Math.round((1 - pct) * 15);
                let two = Math.round((1 - pct) * 3);
                let one = 100 - (five + four + three + two);
                
                // Ensure no negative values due to rounding errors
                if (one < 0) {
                    five += one; // Subtract from highest bucket
                    one = 0;
                }
                
                ratingBarsContainer.innerHTML = [
                    { label: '5', val: five },
                    { label: '4', val: four },
                    { label: '3', val: three },
                    { label: '2', val: two },
                    { label: '1', val: one }
                ].map(b => `
                    <div class="rating-bar-row">
                        <span class="bar-label">${b.label}</span>
                        <div class="bar-track"><div class="bar-fill bg-primary" style="width: ${b.val}%"></div></div>
                        <span class="bar-pct">${b.val}%</span>
                    </div>
                `).join('');
            } else {
                ratingBarsContainer.innerHTML = '<p class="text-muted text-sm">Not enough ratings</p>';
            }
        }

        // Genre
        const genreText = data.genres && data.genres.length > 0 ? data.genres.join(', ') : 'Unknown';
        document.getElementById('detail-main-genres').innerText = genreText;

        // Synopsis
        document.getElementById('detail-synopsis-text').innerText = data.description || 'No synopsis available.';

        // Cast Grid
        const castContainer = document.getElementById('detail-cast-grid');
        if (castContainer) {
            if (data.cast && data.cast.length > 0) {
                castContainer.innerHTML = data.cast.slice(0, 8).map(c => `
                    <div class="cast-member">
                        <div class="cast-photo-wrapper">
                            <img src="${c.profile_path || 'https://via.placeholder.com/150x150/161B22/6E7681?text=?'}" alt="${c.name}">
                        </div>
                        <div>
                            <div class="cast-name">${c.name}</div>
                            <div class="cast-role">${c.character || 'Actor'}</div>
                        </div>
                    </div>
                `).join('');
            } else {
                castContainer.innerHTML = '<p class="text-muted col-span-full">No cast info available.</p>';
            }
        }

        // Movie Info Table
        const dirEl = document.getElementById('detail-info-director');
        if (dirEl) dirEl.innerText = data.director || (data.creators ? data.creators.join(', ') : 'Unknown');
        
        const langEl = document.getElementById('detail-info-language');
        if (langEl) langEl.innerText = data.original_language ? data.original_language.toUpperCase() : 'Unknown';

        const typeEl = document.getElementById('detail-info-type');
        if (typeEl) typeEl.innerText = data.content_type ? data.content_type.charAt(0).toUpperCase() + data.content_type.slice(1) : 'Movie';

        // Trailer Button
        const trailerBtn = document.getElementById('detail-trailer-btn');
        if (trailerBtn) {
            if (data.trailer_url) {
                trailerBtn.classList.remove('hidden');
                trailerBtn.onclick = () => {
                    const modal = document.getElementById('trailer-modal');
                    const iframe = document.getElementById('trailer-iframe');
                    if (modal && iframe) {
                        iframe.src = data.trailer_url;
                        modal.classList.remove('hidden');
                    }
                };
            } else {
                trailerBtn.classList.add('hidden');
            }
        }

        // Watch Providers
        const providersContainer = document.getElementById('detail-providers');
        const providersList = document.getElementById('detail-providers-list');
        if (providersContainer && providersList) {
            if (data.watch_providers && data.watch_providers.length > 0) {
                providersContainer.classList.remove('hidden');
                providersList.innerHTML = data.watch_providers.map(p => `
                    <img src="${p.logo_path}" alt="${p.provider_name}" class="provider-logo" title="${p.provider_name}">
                `).join('');
            } else {
                providersContainer.classList.add('hidden');
            }
        }

        // Watchlist Button
        const watchlistBtn = document.getElementById('detail-watchlist-btn');
        if (watchlistBtn) {
            watchlistBtn.id = 'panel-watchlist'; 
            const updateWatchlistBtn = () => {
                const _isSaved = SavedManager.isSaved(data.content_id);
                watchlistBtn.innerHTML = `<span class="material-symbols-outlined">${_isSaved ? 'remove' : 'add'}</span> ${_isSaved ? 'Remove Watchlist' : 'Add to Watchlist'}`;
                watchlistBtn.style.background = _isSaved ? 'rgba(239, 68, 68, 0.2)' : '';
                watchlistBtn.style.color = _isSaved ? '#ef4444' : '';
                watchlistBtn.style.borderColor = _isSaved ? '#ef4444' : '';
            };
            updateWatchlistBtn();
            watchlistBtn.onclick = () => { SavedManager.toggle(data); updateWatchlistBtn(); };
        }

        // Load Comments + Similar
        if (typeof loadPanelComments === 'function') loadPanelComments(contentId);
        if (typeof setupCommentForm === 'function') setupCommentForm(contentId);
        
        // Load Similar using new layout markup
        loadDetailSimilarContent(contentId);

    } catch (e) {
        console.error('Error loading detail:', e);
        document.getElementById('detail-main-title').innerText = 'Error loading details';
    }
}

async function loadDetailSimilarContent(contentId) {
    const container = document.getElementById('detail-similar-list');
    if (!container) return;
    
    container.innerHTML = '<div class="text-muted">Loading...</div>';
    try {
        const res = await fetch(`${API_BASE}/content/${contentId}/similar`);
        if (!res.ok) throw new Error('Failed to load similar');
        
        const json = await res.json();
        const items = json.results || [];
        if (items.length === 0) {
            container.innerHTML = '<div class="text-muted">No similar content found.</div>';
            return;
        }

        container.innerHTML = items.slice(0, 4).map(item => `
            <div class="similar-item" onclick="openDetail('${item.content_id}')">
                <img class="similar-thumb" src="${item.thumbnail_url || 'https://via.placeholder.com/60x85/1A1608/F2CC0D'}" alt="${item.title}">
                <div class="similar-info">
                    <h5 class="similar-title">${item.title}</h5>
                    <div class="similar-meta">
                        ${item.release_year || 'Unknown Year'} • ${item.rating ? item.rating.toFixed(1) + ' Rating' : ''}
                    </div>
                </div>
            </div>
        `).join('');

    } catch (e) {
        console.error(e);
        container.innerHTML = '';
    }
}

// Global state
let currentAuthToken = localStorage.getItem('auth_token');
let currentUser = null;

// =========================================
// INTERSECTION OBSERVER FOR ANIMATIONS
// =========================================
const animationObserver = new IntersectionObserver((entries) => {
    // We group entries that intersect together to stagger them
    const intersecting = entries.filter(e => e.isIntersecting);
    
    intersecting.forEach((entry, index) => {
        // Unobserve to only animate once
        animationObserver.unobserve(entry.target);
        
        // Add staggered delay based on index in the current batch
        if (index > 0) {
            entry.target.style.transitionDelay = `${index * 50}ms`;
        }
        
        // Use requestAnimationFrame to ensure CSS applies smooth
        requestAnimationFrame(() => {
            entry.target.classList.add('is-visible');
            
            // Cleanup inline styles after animation finishes (500ms)
            setTimeout(() => {
                entry.target.style.transitionDelay = '';
            }, 600);
        });
    });
}, {
    root: null,
    rootMargin: '0px 0px -50px 0px', // Trigger slightly before element comes fully into view
    threshold: 0.1
});

// Helper to observe new elements
window.observeElement = (elem) => {
    if (elem) {
        elem.classList.add('animate-on-scroll');
        animationObserver.observe(elem);
    }
};

/* --- CONTINUE WATCHING TRACKER --- */
function trackRecentlyViewed(contentId) {
    const KEY = 'streamai_recent';
    let recent = JSON.parse(localStorage.getItem(KEY) || '[]');
    recent = recent.filter(r => r.id !== contentId);
    recent.unshift({ id: contentId, ts: Date.now() });
    if (recent.length > 20) recent = recent.slice(0, 20);
    localStorage.setItem(KEY, JSON.stringify(recent));

    // Sync with backend if logged in
    if (AuthManager.isLoggedIn()) {
        fetch(`${API_BASE}/history/${contentId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...AuthManager.getHeader()
            },
            body: JSON.stringify({ progress: 0 }) // Sync start
        }).catch(err => console.error("Failed to sync history:", err));
    }
}

async function loadContinueWatching() {
    const section = document.getElementById('continue-watching-section');
    const grid = document.getElementById('continue-watching-grid');
    if (!section || !grid) return;

    const recent = JSON.parse(localStorage.getItem('streamai_recent') || '[]');
    if (recent.length < 2) { section.classList.add('hidden'); return; }

    const ids = recent.slice(0, 10).map(r => r.id);
    try {
        const results = [];
        for (const id of ids) {
            const res = await fetch(`${API_BASE}/content/${id}`);
            if (res.ok) {
                const data = await res.json();
                results.push(data);
            }
        }
        if (results.length > 0) {
            grid.innerHTML = results.map(item => createCardHTML({
                content_id: item.content_id, title: item.title,
                thumbnail_url: item.thumbnail_url, rating: item.rating,
                content_type: item.content_type, reason: '🕐 Recently viewed'
            })).join('');
            grid.querySelectorAll('.animate-on-scroll').forEach(el => window.observeElement(el));
            section.classList.remove('hidden');
        } else { section.classList.add('hidden'); }
    } catch (e) {
        console.error('Continue watching failed:', e);
        section.classList.add('hidden');
    }
}

// --- Panel Comments Functions ---
async function loadPanelComments(contentId) {
    const container = document.getElementById('panel-comments');
    if (!container) return;

    container.innerHTML = '<p class="text-muted">Loading comments...</p>';

    try {
        const res = await fetch(`${API_BASE}/comments/${contentId}`);
        if (!res.ok) throw new Error('Failed to load comments');

        const comments = await res.json();

        if (comments.length === 0) {
            container.innerHTML = '<p class="text-muted">No comments yet. Be the first!</p>';
            return;
        }

        container.innerHTML = comments.map(c => {
            const time = new Date(c.created_at).toLocaleDateString();
            return `
                <div class="comment-item">
                    <div class="comment-avatar" style="background-color: ${c.avatar_color || '#3B82F6'}">
                        ${(c.display_name || 'A')[0].toUpperCase()}
                    </div>
                    <div class="comment-content">
                        <div class="comment-header">
                            <span class="comment-name">${c.display_name || 'Anonymous'}</span>
                            <span class="comment-time">${time}</span>
                        </div>
                        <p class="comment-text">${escapeHtml(c.comment_text)}</p>
                    </div>
                </div>
            `;
        }).join('');
    } catch (e) {
        console.error('Failed to load comments:', e);
        container.innerHTML = '<p class="text-muted">Failed to load comments.</p>';
    }
}

function setupCommentForm(contentId) {
    const form = document.getElementById('comment-form');
    const hint = document.getElementById('comment-login-hint');
    const submitBtn = document.getElementById('submit-comment-btn');
    const input = document.getElementById('comment-input');

    // Show form if logged in, otherwise show hint
    if (AuthManager.isLoggedIn()) {
        form?.classList.remove('hidden');
        hint?.classList.add('hidden');
    } else {
        form?.classList.add('hidden');
        hint?.classList.remove('hidden');
    }

    // Setup submit handler (reattach to avoid duplicates)
    if (submitBtn) {
        submitBtn.onclick = async () => {
            const text = input?.value?.trim();
            if (!text) return;

            submitBtn.disabled = true;
            try {
                const res = await fetch(`${API_BASE}/comments/${contentId}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        ...AuthManager.getHeader()
                    },
                    body: JSON.stringify({ comment_text: text })
                });

                if (res.ok) {
                    input.value = '';
                    loadPanelComments(contentId);
                } else {
                    throw new Error('Failed to post comment');
                }
            } catch (e) {
                console.error('Comment failed:', e);
                alert('Failed to post comment. Please try again.');
            } finally {
                submitBtn.disabled = false;
            }
        };
    }
}





/* --- 3. HOME LOGIC --- */
// Global Home State
let selectedMood = null;
let selectedGenres = [];
let discoverMode = 'popular';

let homeInitDone = false;

function initHome() {
    if (homeInitDone) return;
    homeInitDone = true;


    // MOOD BUTTONS (Single Select)
    document.querySelectorAll('.mood-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const mood = btn.dataset.mood;
            if (selectedMood === mood) {
                selectedMood = null;
                btn.classList.remove('active');
            } else {
                document.querySelectorAll('.mood-btn').forEach(b => b.classList.remove('active'));
                selectedMood = mood;
                btn.classList.add('active');
            }
            loadDiscoverContent();
        });
    });

    // GENRE CHIPS (Multi-Select)
    document.querySelectorAll('.genre-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            const genre = chip.dataset.genre;
            if (selectedGenres.includes(genre)) {
                selectedGenres = selectedGenres.filter(g => g !== genre);
                chip.classList.remove('active');
            } else {
                selectedGenres.push(genre);
                chip.classList.add('active');
            }
            loadDiscoverContent();
        });
    });

    // DISCOVER BUTTONS (Trending/Popular/Latest)
    document.querySelectorAll('.discover-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.discover-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            discoverMode = btn.dataset.mode;
            loadDiscoverContent();
        });
    });

    // LOAD DISCOVER CONTENT
    // Uses AI semantic search (POST /search) for text queries,
    // and SQL-based discover (POST /discover) for filter-only browsing.
    async function loadDiscoverContent() {
        const discoverGrid = document.getElementById('discover-results-grid');
        const discoverHeading = document.getElementById('discover-heading');

        const searchQuery = document.getElementById('home-search-input')?.value?.trim();

        // Update heading
        const moodText = selectedMood ? ` • ${selectedMood} ` : '';
        const genreText = selectedGenres.length > 0 ? ` • ${selectedGenres.join(', ')} ` : '';
        const queryText = searchQuery ? ` for "${searchQuery}"` : '';
        discoverHeading.innerText = searchQuery
            ? `AI Results for "${searchQuery}"${moodText}${genreText}`
            : `${discoverMode.charAt(0).toUpperCase() + discoverMode.slice(1)}${moodText}${genreText}`;

        discoverGrid.innerHTML = '<p class="text-muted">Loading...</p>';

        try {
            let data;

            if (searchQuery) {
                // ── AI SEMANTIC SEARCH (FAISS vector search) ──
                // Natural language queries like "space action comedy" need
                // vector-based semantic understanding, not SQL LIKE matching.
                const res = await fetch(`${API_BASE}/search`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        base_prompt: searchQuery,
                        mood: selectedMood,
                        genres: selectedGenres.length > 0 ? selectedGenres : null
                    })
                });
                data = await res.json();
            } else {
                // ── SQL DISCOVER (filter-only browsing) ──
                const res = await fetch(`${API_BASE}/discover`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        mode: discoverMode,
                        mood: selectedMood,
                        genres: selectedGenres.length > 0 ? selectedGenres : null,
                        query: null
                    })
                });
                data = await res.json();
            }

            if (data.results && data.results.length > 0) {
                discoverGrid.innerHTML = data.results.map(item => createCardHTML(item)).join('');
                // Observe new cards for scroll animations
                discoverGrid.querySelectorAll('.animate-on-scroll').forEach(el => window.observeElement(el));
            } else {
                discoverGrid.innerHTML = '<p class="text-muted">No content found. Try different filters.</p>';
            }
        } catch (err) {
            console.error('Discover failed:', err);
            discoverGrid.innerHTML = '<p class="text-muted">Failed to load content.</p>';
        }
    }

    // Listen for global trigger from search box
    window.addEventListener('triggerSearchDiscover', () => {
        loadDiscoverContent();
    });

    // Initial load of discover content
    loadDiscoverContent();

    // 3. PERSONALIZED RECOMMENDATIONS
    loadPersonalRecommendations();

    // 4. CONTINUE WATCHING
    loadContinueWatching();
}

function setupGlobalSearch() {
    const searchInput = document.getElementById('home-search-input');
    const discoverSection = document.getElementById('discover-results-section');

    if (searchInput) {
        searchInput.addEventListener('keypress', async (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                
                // Ensure we are on Home View
                if (window.location.pathname !== '/') {
                    navigateTo('/');
                    await new Promise(r => setTimeout(r, 50));
                }

                // Scroll to the discover results, which will now automatically incorporate the search query
                if (discoverSection) {
                    discoverSection.scrollIntoView({ behavior: 'smooth' });
                }

                // Since loadDiscoverContent needs access to the home-search-input value, 
                // and it's inside initHome's scope, we can simulate a filter change 
                // by re-running the fetch. The easiest way is to let the user type, 
                // but since we want to trigger it on ENTER, we can just dispatch an 
                // event or call a global function.
                // However, since loadDiscoverContent is inside initHome closure, 
                // we'll dispatch a custom event on the window to trigger it.
                window.dispatchEvent(new CustomEvent('triggerSearchDiscover'));
            }
        });
    }
}




async function getBrowse(type, page, endpoint = '') {
    // If endpoint is 'browse' or empty, use base browse logic
    let url = `${API_BASE}/browse`;
    if (endpoint && endpoint !== 'browse') {
        url += `/${endpoint}`; // e.g. /browse/trending
    }

    url += `?content_type=${type}&page=${page}&limit=20`;

    try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        return data.results || [];
    } catch (e) {
        console.error(`getBrowse failed for ${type}/${endpoint}:`, e);
        throw e; // Propagate to scroller
    }
}


/* --- 4. SEARCH LOGIC (REDESIGNED) --- */
let searchInitDone = false;
let searchState = {
    scope: 'movie',
    category: 'trending',
    mood: null,
    rating: null,
    yearMin: 1980,
    yearMax: 2025
};
let searchScroller = null;

function initSearch() {
    if (!searchInitDone) {
        setupSearchEventListeners();
        searchInitDone = true;
    }
    // Load initial content based on default category
    loadCategoryContent();
}

function setupSearchEventListeners() {
    // 1. Filter Popup Toggle
    const openBtn = document.getElementById('open-filters-btn');
    const closeBtn = document.getElementById('close-filters-btn');
    const overlay = document.getElementById('filter-popup-overlay');
    const applyBtn = document.getElementById('apply-filters-btn');
    const resetBtn = document.getElementById('reset-filters-btn');

    openBtn?.addEventListener('click', () => {
        overlay?.classList.remove('hidden');
    });

    closeBtn?.addEventListener('click', () => {
        overlay?.classList.add('hidden');
    });

    // Close on overlay click
    overlay?.addEventListener('click', (e) => {
        if (e.target === overlay) {
            overlay.classList.add('hidden');
        }
    });

    applyBtn?.addEventListener('click', () => {
        overlay?.classList.add('hidden');
        loadCategoryContent();
    });

    resetBtn?.addEventListener('click', () => {
        // Reset filters
        searchState.rating = null;
        searchState.yearMin = 1980;
        searchState.yearMax = 2025;
        document.querySelectorAll('.rating-chip').forEach(c => c.classList.remove('active'));
        document.getElementById('year-min').value = 1980;
        document.getElementById('year-max').value = 2025;
        document.getElementById('year-min-val').innerText = '1980';
        document.getElementById('year-max-val').innerText = '2025';
    });

    // 2. Scope Tabs (Movies/Series)
    document.querySelectorAll('.scope-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.scope-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            searchState.scope = tab.dataset.scope;
            loadCategoryContent();
        });
    });

    // 3. Category Toggle Buttons
    document.querySelectorAll('.category-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.category-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            searchState.category = btn.dataset.category;
            loadCategoryContent();
        });
    });

    // 4. Mood Chips
    document.getElementById('mood-chips')?.addEventListener('click', (e) => {
        if (e.target.classList.contains('mood-chip')) {
            const mood = e.target.dataset.mood;
            if (searchState.mood === mood) {
                searchState.mood = null;
                e.target.classList.remove('active');
            } else {
                document.querySelectorAll('.mood-chip').forEach(c => c.classList.remove('active'));
                searchState.mood = mood;
                e.target.classList.add('active');
            }
            loadCategoryContent();
        }
    });

    // 5. Rating Chips
    document.querySelectorAll('.rating-chip').forEach(btn => {
        btn.addEventListener('click', () => {
            if (btn.classList.contains('active')) {
                btn.classList.remove('active');
                searchState.rating = null;
            } else {
                document.querySelectorAll('.rating-chip').forEach(c => c.classList.remove('active'));
                btn.classList.add('active');
                searchState.rating = btn.dataset.rating;
            }
        });
    });

    // 6. Year Slider
    const minRange = document.getElementById('year-min');
    const maxRange = document.getElementById('year-max');

    function updateYear() {
        const min = parseInt(minRange.value, 10);
        const max = parseInt(maxRange.value, 10);
        document.getElementById('year-min-val').innerText = min;
        document.getElementById('year-max-val').innerText = max;
        searchState.yearMin = min;
        searchState.yearMax = max;
    }

    if (minRange && maxRange) {
        minRange.addEventListener('input', updateYear);
        maxRange.addEventListener('input', updateYear);
        updateYear();
    }

    // 7. Search Input
    document.getElementById('search-page-input')?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            performTextSearch();
        }
    });
}

function loadCategoryContent() {
    const container = document.getElementById('search-results-grid');
    const heading = document.getElementById('search-results-heading');
    const loading = document.getElementById('search-loading');
    const query = document.getElementById('search-page-input')?.value?.trim();

    // If there's a search query, do text search instead
    if (query) {
        performTextSearch();
        return;
    }

    // Update heading
    const categoryLabels = {
        trending: 'Trending',
        popular: 'Popular',
        latest: 'Latest'
    };
    const scopeLabel = searchState.scope === 'movie' ? 'Movies' : 'Series';
    heading.innerText = `${categoryLabels[searchState.category]} ${scopeLabel}`;

    // Clear container
    container.innerHTML = '';

    // Map category to specific API endpoint
    const endpointMap = {
        trending: 'trending',
        popular: 'top-rated',
        latest: 'latest'
    };
    const endpoint = endpointMap[searchState.category] || 'trending';

    // Fetch function - these specific endpoints don't support pagination,
    // so we only load once with a large limit to avoid mixing irrelevant content
    const fetchFn = async (page) => {
        // Only fetch on page 1 - specific endpoints don't support pagination
        if (page > 1) return [];

        loading?.classList.remove('hidden');
        try {
            // Use specific endpoint for correct category content
            const url = `${API_BASE}/browse/${endpoint}?content_type=${searchState.scope}&limit=100`;

            const res = await fetch(url);
            const data = await res.json();
            loading?.classList.add('hidden');

            let results = data.results || [];

            // Apply client-side filters since specific endpoints don't support them
            if (searchState.rating) {
                const minRating = parseFloat(searchState.rating);
                results = results.filter(item => (item.rating || 0) >= minRating);
            }
            if (searchState.yearMin > 1980 || searchState.yearMax < 2025) {
                results = results.filter(item => {
                    const year = item.release_year || 0;
                    return year >= searchState.yearMin && year <= searchState.yearMax;
                });
            }

            return results;
        } catch (e) {
            console.error('Failed to load content:', e);
            loading?.classList.add('hidden');
            return [];
        }
    };

    // Stop previous scroller
    if (searchScroller) {
        searchScroller.finished = true;
    }

    // Create new infinite scroller
    searchScroller = new InfiniteScroller('search-results-grid', fetchFn, { triggerId: 'trigger-search' });
}

function performTextSearch() {
    const container = document.getElementById('search-results-grid');
    const heading = document.getElementById('search-results-heading');
    const loading = document.getElementById('search-loading');
    const query = document.getElementById('search-page-input')?.value?.trim();

    if (!query) {
        loadCategoryContent();
        return;
    }

    heading.innerText = `Results for "${query}"`;
    container.innerHTML = '';

    const fetchFn = async (page) => {
        // Search API doesn't support pagination well, only fetch page 1
        if (page > 1) return [];

        loading?.classList.remove('hidden');
        try {
            const payload = {
                base_prompt: query,
                mood: searchState.mood,
                filters: {
                    content_type: [searchState.scope],
                    min_rating: searchState.rating ? parseFloat(searchState.rating) : null,
                    min_year: searchState.yearMin,
                    max_year: searchState.yearMax
                }
            };

            const res = await fetch(`${API_BASE}/search`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            loading?.classList.add('hidden');

            // Filter by scope
            return (data.results || []).filter(item => item.content_type === searchState.scope);
        } catch (e) {
            console.error('Search failed:', e);
            loading?.classList.add('hidden');
            return [];
        }
    };

    if (searchScroller) {
        searchScroller.finished = true;
    }

    searchScroller = new InfiniteScroller('search-results-grid', fetchFn, { triggerId: 'trigger-search' });
}


/* --- 5. COMMUNITY LOGIC --- */

// Auth Manager - handles login state (supports both Cognito JWT and dev login)
const AuthManager = {
    getEmail: () => localStorage.getItem('flimo_user_email') || localStorage.getItem('streamai_user_email'),
    getToken: () => localStorage.getItem('flimo_jwt_token') || localStorage.getItem('streamai_jwt_token'),
    getUserId: () => localStorage.getItem('flimo_user_id'),
    getUserName: () => localStorage.getItem('flimo_user_name'),
    setAuth: (token, email, name, userId) => {
        localStorage.setItem('flimo_jwt_token', token);
        localStorage.setItem('flimo_user_email', email);
        if (name) localStorage.setItem('flimo_user_name', name);
        if (userId) localStorage.setItem('flimo_user_id', userId);
        // Legacy compat
        localStorage.setItem('streamai_user_email', email);
        localStorage.setItem('streamai_jwt_token', token);
    },
    clearAuth: () => {
        localStorage.removeItem('flimo_jwt_token');
        localStorage.removeItem('flimo_user_email');
        localStorage.removeItem('flimo_user_name');
        localStorage.removeItem('flimo_user_id');
        localStorage.removeItem('streamai_user_email');
        localStorage.removeItem('streamai_jwt_token');
    },
    isLoggedIn: () => !!AuthManager.getToken(),
    getHeader: () => {
        const headers = {};
        const token = AuthManager.getToken();
        if (token) headers['Authorization'] = `Bearer ${token}`;
        const email = AuthManager.getEmail();
        if (email) headers['x-user-email'] = email;
        return headers;
    }
};

// Current user profile (cached after fetch)
let currentUserProfile = null;

// Chat refresh interval
let chatRefreshInterval = null;

function initAuth() {
    const loginModal = document.getElementById('login-modal');

    // Check if already logged in
    if (AuthManager.isLoggedIn()) {
        showLoggedInState();
    } else {
        showLoggedOutState();
    }

    // Login circle button - open modal
    document.getElementById('login-trigger-btn')?.addEventListener('click', () => {
        loginModal?.classList.remove('hidden');
        document.getElementById('login-email')?.focus();
    });

    // Close modal
    document.getElementById('login-modal-close')?.addEventListener('click', () => {
        loginModal?.classList.add('hidden');
    });

    // Close modal on backdrop click
    document.querySelector('.login-modal-backdrop')?.addEventListener('click', () => {
        loginModal?.classList.add('hidden');
    });

    // Login button
    document.getElementById('login-btn')?.addEventListener('click', handleLogin);
    document.getElementById('login-email')?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleLogin();
    });

    // Logout button
    document.getElementById('logout-btn')?.addEventListener('click', handleLogout);

    // Edit profile button
    document.getElementById('edit-profile-btn')?.addEventListener('click', handleEditProfile);
}

function initCommunity() {
    // Initialize Supabase Real-Time Chat (new module)
    if (window.chatManager && typeof window.chatManager.init === 'function') {
        window.chatManager.init();
    } else if (typeof window.initChat === 'function') {
        window.initChat();
    }

    // Load reviews and top rated
    loadCommunityReviews();
    loadTopRated();
}

async function handleLogin() {
    const emailInput = document.getElementById('login-email');
    const email = emailInput?.value?.trim();

    if (!email || !email.includes('@')) {
        alert('Please enter a valid email address');
        return;
    }

    // Use dev login endpoint to get a proper JWT
    try {
        const res = await fetch(`${API_BASE}/auth/dev`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email })
        });

        if (!res.ok) throw new Error('Dev login failed');

        const data = await res.json();
        AuthManager.setAuth(
            data.access_token,
            data.user?.email || email,
            data.user?.name || email.split('@')[0],
            data.user?.user_id
        );

        // Close the login modal
        document.getElementById('login-modal')?.classList.add('hidden');
        showLoggedInState();

        // Fetch profile
        fetchAndDisplayProfile();
    } catch (e) {
        console.error('Login failed:', e);
        AuthManager.clearAuth();
        alert('Login failed. Please try again.');
    }
}

function handleLogout() {
    AuthManager.clearAuth();
    currentUserProfile = null;
    showLoggedOutState();

    // Clear chat refresh
    if (chatRefreshInterval) {
        clearInterval(chatRefreshInterval);
        chatRefreshInterval = null;
    }
}

function showLoggedInState() {
    document.getElementById('community-login')?.classList.add('hidden');
    document.getElementById('community-profile')?.classList.remove('hidden');
    document.getElementById('chat-input-area')?.classList.remove('hidden');
    document.querySelector('.chat-placeholder')?.classList.add('hidden');

    // Load profile if not cached
    if (!currentUserProfile) {
        fetchAndDisplayProfile();
    } else {
        displayProfile(currentUserProfile);
    }

    // LEGACY CHAT REMOVED - using new real-time chat module instead
    // Previous polling logic removed to prevent conflict
}

function showLoggedOutState() {
    document.getElementById('community-login')?.classList.remove('hidden');
    document.getElementById('community-profile')?.classList.add('hidden');
    document.getElementById('chat-input-area')?.classList.add('hidden');
    document.querySelector('.chat-placeholder')?.classList.remove('hidden');
}

async function fetchAndDisplayProfile() {
    if (!AuthManager.isLoggedIn()) return;

    try {
        const res = await fetch(`${API_BASE}/profile`, {
            headers: { ...AuthManager.getHeader() }
        });
        if (res.ok) {
            currentUserProfile = await res.json();
            displayProfile(currentUserProfile);
        }
    } catch (e) {
        console.error('Failed to fetch profile:', e);
    }
}

function displayProfile(profile) {
    const avatarEl = document.getElementById('profile-avatar');
    const nameEl = document.getElementById('profile-display-name');
    const emailEl = document.getElementById('profile-email');

    if (avatarEl) {
        avatarEl.textContent = (profile.display_name || profile.email || 'U')[0].toUpperCase();
        avatarEl.style.backgroundColor = profile.avatar_color || '#3B82F6';
    }
    if (nameEl) nameEl.textContent = profile.display_name || profile.email?.split('@')[0] || 'User';
    if (emailEl) emailEl.textContent = profile.email || '';
}

async function handleEditProfile() {
    const newName = prompt('Enter display name:', currentUserProfile?.display_name || '');
    if (newName === null) return; // Cancelled

    try {
        const res = await fetch(`${API_BASE}/profile`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                ...AuthManager.getHeader()
            },
            body: JSON.stringify({ display_name: newName })
        });

        if (res.ok) {
            currentUserProfile = await res.json();
            displayProfile(currentUserProfile);
        }
    } catch (e) {
        console.error('Profile update failed:', e);
    }
}

// --- Chat Functions ---
async function loadChatMessages() {
    const container = document.getElementById('chat-messages');
    if (!container) return;

    try {
        const res = await fetch(`${API_BASE}/chat`);
        if (!res.ok) throw new Error('Failed to load chat');

        const messages = await res.json();

        if (messages.length === 0) {
            if (!AuthManager.isLoggedIn()) {
                container.innerHTML = '<p class="text-muted chat-placeholder">Sign in to join the conversation!</p>';
            } else {
                container.innerHTML = '<p class="text-muted chat-placeholder">No messages yet. Start the conversation!</p>';
            }
            return;
        }

        const currentUserId = currentUserProfile?.user_id;

        container.innerHTML = messages.map(msg => {
            const isOwn = msg.user_id === currentUserId;
            const time = new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

            return `
                <div class="chat-message ${isOwn ? 'own' : ''}">
                    <div class="chat-message-avatar" style="background-color: ${msg.avatar_color || '#3B82F6'}">
                        ${(msg.display_name || 'U')[0].toUpperCase()}
                    </div>
                    <div class="chat-message-content">
                        <div class="chat-message-header">
                            <span class="chat-message-name">${msg.display_name || 'Anonymous'}</span>
                            <span class="chat-message-time">${time}</span>
                        </div>
                        <div class="chat-message-text">${escapeHtml(msg.message)}</div>
                    </div>
                </div>
            `;
        }).join('');

        // Scroll to bottom
        container.scrollTop = container.scrollHeight;
    } catch (e) {
        console.error('Failed to load chat:', e);
    }
}

async function sendChatMessage() {
    const input = document.getElementById('chat-input');
    const message = input?.value?.trim();

    if (!message || !AuthManager.isLoggedIn()) return;

    input.value = '';

    try {
        const res = await fetch(`${API_BASE}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...AuthManager.getHeader()
            },
            body: JSON.stringify({ message })
        });

        if (res.ok) {
            loadChatMessages();
        }
    } catch (e) {
        console.error('Failed to send message:', e);
        input.value = message; // Restore on failure
    }
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// --- Community Reviews ---
function loadCommunityReviews() {
    const reviewsContainer = document.getElementById('community-reviews');
    // Mock Data (since we don't have a reviews feed endpoint yet)
    const mockReviews = [
        { user: "Alice", title: "Inception", rating: 5, text: "Mind blowing!" },
        { user: "Bob", title: "The Office", rating: 4.5, text: "Classic comedy." },
        { user: "Charlie", title: "Breaking Bad", rating: 5, text: "Masterpiece." }
    ];

    if (reviewsContainer) {
        reviewsContainer.innerHTML = mockReviews.map(r => `
            <div class="review-card">
                <div class="review-avatar" style="width:40px;height:40px;background:#333;border-radius:50%"></div>
                <div class="review-content">
                    <h4>${r.title} <span style="color:#fbbf24">★ ${r.rating}</span></h4>
                    <p>"${r.text}" - ${r.user}</p>
                </div>
            </div>
        `).join('');
    }
}

function loadTopRated() {
    const topContainer = document.getElementById('community-top-rated');
    if (topContainer) {
        getBrowse('movie', 1).then(items => {
            topContainer.innerHTML = items.slice(0, 5).map(createCardHTML).join('');
        });
    }
}


/* --- SAVED / WATCHLIST LOGIC --- */
// SavedManager moved to top of file


/* --- 6. SAVED PAGE LOGIC --- */
function initSaved() {
    const container = document.getElementById('view-saved');
    // Clear previous if any
    container.innerHTML = '';

    // Inject Structure
    container.innerHTML = `
        <div class="saved-header">
            <h2 class="page-title">Your Collection</h2>
            <div class="saved-actions">
                 <button class="btn btn-secondary" onclick="shareSavedList()">📋 Share List</button>
            </div>
        </div>

        <!-- TABS -->
        <div class="saved-tabs">
            <div class="tab-group status-tabs">
                <button class="tab-btn active" id="tab-queued" onclick="setSavedTab('queued')">To Watch</button>
                <button class="tab-btn" id="tab-watched" onclick="setSavedTab('watched')">Watched</button>
            </div>
            <div class="tab-group type-tabs">
                <button class="filter-chip active" id="type-all" onclick="setSavedType('all')">All</button>
                <button class="filter-chip" id="type-movie" onclick="setSavedType('movie')">Movies</button>
                <button class="filter-chip" id="type-series" onclick="setSavedType('series')">Series</button>
            </div>
        </div>
        
        <div class="results-grid" id="saved-grid"></div>
        
        <div id="saved-recommendations" class="content-section hidden" style="margin-top: 3rem;">
             <h3 class="section-heading" style="margin-bottom: 1.5rem;">✨ Because you like...</h3>
             <div class="results-grid" id="recs-grid"></div>
        </div>
    `;

    renderSavedGrid();
}

// State for filtering
let savedState = { tab: 'queued', type: 'all' };

window.setSavedTab = (tab) => {
    savedState.tab = tab;
    // Update active classes
    document.querySelectorAll('.status-tabs .tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(`tab-${tab}`).classList.add('active');
    renderSavedGrid();
};

window.setSavedType = (type) => {
    savedState.type = type;
    document.querySelectorAll('.type-tabs .filter-chip').forEach(b => b.classList.remove('active'));
    document.getElementById(`type-${type}`).classList.add('active');
    renderSavedGrid();
};

window.renderSavedGrid = () => {
    const allSaved = SavedManager.getSaved();
    const grid = document.getElementById('saved-grid');

    // Filter
    const filtered = allSaved.filter(item => {
        const statusMatch = item.status === savedState.tab; // queued or watched
        const typeMatch = savedState.type === 'all' || item.content_type === savedState.type;
        return statusMatch && typeMatch;
    });

    if (filtered.length === 0) {
        grid.innerHTML = `
            <div class="empty-state" style="grid-column: 1/-1; text-align: center; padding: 40px;">
                <h3 class="text-muted">${savedState.tab === 'watched' ? 'No watched items yet' : 'Your watchlist is empty'}</h3>
                <p class="text-muted">Start saving movies to see them here!</p>
            </div>
        `;
    } else {
        grid.innerHTML = filtered.map(item => createSavedCardHTML(item)).join('');
    }

    // Recommendations logic (only on main 'queued' tab for relevance)
    if (savedState.tab === 'queued' && allSaved.length > 0) {
        loadSavedRecommendations(allSaved);
    } else {
        document.getElementById('saved-recommendations').classList.add('hidden');
    }
};

window.shareSavedList = () => {
    const saved = SavedManager.getSaved();
    if (saved.length === 0) return alert("Nothing to share!");

    const text = "🎬 My Flimo Watchlist:\n\n" +
        saved.map(i => `${i.status === 'watched' ? '✅' : '⭕'} ${i.title} (${i.rating || '-'})`).join('\n');

    navigator.clipboard.writeText(text).then(() => alert("List copied to clipboard!"));
};

// Special Card for Saved Page
function createSavedCardHTML(item) {
    const baseHTML = createCardHTML(item);
    const isWatched = item.status === 'watched';

    // Inject Custom Controls
    const controls = `
         <div class="saved-card-controls" onclick="event.stopPropagation()">
            <button class="control-btn ${isWatched ? 'active' : ''}" onclick="window.toggleWatched(event, '${item.content_id}')" title="${isWatched ? 'Mark Unwatched' : 'Mark Watched'}">
                <span class="material-symbols-outlined" style="font-size:16px;">${isWatched ? 'visibility_off' : 'visibility'}</span>
            </button>
            <button class="control-btn remove-btn" onclick="window.toggleSave(event, '${encodeURIComponent(JSON.stringify(item))}')" title="Remove">
                <span class="material-symbols-outlined" style="font-size:16px;">delete</span>
            </button>
        </div>
    `;

    // Replace the default overlay save button with custom controls
    return baseHTML.replace(/<button class="save-btn.*?<\/button>/s, controls);
}

// Smart Recommendations Logic
async function loadSavedRecommendations(savedItems) {
    const recsSection = document.getElementById('saved-recommendations');
    const recsGrid = document.getElementById('recs-grid');

    // Extract top genres
    const genreCounts = {};
    savedItems.forEach(i => {
        if (i.genres) i.genres.forEach(g => genreCounts[g] = (genreCounts[g] || 0) + 1);
    });
    const topGenres = Object.entries(genreCounts)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 2)
        .map(e => e[0]);

    if (topGenres.length === 0) return;

    // Fetch popular items with these genres
    try {
        const res = await fetch(`${API_BASE}/discover`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                mode: 'popular',
                genres: topGenres,
                limit: 10
            })
        });
        const data = await res.json();
        // Filter out already saved
        const newRecs = data.results.filter(r => !SavedManager.isSaved(r.content_id)).slice(0, 5);

        if (newRecs.length > 0) {
            recsSection.classList.remove('hidden');
            recsGrid.innerHTML = newRecs.map(createCardHTML).join('');
            recsSection.querySelector('h3').innerText = `✨ Because you like ${topGenres.join(', ')}...`;
        } else {
            recsSection.classList.add('hidden');
        }
    } catch (e) { console.error(e); }
}

// --- PERSONALIZATION & HISTORY ---

async function loadPersonalRecommendations() {
    const history = JSON.parse(localStorage.getItem('streamai_history') || '[]');
    const seedIds = history.map(item => item.content_id).slice(0, 5); // Last 5 items

    const container = document.getElementById('personal-recs-section');
    const grid = document.getElementById('personal-recs-grid');

    if (!container || !grid) return;

    if (seedIds.length === 0) {
        container.classList.add('hidden');
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/recommendations/personal`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ seed_ids: seedIds, limit: 10 })
        });
        const data = await res.json();

        if (data.results && data.results.length > 0) {
            container.classList.remove('hidden');
            grid.innerHTML = data.results.map(createCardHTML).join('');
        } else {
            container.classList.add('hidden');
        }
    } catch (e) {
        console.error("Failed to load personal recommendations:", e);
        container.classList.add('hidden');
    }
}

async function loadContinueWatching() {
    const history = JSON.parse(localStorage.getItem('streamai_history') || '[]');
    const container = document.getElementById('continue-watching-section');
    const grid = document.getElementById('continue-watching-grid');

    if (!container || !grid) return;

    if (history.length === 0) {
        container.classList.add('hidden');
        return;
    }

    // Check if we have full objects or just IDs
    const validItems = history.filter(i => i.content_id && i.thumbnail_url).slice(0, 10);

    if (validItems.length > 0) {
        container.classList.remove('hidden');
        grid.innerHTML = validItems.map(item => createCardHTML(item)).join('');
    } else {
        // Fallback: Fetch details if we only have IDs (legacy data)
        const ids = history.map(i => i.content_id).filter(id => id).slice(0, 10);
        if (ids.length === 0) return;

        try {
            const res = await fetch(`${API_BASE}/content/batch`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content_ids: ids })
            });
            const items = await res.json();
            if (items.length > 0) {
                container.classList.remove('hidden');
                grid.innerHTML = items.map(createCardHTML).join('');
            }
        } catch (e) { console.error(e); }
    }
}

window.trackRecentlyViewed = function (item) {
    if (!item || !item.content_id) return;

    let history = JSON.parse(localStorage.getItem('streamai_history') || '[]');

    // Remove if exists
    history = history.filter(i => i.content_id !== item.content_id);

    // Add to front
    history.unshift({
        content_id: item.content_id,
        title: item.title,
        thumbnail_url: item.thumbnail_url,
        content_type: item.content_type,
        rating: item.rating,
        reason: item.reason,
        timestamp: Date.now()
    });

    if (history.length > 20) history.pop();

    localStorage.setItem('streamai_history', JSON.stringify(history));

    // Refresh lists if on home
    if (window.location.pathname === '/' || window.location.pathname.endsWith('index.html')) {
        loadContinueWatching();
        // Debounce personal recs refresh to avoid spamming API on every click
        // But for now, simple is fine
    }
};
