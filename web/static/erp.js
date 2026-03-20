/**
 * ERP Dashboard Alpine.js Component
 * ===================================
 * Handles all ERP UI state and API calls.
 * Calls /api/erp/* endpoints and /api/chat/stream for AI bar.
 */
function erpApp() {
  return {
    // ── Navigation ───────────────────────────────
    view: 'dashboard',
    aiOpen: false,

    // ── KPI ──────────────────────────────────────
    kpi: {
      receivables_total: 0, receivables_count: 0,
      overdue_total: 0, overdue_count: 0,
      payables_total: 0, payables_count: 0,
      cashflow: 0,
    },

    // ── Data stores ──────────────────────────────
    customers: [], loadingCustomers: false,
    customerSearch: '', customerTypeFilter: '',

    invoices: [], loadingInvoices: false,
    invoiceTypeFilter: '', invoiceStatusFilter: '',
    invoiceDateFrom: '', invoiceDateTo: '',

    vendorInvoices: [], loadingVendor: false,
    vendorStatusFilter: '', vendorPaymentFilter: '',

    products: [], loadingProducts: false,
    lowStockFilter: false,

    overdueInvoices: [],
    lowStockProducts: [],
    activityFeed: [],
    loadingActivity: false,

    // ── Reports ──────────────────────────────────
    reportTab: 'vat',
    vatYear: new Date().getFullYear(),
    vatMonth: new Date().getMonth() + 1,
    vatReport: null,
    agingReport: null,
    payablesReport: null,
    financialReport: null,
    finStart: `${new Date().getFullYear()}-01-01`,
    finEnd: new Date().toISOString().slice(0, 10),

    // ── Modals ───────────────────────────────────
    paymentModal: {
      open: false, isVendor: false,
      invoiceId: '', invoiceType: '', displayId: '',
      amountDue: 0, amount: '', date: new Date().toISOString().slice(0, 10),
      method: 'transfer', reference: '',
      error: '', submitting: false,
    },
    adjustModal: {
      open: false, productId: '', productName: '',
      currentQty: 0, newQty: '', reason: '',
      error: '', submitting: false,
    },
    uraDetail: { open: false, data: {} },
    movementsModal: { open: false, movements: [], productName: '', loading: false },

    // ── AI bar ───────────────────────────────────
    aiInput: '', aiResponse: '', aiStreaming: false,

    // =======================================================================
    // Init
    // =======================================================================
    async init() {
      await this.loadDashboard();
    },

    async loadDashboard() {
      // Load receivables
      try {
        const r = await this.apiFetch('/api/erp/receivables');
        this.kpi.receivables_total = r.total_open_eur || 0;
        this.kpi.receivables_count = r.total_count || 0;
        const overdueBuckets = ['1_30', '31_60', '61_90', 'over_90'];
        let overdueTotal = 0, overdueCount = 0, overdueList = [];
        for (const b of overdueBuckets) {
          const bucket = r.buckets?.[b] || {};
          overdueTotal += bucket.total || 0;
          overdueCount += (bucket.invoices || []).length;
          overdueList.push(...(bucket.invoices || []));
        }
        this.kpi.overdue_total = overdueTotal;
        this.kpi.overdue_count = overdueCount;
        this.overdueInvoices = overdueList.sort((a, b) =>
          (b.erp_amount_due || 0) - (a.erp_amount_due || 0)
        );
      } catch (e) { console.warn('Receivables load error', e); }

      // Load payables
      try {
        const p = await this.apiFetch('/api/erp/payables');
        this.kpi.payables_total = p.total_due_eur || 0;
        this.kpi.payables_count = p.total_count || 0;
      } catch (e) { console.warn('Payables load error', e); }

      // Load cashflow (30 days)
      try {
        const today = new Date();
        const d30 = new Date(today); d30.setDate(d30.getDate() - 30);
        const cf = await this.apiFetch(
          `/api/erp/reports/cashflow?start=${d30.toISOString().slice(0,10)}&end=${today.toISOString().slice(0,10)}`
        );
        this.kpi.cashflow = cf.net || 0;
      } catch (e) { console.warn('Cashflow load error', e); }

      // Load low stock
      try {
        const prods = await this.apiFetch('/api/erp/products?low_stock_only=true&limit=20');
        this.lowStockProducts = prods;
      } catch (e) { console.warn('Products load error', e); }

      // Load activity feed
      await this.loadActivity();
    },

    async loadActivity() {
      this.loadingActivity = true;
      try {
        this.activityFeed = await this.apiFetch('/api/erp/activity?limit=20');
      } catch (e) { console.warn('Activity feed error', e); this.activityFeed = []; }
      this.loadingActivity = false;
    },

    // =======================================================================
    // Customers
    // =======================================================================
    async loadCustomers() {
      this.loadingCustomers = true;
      try {
        const params = new URLSearchParams();
        if (this.customerSearch) params.set('search', this.customerSearch);
        if (this.customerTypeFilter) params.set('party_type', this.customerTypeFilter);
        this.customers = await this.apiFetch(`/api/erp/customers?${params}`);
      } catch (e) { console.warn('Customers load error', e); this.customers = []; }
      this.loadingCustomers = false;
    },

    async viewCustomerBalance(c) {
      try {
        const b = await this.apiFetch(`/api/erp/customers/${c._id}/balance`);
        alert(`${c.name}\nOtvoreno: ${this.fmt(b.total_due_eur)}\nRačuna: ${b.open_invoices}`);
      } catch (e) { alert('Greška pri dohvaćanju salda.'); }
    },

    // =======================================================================
    // Invoices
    // =======================================================================
    async loadInvoices() {
      this.loadingInvoices = true;
      try {
        const p = new URLSearchParams();
        if (this.invoiceTypeFilter) p.set('invoice_type', this.invoiceTypeFilter);
        if (this.invoiceStatusFilter) p.set('payment_status', this.invoiceStatusFilter);
        if (this.invoiceDateFrom) p.set('date_from', this.invoiceDateFrom);
        if (this.invoiceDateTo) p.set('date_to', this.invoiceDateTo);
        this.invoices = await this.apiFetch(`/api/erp/invoices?${p}`);
      } catch (e) { console.warn('Invoices load error', e); this.invoices = []; }
      this.loadingInvoices = false;
    },

    // =======================================================================
    // Vendor Invoices
    // =======================================================================
    async loadVendorInvoices() {
      this.loadingVendor = true;
      try {
        const p = new URLSearchParams();
        if (this.vendorStatusFilter) p.set('document_status', this.vendorStatusFilter);
        if (this.vendorPaymentFilter) p.set('payment_status', this.vendorPaymentFilter);
        this.vendorInvoices = await this.apiFetch(`/api/erp/vendor-invoices?${p}`);
      } catch (e) { console.warn('Vendor invoices load error', e); this.vendorInvoices = []; }
      this.loadingVendor = false;
    },

    openURADetail(ura) {
      this.uraDetail.data = ura;
      this.uraDetail.open = true;
    },

    async confirmURAReceived(ura) {
      if (!confirm(`Potvrditi primitak ${ura.display_id || ura._id}?\n(Status: draft → received)`)) return;
      try {
        await this.apiFetch(`/api/erp/vendor-invoices/${ura._id}/receive`, { method: 'POST' });
        await this.loadVendorInvoices();
        // Refresh detail if open
        if (this.uraDetail.open) {
          this.uraDetail.data = this.vendorInvoices.find(v => v._id === ura._id) || this.uraDetail.data;
        }
      } catch (e) {
        alert(`Greška: ${e.message}`);
      }
    },

    async approveURA(ura) {
      if (!confirm(`Odobriti URA: ${ura.display_id || ura._id}?`)) return;
      try {
        await this.apiFetch(`/api/erp/vendor-invoices/${ura._id}/approve`, { method: 'POST' });
        await this.loadVendorInvoices();
        if (this.uraDetail.open) {
          this.uraDetail.data = this.vendorInvoices.find(v => v._id === ura._id) || this.uraDetail.data;
        }
      } catch (e) {
        alert(`Greška: ${e.message}`);
      }
    },

    // =======================================================================
    // Products
    // =======================================================================
    async loadProducts() {
      this.loadingProducts = true;
      try {
        const p = new URLSearchParams();
        if (this.lowStockFilter) p.set('low_stock_only', 'true');
        this.products = await this.apiFetch(`/api/erp/products?${p}`);
      } catch (e) { console.warn('Products load error', e); this.products = []; }
      this.loadingProducts = false;
    },

    async openMovements(p) {
      this.movementsModal = { open: true, movements: [], productName: p.name, loading: true };
      try {
        this.movementsModal.movements = await this.apiFetch(`/api/erp/products/${p._id}/movements?limit=50`);
      } catch (e) { console.warn('Movements load error', e); }
      this.movementsModal.loading = false;
    },

    // =======================================================================
    // Reports
    // =======================================================================
    async loadReport(tab) {
      this.reportTab = tab;
      if (tab === 'vat') {
        try {
          this.vatReport = await this.apiFetch(
            `/api/erp/reports/vat?year=${this.vatYear}&month=${this.vatMonth}`
          );
        } catch (e) { console.warn('VAT report error', e); }
      } else if (tab === 'receivables') {
        try {
          this.agingReport = await this.apiFetch('/api/erp/reports/receivables-aging');
        } catch (e) { console.warn('Aging report error', e); }
      } else if (tab === 'payables') {
        try {
          this.payablesReport = await this.apiFetch('/api/erp/reports/payables-aging');
        } catch (e) { console.warn('Payables aging error', e); }
      } else if (tab === 'financial') {
        try {
          this.financialReport = await this.apiFetch(
            `/api/erp/reports/financial-summary?start=${this.finStart}&end=${this.finEnd}`
          );
        } catch (e) { console.warn('Financial report error', e); }
      }
    },

    sortedExpenses() {
      const cats = this.financialReport?.expenses_by_category || {};
      return Object.entries(cats).sort((a, b) => b[1] - a[1]);
    },

    barWidth(amount, total) {
      if (!total) return 0;
      return Math.max(2, Math.round((amount / total) * 100));
    },

    // =======================================================================
    // Payment Modal (outgoing invoices)
    // =======================================================================
    openPayment(inv) {
      this.paymentModal = {
        open: true, isVendor: false,
        invoiceId: inv._id,
        invoiceType: inv.invoice_type || 'b2c',
        displayId: inv.invoice_number || inv.display_id || inv._id,
        amountDue: parseFloat(inv.erp_amount_due || 0),
        amount: parseFloat(inv.erp_amount_due || 0).toFixed(2),
        date: new Date().toISOString().slice(0, 10),
        method: 'transfer', reference: '',
        error: '', submitting: false,
      };
    },

    openVendorPayment(ura) {
      this.paymentModal = {
        open: true, isVendor: true,
        invoiceId: ura._id,
        invoiceType: 'vendor',
        displayId: ura.display_id || ura._id,
        amountDue: parseFloat(ura.amount_due || 0),
        amount: parseFloat(ura.amount_due || 0).toFixed(2),
        date: new Date().toISOString().slice(0, 10),
        method: 'transfer', reference: '',
        error: '', submitting: false,
      };
    },

    async submitPayment() {
      const m = this.paymentModal;
      m.error = '';
      if (!m.amount || parseFloat(m.amount) <= 0) { m.error = 'Iznos mora biti > 0.'; return; }
      if (parseFloat(m.amount) > m.amountDue) { m.error = `Iznos ne smije biti veći od dugovanja (${m.amountDue.toFixed(2)} EUR).`; return; }
      m.submitting = true;
      try {
        const body = {
          amount: parseFloat(m.amount),
          payment_date: m.date,
          payment_method: m.method,
          reference: m.reference,
          idempotency_key: crypto.randomUUID(),
        };
        let url;
        if (m.isVendor) {
          url = `/api/erp/vendor-invoices/${m.invoiceId}/payment`;
        } else {
          url = `/api/erp/invoices/${m.invoiceType}/${m.invoiceId}/payment`;
        }
        const result = await this.apiFetch(url, { method: 'POST', body: JSON.stringify(body) });
        m.open = false;
        // Refresh relevant data
        if (m.isVendor) {
          await this.loadVendorInvoices();
        } else {
          await this.loadInvoices();
        }
        await this.loadDashboard();
      } catch (e) {
        m.error = e.message || 'Greška pri snimanju uplate.';
      }
      m.submitting = false;
    },

    // =======================================================================
    // Stock Adjust Modal
    // =======================================================================
    openAdjust(p) {
      this.adjustModal = {
        open: true,
        productId: p._id,
        productName: p.name,
        currentQty: parseFloat(p.stock_quantity || 0),
        newQty: parseFloat(p.stock_quantity || 0),
        reason: '',
        error: '', submitting: false,
      };
    },

    async submitAdjust() {
      const m = this.adjustModal;
      m.error = '';
      if (m.reason.trim().length < 5) { m.error = 'Razlog mora imati minimalno 5 znakova.'; return; }
      if (m.newQty < 0) { m.error = 'Količina ne može biti negativna.'; return; }
      m.submitting = true;
      try {
        await this.apiFetch(`/api/erp/products/${m.productId}/adjust`, {
          method: 'POST',
          body: JSON.stringify({ new_quantity: parseFloat(m.newQty), reason: m.reason }),
        });
        m.open = false;
        await this.loadProducts();
        await this.loadDashboard();
      } catch (e) {
        m.error = e.message || 'Greška pri usklađivanju.';
      }
      m.submitting = false;
    },

    // =======================================================================
    // AI Command Bar
    // =======================================================================
    async sendAI() {
      if (!this.aiInput.trim() || this.aiStreaming) return;
      const msg = `[ERP] ${this.aiInput}`;
      this.aiInput = '';
      this.aiResponse = '';
      this.aiStreaming = true;
      try {
        const token = localStorage.getItem('api_token');
        const headers = { 'Content-Type': 'application/json' };
        if (token) headers['Authorization'] = `Bearer ${token}`;
        const resp = await fetch('/api/chat/stream', {
          method: 'POST',
          headers,
          body: JSON.stringify({ message: msg, user_id: 'erp-user' }),
        });
        const reader = resp.body.getReader();
        const dec = new TextDecoder();
        let buf = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          const lines = buf.split('\n');
          buf = lines.pop();
          for (const line of lines) {
            if (line.startsWith('data:')) {
              const data = line.slice(5).trim();
              if (data && data !== '[DONE]') {
                try {
                  const parsed = JSON.parse(data);
                  if (parsed.text) this.aiResponse += parsed.text;
                  else if (typeof parsed === 'string') this.aiResponse += parsed;
                } catch {
                  this.aiResponse += data;
                }
              }
            }
          }
        }
      } catch (e) {
        this.aiResponse = `Greška: ${e.message}`;
      }
      this.aiStreaming = false;
    },

    // =======================================================================
    // Helpers
    // =======================================================================
    async apiFetch(url, opts = {}) {
      const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
      const token = localStorage.getItem('api_token');
      if (token) headers['Authorization'] = `Bearer ${token}`;
      const r = await fetch(url, { ...opts, headers });
      if (!r.ok) {
        let errMsg = `HTTP ${r.status}`;
        try {
          const err = await r.json();
          errMsg = err.message || err.detail || errMsg;
        } catch {}
        throw new Error(errMsg);
      }
      return r.json();
    },

    fmt(val) {
      if (val === null || val === undefined) return '—';
      return new Intl.NumberFormat('hr-HR', {
        style: 'currency', currency: 'EUR', minimumFractionDigits: 2
      }).format(parseFloat(val) || 0);
    },

    daysOverdue(inv) {
      const due = inv.due_date || inv.erp_due_date;
      if (!due) return 0;
      const diff = (new Date() - new Date(due)) / (1000 * 60 * 60 * 24);
      return Math.max(0, Math.round(diff));
    },

    paymentBadge(inv) {
      const s = inv.erp_payment_status || inv.payment_status || 'unpaid';
      const overdue = inv.is_overdue;
      if (overdue && s !== 'paid') return 'badge-overdue';
      if (s === 'paid') return 'badge-paid';
      if (s === 'partial') return 'badge-partial';
      return 'badge-unpaid';
    },

    paymentLabel(inv) {
      const s = inv.erp_payment_status || inv.payment_status || 'unpaid';
      if (inv.is_overdue && s !== 'paid') return 'Zakašnjelo';
      const labels = { paid: 'Plaćeno', partial: 'Djelomično', unpaid: 'Neplaćeno' };
      return labels[s] || s;
    },

    bucketLabel(bucket) {
      const labels = {
        current: 'Tekući (nije dospjelo)',
        '1_30': 'Zakašnjelo 1–30 dana',
        '31_60': 'Zakašnjelo 31–60 dana',
        '61_90': 'Zakašnjelo 61–90 dana',
        over_90: 'Zakašnjelo više od 90 dana',
      };
      return labels[bucket] || bucket;
    },

    monthName(m) {
      return new Date(2024, m - 1, 1).toLocaleDateString('hr-HR', { month: 'long' });
    },

    activityIcon(action) {
      const icons = {
        customer_created: '+', customer_deleted: '-',
        product_created: '+', stock_adjusted: '~',
        vendor_invoice_created: '+', vendor_invoice_received: '!',
        vendor_invoice_approved: '!', vendor_payment_recorded: '$',
        payment_recorded: '$', invoice_created: '+',
      };
      return icons[action] || '*';
    },

    activityTime(ts) {
      if (!ts) return '';
      const d = new Date(ts);
      const now = new Date();
      const diffMs = now - d;
      const diffMin = Math.round(diffMs / 60000);
      if (diffMin < 1) return 'upravo';
      if (diffMin < 60) return `prije ${diffMin} min`;
      const diffH = Math.round(diffMin / 60);
      if (diffH < 24) return `prije ${diffH}h`;
      return d.toLocaleDateString('hr-HR', { day: 'numeric', month: 'short' });
    },

    movementLabel(type) {
      const labels = {
        manual_adjust: 'Ručno usklađivanje',
        purchase: 'Nabava',
        sale: 'Prodaja',
        write_off: 'Otpis',
      };
      return labels[type] || type;
    },
  };
}
