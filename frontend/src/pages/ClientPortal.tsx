import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';
import { LogOut, Plus, MessageSquare, Send, User } from 'lucide-react';

interface ChatSession {
  session_id: string;
  title: string;
  created_at: string;
}

interface Message {
  role: string;
  content: string;
  timestamp: string;
}

export const ClientPortal: React.FC = () => {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSession, setActiveSession] = useState<string | null>(null);
  const [chatHistory, setChatHistory] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [loadingMsg, setLoadingMsg] = useState(false);
  const [user, setUser] = useState<{ email: string; role: string } | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const userStr = localStorage.getItem('user');
    if (userStr) {
      setUser(JSON.parse(userStr));
    }
    fetchSessions();
  }, []);

  useEffect(() => {
    if (activeSession) {
      fetchSessionHistory(activeSession);
    }
  }, [activeSession]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory]);

  const fetchSessions = async () => {
    try {
      const res = await api.get('/api/chat/sessions');
      setSessions(res.data);
      if (res.data.length > 0 && !activeSession) {
        setActiveSession(res.data[0].session_id);
      }
    } catch (err) {
      console.error('Error fetching sessions', err);
    }
  };

  const fetchSessionHistory = async (sessId: string) => {
    try {
      const res = await api.get(`/api/chat/session/${sessId}`);
      setChatHistory(res.data.messages);
    } catch (err) {
      console.error('Error fetching chat history', err);
    }
  };

  const handleCreateSession = async () => {
    try {
      const title = `Chat ${sessions.length + 1}`;
      const res = await api.post('/api/chat/session', { title });
      setSessions((prev) => [res.data, ...prev]);
      setActiveSession(res.data.session_id);
      setChatHistory([]);
    } catch (err) {
      console.error('Failed to create session', err);
    }
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputMessage.trim() || !activeSession || loadingMsg) return;

    const tempMsg = inputMessage;
    setInputMessage('');
    setLoadingMsg(true);

    // Optimistically update message
    setChatHistory((prev) => [...prev, { role: 'user', content: tempMsg, timestamp: new Date().toISOString() }]);

    try {
      const res = await api.post(`/api/chat/message/${activeSession}`, { content: tempMsg });
      setChatHistory((prev) => [...prev, { role: 'assistant', content: res.data.reply, timestamp: new Date().toISOString() }]);
    } catch (err) {
      console.error('Failed to send message', err);
    } finally {
      setLoadingMsg(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user');
    navigate('/login');
  };

  return (
    <div style={{ display: 'flex', height: '100vh', backgroundColor: 'var(--color-canvas)', overflow: 'hidden' }}>
      
      {/* Sidebar - Sessions History */}
      <div style={{
        width: '320px',
        backgroundColor: 'var(--color-canvas-soft)',
        borderRight: '1px solid var(--color-hairline-soft)',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between'
      }}>
        
        <div>
          {/* Sidebar Header */}
          <div style={{ padding: '24px', borderBottom: '1px solid var(--color-hairline-soft)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: 'var(--color-brand)' }}></div>
              <span className="mono-eyebrow" style={{ color: 'var(--color-on-primary)', fontSize: '14px', letterSpacing: '-0.5px' }}>Sync Agent</span>
            </div>
            <button className="btn-secondary" style={{ padding: '8px', height: '32px' }} onClick={handleCreateSession}>
              <Plus size={16} />
            </button>
          </div>

          {/* Session List */}
          <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '8px', overflowY: 'auto', maxHeight: 'calc(100vh - 200px)' }}>
            <span className="mono-caps" style={{ padding: '0 8px 8px', fontSize: '10px' }}>Your Conversations</span>
            {sessions.map((sess) => (
              <div 
                key={sess.session_id} 
                onClick={() => setActiveSession(sess.session_id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  padding: '12px 16px',
                  borderRadius: 'var(--rounded-app-md)',
                  cursor: 'pointer',
                  backgroundColor: activeSession === sess.session_id ? 'var(--color-ink-soft)' : 'transparent',
                  border: activeSession === sess.session_id ? '1px solid var(--color-hairline-soft)' : '1px solid transparent',
                  transition: 'background-color 0.2s'
                }}
                className="session-item"
              >
                <MessageSquare size={16} style={{ color: activeSession === sess.session_id ? 'var(--color-brand)' : 'var(--color-mute)' }} />
                <span style={{ fontSize: '14px', color: activeSession === sess.session_id ? 'var(--color-on-primary)' : 'var(--color-ash)' }}>
                  {sess.title}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* User Info / Logout Footer */}
        <div style={{ padding: '24px', borderTop: '1px solid var(--color-hairline-soft)', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {user && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div style={{ 
                width: '36px', 
                height: '36px', 
                borderRadius: '50%', 
                backgroundColor: 'var(--color-ink-soft)', 
                display: 'flex', 
                alignItems: 'center', 
                justifyContent: 'center',
                border: '1px solid var(--color-hairline-soft)'
              }}>
                <User size={18} style={{ color: 'var(--color-brand)' }} />
              </div>
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <span style={{ fontSize: '14px', color: 'var(--color-on-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '160px' }}>
                  {user.email}
                </span>
                <span className="mono-micro" style={{ color: 'var(--color-mute)' }}>
                  {user.role} portal
                </span>
              </div>
            </div>
          )}
          
          <div style={{ display: 'flex', gap: '8px' }}>
            {user?.role === 'admin' && (
              <button 
                className="btn-secondary" 
                style={{ flex: 1 }}
                onClick={() => navigate('/admin')}
              >
                Admin Panel
              </button>
            )}
            <button 
              className="btn-secondary" 
              style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: user?.role === 'admin' ? 'none' : 1 }}
              onClick={handleLogout}
            >
              <LogOut size={16} />
              {user?.role !== 'admin' && 'Logout'}
            </button>
          </div>
        </div>

      </div>

      {/* Main Chat Area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100%' }}>
        
        {/* Chat Header */}
        <div style={{ 
          height: '64px', 
          borderBottom: '1px solid var(--color-hairline-soft)', 
          padding: '0 32px', 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'space-between',
          backgroundColor: 'var(--color-canvas)'
        }}>
          <h1 className="heading-sm" style={{ color: 'var(--color-on-primary)', fontSize: '18px' }}>
            {sessions.find(s => s.session_id === activeSession)?.title || 'Knowledge Base Agent'}
          </h1>
          <span className="mono-eyebrow" style={{ fontSize: '11px', color: 'var(--color-brand)' }}>
            Status: connected
          </span>
        </div>

        {/* Messages */}
        <div style={{ flex: 1, padding: '32px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
          {chatHistory.length === 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: '16px' }}>
              <div style={{ width: '40px', height: '40px', borderRadius: '50%', backgroundColor: 'var(--color-canvas-soft)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <div style={{ width: '10px', height: '10px', borderRadius: '50%', backgroundColor: 'var(--color-brand)' }}></div>
              </div>
              <h2 className="display-sm" style={{ fontSize: '28px', letterSpacing: '-0.8px', color: 'var(--color-on-primary)', textAlign: 'center' }}>
                Structure powers intelligence.
              </h2>
              <p className="mono-eyebrow" style={{ color: 'var(--color-mute)', textAlign: 'center', maxWidth: '400px' }}>
                Ask anything about MYK Laticrete chemical catalog. The agent will orchestrate graph and vector tools.
              </p>
            </div>
          ) : (
            chatHistory.map((msg, idx) => (
              <div 
                key={idx} 
                style={{
                  display: 'flex',
                  gap: '16px',
                  maxWidth: '800px',
                  alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                  flexDirection: msg.role === 'user' ? 'row-reverse' : 'row'
                }}
              >
                <div style={{ 
                  width: '32px', 
                  height: '32px', 
                  borderRadius: '50%', 
                  backgroundColor: msg.role === 'user' ? 'var(--color-brand)' : 'var(--color-canvas-soft)',
                  border: '1px solid var(--color-hairline-soft)',
                  flexShrink: 0,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '12px',
                  color: msg.role === 'user' ? 'var(--color-ink)' : 'var(--color-on-primary)',
                  fontWeight: 'bold'
                }}>
                  {msg.role === 'user' ? 'U' : 'A'}
                </div>
                
                <div style={{ 
                  backgroundColor: msg.role === 'user' ? 'var(--color-canvas-soft)' : 'transparent',
                  border: msg.role === 'user' ? '1px solid var(--color-hairline-soft)' : 'none',
                  borderRadius: 'var(--rounded-marketing)',
                  padding: msg.role === 'user' ? '12px 20px' : '0px',
                  color: 'var(--color-ash)',
                  fontSize: '15px',
                  lineHeight: '1.6',
                  whiteSpace: 'pre-wrap'
                }}>
                  {msg.content}
                </div>
              </div>
            ))
          )}
          {loadingMsg && (
            <div style={{ display: 'flex', gap: '16px', alignSelf: 'flex-start' }}>
              <div style={{ 
                width: '32px', 
                height: '32px', 
                borderRadius: '50%', 
                backgroundColor: 'var(--color-canvas-soft)',
                border: '1px solid var(--color-hairline-soft)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--color-brand)'
              }}>
                ...
              </div>
              <div className="mono-eyebrow" style={{ color: 'var(--color-mute)', alignSelf: 'center' }}>
                Agent thinking and invoking tools...
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Bar */}
        <div style={{ padding: '24px 32px', borderTop: '1px solid var(--color-hairline-soft)' }}>
          <form onSubmit={handleSendMessage} style={{ display: 'flex', gap: '12px' }}>
            <input 
              type="text" 
              className="input-dark" 
              placeholder="Ask about vitrified tiles adhesives, maximum thickeness, standards..." 
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              disabled={!activeSession}
            />
            <button type="submit" className="btn-brand" style={{ padding: '0 24px', display: 'flex', alignItems: 'center', gap: '8px' }} disabled={!activeSession || loadingMsg}>
              <Send size={16} />
              <span>Send</span>
            </button>
          </form>
        </div>

      </div>

    </div>
  );
};
