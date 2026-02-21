import React from 'react';
import {
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    Box,
    Typography,
    Chip,
    Grid,
    Paper,
    Stack,
    Divider,
    Button
} from '@mui/material';
import { InfoOutlined } from '@mui/icons-material';
import MuiTooltip from '@mui/material/Tooltip';

interface TradeDetailsModalProps {
    open: boolean;
    onClose: () => void;
    selectedTrade: any | null;
}

const TradeDetailsModal: React.FC<TradeDetailsModalProps> = ({ open, onClose, selectedTrade }) => {
    return (
        <Dialog
            open={open}
            onClose={onClose}
            maxWidth="md"
            fullWidth
            PaperProps={{
                sx: { bgcolor: '#1e1e1e', color: '#fff' }
            }}
        >
            {selectedTrade && (
                <>
                    <DialogTitle sx={{ borderBottom: '1px solid #333', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Box display="flex" alignItems="center" gap={2}>
                            <Typography variant="h6">Trade #{selectedTrade.id}</Typography>
                            <Chip
                                label={selectedTrade.direction?.toUpperCase()}
                                color={selectedTrade.direction === 'LONG' ? 'success' : 'error'}
                                size="small"
                                variant="outlined"
                            />
                            <Chip
                                label={selectedTrade.pnl >= 0 ? "WIN" : "LOSS"}
                                color={selectedTrade.pnl >= 0 ? "success" : "error"}
                                size="small"
                            />
                        </Box>
                        <Typography variant="h5" color={selectedTrade.pnl >= 0 ? "success.main" : "error.main"}>
                            {selectedTrade.pnl >= 0 ? "+" : ""}${selectedTrade.pnl?.toFixed(2)} ({selectedTrade.pnl_percent?.toFixed(2)}%)
                        </Typography>
                    </DialogTitle>
                    <DialogContent sx={{ mt: 2 }}>
                        <Grid container spacing={3}>
                            <Grid item xs={12}>
                                <Paper variant="outlined" sx={{ p: 2, bgcolor: 'rgba(255,255,255,0.05)', borderColor: '#333' }}>
                                    <Typography variant="caption" sx={{ color: '#fff', opacity: 0.7 }} gutterBottom display="block">ENTRY REASON / CONTEXT</Typography>
                                    <Typography variant="body1" sx={{ fontStyle: 'italic', fontWeight: 'medium', color: '#fff' }}>
                                        "{selectedTrade.reason || 'No specific reason recorded'}"
                                    </Typography>

                                    {selectedTrade.metadata && Object.keys(selectedTrade.metadata).length > 0 && (
                                        <Box sx={{ mt: 2, pt: 2, borderTop: '1px solid rgba(255,255,255,0.1)' }}>
                                            <Typography variant="caption" sx={{ color: '#fff', opacity: 0.7 }} gutterBottom display="block">ADDITIONAL CONTEXT</Typography>
                                            <Grid container spacing={1}>
                                                {Object.entries(selectedTrade.metadata).map(([key, value]) => (
                                                    <Grid item xs={6} md={4} key={key}>
                                                        <Typography variant="caption" sx={{ color: '#aaa', textTransform: 'uppercase', fontSize: '0.7rem' }} display="block">
                                                            {key.replace(/_/g, ' ')}
                                                        </Typography>
                                                        <Typography variant="body2" sx={{ color: '#fff' }}>
                                                            {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                                                        </Typography>
                                                    </Grid>
                                                ))}
                                            </Grid>
                                        </Box>
                                    )}
                                </Paper>
                            </Grid>

                            {/* PnL Calculation Breakdown */}
                            <Grid item xs={12}>
                                <Paper variant="outlined" sx={{ p: 2, bgcolor: 'rgba(255,255,255,0.05)', borderColor: '#333' }}>
                                    <Typography variant="caption" sx={{ color: '#fff', opacity: 0.7 }} gutterBottom display="block">PnL CALCULATION</Typography>

                                    {(() => {
                                        const isLong = selectedTrade.direction === 'LONG';
                                        const exitPrice = selectedTrade.exit_price || 0;
                                        const entryPrice = selectedTrade.entry_price || 0;
                                        const size = selectedTrade.size || 0;
                                        const commission = selectedTrade.commission || 0;

                                        const priceDiff = isLong ? (exitPrice - entryPrice) : (entryPrice - exitPrice);
                                        const grossPnl = priceDiff * size;
                                        // netPnl should match selectedTrade.pnl roughly

                                        const pnlColor = grossPnl >= 0 ? '#4caf50' : '#f44336';

                                        return (
                                            <Box sx={{ fontFamily: 'Monospace', fontSize: '0.9rem', color: '#ccc' }}>
                                                <Box display="flex" justifyContent="space-between" mb={1}>
                                                    <span>Formula:</span>
                                                    <span style={{ color: '#aaa' }}>
                                                        ({isLong ? 'Exit' : 'Entry'} - {isLong ? 'Entry' : 'Exit'}) × Size - Comm
                                                    </span>
                                                </Box>

                                                <Box display="flex" justifyContent="space-between">
                                                    <span>Price Diff:</span>
                                                    <span>
                                                        ({isLong ? exitPrice.toFixed(2) : entryPrice.toFixed(2)} - {isLong ? entryPrice.toFixed(2) : exitPrice.toFixed(2)}) × {size.toFixed(4)}
                                                    </span>
                                                </Box>

                                                <Box display="flex" justifyContent="space-between" sx={{ borderBottom: '1px solid #444', pb: 1, mb: 1 }}>
                                                    <span>Gross PnL:</span>
                                                    <span style={{ color: pnlColor }}>
                                                        {grossPnl >= 0 ? '+' : ''}{grossPnl.toFixed(2)}
                                                    </span>
                                                </Box>

                                                <Box display="flex" justifyContent="space-between">
                                                    <span>Commission:</span>
                                                    <span style={{ color: '#f44336' }}>
                                                        -{commission.toFixed(2)}
                                                    </span>
                                                </Box>

                                                <Box display="flex" justifyContent="space-between" sx={{ borderTop: '1px solid #555', pt: 1, mt: 1, fontWeight: 'bold' }}>
                                                    <span>Net PnL:</span>
                                                    <span style={{ color: selectedTrade.pnl >= 0 ? '#4caf50' : '#f44336' }}>
                                                        {selectedTrade.pnl >= 0 ? '+' : ''}{selectedTrade.pnl?.toFixed(2)}
                                                    </span>
                                                </Box>
                                            </Box>
                                        );
                                    })()}
                                </Paper>
                            </Grid>

                            <Grid item xs={12} md={6}>
                                <Stack spacing={2}>
                                    <Box>
                                        <Typography variant="subtitle2" color="gray">ENTRY TIME</Typography>
                                        <Typography variant="body1">{selectedTrade.entry_time ? new Date(selectedTrade.entry_time).toLocaleString() : 'N/A'}</Typography>
                                    </Box>
                                    <Box>
                                        <Typography variant="subtitle2" color="gray">ENTRY PRICE</Typography>
                                        <Typography variant="body1">${selectedTrade.entry_price?.toFixed(2)}</Typography>
                                    </Box>
                                    <Box>
                                        <Typography variant="subtitle2" color="gray">SIZE</Typography>
                                        <Typography variant="body1">{selectedTrade.size?.toFixed(4)}</Typography>
                                    </Box>
                                </Stack>
                            </Grid>

                            <Grid item xs={12} md={6}>
                                <Stack spacing={2}>
                                    <Box>
                                        <Typography variant="subtitle2" color="gray">EXIT TIME</Typography>
                                        <Typography variant="body1">{selectedTrade.exit_time ? new Date(selectedTrade.exit_time).toLocaleString() : 'N/A'}</Typography>
                                    </Box>
                                    <Box>
                                        <Typography variant="subtitle2" color="gray">EXIT PRICE</Typography>
                                        <Typography variant="body1">${selectedTrade.exit_price?.toFixed(2)}</Typography>
                                    </Box>
                                    <Box>
                                        <Typography variant="subtitle2" color="gray">DURATION</Typography>
                                        <Typography variant="body1">
                                            {(() => {
                                                if (!selectedTrade.duration) return 'N/A';

                                                // Handle "X days, HH:MM:SS" format from Python timedelta
                                                if (selectedTrade.duration.includes('day')) {
                                                    return selectedTrade.duration.split('.')[0]; // Remove microseconds if any
                                                }

                                                // Parse duration string "HH:MM:SS"
                                                const parts = selectedTrade.duration.split(':');
                                                if (parts.length >= 2) {
                                                    const h = parseInt(parts[0]);
                                                    const m = parseInt(parts[1]);
                                                    return `${h}h ${m}m`;
                                                }
                                                return selectedTrade.duration;
                                            })()}
                                        </Typography>
                                    </Box>
                                </Stack>
                            </Grid>

                            <Grid item xs={12}>
                                <Divider sx={{ borderColor: '#333', my: 1 }} />
                            </Grid>

                            <Grid item xs={6} md={3}>
                                <Typography variant="caption" color="gray">INITIAL STOP LOSS</Typography>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                    <Typography variant="body2">
                                        ${selectedTrade.stop_loss?.toFixed(2)}
                                    </Typography>
                                    <MuiTooltip
                                        title={<span style={{ whiteSpace: 'pre-wrap' }}>{selectedTrade.sl_calculation || "Calculation details not available"}</span>}
                                        arrow
                                        placement="top"
                                    >
                                        <InfoOutlined fontSize="small" sx={{ cursor: 'help', width: 16, height: 16, color: '#2196f3' }} />
                                    </MuiTooltip>
                                </Box>
                            </Grid>
                            <Grid item xs={6} md={3}>
                                <Typography variant="caption" color="gray">INITIAL TAKE PROFIT</Typography>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                    <Typography variant="body2">
                                        ${selectedTrade.take_profit?.toFixed(2)}
                                    </Typography>
                                    <MuiTooltip
                                        title={<span style={{ whiteSpace: 'pre-wrap' }}>{selectedTrade.tp_calculation || "Calculation details not available"}</span>}
                                        arrow
                                        placement="top"
                                    >
                                        <InfoOutlined fontSize="small" sx={{ cursor: 'help', width: 16, height: 16, color: '#2196f3' }} />
                                    </MuiTooltip>
                                </Box>
                            </Grid>
                            <Grid item xs={6} md={3}>
                                <Typography variant="caption" color="gray">COMMISSION</Typography>
                                <Typography variant="body2">${selectedTrade.commission?.toFixed(2) || '0.00'}</Typography>
                            </Grid>
                            <Grid item xs={12} md={3}>
                                <Typography variant="caption" color="gray">EXIT REASON</Typography>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                    <Typography variant="body2" sx={{
                                        color: selectedTrade.exit_reason === 'Take Profit' ? '#4caf50' :
                                            selectedTrade.exit_reason === 'Stop Loss' ? '#f44336' : 'white'
                                    }}>
                                        {selectedTrade.exit_reason || 'Unknown'}
                                    </Typography>
                                    {selectedTrade.sl_history && selectedTrade.sl_history.length > 0 && (
                                        <MuiTooltip
                                            title={
                                                <Box sx={{ p: 0.5, maxHeight: '300px', overflowY: 'auto' }}>
                                                    <Typography variant="subtitle2" sx={{ borderBottom: '1px solid rgba(255,255,255,0.2)', mb: 1, pb: 0.5 }}>
                                                        Trailing Stop History
                                                    </Typography>
                                                    {selectedTrade.sl_history.map((h: any, i: number) => {
                                                        const isFirst = i === 0;
                                                        const isLast = i === selectedTrade.sl_history.length - 1;

                                                        return (
                                                            <Box key={i} sx={{ mb: 1, '&:last-child': { mb: 0 } }}>
                                                                <Typography
                                                                    variant="caption"
                                                                    display="block"
                                                                    sx={{
                                                                        color: isFirst ? '#90caf9' : isLast ? '#a5d6a7' : '#b0bec5',
                                                                        fontWeight: (isFirst || isLast) ? 'bold' : 'normal'
                                                                    }}
                                                                >
                                                                    {h.reason}
                                                                </Typography>
                                                                <Typography
                                                                    variant="body2"
                                                                    sx={{
                                                                        fontFamily: 'monospace',
                                                                        color: (isFirst || isLast) ? 'white' : 'inherit',
                                                                        fontWeight: (isFirst || isLast) ? 'bold' : 'normal'
                                                                    }}
                                                                >
                                                                    ${h.price.toFixed(2)}
                                                                </Typography>
                                                            </Box>
                                                        );
                                                    })}
                                                </Box>
                                            }
                                            arrow
                                            placement="top"
                                        >
                                            <InfoOutlined fontSize="small" sx={{ cursor: 'help', width: 16, height: 16, color: '#2196f3' }} />
                                        </MuiTooltip>
                                    )}
                                </Box>
                            </Grid>

                            {/* Trade Narrative Section */}
                            {selectedTrade.narrative && (
                                <Grid item xs={12} sx={{ mt: 2 }}>
                                    <Box sx={{ p: 2, bgcolor: 'rgba(255,255,255,0.05)', borderRadius: 1, borderLeft: '3px solid #64b5f6' }}>
                                        <Typography variant="subtitle2" color="#64b5f6" gutterBottom>
                                            TRADE ANALYSIS
                                        </Typography>
                                        <Typography variant="body2" color="#e0e0e0" sx={{ fontStyle: 'italic' }}>
                                            "{selectedTrade.narrative}"
                                        </Typography>
                                    </Box>
                                </Grid>
                            )}
                        </Grid>
                    </DialogContent>
                    <DialogActions sx={{ borderTop: '1px solid #333', p: 2 }}>
                        <Button onClick={onClose} color="inherit">Close</Button>
                    </DialogActions>
                </>
            )}
        </Dialog>
    );
};

export default TradeDetailsModal;
