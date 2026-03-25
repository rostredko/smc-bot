import { memo } from 'react';
import { Grid, Box, TextField, FormControlLabel, Switch, Tooltip as MuiTooltip, Typography, MenuItem } from '@mui/material';

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
    error?: string;
    dependencyText?: string;
    isDependent?: boolean;
}

const StrategyField = memo(({ fieldKey, schema, value, label, tooltip, isDisabled, onChange, description, compact, error, dependencyText, isDependent }: StrategyFieldProps) => {
    const isBoolean = schema?.type === "boolean" || typeof value === "boolean" || value === "true" || value === "false";
    const hasOptions = Array.isArray(schema?.options) && schema.options.length > 0;
    const gridMd = isBoolean ? (compact ? 6 : 12) : 6;

    return (
        <Grid item xs={12} md={gridMd}>
            <MuiTooltip title={tooltip} arrow placement="top">
                <Box
                    sx={{
                        opacity: isDependent ? 0.6 : 1,
                        transition: 'opacity 150ms ease',
                    }}
                >
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
                            {dependencyText && (
                                <Typography variant="caption" display="block" sx={{ color: 'text.disabled', mt: 0.25, pl: 7 }}>
                                    {dependencyText}
                                </Typography>
                            )}
                        </Box>
                    ) : (
                        <TextField
                            select={hasOptions}
                            label={label}
                            type={schema?.type === "number" ? "number" : "text"}
                            value={value !== undefined ? value : (schema?.default || "")}
                            onChange={e => {
                                const newValue = schema?.type === "number" ? parseFloat(e.target.value) : e.target.value;
                                onChange(fieldKey, newValue);
                            }}
                            disabled={isDisabled}
                            error={!!error}
                            helperText={error || dependencyText}
                            fullWidth
                        >
                            {hasOptions ? schema.options.map((option: string) => (
                                <MenuItem key={option} value={option}>
                                    {option}
                                </MenuItem>
                            )) : null}
                        </TextField>
                    )}
                </Box>
            </MuiTooltip>
        </Grid>
    );
});

export default StrategyField;
