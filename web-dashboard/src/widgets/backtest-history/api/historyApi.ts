import { API_BASE } from '../../../shared/api/config';

export const fetchBacktestHistory = async (page: number, pageSize: number = 10) => {
    const response = await fetch(`${API_BASE}/api/backtest/history?page=${page}&page_size=${pageSize}`);
    if (!response.ok) {
        throw new Error(`Failed to fetch history: HTTP ${response.status}`);
    }
    return response.json();
};

export const fetchDetailedResults = async (filename: string) => {
    const response = await fetch(`${API_BASE}/results/${filename}`);
    if (!response.ok) {
        throw new Error(`Failed to fetch detailed results for ${filename}`);
    }
    return response.json();
};

export const saveUserConfigTemplate = async (templateName: string, configuration: any) => {
    const response = await fetch(`${API_BASE}/api/user-configs/${templateName}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(configuration),
    });
    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to save configuration.");
    }
    return response;
};

export const deleteBacktestHistory = async (filename: string) => {
    const response = await fetch(`${API_BASE}/api/backtest/history/${filename}`, {
        method: 'DELETE',
    });
    if (!response.ok) {
        throw new Error(`Failed to delete backtest: HTTP ${response.status}`);
    }
    return response;
};
