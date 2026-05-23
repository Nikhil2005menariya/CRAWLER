import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';
import { RefreshCw, Database, ArrowLeft, Activity, TrendingUp, Layers, Clock, AlertTriangle, Check, Trash2, Edit3, X } from 'lucide-react';

interface CrawlRecord {
  id: number;
  url: string;
  title: string;
  timestamp: string;
}

interface PipelineMetrics {
  crawled_pages_count: number;
  parsed_products_count: number;
  needs_review_count: number;
  active_products_gauge: number;
  freshness_lag_seconds: number;
}

interface ReviewProduct {
  id: number;
  sku: string;
  product_name: string;
  product_family: string;
  confidence: number;
  needs_review: number;
  version: number;
  details: {
    product_name?: string;
    sku?: string;
    product_family?: string;
    description?: string;
    grade_classification?: string;
    substrate_compatibility?: string[];
    tile_compatibility?: string[];
    recommended_use_cases?: string[];
    technical_specs?: {
      coverage_rate?: string;
      open_time?: string;
    };
    packaging?: {
      sizes?: string[];
      shelf_life?: string;
    };
  };
}

export const AdminPortal: React.FC = () => {
  const [crawlRecords, setCrawlRecords] = useState<CrawlRecord[]>([]);
  const [metrics, setMetrics] = useState<PipelineMetrics>({
    crawled_pages_count: 0,
    parsed_products_count: 0,
    needs_review_count: 0,
    active_products_gauge: 0,
    freshness_lag_seconds: 0.0
  });
  const [reviewProducts, setReviewProducts] = useState<ReviewProduct[]>([]);
  
  // Editor State
  const [selectedProduct, setSelectedProduct] = useState<ReviewProduct | null>(null);
  const [editName, setEditName] = useState('');
  const [editSku, setEditSku] = useState('');
  const [editFamily, setEditFamily] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editGrade, setEditGrade] = useState('');
  const [editSubstrates, setEditSubstrates] = useState('');
  const [editTiles, setEditTiles] = useState('');
  const [editUseCases, setEditUseCases] = useState('');
  
  const [crawling, setCrawling] = useState(false);
  const [crawlingMsg, setCrawlingMsg] = useState('');
  const [toastMsg, setToastMsg] = useState('');
  
  const navigate = useNavigate();

  useEffect(() => {
    fetchCrawlRecords();
    fetchMetrics();
    fetchReviewProducts();
    
    // Poll metrics every 10 seconds for real-time Prometheus updates
    const interval = setInterval(fetchMetrics, 10000);
    return () => clearInterval(interval);
  }, []);

  const fetchCrawlRecords = async () => {
    try {
      const res = await api.get('/api/admin/crawl/records');
      setCrawlRecords(res.data.records);
    } catch (err) {
      console.error('Error fetching crawl records:', err);
    }
  };

  const fetchMetrics = async () => {
    try {
      const res = await api.get('/api/admin/metrics');
      setMetrics(res.data);
    } catch (err) {
      console.error('Error fetching pipeline metrics:', err);
    }
  };

  const fetchReviewProducts = async () => {
    try {
      const res = await api.get('/api/admin/review/products');
      setReviewProducts(res.data.products);
    } catch (err) {
      console.error('Error fetching review products:', err);
    }
  };

  const handleTriggerCrawl = async () => {
    setCrawling(true);
    setCrawlingMsg('Starting background crawl pipeline (n_urls=64)...');
    try {
      await api.post('/api/ingest', {});
      setCrawlingMsg('Ingestion scheduled successfully in background cycle!');
      setTimeout(() => {
        setCrawling(false);
        fetchCrawlRecords();
        fetchMetrics();
        fetchReviewProducts();
      }, 3000);
    } catch (err) {
      setCrawlingMsg('Failed to trigger background crawl.');
      setTimeout(() => setCrawling(false), 3000);
    }
  };

  const handleSelectProduct = (prod: ReviewProduct) => {
    setSelectedProduct(prod);
    setEditName(prod.details.product_name || prod.product_name || '');
    setEditSku(prod.details.sku || prod.sku || '');
    setEditFamily(prod.details.product_family || prod.product_family || '');
    setEditDescription(prod.details.description || '');
    setEditGrade(prod.details.grade_classification || '');
    setEditSubstrates((prod.details.substrate_compatibility || []).join(', '));
    setEditTiles((prod.details.tile_compatibility || []).join(', '));
    setEditUseCases((prod.details.recommended_use_cases || []).join(', '));
  };

  const showToast = (msg: string) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(''), 4000);
  };

  const handleSaveOrApprove = async (approve: boolean) => {
    if (!selectedProduct) return;
    
    // Format csv text back to arrays
    const substratesArray = editSubstrates.split(',').map(s => s.trim()).filter(Boolean);
    const tilesArray = editTiles.split(',').map(s => s.trim()).filter(Boolean);
    const useCasesArray = editUseCases.split(',').map(s => s.trim()).filter(Boolean);
    
    // Construct updated details JSON dict
    const updatedDetails = {
      ...selectedProduct.details,
      product_name: editName,
      sku: editSku || null,
      product_family: editFamily,
      description: editDescription,
      grade_classification: editGrade,
      substrate_compatibility: substratesArray,
      tile_compatibility: tilesArray,
      recommended_use_cases: useCasesArray
    };
    
    try {
      const res = await api.put(`/api/admin/review/products/${selectedProduct.id}`, {
        details: updatedDetails,
        approve: approve
      });
      
      showToast(res.data.message);
      setSelectedProduct(null);
      fetchMetrics();
      fetchReviewProducts();
    } catch (err) {
      console.error(err);
      showToast('Error saving product updates.');
    }
  };

  const handleDeleteProduct = async (id: number) => {
    if (!window.confirm('Are you sure you want to delete this product from the catalog completely?')) return;
    
    try {
      const res = await api.delete(`/api/admin/review/products/${id}`);
      showToast(res.data.message);
      setSelectedProduct(null);
      fetchMetrics();
      fetchReviewProducts();
    } catch (err) {
      console.error(err);
      showToast('Failed to delete product.');
    }
  };

  return (
    <div style={{ backgroundColor: 'var(--color-canvas)', color: 'var(--color-ash)', minHeight: '100vh', paddingBottom: '64px' }}>
      
      {/* Dynamic Toast Success Indicator */}
      {toastMsg && (
        <div style={{
          position: 'fixed',
          bottom: '24px',
          right: '24px',
          backgroundColor: 'var(--color-ink)',
          color: '#ffffff',
          padding: '16px 24px',
          borderRadius: 'var(--rounded-app-md)',
          boxShadow: '0 8px 30px rgba(0, 0, 0, 0.5)',
          borderLeft: '4px solid var(--color-success)',
          zIndex: 9999,
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          animation: 'slideIn 0.3s ease-out'
        }}>
          <Check size={16} style={{ color: 'var(--color-success)' }} />
          <span style={{ fontSize: '13px', fontFamily: 'var(--font-mono)' }}>{toastMsg}</span>
        </div>
      )}

      {/* Top Navbar */}
      <div style={{
        height: '64px',
        backgroundColor: 'var(--color-canvas)',
        borderBottom: '1px solid var(--color-hairline-soft)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 32px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <button 
            className="btn-secondary" 
            style={{ display: 'flex', alignItems: 'center', gap: '8px', height: '32px' }}
            onClick={() => navigate('/')}
          >
            <ArrowLeft size={14} />
            <span>Chat View</span>
          </button>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: 'var(--color-brand)' }}></div>
            <span className="mono-eyebrow" style={{ color: 'var(--color-on-primary)', fontSize: '14px', textTransform: 'none' }}>Admin Center</span>
          </div>
        </div>
        <span className="mono-micro" style={{ color: 'var(--color-mute)' }}>Secure System Shell v1.0</span>
      </div>

      {/* Hero Display Header */}
      <div className="grid-container" style={{ paddingTop: '48px', paddingBottom: '32px' }}>
        <span className="mono-eyebrow">Enterprise Engine Admin</span>
        <h1 className="display-sm" style={{ color: 'var(--color-on-primary)', marginTop: '8px', letterSpacing: '-1.5px' }}>
          Knowledge Management Console.
        </h1>
      </div>

      {/* Section: Prometheus & Grafana Live Metrics Grid */}
      <div className="grid-container" style={{ marginBottom: '32px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
          <Activity size={16} style={{ color: 'var(--color-brand)' }} />
          <span className="mono-eyebrow" style={{ fontSize: '12px' }}>Prometheus & Grafana Telemetry</span>
        </div>
        
        {/* bento grid 4 columns */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '20px'
        }}>
          
          {/* Card 1: Crawled Count */}
          <div className="card-dark" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '12px', border: '1px solid var(--color-hairline-soft)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="mono-eyebrow" style={{ fontSize: '11px', color: 'var(--color-mute)' }}>Crawl Ingestion Total</span>
              <Database size={16} style={{ color: 'var(--color-brand)' }} />
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
              <span style={{ fontSize: '32px', fontWeight: 'bold', fontFamily: 'var(--font-mono)', color: 'var(--color-on-primary)' }}>
                {metrics.crawled_pages_count}
              </span>
              <span style={{ fontSize: '12px', color: 'var(--color-success)', fontFamily: 'var(--font-mono)' }}>pages</span>
            </div>
            <span style={{ fontSize: '12px', color: 'var(--color-mute)' }}>Raw discovered catalog addresses</span>
          </div>

          {/* Card 2: Active Products Gauge */}
          <div className="card-dark" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '12px', border: '1px solid var(--color-hairline-soft)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="mono-eyebrow" style={{ fontSize: '11px', color: 'var(--color-mute)' }}>Prometheus Active Products</span>
              <Layers size={16} style={{ color: 'var(--color-success)' }} />
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
              <span style={{ fontSize: '32px', fontWeight: 'bold', fontFamily: 'var(--font-mono)', color: 'var(--color-success)' }}>
                {metrics.active_products_gauge}
              </span>
              <span style={{ fontSize: '12px', color: 'var(--color-success)', fontFamily: 'var(--font-mono)' }}>items</span>
            </div>
            <span style={{ fontSize: '12px', color: 'var(--color-mute)' }}>Active knowledge nodes in Neo4j</span>
          </div>

          {/* Card 3: QA Review Queue */}
          <div className="card-dark" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '12px', border: '1px solid var(--color-hairline-soft)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="mono-eyebrow" style={{ fontSize: '11px', color: 'var(--color-mute)' }}>Quality Review Queue</span>
              <TrendingUp size={16} style={{ color: metrics.needs_review_count > 0 ? '#f59e0b' : 'var(--color-mute)' }} />
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
              <span style={{ 
                fontSize: '32px', 
                fontWeight: 'bold', 
                fontFamily: 'var(--font-mono)', 
                color: metrics.needs_review_count > 0 ? '#f59e0b' : 'var(--color-on-primary)' 
              }}>
                {metrics.needs_review_count}
              </span>
              <span style={{ fontSize: '12px', color: 'var(--color-mute)', fontFamily: 'var(--font-mono)' }}>pending</span>
            </div>
            <span style={{ fontSize: '12px', color: 'var(--color-mute)' }}>Products below extraction threshold</span>
          </div>

          {/* Card 4: freshness lag status */}
          <div className="card-dark" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '12px', border: '1px solid var(--color-hairline-soft)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="mono-eyebrow" style={{ fontSize: '11px', color: 'var(--color-mute)' }}>Telemetry Sync Freshness</span>
              <Clock size={16} style={{ color: 'var(--color-brand)' }} />
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
              <span style={{ fontSize: '32px', fontWeight: 'bold', fontFamily: 'var(--font-mono)', color: 'var(--color-on-primary)' }}>
                {metrics.freshness_lag_seconds === 0 ? 'LIVE' : `${metrics.freshness_lag_seconds}s`}
              </span>
              <span style={{ display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%', backgroundColor: 'var(--color-success)', alignSelf: 'center' }}></span>
            </div>
            <span style={{ fontSize: '12px', color: 'var(--color-mute)' }}>FastAPI pipeline response state</span>
          </div>

        </div>
      </div>

      {/* Main Grid: Left is QA audit queue, Right is the selected product metadata editor */}
      <div className="grid-container" style={{ display: 'grid', gridTemplateColumns: selectedProduct ? '1.2fr 1fr' : '1fr', gap: '32px', marginBottom: '48px', transition: 'all 0.3s ease-out' }}>
        
        {/* Panel 1: QA Review Queue List */}
        <div className="card-dark" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <AlertTriangle size={20} style={{ color: '#f59e0b' }} />
            <div>
              <h2 className="heading-sm" style={{ color: 'var(--color-on-primary)' }}>Quality Review Audit Log</h2>
              <p style={{ fontSize: '12px', color: 'var(--color-mute)', margin: '4px 0 0 0' }}>Verify LLM extractions flagging confidence levels below 60%</p>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {reviewProducts.length === 0 ? (
              <div style={{
                textAlign: 'center',
                padding: '48px',
                border: '1.5px dashed var(--color-hairline-soft)',
                borderRadius: 'var(--rounded-marketing)',
                color: 'var(--color-mute)'
              }}>
                🎉 All ingested products satisfy high extraction confidence metrics! Queue is clean.
              </div>
            ) : (
              reviewProducts.map(prod => (
                <div 
                  key={prod.id} 
                  style={{
                    backgroundColor: 'var(--color-canvas-light)',
                    borderRadius: 'var(--rounded-app-md)',
                    border: selectedProduct?.id === prod.id ? '2px solid var(--color-brand)' : '1px solid var(--color-hairline)',
                    padding: '20px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '16px',
                    color: 'var(--color-ink)',
                    transition: 'all 0.2s ease-out'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                        <span className="badge-blue" style={{ fontSize: '11px' }}>{prod.product_family || 'No Family'}</span>
                        {prod.sku && <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--color-mute)' }}>SKU: {prod.sku}</span>}
                      </div>
                      <h3 style={{ fontSize: '16px', fontWeight: 'bold', color: 'var(--color-ink)', margin: 0 }}>
                        {prod.product_name || 'Unnamed Extracted Node'}
                      </h3>
                    </div>

                    {/* Confidence gauge display */}
                    <div style={{ textAlign: 'right' }}>
                      <span style={{ fontSize: '11px', color: 'var(--color-mute)', display: 'block', marginBottom: '4px' }}>CONFIDENCE</span>
                      <span style={{ 
                        fontFamily: 'var(--font-mono)', 
                        fontSize: '16px', 
                        fontWeight: 'bold', 
                        color: prod.confidence < 0.5 ? 'var(--color-error)' : '#d97706' 
                      }}>
                        {Math.round(prod.confidence * 100)}%
                      </span>
                    </div>
                  </div>

                  <p style={{ fontSize: '12.5px', color: 'var(--color-mute)', margin: 0, lineHeight: 1.5, maxHeight: '60px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {prod.details.description || 'No product catalog description extracted.'}
                  </p>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid var(--color-hairline)', paddingTop: '14px' }}>
                    <span className="mono-micro" style={{ color: 'var(--color-mute)' }}>v{prod.version} Schema Record</span>
                    <div style={{ display: 'flex', gap: '10px' }}>
                      <button 
                        className="btn-secondary" 
                        style={{ height: '32px', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', padding: '0 12px' }}
                        onClick={() => handleSelectProduct(prod)}
                      >
                        <Edit3 size={12} />
                        <span>Audit Record</span>
                      </button>
                      <button 
                        className="btn-danger" 
                        style={{ height: '32px', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', padding: '0 12px', backgroundColor: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.4)', color: '#ef4444' }}
                        onClick={() => handleDeleteProduct(prod.id)}
                      >
                        <Trash2 size={12} />
                        <span>Delete</span>
                      </button>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Panel 2: Product Metadata Audit Editor (Displays dynamically on selection) */}
        {selectedProduct && (
          <div className="card-dark" style={{ display: 'flex', flexDirection: 'column', gap: '24px', border: '1px solid var(--color-brand)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <Edit3 size={18} style={{ color: 'var(--color-brand)' }} />
                <h2 className="heading-sm" style={{ color: 'var(--color-on-primary)' }}>Manual Auditor</h2>
              </div>
              <button 
                onClick={() => setSelectedProduct(null)} 
                style={{ backgroundColor: 'transparent', border: 'none', color: 'var(--color-mute)', cursor: 'pointer' }}
              >
                <X size={20} />
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              
              <div>
                <label className="mono-caps" style={{ display: 'block', marginBottom: '6px', color: 'var(--color-mute)' }}>Product Name</label>
                <input 
                  type="text" 
                  className="input-dark" 
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  style={{ width: '100%', fontSize: '13px' }}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                <div>
                  <label className="mono-caps" style={{ display: 'block', marginBottom: '6px', color: 'var(--color-mute)' }}>SKU Code</label>
                  <input 
                    type="text" 
                    className="input-dark" 
                    value={editSku}
                    onChange={(e) => setEditSku(e.target.value)}
                    style={{ width: '100%', fontSize: '13px' }}
                  />
                </div>
                <div>
                  <label className="mono-caps" style={{ display: 'block', marginBottom: '6px', color: 'var(--color-mute)' }}>Product Family</label>
                  <input 
                    type="text" 
                    className="input-dark" 
                    value={editFamily}
                    onChange={(e) => setEditFamily(e.target.value)}
                    style={{ width: '100%', fontSize: '13px' }}
                  />
                </div>
              </div>

              <div>
                <label className="mono-caps" style={{ display: 'block', marginBottom: '6px', color: 'var(--color-mute)' }}>Description</label>
                <textarea 
                  className="textarea-dark" 
                  rows={4}
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  style={{ width: '100%', fontSize: '13px' }}
                />
              </div>

              <div>
                <label className="mono-caps" style={{ display: 'block', marginBottom: '6px', color: 'var(--color-mute)' }}>Grade / Classification</label>
                <input 
                  type="text" 
                  className="input-dark" 
                  value={editGrade}
                  onChange={(e) => setEditGrade(e.target.value)}
                  style={{ width: '100%', fontSize: '13px' }}
                  placeholder="e.g. C2TES1, ISO 13007"
                />
              </div>

              <div>
                <label className="mono-caps" style={{ display: 'block', marginBottom: '6px', color: 'var(--color-mute)' }}>Substrate Compatibility (Comma Separated)</label>
                <input 
                  type="text" 
                  className="input-dark" 
                  value={editSubstrates}
                  onChange={(e) => setEditSubstrates(e.target.value)}
                  style={{ width: '100%', fontSize: '13px' }}
                />
              </div>

              <div>
                <label className="mono-caps" style={{ display: 'block', marginBottom: '6px', color: 'var(--color-mute)' }}>Tile Compatibility (Comma Separated)</label>
                <input 
                  type="text" 
                  className="input-dark" 
                  value={editTiles}
                  onChange={(e) => setEditTiles(e.target.value)}
                  style={{ width: '100%', fontSize: '13px' }}
                />
              </div>

              <div>
                <label className="mono-caps" style={{ display: 'block', marginBottom: '6px', color: 'var(--color-mute)' }}>Recommended Use Cases (Comma Separated)</label>
                <input 
                  type="text" 
                  className="input-dark" 
                  value={editUseCases}
                  onChange={(e) => setEditUseCases(e.target.value)}
                  style={{ width: '100%', fontSize: '13px' }}
                />
              </div>

              {/* Action Operations for Editor */}
              <div style={{ display: 'flex', gap: '12px', marginTop: '12px', justifyContent: 'flex-end' }}>
                <button 
                  className="btn-secondary" 
                  style={{ height: '36px', fontSize: '13px' }}
                  onClick={() => handleSaveOrApprove(false)}
                >
                  Save Draft
                </button>
                <button 
                  className="btn-brand" 
                  style={{ height: '36px', display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', padding: '0 20px' }}
                  onClick={() => handleSaveOrApprove(true)}
                >
                  <Check size={14} />
                  <span>Approve & Sync</span>
                </button>
              </div>

            </div>
          </div>
        )}

      </div>

      {/* Grid: Crawl Management (Full Width Card for Clean Ingestion log auditing) */}
      <div className="grid-container">
        
        {/* Panel: Web Crawler Manager (SQLite View) */}
        <div className="card-dark" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <Database size={20} style={{ color: 'var(--color-brand)' }} />
              <h2 className="heading-sm" style={{ color: 'var(--color-on-primary)' }}>Ingestion & Crawl Hub</h2>
            </div>
            <button 
              className="btn-brand" 
              style={{ display: 'flex', alignItems: 'center', gap: '8px', height: '36px', padding: '0 16px', fontSize: '13px' }}
              onClick={handleTriggerCrawl}
              disabled={crawling}
            >
              <RefreshCw size={14} className={crawling ? 'spin' : ''} />
              <span>{crawling ? 'Crawling...' : 'Request Recrawl'}</span>
            </button>
          </div>

          {crawling && (
            <div style={{
              backgroundColor: 'var(--color-ink-soft)',
              border: '1px solid var(--color-brand)',
              borderRadius: 'var(--rounded-app-md)',
              padding: '16px',
              color: 'var(--color-brand)',
              fontFamily: 'var(--font-mono)',
              fontSize: '12px'
            }}>
              {crawlingMsg}
            </div>
          )}

          {/* SQLite Table (Styling: Polarity Inversion to Light inside card for legibility) */}
          <div style={{ backgroundColor: 'var(--color-canvas-light)', borderRadius: 'var(--rounded-marketing)', padding: '16px', overflowX: 'auto', border: '1px solid var(--color-hairline)' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', color: 'var(--color-ink)', fontSize: '13px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--color-hairline)', textAlign: 'left' }}>
                  <th className="mono-caps" style={{ padding: '8px', color: 'var(--color-mute)' }}>Title</th>
                  <th className="mono-caps" style={{ padding: '8px', color: 'var(--color-mute)' }}>Target Source</th>
                  <th className="mono-caps" style={{ padding: '8px', color: 'var(--color-mute)' }}>Crawl Date</th>
                </tr>
              </thead>
              <tbody>
                {crawlRecords.length === 0 ? (
                  <tr>
                    <td colSpan={3} style={{ textAlign: 'center', padding: '24px', color: 'var(--color-mute)' }}>No records crawled yet.</td>
                  </tr>
                ) : (
                  crawlRecords.slice(0, 10).map((rec) => (
                    <tr key={rec.id} style={{ borderBottom: '1px solid var(--color-hairline)' }}>
                      <td style={{ padding: '12px 8px', fontWeight: 'bold' }}>{rec.title || 'Unknown Title'}</td>
                      <td style={{ padding: '12px 8px', fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--color-link-blue)' }}>
                        <a href={rec.url} target="_blank" rel="noopener noreferrer" style={{ textDecoration: 'none' }}>{rec.url.replace('https://myklaticrete.com', '')}</a>
                      </td>
                      <td style={{ padding: '12px 8px', color: 'var(--color-mute)' }}>{new Date(rec.timestamp).toLocaleDateString()}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

      </div>

    </div>
  );
};
