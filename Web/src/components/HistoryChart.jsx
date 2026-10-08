import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from "recharts";

export default function HistoryChart({ title, data, lines }) {
  return (
    <section className="chart-panel">
      <h2>{title}</h2>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={data}>
          <CartesianGrid stroke="rgba(0,229,255,0.12)" strokeDasharray="3 3" />
          <XAxis dataKey="time" stroke="#6f8aa6" tick={{ fontSize: 11 }} />
          <YAxis stroke="#6f8aa6" tick={{ fontSize: 11 }} />
          <Tooltip
            contentStyle={{
              background: "#0a1626",
              border: "1px solid #00e5ff",
              fontFamily: "Share Tech Mono, monospace",
            }}
          />
          <Legend />
          {lines.map((l) => (
            <Line
              key={l.key}
              type="monotone"
              dataKey={l.key}
              name={l.label}
              stroke={l.color}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </section>
  );
}