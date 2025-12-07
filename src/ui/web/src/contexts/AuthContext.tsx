import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import api from '../services/api';

interface User {
  id: number;
  username: string;
  email: string;
  full_name: string;
  role: string;
  status: string;
}

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('auth_token');
    if (token) {
      // Verify token and get user info
      // Use longer timeout for token verification (might be slow on first load)
      api.get('/api/v1/auth/me', {
        timeout: 30000, // 30 second timeout
      })
        .then(response => {
          setUser(response.data);
        })
        .catch(() => {
          // Token is invalid, remove it
          localStorage.removeItem('auth_token');
          localStorage.removeItem('user_info');
        })
        .finally(() => {
          setIsLoading(false);
        });
    } else {
      setIsLoading(false);
    }
  }, []);

  const login = async (username: string, password: string) => {
    // Login timeout increased to 30 seconds to accommodate slow backend responses
    // Login should be fast, but backend might be slow during initialization
    const response = await api.post('/auth/login', {
      username,
      password,
    }, {
      timeout: 30000, // 30 second timeout for login
    });

    if (response.data.access_token) {
      localStorage.setItem('auth_token', response.data.access_token);
      
      // Extract user data from JWT token
      const token = response.data.access_token;
      const payload = JSON.parse(atob(token.split('.')[1]));
      const userData = {
        id: parseInt(payload.sub),
        username: payload.username,
        email: payload.email,
        full_name: payload.username, // Use username as fallback for full_name
        role: payload.role,
        status: 'active' // Default status
      };
      
      localStorage.setItem('user_info', JSON.stringify(userData));
      setUser(userData);
    } else {
      throw new Error('No token received');
    }
  };

  const logout = () => {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('user_info');
    setUser(null);
  };

  const value: AuthContextType = {
    user,
    isAuthenticated: !!user,
    isLoading,
    login,
    logout,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};
