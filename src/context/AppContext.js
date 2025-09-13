import React, { createContext, useContext, useReducer } from 'react';

// Initial state
const initialState = {
  user: null,
  portfolio: {
    totalCapital: 0,
    utilizedCapital: 0,
    availableCapital: 0,
    totalValue: 0,
    totalPnL: 0,
    totalPnLPercent: 0,
  },
  activeTrades: [],
  marketData: {
    indices: [],
    trendingStocks: [],
    marketStatus: 'closed',
  },
  riskMetrics: {
    portfolioRisk: 0,
    maxRisk: 0,
    riskUtilization: 0,
  },
  loading: false,
  error: null,
};

// Action types
export const ACTION_TYPES = {
  SET_USER: 'SET_USER',
  SET_PORTFOLIO: 'SET_PORTFOLIO',
  SET_ACTIVE_TRADES: 'SET_ACTIVE_TRADES',
  SET_MARKET_DATA: 'SET_MARKET_DATA',
  SET_RISK_METRICS: 'SET_RISK_METRICS',
  SET_LOADING: 'SET_LOADING',
  SET_ERROR: 'SET_ERROR',
  ADD_TRADE: 'ADD_TRADE',
  UPDATE_TRADE: 'UPDATE_TRADE',
  REMOVE_TRADE: 'REMOVE_TRADE',
};

// Reducer
const appReducer = (state, action) => {
  switch (action.type) {
    case ACTION_TYPES.SET_USER:
      return { ...state, user: action.payload };
    case ACTION_TYPES.SET_PORTFOLIO:
      return { ...state, portfolio: action.payload };
    case ACTION_TYPES.SET_ACTIVE_TRADES:
      return { ...state, activeTrades: action.payload };
    case ACTION_TYPES.SET_MARKET_DATA:
      return { ...state, marketData: action.payload };
    case ACTION_TYPES.SET_RISK_METRICS:
      return { ...state, riskMetrics: action.payload };
    case ACTION_TYPES.SET_LOADING:
      return { ...state, loading: action.payload };
    case ACTION_TYPES.SET_ERROR:
      return { ...state, error: action.payload };
    case ACTION_TYPES.ADD_TRADE:
      return { ...state, activeTrades: [...state.activeTrades, action.payload] };
    case ACTION_TYPES.UPDATE_TRADE:
      return {
        ...state,
        activeTrades: state.activeTrades.map(trade =>
          trade.id === action.payload.id ? { ...trade, ...action.payload } : trade
        ),
      };
    case ACTION_TYPES.REMOVE_TRADE:
      return {
        ...state,
        activeTrades: state.activeTrades.filter(trade => trade.id !== action.payload),
      };
    default:
      return state;
  }
};

// Context
const AppContext = createContext();

// Provider component
export const AppProvider = ({ children }) => {
  const [state, dispatch] = useReducer(appReducer, initialState);

  const value = {
    ...state,
    dispatch,
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
};

// Custom hook to use the context
export const useApp = () => {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error('useApp must be used within an AppProvider');
  }
  return context;
};
