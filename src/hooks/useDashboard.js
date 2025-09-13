import { useState, useEffect, useCallback } from 'react';
import { useApp } from '../context/AppContext';
import dashboardService from '../services/dashboardService';
import { ACTION_TYPES } from '../context/AppContext';

export const useDashboard = () => {
  const { dispatch, portfolio, activeTrades, marketData, riskMetrics, loading } = useApp();
  const [refreshing, setRefreshing] = useState(false);

  const fetchDashboardData = useCallback(async (showLoading = true) => {
    try {
      console.log('Fetching dashboard data...');
      if (showLoading) {
        dispatch({ type: ACTION_TYPES.SET_LOADING, payload: true });
      } else {
        setRefreshing(true);
      }

      const data = await dashboardService.getDashboardOverview();
      console.log('Dashboard data received:', data);
      
      dispatch({ type: ACTION_TYPES.SET_PORTFOLIO, payload: data.portfolio });
      dispatch({ type: ACTION_TYPES.SET_ACTIVE_TRADES, payload: data.activeTrades });
      dispatch({ type: ACTION_TYPES.SET_MARKET_DATA, payload: data.marketData });
      dispatch({ type: ACTION_TYPES.SET_RISK_METRICS, payload: data.riskMetrics });
      dispatch({ type: ACTION_TYPES.SET_ERROR, payload: null });
    } catch (error) {
      dispatch({ type: ACTION_TYPES.SET_ERROR, payload: error.message });
      console.error('Dashboard data fetch error:', error);
    } finally {
      dispatch({ type: ACTION_TYPES.SET_LOADING, payload: false });
      setRefreshing(false);
    }
  }, [dispatch]);

  const refreshData = useCallback(() => {
    fetchDashboardData(false);
  }, [fetchDashboardData]);

  const executeTrade = async (tradeData) => {
    try {
      dispatch({ type: ACTION_TYPES.SET_LOADING, payload: true });
      const result = await dashboardService.executeTrade(tradeData);
      
      if (result.success) {
        // Refresh data after successful trade execution
        await fetchDashboardData(false);
        return result;
      }
      throw new Error(result.message || 'Trade execution failed');
    } catch (error) {
      dispatch({ type: ACTION_TYPES.SET_ERROR, payload: error.message });
      throw error;
    } finally {
      dispatch({ type: ACTION_TYPES.SET_LOADING, payload: false });
    }
  };

  useEffect(() => {
    fetchDashboardData();
  }, [fetchDashboardData]);

  return {
    portfolio,
    activeTrades,
    marketData,
    riskMetrics,
    loading,
    refreshing,
    refreshData,
    executeTrade,
    fetchDashboardData,
  };
};
