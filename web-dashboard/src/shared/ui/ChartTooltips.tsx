export const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
        return (
            <div style={{
                backgroundColor: '#fff',
                border: '1px solid #ccc',
                borderRadius: '4px',
                padding: '8px',
                boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
            }}>
                <p style={{ margin: 0, fontWeight: 'bold' }}>{label}</p>
                {payload.map((entry: any, index: number) => (
                    <p key={index} style={{ margin: 0, color: entry.color }}>
                        {`${entry.dataKey}: ${entry.value?.toFixed(1)}`}
                    </p>
                ))}
            </div>
        );
    }
    return null;
};

export const CustomPieTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
        return (
            <div style={{
                backgroundColor: '#fff',
                border: '1px solid #ccc',
                borderRadius: '4px',
                padding: '8px',
                boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
            }}>
                <p style={{ margin: 0, fontWeight: 'bold' }}>{payload[0].name}</p>
                <p style={{ margin: 0, color: payload[0].color }}>
                    {`Value: ${payload[0].value?.toFixed(1)}`}
                </p>
            </div>
        );
    }
    return null;
};
