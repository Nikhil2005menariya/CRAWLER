import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { api } from '../api';

export const Register: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('client');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = await api.post('/api/auth/register', { email, password, role });
      localStorage.setItem('access_token', res.data.access_token);
      localStorage.setItem('user', JSON.stringify(res.data.user));
      
      if (res.data.user.role === 'admin') {
        navigate('/admin');
      } else {
        navigate('/');
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="section-dark" style={{ minHeight: '100vh', display: 'flex', alignItems: 'center' }}>
      <div className="grid-container" style={{ width: '100%', maxWidth: '480px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '32px', justifyContent: 'center' }}>
          <div style={{ width: '12px', height: '12px', borderRadius: '50%', backgroundColor: 'var(--color-brand)' }}></div>
          <span className="mono-eyebrow" style={{ color: 'var(--color-on-primary)', fontSize: '20px', letterSpacing: '0px', textTransform: 'none' }}>Saniti Sync</span>
        </div>
        
        <div className="card-dark" style={{ padding: '32px' }}>
          <h1 className="heading-sm" style={{ color: 'var(--color-on-primary)', marginBottom: '8px' }}>Create an account</h1>
          <p className="mono-eyebrow" style={{ marginBottom: '24px' }}>Register to interact with the engine.</p>
          
          {error && (
            <div style={{ color: 'var(--color-error)', fontSize: '14px', marginBottom: '16px', fontFamily: 'var(--font-mono)' }}>
              Error: {error}
            </div>
          )}

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div>
              <label className="mono-caps" style={{ display: 'block', marginBottom: '8px' }}>Email Address</label>
              <input 
                type="email" 
                className="input-dark" 
                value={email} 
                onChange={(e) => setEmail(e.target.value)} 
                required 
              />
            </div>
            <div>
              <label className="mono-caps" style={{ display: 'block', marginBottom: '8px' }}>Password</label>
              <input 
                type="password" 
                className="input-dark" 
                value={password} 
                onChange={(e) => setPassword(e.target.value)} 
                required 
              />
            </div>
            <div>
              <label className="mono-caps" style={{ display: 'block', marginBottom: '8px' }}>Register as</label>
              <div style={{ display: 'flex', gap: '12px', marginTop: '8px' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '14px' }}>
                  <input 
                    type="radio" 
                    name="role" 
                    value="client" 
                    checked={role === 'client'} 
                    onChange={() => setRole('client')} 
                    style={{ accentColor: 'var(--color-brand)' }}
                  />
                  Customer / Client
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '14px' }}>
                  <input 
                    type="radio" 
                    name="role" 
                    value="admin" 
                    checked={role === 'admin'} 
                    onChange={() => setRole('admin')} 
                    style={{ accentColor: 'var(--color-brand)' }}
                  />
                  Administrator
                </label>
              </div>
            </div>
            
            <button type="submit" className="btn-primary" style={{ width: '100%', marginTop: '8px' }} disabled={loading}>
              {loading ? 'Processing...' : 'Register'}
            </button>
          </form>

          <p style={{ marginTop: '24px', textAlign: 'center', fontSize: '13px', color: 'var(--color-mute)' }}>
            Already have an account?{' '}
            <Link to="/login" style={{ color: 'var(--color-brand)', textDecoration: 'none' }}>Sign In here</Link>
          </p>
        </div>
      </div>
    </div>
  );
};
