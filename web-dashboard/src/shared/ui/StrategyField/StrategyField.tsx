import { memo } from 'react';
import { Grid, Box, TextField, FormControlLabel, Switch, Tooltip as MuiTooltip, Typography } from '@mui/material';

interface StrategyFieldProps {
    fieldKey: string;
    schema: any;
    value: any;
    label: string;
    tooltip: string;
    isDisabled: boolean;
    onChange: (key: string, value: any) => void;
    description?: string;
    compact?: boolean;
}

const StrategyField = memo(({ fieldKey, schema, value, label, tooltip, isDisabled, onChange, description, compact }: StrategyFieldProps) => {
    const isBoolean = schema?.type === "boolean" || typeof value === "boolean" || value === "true" || value === "false";
    const gridMd = isBoolean ? (compact ? 6 : 12) : 6;

    return (
        <Grid item xs={12} md={gridMd}>
            <MuiTooltip title={tooltip} arrow placement="top">
                <Box>
                    {isBoolean ? (
                        <Box>
                            <FormControlLabel
                                control={
                                    <Switch
                                        checked={value !== undefined ? Boolean(value === true || value === "true") : Boolean(schema?.default)}
                                        onChange={e => onChange(fieldKey, e.target.checked)}
                                        disabled={isDisabled}
                                    />
                                }
                                label={label}
                            />
                            {description && (
                                <Typography variant="caption" display="block" sx={{ color: 'text.secondary', mt: 0.5, pl: 7 }}>
                                    {description}
                                </Typography>
                            )}
                        </Box>
                    ) : (
                        <TextField
                            label={label}
                            type={schema?.type === "number" ? "number" : "text"}
                            value={value !== undefined ? value : (schema?.default || "")}
                            onChange={e => {
                                const newValue = schema?.type === "number" ? parseFloat(e.target.value) : e.target.value;
                                onChange(fieldKey, newValue);
                            }}
                            disabled={isDisabled}
                            fullWidth
                        />
                    )}
                </Box>
            </MuiTooltip>
        </Grid>
    );
});

export default StrategyField;
