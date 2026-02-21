import { memo } from 'react';
import { Grid, Box, TextField, FormControlLabel, Switch, Tooltip as MuiTooltip } from '@mui/material';

interface StrategyFieldProps {
    fieldKey: string;
    schema: any;
    value: any;
    label: string;
    tooltip: string;
    isDisabled: boolean;
    onChange: (key: string, value: any) => void;
}

const StrategyField = memo(({ fieldKey, schema, value, label, tooltip, isDisabled, onChange }: StrategyFieldProps) => {
    const isBoolean = schema?.type === "boolean" || typeof value === "boolean" || value === "true" || value === "false";

    // Debouncing logic could be added here if memoization isn't enough, 
    // but memoizaion usually solves the "render whole app on single char type" issue.

    return (
        <Grid item xs={12} md={isBoolean ? 12 : 6}>
            <MuiTooltip title={tooltip} arrow placement="top">
                <Box>
                    {isBoolean ? (
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
